#
# Copyright (C) 2019 ifm electronic, gmbh
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import os
import re
import sys
import platform
import subprocess
import sysconfig

from setuptools import setup, Extension, find_packages
from setuptools.command.build_ext import build_ext

SOURCE_DIR = os.path.abspath(os.path.dirname(__file__))

#
# This setup script was borrowed and modified from the pybind11 sample
# project found here: https://github.com/pybind/cmake_example
#


def _git_output(*args):
    """
    Run a git command in the source directory, or return None if it fails
    """
    try:
        return subprocess.check_output(
            ["git"] + list(args),
            cwd=SOURCE_DIR,
            stderr=subprocess.DEVNULL).decode("utf-8").strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def get_version_from_git():
    """
    Helper to get the ifm3d package version from the most recent git tag.
    Returns None when git is unavailable or no tag can be found (e.g. in a
    shallow or tag-less clone, as created by `pip`/`uv install git+...`).
    """
    version = _git_output("describe", "--abbrev=0", "--tags")
    if not version:
        return None

    version_ahead = _git_output("rev-list", version + "..HEAD", "--count")

    if version_ahead and int(version_ahead) > 0:
        # PyPI does not allow uploading versions with metadata so we can't include the commit hash...
        version = "{}-{}".format(version, version_ahead)

    return version.lstrip("v")


def get_version_from_file():
    """
    Helper to get the ifm3d package version from the VERSION file, which is
    the same fallback the CMake build uses when git is not available. The file
    holds '*'-separated fields:
    FULL*STRING*MAJOR*MINOR*PATCH*TWEAK*AHEAD*SHA
    """
    try:
        with open(os.path.join(SOURCE_DIR, "VERSION"), encoding="utf-8") as f:
            fields = f.read().strip().split("*")
    except OSError:
        return None

    # Field 1 is the tag the release was cut from, e.g. 'v2.0.7'
    if len(fields) < 2 or not fields[1]:
        return None

    return fields[1].lstrip("v")


def get_version():
    """
    Helper to get the ifm3d package version
    """
    return get_version_from_git() or get_version_from_file() or "0.0.0"


class CMakeExtension(Extension):
    def __init__(self, name, sourcedir=''):
        Extension.__init__(self, name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)


class CMakeBuild(build_ext):
    def run(self):
        try:
            out = subprocess.check_output(['cmake', '--version'])
        except OSError:
            raise RuntimeError("CMake must be installed to build the following extensions: " +
                               ", ".join(e.name for e in self.extensions))

        if platform.system() == "Windows":
            cmake_version = tuple(int(part) for part in re.search(
                r'version\s*([\d.]+)', out.decode()).group(1).split('.'))
            if cmake_version < (3, 1, 0):
                raise RuntimeError("CMake >= 3.1.0 is required on Windows")

        for ext in self.extensions:
            self.build_extension(ext)

    def build_extension(self, ext):
        extdir = os.path.abspath(os.path.dirname(
            self.get_ext_fullpath(ext.name)))

        python_home = sys.prefix 

        python_include = sysconfig.get_path('include')

        # Build with cmake -- build only camera and framegrabber. Also build
        # them as static libs so the resulting python module is isolated.
        cmake_args = ['-DBUILD_MODULE_IMAGE=OFF',
                      '-DBUILD_MODULE_SWUPDATER=ON',
                      '-DBUILD_MODULE_TOOLS=ON',
                      '-DBUILD_MODULE_PYBIND11=ON',
                      '-DBUILD_TESTS=OFF',
                      '-DBUILD_SHARED_LIBS=OFF',
                      '-DCMAKE_USE_OPENSSL=OFF',
                      '-DCMAKE_LIBRARY_OUTPUT_DIRECTORY=' + extdir,
                      '-DPYTHON_ARCHIVE_OUTPUT_DIRECTORY=' + extdir,
                      '-DCREATE_PYTHON_STUBS=OFF',
                      f'-DPython_EXECUTABLE={sys.executable}',
                      f'-DPython_ROOT_DIR={python_home}',
                      f'-DPython_INCLUDE_DIR={python_include}',
                      '-DPython_FIND_STRATEGY=LOCATION',
                      '-DPYBIND11_FINDPYTHON=ON']

        cfg = 'Debug' if self.debug else 'Release'
        build_args = ['--config', cfg]

        if platform.system() == "Windows":
            cmake_args += [
                '-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{}={}'.format(cfg.upper(), extdir)]

            if 'IFM3D_BUILD_DIR' in os.environ:
                cmake_args += ['-DCMAKE_PREFIX_PATH=' +
                               os.environ['IFM3D_BUILD_DIR'].replace('"', '') + '\\install']

            # If a generator was specified, use it. Otherwise use the machine's
            # architecture and the default generator.
            if 'IFM3D_CMAKE_GENERATOR' in os.environ:
                cmake_args += ['-G',
                               os.environ['IFM3D_CMAKE_GENERATOR'].replace('"', '')]
            elif sys.maxsize > 2**32:
                cmake_args += ['-A', 'x64']

            build_args += ['--', '/m']
        else:
            cmake_args += ['-DCMAKE_BUILD_TYPE=' + cfg]
            cmake_args += ['-DCMAKE_POSITION_INDEPENDENT_CODE=ON']
            build_args += ['--']

        env = os.environ.copy()
        env['CXXFLAGS'] = '{} -DVERSION_INFO=\\"{}\\"'.format(env.get('CXXFLAGS', ''),
                                                              self.distribution.get_version())
        if not os.path.exists(self.build_temp):
            os.makedirs(self.build_temp)
        subprocess.check_call(['cmake', ext.sourcedir] +
                              cmake_args, cwd=self.build_temp, env=env)
        subprocess.check_call(['cmake', '--build', '.', f'-j{os.cpu_count()}'] +
                              build_args, cwd=self.build_temp)

# Read the contents of README file
def read_description(fname):
    return open(os.path.join(os.path.dirname(__file__), fname), encoding='utf-8').read()

setup(
    name='ifm3dpy',
    version=get_version(),
    author='ifm Robotics Perception',
    author_email='support.robotics@ifm.com',
    description='Library for working with ifm pmd-based 3D ToF Cameras',
    url='https://github.com/ifm/ifm3d',
    license='Apache 2.0',
    long_description=read_description("README.md"),
    long_description_content_type='text/markdown',
    ext_modules=[CMakeExtension('IFM3D_PYBIND11')],
    cmdclass=dict(build_ext=CMakeBuild),
    zip_safe=False,
    packages=find_packages(),
    python_requires='>=3.10',
    install_requires=['numpy'],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: C++',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
        'Topic :: Scientific/Engineering',
    ],
    project_urls={
        'Documentation': 'https://ifm3d.com/',
        'Issue Tracker': 'https://github.com/ifm/ifm3d/issues',
        'Source Code': 'https://github.com/ifm/ifm3d'
    }
)

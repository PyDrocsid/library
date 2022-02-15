from distutils.core import setup
from os import environ
from subprocess import getoutput  # noqa: S404

from setuptools import find_packages

version = environ["VERSION"] if "VERSION" in environ else getoutput("git describe --tags --always").replace("-", "+", 1)

setup(
    name="PyDrocsid",
    version=version,
    url="https://github.com/PyDrocsid/library",
    author="Defelo",
    author_email="elodef42@gmail.com",
    description="Python Discord Bot Framework based on pycord",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    include_package_data=True,
    install_requires=open("requirements.txt").read().splitlines(),
)

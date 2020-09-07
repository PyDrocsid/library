from distutils.core import setup
from os import environ

from setuptools import find_packages

setup(
    name="PyDrocsid",
    version=environ["VERSION"],
    url="https://github.com/Defelo/PyDrocsid",
    author="Defelo",
    author_email="elodef42@gmail.com",
    description="Python Discord Bot Framework based on Discord.py",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    include_package_data=True,
    install_requires=open("requirements.txt").read().splitlines(),
)

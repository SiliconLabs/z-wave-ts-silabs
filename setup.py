#!/usr/bin/python3
# coding: utf-8

import os

from setuptools import setup, find_packages

NAME = "z_wave_ts_silabs"
VERSION = "0.1.3"

# To install the library, run the following
#
# python setup.py install
#
# prerequisite: setuptools
# http://pypi.python.org/pypi/setuptools

# see https://setuptools.pypa.io/en/latest/userguide/quickstart.html

REQUIRES = [ ]

# Utility function to read the README.md file for the long_description.
def read(filename):
    return open(os.path.join(os.path.dirname(__file__), filename)).read()

setup(
    name=NAME,
    version=VERSION,
    description="Python interface for Silicon Labs Z-Wave devices",
    author="Luis Thomas",
    author_email="luis.thomas@silabs.com",
    license="Copyright 2024 Silicon Laboratories Inc. www.silabs.com",
    url="https://stash.silabs.com/projects/SADDLE/repos/z_wave_ts_silabs",
    keywords=["Z-Wave"],
    install_requires=REQUIRES,
    packages=find_packages(),
    long_description=read("README.md"),
    include_package_data=True
)

#!/usr/bin/python3
# coding: utf-8

import os

from setuptools import setup, find_packages

NAME = "z_wave_ts_silabs"
VERSION = "0.4.1"

# To install the library, run the following
#
# python setup.py install
#
# prerequisite: setuptools
# http://pypi.python.org/pypi/setuptools

# see https://setuptools.pypa.io/en/latest/userguide/quickstart.html

# Utility function to read the README.md file for the long_description.
def read(filename):
    return open(os.path.join(os.path.dirname(__file__), filename)).read()

setup(
    name=NAME,
    version=VERSION,
    python_requires='>=3.12',
    description="Python interface for Silicon Labs Z-Wave devices",
    author="Luis Thomas",
    author_email="luis.thomas@silabs.com",
    license="Copyright 2024 Silicon Laboratories Inc. www.silabs.com",
    url="https://github.com/SiliconLabs/z-wave-ts-silabs",
    keywords=["Z-Wave"],
    install_requires=[
        "paho-mqtt",
        "pytest"
    ],
    entry_points={
        'pytest11': ['z_wave_ts_silabs = z_wave_ts_silabs.fixtures']
    },
    packages=find_packages(),
    long_description=read("README.md"),
    include_package_data=True
)

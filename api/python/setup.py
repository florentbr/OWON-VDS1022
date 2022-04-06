#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Setup script for the `vds1022` package.
Learn more at https://github.com/florentbr/OWON-VDS1022/
"""

import glob
import shutil

from os import path
from distutils.core import setup

root = path.dirname(__file__)


src = path.join(root, r'../../fwr/*.bin')
dst = path.join(root, r'vds1022/fwr/')
for file in glob.glob(src):
    shutil.copy(file, dst)


setup(
    name='vds1022',
    version='1.1.3',
    description='API for the OWON VDS1022 oscilloscope',
    author='florent',
    author_email='florentbr@gmail.com',
    url='https://github.com/florentbr/OWON-VDS1022/',
    packages=['vds1022'],
    package_data={
        'vds1022': ['fwr/*.bin'],
    },
    include_package_data=True,
    python_requires='>=3.4',
    install_requires=[
        'pyusb',
        'numpy',
        'pandas',
        'bokeh',
    ],
    keywords=['vds1022', 'vds1022i', 'MP720016', 'MP720017'],
)

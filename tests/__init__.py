# -*- coding: utf-8 -*-
"""
LinuxTask - tests/__init__.py
Description: Package bootstrap for the test suite. Puts src/ on sys.path
             once, so no individual test file has to patch it (they used to
             repeat the same two lines, and a new test that forgot them
             failed at import instead of at assert).
Author: JADRT22 (https://github.com/JADRT22)
License: MIT
"""

import os
import sys

SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')
)

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

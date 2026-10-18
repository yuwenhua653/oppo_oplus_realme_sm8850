#!/usr/bin/env python3
"""Offline candidate tests. Fake sysfs only; no adb/fastboot, root or network access."""
from pathlib import Path
import sys
import unittest
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root))
sys.path.insert(0,str(root/'tests'))
if __name__=='__main__':
    suite=unittest.defaultTestLoader.discover(str(root/'tests'),pattern='test_*.py')
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())

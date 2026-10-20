#!/usr/bin/env python3
"""Run the actual-function WLAN candidate regression harness."""
from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "tests/test_nss_candidate.py"),
                   run_name="__main__")

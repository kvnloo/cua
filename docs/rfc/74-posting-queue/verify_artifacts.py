#!/usr/bin/env python3
"""Verify the kvnloo/cua#74 posting queue (thin wrapper; the checks live in ../10-final-accounting).

  python3 docs/rfc/74-posting-queue/verify_artifacts.py [--offline] [--extra-md FILE ...]
"""
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "10-final-accounting", "verify_artifacts.py")

if __name__ == "__main__":
    if "--target" not in sys.argv:
        sys.argv[1:1] = ["--target", "74"]
    sys.argv[0] = TARGET
    runpy.run_path(TARGET, run_name="__main__")

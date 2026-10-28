#!/usr/bin/env python3
"""Run the project's current Python scripts as a simple smoke test."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_DIR = ROOT / "src"


def discover_current_tests() -> list[Path]:
    """Return the active script files already in the project."""
    return sorted(TEST_DIR.glob("test_*.py"))


def main() -> int:
    tests = discover_current_tests()

    if not tests:
        print("No current test files found in src/.")
        return 1

    print("Running current project test scripts:")
    overall_status = 0

    for test_file in tests:
        command = [sys.executable, str(test_file)]
        print(f"\n> {' '.join(command)}")
        result = subprocess.run(command, cwd=str(ROOT))
        if result.returncode != 0:
            print(f"FAIL: {test_file.name} exited with code {result.returncode}")
            overall_status = result.returncode

    if overall_status == 0:
        print("\nAll current project test scripts passed.")
    else:
        print(f"\nOne or more current project test scripts failed (exit code {overall_status}).")

    return overall_status


if __name__ == "__main__":
    raise SystemExit(main())

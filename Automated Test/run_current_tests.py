#!/usr/bin/env python3
"""Run the project's current Python scripts as a simple smoke test."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# The repository's smoke-test runner should work from either the repo root or the
# Automation folder, so define both candidate test locations explicitly.
ROOT = Path(__file__).resolve().parent.parent
TEST_DIRS = [ROOT / "src", ROOT / "Automated Test"]


def discover_current_tests() -> list[Path]:
    """Return the active script files already in the project.

    This keeps the smoke-test workflow resilient as tests are added to either the
    src folder or the Automated Test folder, while avoiding duplicate entries if
    the same file is discovered through multiple directories.
    """
    tests: list[Path] = []
    seen: set[Path] = set()

    for test_dir in TEST_DIRS:
        if not test_dir.exists():
            continue
        for test_file in sorted(test_dir.glob("test_*.py")):
            resolved = test_file.resolve()
            if resolved not in seen:
                tests.append(test_file)
                seen.add(resolved)

    return tests


def main() -> int:
    # Discover the current test scripts and then run each one as its own process.
    tests = discover_current_tests()

    if not tests:
        # The workflow should fail clearly if no test files are present anywhere
        # in the repository's expected test locations.
        print("No current test files found in src/.")
        return 1

    print("Running current project test scripts:")
    overall_status = 0

    for test_file in tests:
        # Run each test file in its own Python process so failures do not leak
        # across scripts and the overall status reflects each runner outcome.
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

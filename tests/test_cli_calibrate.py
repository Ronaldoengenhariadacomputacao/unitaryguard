"""Smoke test for `unitaryguard calibrate-workers`: must run end to end and
exit 0, without asserting any specific speedup number (that's inherently
machine-dependent -- the whole point of this command)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unitaryguard.cli import main


def test_calibrate_workers_runs_end_to_end() -> None:
    exit_code = main([
        "calibrate-workers",
        "tests.fixtures.toy_normal_form:fixed_transform",
        "--qubits", "1",
        "--gates", "h,s,t",
        "--probe-length", "3",
    ])
    assert exit_code == 0


if __name__ == "__main__":
    test_calibrate_workers_runs_end_to_end()
    print("calibrate-workers smoke test passed")

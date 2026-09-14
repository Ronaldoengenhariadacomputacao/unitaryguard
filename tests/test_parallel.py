"""Correctness test for the process-pool exhaustive checker: must find the
exact same result as the sequential one (same failures, same minimal
length), using a target-spec string (not a live callable) since that's what
makes it work across the process boundary.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unitaryguard import check_transform_exhaustive_parallel
from tests.fixtures.toy_normal_form import circuit_to_gate_string


def test_parallel_matches_sequential_on_known_bug() -> None:
    report = check_transform_exhaustive_parallel(
        "tests.fixtures.toy_normal_form:buggy_transform",
        n_qubits=1,
        gate_set=["h", "s", "t"],
        max_length=6,
        tol=1e-7,
        n_workers=4,
    )
    assert not report.ok
    assert report.smallest_failing_length == 4
    found_strings = {circuit_to_gate_string(f.original) for f in report.failures}
    assert "SHTT" in found_strings


def test_parallel_matches_sequential_on_fixed_version() -> None:
    report = check_transform_exhaustive_parallel(
        "tests.fixtures.toy_normal_form:fixed_transform",
        n_qubits=1,
        gate_set=["h", "s", "t"],
        max_length=6,
        tol=1e-7,
        n_workers=4,
        stop_at_first_length_with_failure=False,
    )
    assert report.ok, report.summary()
    assert report.n_checked == sum(3 ** L for L in range(0, 7))


if __name__ == "__main__":
    test_parallel_matches_sequential_on_known_bug()
    test_parallel_matches_sequential_on_fixed_version()
    print("all parallel tests passed")

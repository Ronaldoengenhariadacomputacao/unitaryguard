"""Regression tests for the exhaustive (deterministic) checker: it must
find the SHT-merge bug's real minimal counterexample ("SHTT", length 4)
DETERMINISTICALLY -- by construction, not by chance -- and must not flag
the fixed version at all, checking every circuit up to the same length.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unitaryguard import check_transform_exhaustive
from unitaryguard.exhaustive import enumerate_circuits
from tests.fixtures.toy_normal_form import circuit_to_gate_string, make_transform


def test_enumerate_circuits_covers_expected_count() -> None:
    # 3 gates, arity 1, n_qubits=1 -> exactly 3 choices per slot -> 3^length
    circuits = list(enumerate_circuits(n_qubits=1, gate_set=["h", "s", "t"], length=3))
    assert len(circuits) == 27


def test_exhaustive_finds_sht_bug_deterministically_at_length_4() -> None:
    buggy = make_transform(buggy=True)
    report = check_transform_exhaustive(
        buggy, n_qubits=1, gate_set=["h", "s", "t"], max_length=6, tol=1e-7
    )
    assert not report.ok
    assert report.smallest_failing_length == 4, (
        f"expected the real minimal counterexample at length 4 (SHTT), "
        f"got length {report.smallest_failing_length}"
    )
    # every failure at the minimal length must already be a minimal
    # circuit -- no shrinking needed, unlike the random-sampling path
    found_strings = {circuit_to_gate_string(f.original) for f in report.failures}
    assert "SHTT" in found_strings, (
        f"expected 'SHTT' among the length-4 counterexamples, got {found_strings}"
    )


def test_exhaustive_no_failures_up_to_length_6_when_fixed() -> None:
    fixed = make_transform(buggy=False)
    report = check_transform_exhaustive(
        fixed, n_qubits=1, gate_set=["h", "s", "t"], max_length=6, tol=1e-7,
        stop_at_first_length_with_failure=False,
    )
    assert report.ok, report.summary()
    assert report.n_checked == sum(3 ** L for L in range(0, 7))


if __name__ == "__main__":
    test_enumerate_circuits_covers_expected_count()
    test_exhaustive_finds_sht_bug_deterministically_at_length_4()
    test_exhaustive_no_failures_up_to_length_6_when_fixed()
    print("all exhaustive tests passed")

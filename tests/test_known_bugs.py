"""Regression tests: UnitaryGuard must catch both real bug shapes found this
session, and must NOT false-positive on a correct transform.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unitaryguard import Circuit, Gate, CheckConfig, check_transform
from tests.fixtures.toy_normal_form import make_transform


def identity_transform(circ: Circuit) -> Circuit:
    return circ.copy()


def s_sdg_swap_bug(circ: Circuit) -> Circuit:
    """Stand-in for the real Qiskit OptimizeCliffordT bug shape: a transform
    that silently swaps S and Sdg wherever they occur. S and Sdg are not
    interchangeable (S != Sdg in general), so this breaks unitary
    equivalence on any circuit containing at least one S/Sdg -- the same
    'two-token transcription swap' shape as the real bug, without depending
    on Qiskit's actual (already-fixed) Rust source.
    """
    out = Circuit(circ.n_qubits)
    for g in circ.gates:
        if g.kind == "s":
            out.gates.append(Gate("sdg", g.qubits, g.params))
        elif g.kind == "sdg":
            out.gates.append(Gate("s", g.qubits, g.params))
        else:
            out.gates.append(g)
    return out


def test_identity_transform_never_fails() -> None:
    cfg = CheckConfig(n_qubits=2, gate_set=["h", "s", "sdg", "t", "tdg", "cx"], n_samples=150, seed=1)
    report = check_transform(identity_transform, cfg)
    assert report.ok, report.summary()


def test_catches_s_sdg_swap_bug_shape() -> None:
    cfg = CheckConfig(n_qubits=1, gate_set=["s", "sdg", "h"], n_samples=100, min_gates=1, max_gates=4, seed=2)
    report = check_transform(s_sdg_swap_bug, cfg)
    assert not report.ok, "expected the S/Sdg swap bug to be caught"
    # every failure should shrink to a tiny reproduction (a lone S or Sdg is
    # already enough: S != Sdg)
    smallest = min(len(f.minimized.gates) for f in report.failures)
    assert smallest <= 2, f"shrinking did not reach a small reproduction (got {smallest} gates)"


def test_catches_real_sht_merge_bug_shape() -> None:
    """The central regression: a faithful port of rsgridsynth's NormalForm,
    with the real H*S*H bug enabled, must be caught -- and shrunk close to
    the actual minimal case we found by hand during the investigation
    ("SHTT", 4 gates).
    """
    buggy = make_transform(buggy=True)
    cfg = CheckConfig(n_qubits=1, gate_set=["h", "s", "t"], n_samples=300, min_gates=2, max_gates=8, seed=3)
    report = check_transform(buggy, cfg)
    assert not report.ok, "expected the SHT-merge bug to be caught"
    smallest = min(len(f.minimized.gates) for f in report.failures)
    assert smallest <= 4, f"shrinking did not reach the known-minimal case size (got {smallest} gates)"


def test_fixed_sht_merge_has_no_known_failures() -> None:
    fixed = make_transform(buggy=False)
    cfg = CheckConfig(n_qubits=1, gate_set=["h", "s", "t"], n_samples=300, min_gates=2, max_gates=8, seed=3)
    report = check_transform(fixed, cfg)
    assert report.ok, report.summary()


if __name__ == "__main__":
    test_identity_transform_never_fails()
    test_catches_s_sdg_swap_bug_shape()
    test_catches_real_sht_merge_bug_shape()
    test_fixed_sht_merge_has_no_known_failures()
    print("all tests passed")

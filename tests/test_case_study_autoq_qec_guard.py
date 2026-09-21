"""Case study (see CASE_STUDIES.md, Method 1): demonstrates UnitaryGuard's
own random-sampling methodology finding Qiskit's real, confirmed
OptimizeCliffordT unitarity bug (merged fix: Qiskit/qiskit#16729, included
starting Qiskit 2.5.2 -- affects 2.4.0 through 2.5.1) by pointing
check_transform at a real, external, production function:
`autoq_qec.qec_estimator._transpile_clifford_t`, which is used for real
QEC resource estimation in a separate project (AutoQ EngineBR).

Tests BOTH configurations that function already supports:
- validate=False: the raw, unguarded Qiskit path (exposes the bug).
- validate=True: the actual guarded path autoq_qec uses in production.

SKIPPED (not a failure) if the `autoq_qec` package (a separate, external
project) isn't importable -- adjust _AUTOQ_QEC_ROOT below to point at a
local checkout if you want to run this.

Run manually: python tests/test_case_study_autoq_qec_guard.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unitaryguard import Circuit, Gate, CheckConfig, check_transform

# Ajuste este caminho pro seu checkout local do AutoQ EngineBR, se for
# rodar este script -- autoq_qec e' um pacote de um projeto SEPARADO,
# nao uma dependencia do unitaryguard.
_AUTOQ_QEC_ROOT = r"C:\Users\CentralS\Documents\projeto transpileZig\Motor Zig v1.7.83 - 2026-09-21"

try:
    sys.path.insert(0, _AUTOQ_QEC_ROOT)
    from qiskit import QuantumCircuit
    from autoq_qec.qec_estimator import _transpile_clifford_t
    _HAS_AUTOQ_QEC = True
except ImportError:
    _HAS_AUTOQ_QEC = False

_METHOD = {"h": "h", "s": "s", "sdg": "sdg", "t": "t", "tdg": "tdg", "x": "x", "cx": "cx"}
_METHOD_PARAM = {"rz": "rz"}


def _to_qiskit(circ: Circuit) -> "QuantumCircuit":
    qc = QuantumCircuit(circ.n_qubits)
    for g in circ.gates:
        if g.kind in _METHOD:
            getattr(qc, _METHOD[g.kind])(*g.qubits)
        elif g.kind in _METHOD_PARAM:
            getattr(qc, _METHOD_PARAM[g.kind])(g.params[0], *g.qubits)
    return qc


def _from_qiskit(qc: "QuantumCircuit", n_qubits: int) -> Circuit:
    circ = Circuit(n_qubits)
    for instr in qc.data:
        name = instr.operation.name
        qubits = tuple(qc.find_bit(q).index for q in instr.qubits)
        params = tuple(float(p) for p in instr.operation.params) if instr.operation.params else ()
        circ.gates.append(Gate(name, qubits, params))
    return circ


def transform_unguarded(circ: Circuit) -> Circuit:
    qc = _to_qiskit(circ)
    out = _transpile_clifford_t(qc, validate=False)
    return _from_qiskit(out, circ.n_qubits)


def transform_guarded(circ: Circuit) -> Circuit:
    qc = _to_qiskit(circ)
    out = _transpile_clifford_t(qc, validate=True)
    return _from_qiskit(out, circ.n_qubits)


def test_unguarded_path_shows_the_bug_guarded_path_does_not() -> None:
    if not _HAS_AUTOQ_QEC:
        print(f"SKIPPED -- autoq_qec not importable from {_AUTOQ_QEC_ROOT} "
              "(adjust _AUTOQ_QEC_ROOT to your local checkout)")
        return

    cfg = CheckConfig(
        n_qubits=1,
        gate_set=["h", "s", "sdg", "t", "tdg", "x", "rz"],
        n_samples=300,
        min_gates=2,
        max_gates=10,
        seed=7,
    )

    print("--- validate=False (unguarded -- exposes the real Qiskit bug) ---")
    report_unguarded = check_transform(transform_unguarded, cfg, shrink=False)
    print(f"{report_unguarded.n_failed}/{report_unguarded.n_checked} failed")

    print("\n--- validate=True (guarded -- what autoq_qec uses in production) ---")
    report_guarded = check_transform(transform_guarded, cfg, shrink=False)
    print(f"{report_guarded.n_failed}/{report_guarded.n_checked} failed")

    assert report_guarded.n_failed == 0, "the production guard should neutralize the bug completely"
    assert report_unguarded.n_failed > 0, (
        "expected the unguarded path to expose the known Qiskit bug -- if this "
        "is 0, the installed Qiskit version may already include the fix (2.5.2+)"
    )
    print(f"\nOK -- guard eliminates {report_unguarded.n_failed} failures down to 0")


if __name__ == "__main__":
    test_unguarded_path_shows_the_bug_guarded_path_does_not()

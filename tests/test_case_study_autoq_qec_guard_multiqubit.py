"""Case study (see CASE_STUDIES.md, Method 1): extends the single-qubit
OptimizeCliffordT bug check (test_case_study_autoq_qec_guard.py) to real
multi-qubit circuits with an entangling gate (cx) in the vocabulary --
confirms the bug and the guard are not peculiarities of a 1-qubit toy
circuit.

SKIPPED (not a failure) if the `autoq_qec` package isn't importable --
adjust _AUTOQ_QEC_ROOT below to point at a local checkout if you want to
run this.

Run manually: python tests/test_case_study_autoq_qec_guard_multiqubit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unitaryguard import Circuit, Gate, CheckConfig, check_transform

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
        if name in ("id", "global_phase", "barrier"):
            continue
        qubits = tuple(qc.find_bit(q).index for q in instr.qubits)
        params = tuple(float(p) for p in instr.operation.params) if instr.operation.params else ()
        circ.gates.append(Gate(name, qubits, params))
    return circ


def transform_unguarded(circ: Circuit) -> Circuit:
    return _from_qiskit(_transpile_clifford_t(_to_qiskit(circ), validate=False), circ.n_qubits)


def transform_guarded(circ: Circuit) -> Circuit:
    return _from_qiskit(_transpile_clifford_t(_to_qiskit(circ), validate=True), circ.n_qubits)


def test_bug_and_guard_hold_on_multiqubit_entangled_circuits() -> None:
    if not _HAS_AUTOQ_QEC:
        print(f"SKIPPED -- autoq_qec not importable from {_AUTOQ_QEC_ROOT}")
        return

    for n_qubits in (2, 3):
        cfg = CheckConfig(
            n_qubits=n_qubits,
            gate_set=["h", "s", "sdg", "t", "tdg", "x", "rz", "cx"],
            n_samples=100,
            min_gates=3,
            max_gates=12,
            seed=7,
        )
        report_unguarded = check_transform(transform_unguarded, cfg, shrink=False)
        report_guarded = check_transform(transform_guarded, cfg, shrink=False)
        print(f"n_qubits={n_qubits}: unguarded {report_unguarded.n_failed}/{report_unguarded.n_checked} "
              f"failed, guarded {report_guarded.n_failed}/{report_guarded.n_checked} failed")

        assert report_guarded.n_failed == 0, (
            f"guard should neutralize the bug even with cx in the vocabulary (n_qubits={n_qubits})"
        )
        assert report_unguarded.n_failed > 0, (
            f"expected the unguarded path to expose the bug on multi-qubit circuits too "
            f"(n_qubits={n_qubits}) -- if 0, installed Qiskit may already include the fix (2.5.2+)"
        )

    print("OK -- bug and guard both confirmed on entangled multi-qubit circuits (n_qubits=2,3)")


if __name__ == "__main__":
    test_bug_and_guard_hold_on_multiqubit_entangled_circuits()

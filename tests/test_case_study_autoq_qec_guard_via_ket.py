"""Case study (see CASE_STUDIES.md, Method 1, "Reinforcement, third
independent oracle"): re-runs the SAME Qiskit OptimizeCliffordT bug check
as test_case_study_autoq_qec_guard.py (Qiskit#16729, affects 2.4.0-2.5.1),
but instead of using unitaryguard's own equivalence math (matrices.py),
computes each circuit's statevector directly through Ket's real simulator
for both the original and the `_transpile_clifford_t` output, comparing
those -- removing unitaryguard's own gate-matrix code from the comparison
path entirely for this specific check.

SKIPPED (not a failure) if `ket-lang` or the `autoq_qec` package aren't
importable -- both are external, optional dependencies of this case study,
not of unitaryguard itself. Adjust _AUTOQ_QEC_ROOT below to your local
checkout if you want to run this.

Run manually: python tests/test_case_study_autoq_qec_guard_via_ket.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from unitaryguard import CheckConfig, sample_circuit
from unitaryguard.core import Circuit, Gate

_AUTOQ_QEC_ROOT = r"C:\Users\CentralS\Documents\projeto transpileZig\Motor Zig v1.7.83 - 2026-09-21"

try:
    sys.path.insert(0, _AUTOQ_QEC_ROOT)
    import ket
    from qiskit import QuantumCircuit
    from autoq_qec.qec_estimator import _transpile_clifford_t
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False

_METHOD = {"h": "h", "s": "s", "sdg": "sdg", "t": "t", "tdg": "tdg", "x": "x", "cx": "cx"}
_METHOD_PARAM = {"rz": "rz"}
_KET_1Q = {}
if _HAS_DEPS:
    _KET_1Q = {"h": ket.H, "s": ket.S, "sdg": ket.SD, "t": ket.T, "tdg": ket.TD, "x": ket.X,
               "y": ket.Y, "z": ket.Z, "sx": ket.SX}

# calibrated for Ket's float32 precision (see CASE_STUDIES.md, Method 5) --
# 1e-6 (borrowed from the Qiskit/Ket ORACLE-validation tests, a different
# use case) produces false positives here: first attempt at this script
# used 1e-6 and got 168/300 and 177/300 "failures", INCLUDING on the
# guarded path (which should be impossible if the guard works) -- turned
# out to be exactly this noise floor, not a real divergence. A tolerance
# calibrated for one oracle/comparison does not automatically transfer to
# a different script reusing that oracle.
TOL = 1e-4


def _to_qiskit(circ: Circuit) -> "QuantumCircuit":
    qc = QuantumCircuit(circ.n_qubits)
    for g in circ.gates:
        if g.kind in _METHOD:
            getattr(qc, _METHOD[g.kind])(*g.qubits)
        elif g.kind in _METHOD_PARAM:
            getattr(qc, _METHOD_PARAM[g.kind])(g.params[0], *g.qubits)
    return qc


def _ket_statevector(qc: "QuantumCircuit") -> "np.ndarray":
    n = qc.num_qubits
    p = ket.Process(simulator="dense")
    q = p.alloc(n)
    for instr in qc.data:
        name = instr.operation.name
        qubits = [qc.find_bit(qb).index for qb in instr.qubits]
        params = [float(x) for x in instr.operation.params] if instr.operation.params else []
        if name in _KET_1Q:
            _KET_1Q[name](q[qubits[0]])
        elif name == "rz":
            ket.RZ(params[0], q[qubits[0]])
        elif name == "cx":
            ket.CNOT(q[qubits[0]], q[qubits[1]])
        elif name in ("id", "global_phase"):
            pass
        else:
            raise ValueError(
                f"gate do qiskit sem mapeamento pro Ket: {name} (a saida do "
                "_transpile_clifford_t usou algo alem do gate-set esperado "
                "-- estender _KET_1Q)"
            )
    d = ket.dump(q)
    vec = np.zeros(1 << n, dtype=complex)
    for idx, amp in d.states.items():
        vec[idx] = amp
    return vec


def _fidelity(a, b) -> float:
    return float(np.abs(np.vdot(a, b)) ** 2)


def _check_via_ket(validate: bool, cfg: CheckConfig) -> tuple[int, int]:
    n_checked = 0
    n_failed = 0
    for _ in range(cfg.n_samples):
        circ = sample_circuit(cfg)
        qc_in = _to_qiskit(circ)
        qc_out = _transpile_clifford_t(qc_in, validate=validate)
        fid = _fidelity(_ket_statevector(qc_in), _ket_statevector(qc_out))
        n_checked += 1
        if fid < 1 - TOL:
            n_failed += 1
    return n_checked, n_failed


def test_unguarded_path_shows_the_bug_via_ket_too() -> None:
    if not _HAS_DEPS:
        print(f"SKIPPED -- ket-lang or autoq_qec not importable "
              f"(autoq_qec expected at {_AUTOQ_QEC_ROOT})")
        return

    cfg = CheckConfig(
        n_qubits=1,
        gate_set=["h", "s", "sdg", "t", "tdg", "x", "rz"],
        n_samples=300,
        min_gates=2,
        max_gates=10,
        seed=7,
    )

    n_checked_u, n_failed_u = _check_via_ket(False, cfg)
    print(f"validate=False (unguarded), via Ket: {n_failed_u}/{n_checked_u} failed")

    n_checked_g, n_failed_g = _check_via_ket(True, cfg)
    print(f"validate=True (guarded), via Ket: {n_failed_g}/{n_checked_g} failed")

    assert n_failed_g == 0, "the production guard should neutralize the bug completely (Ket agrees)"
    assert n_failed_u > 0, (
        "expected the unguarded path to expose the known Qiskit bug -- if this "
        "is 0, the installed Qiskit version may already include the fix (2.5.2+)"
    )
    print(f"OK -- Ket (independent simulator, does not use unitaryguard's own "
          f"matrices.py) confirms the SAME split as the matrices.py-based check: "
          f"{n_failed_u}/{n_checked_u} unguarded, {n_failed_g}/{n_checked_g} guarded")


if __name__ == "__main__":
    test_unguarded_path_shows_the_bug_via_ket_too()

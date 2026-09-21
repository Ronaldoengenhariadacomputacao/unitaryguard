"""Optional cross-validation: compares unitaryguard's own gate-matrix table
(unitaryguard/matrices.py, hand-derived from standard definitions) against
Qiskit's real `Operator()`. This is NOT a reintroduction of the Qiskit
dependency removed in v0.2 -- Qiskit is used here purely as a THIRD
independent oracle (alongside Ket, see test_cross_validate_ket.py), the
same way any other framework could be used, never as part of the tool's
own equivalence check. The circularity concern v0.2 was built to avoid
(Qiskit validating a REAL Qiskit pass with its own Operator()) does not
apply here: nothing under test is a Qiskit pass, only unitaryguard's own
gate-matrix table is being checked, against Qiskit as one more independent
reference (same role Ket plays).

IMPORTANT qubit-ordering note (found running this test, 2026-09-21):
Qiskit uses little-endian qubit ordering (qubit 0 = LEAST significant bit
of the statevector/Operator index). unitaryguard's own convention
(matrices.py, and Ket's `dump()`, which agrees with it -- see
test_cross_validate_ket.py) is the opposite: qubit 0 = MOST significant
bit. This is NOT a bug in either side, just a labeling convention
difference (well-documented as a common Qiskit gotcha) -- but it means a
naive circuit_to_qiskit conversion that maps qubit index q -> Qiskit qubit
q directly disagrees with unitaryguard on every gate touching a non-zero
qubit index (confirmed: 9/9 isolated single-gate tests diverged before
the fix below; reversing qubit indices when building the Qiskit circuit
made every one of them match exactly, max_diff=0.0). `_circuit_to_qiskit`
below reverses qubit indices for exactly this reason -- if you copy this
adapter pattern for your own integration, don't drop that reversal.

Pinned to Qiskit 2.5.1 specifically for this run (2026-09-21) -- not a
hard requirement of the test, just what was verified.

SKIPPED (not a failure) if `qiskit` isn't installed.

Run manually: `pip install qiskit==2.5.1 && python tests/test_cross_validate_qiskit.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from unitaryguard import CheckConfig, circuit_unitary, sample_circuit
from unitaryguard.core import Circuit, Gate

try:
    import qiskit
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Operator
    _HAS_QISKIT = True
except ImportError:
    _HAS_QISKIT = False

GATE_SET = ["h", "x", "y", "z", "s", "sdg", "t", "tdg", "sx",
            "rz", "ry", "rx", "p",
            "cx", "cz", "swap", "crz", "crx", "cry", "cp", "rzz", "rxx", "ryy"]

_METHOD_1Q = {"h": "h", "x": "x", "y": "y", "z": "z", "s": "s", "sdg": "sdg",
              "t": "t", "tdg": "tdg", "sx": "sx"}
_METHOD_1Q_PARAM = {"rz": "rz", "ry": "ry", "rx": "rx", "p": "p"}
_METHOD_2Q_FIXED = {"cx": "cx", "cz": "cz", "swap": "swap"}
_METHOD_2Q_PARAM = {"crz": "crz", "crx": "crx", "cry": "cry", "cp": "cp",
                     "rzz": "rzz", "rxx": "rxx", "ryy": "ryy"}


def _circuit_to_qiskit(circ: Circuit) -> "QuantumCircuit":
    # Qiskit is little-endian (qubit 0 = LSB), unitaryguard is the opposite
    # (qubit 0 = MSB) -- see module docstring. Reverse the qubit index when
    # building the Qiskit circuit to compare the two conventions correctly.
    n = circ.n_qubits
    rev = lambda q: n - 1 - q
    qc = QuantumCircuit(n)
    for g in circ.gates:
        name, qubits, params = g.kind, g.qubits, g.params
        if name in _METHOD_1Q:
            getattr(qc, _METHOD_1Q[name])(rev(qubits[0]))
        elif name in _METHOD_1Q_PARAM:
            getattr(qc, _METHOD_1Q_PARAM[name])(params[0], rev(qubits[0]))
        elif name in _METHOD_2Q_FIXED:
            getattr(qc, _METHOD_2Q_FIXED[name])(rev(qubits[0]), rev(qubits[1]))
        elif name in _METHOD_2Q_PARAM:
            getattr(qc, _METHOD_2Q_PARAM[name])(params[0], rev(qubits[0]), rev(qubits[1]))
        else:
            raise ValueError(f"gate sem mapeamento pro Qiskit: {name}")
    return qc


def _unitaryguard_statevector(circ: Circuit) -> "np.ndarray":
    u = circuit_unitary(circ)
    zero = np.zeros(u.shape[0], dtype=complex)
    zero[0] = 1.0
    return u @ zero


def _state_fidelity(a, b) -> float:
    return float(np.abs(np.vdot(a, b)) ** 2)


def test_matrices_agree_with_qiskit_operator() -> None:
    if not _HAS_QISKIT:
        print("SKIPPED -- qiskit not installed")
        return

    print(f"Qiskit version: {qiskit.__version__}")
    n_checked = 0
    for n_qubits, n_samples, seed in ((3, 200, 7), (5, 200, 7), (6, 100, 99)):
        cfg = CheckConfig(n_qubits=n_qubits, gate_set=GATE_SET, n_samples=n_samples, seed=seed)
        for _ in range(n_samples):
            circ = sample_circuit(cfg)
            v_ug = _unitaryguard_statevector(circ)
            qc = _circuit_to_qiskit(circ)
            v_qk = Operator(qc).data[:, 0]  # first column = U|0...0>
            fid = _state_fidelity(v_ug, v_qk)
            n_checked += 1
            assert fid > 1 - 1e-6, (
                f"matrices.py disagrees with Qiskit's Operator() "
                f"(fidelity={fid:.6f}) on circuit: {circ.gates}"
            )
    print(f"OK -- {n_checked} circuits agree between matrices.py and Qiskit "
          f"{qiskit.__version__}'s Operator()")


if __name__ == "__main__":
    test_matrices_agree_with_qiskit_operator()

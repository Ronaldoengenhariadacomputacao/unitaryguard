"""Optional cross-validation: compares unitaryguard's own gate-matrix table
(unitaryguard/matrices.py, hand-derived from standard definitions) against
the REAL, independent simulator from Ket (quantumket.org, libket -- a
Rust-based runtime, unrelated to Qiskit and unrelated to this project's own
math). This is not a test of any transform under test -- it validates the
ORACLE ITSELF: if matrices.py had a subtle sign/convention error, sampling
circuits and running them through both unitaryguard's own math and Ket's
independently-implemented simulator, then comparing the resulting states,
would catch it (a self-consistency check inside unitaryguard alone could
not).

SKIPPED (not a failure) if `ket-lang` isn't installed -- this is a genuine
optional dependency, not part of unitaryguard's own numpy-only core, kept
separate on purpose (see DESIGN.md: the whole point of v0.2 is that the
core has NO external SDK dependency; this test is scaffolding that
verifies the core from outside, using one as an independent oracle, not a
dependency of the tool itself).

Run manually: `pip install ket-lang && python tests/test_cross_validate_ket.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from unitaryguard import CheckConfig, circuit_unitary, sample_circuit
from unitaryguard.core import Circuit, Gate

try:
    import ket
    _HAS_KET = True
except ImportError:
    _HAS_KET = False

_GATE_1Q = {}
_GATE_1Q_PARAM = {}
_GATE_2Q_PARAM = {}
if _HAS_KET:
    _GATE_1Q = {"h": ket.H, "x": ket.X, "y": ket.Y, "z": ket.Z, "s": ket.S,
                "sdg": ket.SD, "t": ket.T, "tdg": ket.TD, "sx": ket.SX}
    _GATE_1Q_PARAM = {"rz": ket.RZ, "ry": ket.RY, "rx": ket.RX, "p": ket.P}
    _GATE_2Q_PARAM = {"crz": ket.RZ, "crx": ket.RX, "cry": ket.RY, "cp": ket.P,
                       "rzz": ket.RZZ, "rxx": ket.RXX, "ryy": ket.RYY}

GATE_SET = ["h", "x", "y", "z", "s", "sdg", "t", "tdg", "sx",
            "rz", "ry", "rx", "p",
            "cx", "cz", "swap", "crz", "crx", "cry", "cp", "rzz", "rxx", "ryy"]


def _run_ket(n_qubits: int, circ: Circuit) -> "np.ndarray":
    p = ket.Process(simulator="dense")
    q = p.alloc(n_qubits)
    for g in circ.gates:
        name, qubits, params = g.kind, g.qubits, g.params
        if name in _GATE_1Q:
            _GATE_1Q[name](q[qubits[0]])
        elif name in _GATE_1Q_PARAM:
            _GATE_1Q_PARAM[name](params[0], q[qubits[0]])
        elif name == "cx":
            ket.CNOT(q[qubits[0]], q[qubits[1]])
        elif name == "cz":
            ket.CZ(q[qubits[0]], q[qubits[1]])
        elif name == "swap":
            ket.SWAP(q[qubits[0]], q[qubits[1]])
        elif name in ("rzz", "rxx", "ryy"):
            _GATE_2Q_PARAM[name](params[0], q[qubits[0]], q[qubits[1]])
        elif name in ("crz", "crx", "cry", "cp"):
            ket.ctrl(q[qubits[0]], _GATE_2Q_PARAM[name](params[0]))(q[qubits[1]])
        else:
            raise ValueError(f"gate sem mapeamento pro Ket: {name}")
    d = ket.dump(q)
    dim = 1 << n_qubits
    vec = np.zeros(dim, dtype=complex)
    for idx, amp in d.states.items():
        vec[idx] = amp
    return vec


def _unitaryguard_statevector(circ: Circuit) -> "np.ndarray":
    u = circuit_unitary(circ)
    zero = np.zeros(u.shape[0], dtype=complex)
    zero[0] = 1.0
    return u @ zero


def _state_fidelity(a, b) -> float:
    return float(np.abs(np.vdot(a, b)) ** 2)


def test_matrices_agree_with_ket_simulator() -> None:
    if not _HAS_KET:
        print("SKIPPED -- ket-lang not installed (pip install ket-lang)")
        return

    n_checked = 0
    for n_qubits, n_samples, seed in ((3, 200, 7), (5, 200, 7), (6, 100, 99)):
        cfg = CheckConfig(n_qubits=n_qubits, gate_set=GATE_SET, n_samples=n_samples, seed=seed)
        for _ in range(n_samples):
            circ = sample_circuit(cfg)
            v_ug = _unitaryguard_statevector(circ)
            v_ket = _run_ket(n_qubits, circ)
            fid = _state_fidelity(v_ug, v_ket)
            n_checked += 1
            assert fid > 1 - 1e-6, (
                f"matrices.py disagrees with Ket's real simulator "
                f"(fidelity={fid:.6f}) on circuit: {circ.gates}"
            )
    print(f"OK -- {n_checked} circuits agree between matrices.py and Ket "
          f"(independent Rust-based simulator)")


if __name__ == "__main__":
    test_matrices_agree_with_ket_simulator()

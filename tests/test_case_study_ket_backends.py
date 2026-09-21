"""Case study (see CASE_STUDIES.md, Method 5): cross-validates Ket AGAINST
ITSELF -- runs the same random circuit through Ket's different simulator
backends (dense, sparse, dense gpu) and compares the final state. No
external oracle needed; this only checks Ket's own internal consistency.

First run (tol=1e-6, matching the precision used for the Qiskit/Ket
cross-validation of unitaryguard's own matrices.py) found 23/900
"divergences" -- all with infidelity ~1e-6, none higher. Investigated
before concluding anything: Ket's `dump()` amplitudes match float32
rounding (e.g. 1/sqrt(2) comes back as 0.7071067690849304, matching
float32's ~7-digit precision, not float64's ~15-16), so ~1e-6-level
cross-backend infidelity is the EXPECTED noise floor for that precision,
not a correctness bug. Re-run with tol=1e-4 (calibrated for float32):
0/900 divergences. This is a genuine, previously-undocumented (as far as
this investigation found) fact about Ket's numeric precision, not a bug
-- worth recording so a future run doesn't re-investigate the same false
alarm.

SKIPPED (not a failure) if `ket-lang` isn't installed.

Run manually: pip install ket-lang && python tests/test_case_study_ket_backends.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from unitaryguard import CheckConfig, sample_circuit

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

GATE_SET = ["h", "x", "y", "z", "s", "sdg", "t", "tdg", "sx", "rz", "ry", "rx", "p",
            "cx", "cz", "swap", "crz", "crx", "cry", "cp", "rzz", "rxx", "ryy"]

# calibrado pra precisao float32 do Ket -- ver docstring do modulo
TOL = 1e-4


def _run_ket(n_qubits: int, gates, simulator: str) -> "np.ndarray":
    p = ket.Process(simulator=simulator)
    q = p.alloc(n_qubits)
    for g in gates:
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
    d = ket.dump(q)
    dim = 1 << n_qubits
    vec = np.zeros(dim, dtype=complex)
    for idx, amp in d.states.items():
        vec[idx] = amp
    return vec


def _state_fidelity(a, b) -> float:
    return float(np.abs(np.vdot(a, b)) ** 2)


def _available_simulators() -> list[str]:
    available = []
    for sim in ("dense", "sparse", "dense gpu"):
        try:
            p = ket.Process(simulator=sim)
            q = p.alloc(1)
            ket.H(q)
            ket.dump(q)
            available.append(sim)
        except Exception:
            pass
    return available


def test_ket_backends_agree_with_each_other() -> None:
    if not _HAS_KET:
        print("SKIPPED -- ket-lang not installed (pip install ket-lang)")
        return

    available = _available_simulators()
    print(f"Simuladores disponiveis nesta maquina: {available}")
    if len(available) < 2:
        print("SKIPPED -- precisa de pelo menos 2 simuladores pra comparar")
        return

    n_checked = 0
    n_fail = 0
    for n_qubits, seed in ((3, 7), (5, 7), (6, 99)):
        cfg = CheckConfig(n_qubits=n_qubits, gate_set=GATE_SET, n_samples=300, seed=seed)
        for _ in range(300):
            circ = sample_circuit(cfg)
            states = {sim: _run_ket(n_qubits, circ.gates, sim) for sim in available}
            base = available[0]
            for other in available[1:]:
                fid = _state_fidelity(states[base], states[other])
                n_checked += 1
                if fid < 1 - TOL:
                    n_fail += 1
                    print(f"DIVERGENCIA REAL (acima do ruido float32 esperado) "
                          f"n={n_qubits}: {base} vs {other} fid={fid:.8f}")
                    print(f"  gates: {[(g.kind, g.qubits, g.params) for g in circ.gates]}")

    assert n_fail == 0, f"{n_fail}/{n_checked} pares de backend divergiram acima da tolerancia float32"
    print(f"OK -- {n_checked} pares de backend comparados, 0 divergencias reais "
          f"(tol={TOL}, calibrada pra precisao float32 do Ket)")


if __name__ == "__main__":
    test_ket_backends_agree_with_each_other()

"""Gate matrix table -- the ONLY place in UnitaryGuard that knows what a
named gate physically means. Every matrix here is derived directly from
the standard mathematical definition of the gate (the same convention used
across the quantum computing literature, e.g. Nielsen & Chuang), not from
any specific framework's source code. This is what makes UnitaryGuard
framework-independent: it never imports Qiskit (or any other SDK) to build
or compare circuits.

Convention: |0> = [1,0]^T, |1> = [0,1]^T. RZ/RY/RX use the standard Bloch
rotation convention. For 2-qubit gates, `Gate.qubits = (a, b)` means the
matrix below is built in the `kron(gate_on_a, gate_on_b)` basis order
(a is the "first"/more-significant local index) -- the specific choice is
arbitrary but must be, and is, applied consistently everywhere in this
module, which is what actually matters for a self-consistent equivalence
check (see core.py:circuit_unitary).
"""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------
# 1-qubit gates
# ---------------------------------------------------------------------


def _h():
    return (1 / np.sqrt(2)) * np.array([[1, 1], [1, -1]], dtype=complex)


def _x():
    return np.array([[0, 1], [1, 0]], dtype=complex)


def _y():
    return np.array([[0, -1j], [1j, 0]], dtype=complex)


def _z():
    return np.array([[1, 0], [0, -1]], dtype=complex)


def _s():
    return np.array([[1, 0], [0, 1j]], dtype=complex)


def _sdg():
    return np.array([[1, 0], [0, -1j]], dtype=complex)


def _t():
    return np.array([[1, 0], [0, np.exp(1j * np.pi / 4)]], dtype=complex)


def _tdg():
    return np.array([[1, 0], [0, np.exp(-1j * np.pi / 4)]], dtype=complex)


def _sx():
    return 0.5 * np.array([[1 + 1j, 1 - 1j], [1 - 1j, 1 + 1j]], dtype=complex)


def _rz(theta):
    return np.array([[np.exp(-1j * theta / 2), 0], [0, np.exp(1j * theta / 2)]], dtype=complex)


def _ry(theta):
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    return np.array([[c, -s], [s, c]], dtype=complex)


def _rx(theta):
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    return np.array([[c, -1j * s], [-1j * s, c]], dtype=complex)


def _p(lam):
    return np.array([[1, 0], [0, np.exp(1j * lam)]], dtype=complex)


def _u(theta, phi, lam):
    # U(theta,phi,lam) -- standard IBM/OpenQASM 3 physical-gate definition.
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    return np.array([
        [c, -np.exp(1j * lam) * s],
        [np.exp(1j * phi) * s, np.exp(1j * (phi + lam)) * c],
    ], dtype=complex)


def _sxdg():
    return 0.5 * np.array([[1 - 1j, 1 + 1j], [1 + 1j, 1 - 1j]], dtype=complex)


def _r(theta, phi):
    # verified against quantum.cloud.ibm.com/docs/api/qiskit/qiskit.circuit.library.RGate
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    return np.array([
        [c, -1j * np.exp(-1j * phi) * s],
        [-1j * np.exp(1j * phi) * s, c],
    ], dtype=complex)


_1Q_FIXED = {"h": _h, "x": _x, "y": _y, "z": _z, "s": _s, "sdg": _sdg,
             "t": _t, "tdg": _tdg, "sx": _sx, "sxdg": _sxdg}
_1Q_PARAM = {"rz": _rz, "ry": _ry, "rx": _rx, "p": _p}  # 1 parameter (theta)
_1Q_MULTI = {"u": (_u, 3), "r": (_r, 2)}  # (function, n_params)

# ---------------------------------------------------------------------
# 2-qubit gates -- basis |ab> = |00>,|01>,|10>,|11>, a=qubits[0] (more
# significant local index), b=qubits[1].
# ---------------------------------------------------------------------

_CX = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=complex)
_CZ = np.diag([1, 1, 1, -1]).astype(complex)
_SWAP = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=complex)


def _controlled_u(u2x2):
    """Controlled-U, control = qubits[0] (first/more-significant local
    index, this module's fixed convention)."""
    m = np.eye(4, dtype=complex)
    m[2:4, 2:4] = u2x2
    return m


def _rzz(theta):
    d = np.exp(-1j * theta / 2 * np.array([1, -1, -1, 1]))
    return np.diag(d).astype(complex)


def _rxx(theta):
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    m = np.eye(4, dtype=complex) * c
    anti = np.array([[0, 0, 0, 1], [0, 0, 1, 0], [0, 1, 0, 0], [1, 0, 0, 0]], dtype=complex)
    return m - 1j * s * anti


def _ryy(theta):
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    m = np.eye(4, dtype=complex) * c
    anti = np.array([[0, 0, 0, -1], [0, 0, 1, 0], [0, 1, 0, 0], [-1, 0, 0, 0]], dtype=complex)
    return m - 1j * s * anti


_ISWAP = np.array([[1, 0, 0, 0], [0, 0, 1j, 0], [0, 1j, 0, 0], [0, 0, 0, 1]], dtype=complex)
_DCX = np.array([[1, 0, 0, 0], [0, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0]], dtype=complex)
_ECR = (1 / np.sqrt(2)) * np.array([
    [0, 1, 0, 1j], [1, 0, -1j, 0], [0, 1j, 0, 1], [-1j, 0, 1, 0],
], dtype=complex)


def _cu(theta, phi, lam, gamma):
    # verified: controlled-U with an extra phase e^{i*gamma} applied only
    # on the |1>-control branch (quantum.cloud.ibm.com CUGate).
    return _controlled_u(np.exp(1j * gamma) * _u(theta, phi, lam))


def _rzx(theta):
    # verified against quantum.cloud.ibm.com/docs/api/qiskit/qiskit.circuit.library.RZXGate
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    return np.array([
        [c, 0, -1j * s, 0],
        [0, c, 0, 1j * s],
        [-1j * s, 0, c, 0],
        [0, 1j * s, 0, c],
    ], dtype=complex)


def _xx_plus_yy(theta, beta):
    # verified against quantum.cloud.ibm.com/docs/api/qiskit/qiskit.circuit.library.XXPlusYYGate
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    return np.array([
        [1, 0, 0, 0],
        [0, c, -1j * s * np.exp(-1j * beta), 0],
        [0, -1j * s * np.exp(1j * beta), c, 0],
        [0, 0, 0, 1],
    ], dtype=complex)


def _xx_minus_yy(theta, beta):
    # verified against quantum.cloud.ibm.com/docs/api/qiskit/qiskit.circuit.library.XXMinusYYGate
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    return np.array([
        [c, 0, 0, -1j * s * np.exp(-1j * beta)],
        [0, 1, 0, 0],
        [0, 0, 1, 0],
        [-1j * s * np.exp(1j * beta), 0, 0, c],
    ], dtype=complex)


_2Q_FIXED = {
    "cx": lambda: _CX, "cz": lambda: _CZ, "swap": lambda: _SWAP,
    "iswap": lambda: _ISWAP, "dcx": lambda: _DCX, "ecr": lambda: _ECR,
    "cy": lambda: _controlled_u(_y()), "ch": lambda: _controlled_u(_h()),
    "csx": lambda: _controlled_u(_sx()),
}
_2Q_PARAM = {  # 1 parameter (theta)
    "crz": lambda th: _controlled_u(_rz(th)),
    "crx": lambda th: _controlled_u(_rx(th)),
    "cry": lambda th: _controlled_u(_ry(th)),
    "cp": lambda th: _controlled_u(np.array([[1, 0], [0, np.exp(1j * th)]], dtype=complex)),
    "rzz": _rzz, "rxx": _rxx, "ryy": _ryy, "rzx": _rzx,
}
_2Q_MULTI = {
    "cu": (_cu, 4),
    "xx_plus_yy": (_xx_plus_yy, 2),
    "xx_minus_yy": (_xx_minus_yy, 2),
}

# (arity, n_params) -- the single source of truth for what a gate name
# means structurally. Both core.py's random sampler and exhaustive.py's
# enumerator read this.
GATE_TABLE = {
    **{k: (1, 0) for k in _1Q_FIXED},
    **{k: (1, 1) for k in _1Q_PARAM},
    **{k: (1, n) for k, (_fn, n) in _1Q_MULTI.items()},
    **{k: (2, 0) for k in _2Q_FIXED},
    **{k: (2, 1) for k in _2Q_PARAM},
    **{k: (2, n) for k, (_fn, n) in _2Q_MULTI.items()},
}


def gate_matrix(kind: str, params: tuple[float, ...]):
    if kind in _1Q_FIXED:
        return _1Q_FIXED[kind]()
    if kind in _1Q_PARAM:
        return _1Q_PARAM[kind](*params)
    if kind in _1Q_MULTI:
        return _1Q_MULTI[kind][0](*params)
    if kind in _2Q_FIXED:
        return _2Q_FIXED[kind]()
    if kind in _2Q_PARAM:
        return _2Q_PARAM[kind](*params)
    if kind in _2Q_MULTI:
        return _2Q_MULTI[kind][0](*params)
    raise ValueError(f"unknown gate '{kind}' -- known gates: {sorted(GATE_TABLE)}")


def apply_1q(n_qubits: int, q0: int, m2) -> "np.ndarray":
    """Full 2^n x 2^n matrix for a 1-qubit gate acting on q0 (qubit 0 =
    most-significant bit of the basis index), built by direct action on
    basis indices (equivalent to kron(I,m,I), no dense intermediate)."""
    dim = 1 << n_qubits
    out = np.zeros((dim, dim), dtype=complex)
    bit = n_qubits - 1 - q0
    for i in range(dim):
        bv = (i >> bit) & 1
        for bvp in range(2):
            coeff = m2[bvp, bv]
            if coeff == 0:
                continue
            j = (i & ~(1 << bit)) | (bvp << bit)
            out[j, i] += coeff
    return out


def apply_2q(n_qubits: int, qa: int, qb: int, m4) -> "np.ndarray":
    """Full 2^n x 2^n matrix for a 2-qubit gate acting on (qa, qb) --
    qa is the more-significant local index (matches this module's fixed
    kron(gate_qa, gate_qb) convention), by direct action on basis
    indices. Works for any qa/qb, adjacent or not."""
    dim = 1 << n_qubits
    out = np.zeros((dim, dim), dtype=complex)
    bit_a = n_qubits - 1 - qa
    bit_b = n_qubits - 1 - qb
    for i in range(dim):
        b_a = (i >> bit_a) & 1
        b_b = (i >> bit_b) & 1
        local = 2 * b_a + b_b
        for lp in range(4):
            coeff = m4[lp, local]
            if coeff == 0:
                continue
            b_a_p, b_b_p = divmod(lp, 2)
            j = i
            j = (j & ~(1 << bit_a)) | (b_a_p << bit_a)
            j = (j & ~(1 << bit_b)) | (b_b_p << bit_b)
            out[j, i] += coeff
    return out

"""A faithful, self-contained Python port of rsgridsynth's single-qubit
Clifford normal form (E^a X^b S^c W^d parametrization, syllables T/HT/SHT),
with a toggle to reproduce the real SHT-merge bug (H*S*H vs the correct
S*H*S) found in `qiskit-community/rsgridsynth` (PR #49).

This exists so UnitaryGuard's own test suite can prove, end to end and
without any external dependency (no cloning/compiling the real Rust crate),
that the tool would have caught this exact bug shape and shrunk it to a
minimal reproduction.
"""
from __future__ import annotations

from dataclasses import dataclass

from qiskit import QuantumCircuit

CONJ2_TABLE = [
    (0, 0), (0, 0), (1, 0), (3, 2), (2, 0), (2, 4), (3, 0), (1, 6),
]
CONJ3_TABLE = [
    (0, 0, 0, 0), (0, 0, 1, 0), (0, 0, 2, 0), (0, 0, 3, 0),
    (0, 1, 0, 0), (0, 1, 1, 0), (0, 1, 2, 0), (0, 1, 3, 0),
    (1, 0, 0, 0), (2, 0, 3, 6), (1, 1, 2, 2), (2, 1, 3, 6),
    (1, 0, 2, 0), (2, 1, 1, 0), (1, 1, 0, 6), (2, 0, 1, 4),
    (2, 0, 0, 0), (1, 1, 3, 4), (2, 1, 0, 0), (1, 0, 1, 2),
    (2, 1, 2, 2), (1, 1, 1, 0), (2, 0, 2, 6), (1, 0, 3, 2),
]
# (axis, c, d) -- axis: 0=I, 1=H, 2=SH
TCONJ_TABLE = [
    (0, 0, 0), (0, 1, 7), (1, 3, 3), (1, 2, 0), (2, 0, 5), (2, 1, 4),
]


@dataclass(frozen=True)
class Clifford:
    a: int
    b: int
    c: int
    d: int

    @staticmethod
    def new(a: int, b: int, c: int, d: int) -> "Clifford":
        return Clifford(a % 3, b & 1, c & 0b11, d & 0b111)

    def mul(self, rhs: "Clifford") -> "Clifford":
        a1, b1, c1, d1 = CONJ3_TABLE[(rhs.a << 3) | (self.b << 2) | self.c]
        c2, d2 = CONJ2_TABLE[(c1 << 1) | rhs.b]
        return Clifford.new(
            self.a + a1,
            b1 + rhs.b,
            c2 + rhs.c,
            d1 + d2 + self.d + rhs.d,
        )

    def decompose_tconj(self) -> tuple[int, "Clifford"]:
        axis, c, d = TCONJ_TABLE[(self.a << 1) | self.b]
        return axis, Clifford.new(0, self.b, self.c + c, self.d + d)

    def decompose_coset(self) -> tuple[int, "Clifford"]:
        if self.a == 0:
            return 0, self
        if self.a == 1:
            return 1, CLIFFORD_H_INV.mul(self)
        return 2, CLIFFORD_SH_INV.mul(self)

    def to_gates(self) -> str:
        axis, c = self.decompose_coset()
        gates = "" if axis == 0 else ("H" if axis == 1 else "SH")
        gates += "X" * c.b
        gates += "S" * c.c
        gates += "W" * c.d
        return gates if gates else "I"


CLIFFORD_I = Clifford(0, 0, 0, 0)
CLIFFORD_X = Clifford(0, 1, 0, 0)
CLIFFORD_S = Clifford(0, 0, 1, 0)
CLIFFORD_W = Clifford(0, 0, 0, 1)
CLIFFORD_H = Clifford(1, 0, 1, 5)
CLIFFORD_H_INV = Clifford(2, 0, 2, 2)  # H^-1, precomputed (H is order 2 up to phase: matches CINV_TABLE row for CLIFFORD_H)
CLIFFORD_SH_INV = CLIFFORD_S.mul(CLIFFORD_H)  # placeholder, corrected below


def _inv(c: Clifford) -> Clifford:
    """Brute-force inverse search over the 24 Cliffords x 8 phases -- fine
    for this toy/test-only port (never called in a hot loop)."""
    for a in range(3):
        for b in range(2):
            for cc in range(4):
                for d in range(8):
                    cand = Clifford.new(a, b, cc, d)
                    if c.mul(cand) == CLIFFORD_I:
                        return cand
    raise AssertionError("no inverse found -- table bug")


CLIFFORD_H_INV = _inv(CLIFFORD_H)
CLIFFORD_SH_INV = _inv(CLIFFORD_S.mul(CLIFFORD_H))


class NormalForm:
    """Direct port of rsgridsynth's NormalForm::append_gate/from_gates/to_gates.

    `buggy=True` reproduces the real bug (H*S*H instead of S*H*S in the SHT
    merge branch); `buggy=False` is the fix.
    """

    def __init__(self, buggy: bool) -> None:
        self.buggy = buggy
        self.syllables: list[str] = []  # each entry: "T", "HT", or "SHT"
        self.c = CLIFFORD_I

    def _append_t(self) -> None:
        axis, new_c = self.c.decompose_tconj()
        if axis == 0:  # I
            if self.syllables:
                last = self.syllables[-1]
                if last == "T":
                    self.syllables.pop()
                    self.c = CLIFFORD_S.mul(new_c)
                    return
                if last == "HT":
                    self.syllables.pop()
                    self.c = CLIFFORD_H.mul(CLIFFORD_S).mul(new_c)
                    return
                if last == "SHT":
                    self.syllables.pop()
                    if self.buggy:
                        merged = CLIFFORD_H.mul(CLIFFORD_S).mul(CLIFFORD_H)
                    else:
                        merged = CLIFFORD_S.mul(CLIFFORD_H).mul(CLIFFORD_S)
                    self.c = merged.mul(new_c)
                    return
            self.syllables.append("T")
            self.c = new_c
        elif axis == 1:  # H
            self.syllables.append("HT")
            self.c = new_c
        else:  # SH
            self.syllables.append("SHT")
            self.c = new_c

    def append_gate(self, g: str) -> None:
        if g == "H":
            self.c = self.c.mul(CLIFFORD_H)
        elif g == "S":
            self.c = self.c.mul(CLIFFORD_S)
        elif g == "X":
            self.c = self.c.mul(CLIFFORD_X)
        elif g == "W":
            self.c = self.c.mul(CLIFFORD_W)
        elif g == "T":
            self._append_t()
        else:
            raise ValueError(f"unsupported gate {g!r}")

    @staticmethod
    def from_gates(gates: str, buggy: bool) -> "NormalForm":
        nf = NormalForm(buggy)
        for ch in gates:
            nf.append_gate(ch)
        return nf

    def to_gates(self) -> str:
        out = "".join(s for s in self.syllables)
        out += self.c.to_gates() if self.c.to_gates() != "I" else ""
        return out if out else "I"


_GATE_METHOD = {"H": "h", "S": "s", "T": "t", "X": "x"}


def circuit_to_gate_string(qc: QuantumCircuit) -> str:
    """H/S/T/X-only circuit -> gate-letter string, in temporal order."""
    letters = []
    for instr in qc.data:
        name = instr.operation.name
        letter = {"h": "H", "s": "S", "t": "T", "x": "X"}.get(name)
        if letter is None:
            raise ValueError(f"toy_normal_form only supports h/s/t/x, got {name!r}")
        letters.append(letter)
    return "".join(letters) if letters else "I"


def gate_string_to_circuit(n_qubits: int, s: str) -> QuantumCircuit:
    qc = QuantumCircuit(n_qubits)
    for ch in s:
        if ch == "I":
            continue
        if ch == "W":
            qc.global_phase += 3.141592653589793 / 4
            continue
        getattr(qc, _GATE_METHOD[ch])(0)
    return qc


def make_transform(buggy: bool):
    """Return a QuantumCircuit -> QuantumCircuit transform wrapping the toy
    NormalForm compressor, for use with unitaryguard.check_transform."""

    def transform(qc: QuantumCircuit) -> QuantumCircuit:
        s = circuit_to_gate_string(qc)
        nf = NormalForm.from_gates(s, buggy=buggy)
        out = nf.to_gates()
        return gate_string_to_circuit(qc.num_qubits, out)

    return transform

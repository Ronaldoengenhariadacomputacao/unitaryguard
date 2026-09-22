"""Core of UnitaryGuard: sample circuits, check unitary equivalence across a
transform, shrink failures to a minimal reproduction.

v0.2: framework-independent -- no Qiskit (or any other SDK) dependency
anywhere in this module. Circuits are a small native `Circuit`/`Gate`
representation; unitary equivalence is checked via `matrices.py`'s gate
table, derived from each gate's standard mathematical definition, built
with numpy alone.

Why this changed from v0.1 (which used `qiskit.QuantumCircuit` +
`qiskit.quantum_info.Operator`): the real use case for this tool is
validating an EXTERNAL engine (e.g. a from-scratch transpiler written in
another language) -- depending on Qiskit for the oracle side is at best an
unnecessary dependency and at worst, when the transform under test is
ITSELF a real Qiskit pass (as some of this project's own earlier examples
were), a genuine circularity: the code being tested and the code judging
it are the same library, so a shared bug in Qiskit's own gate-matrix
definitions can never be caught. See BACKLOG.md for the full writeup.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

from .matrices import GATE_TABLE, apply_1q, apply_2q, apply_3q, gate_matrix


@dataclass(frozen=True)
class Gate:
    kind: str
    qubits: tuple[int, ...]
    params: tuple[float, ...] = ()


@dataclass
class Circuit:
    n_qubits: int
    gates: list[Gate] = field(default_factory=list)

    def copy(self) -> "Circuit":
        return Circuit(self.n_qubits, list(self.gates))


Transform = Callable[[Circuit], Circuit]


@dataclass
class CheckConfig:
    n_qubits: int
    gate_set: Sequence[str]
    n_samples: int = 200
    min_gates: int = 1
    max_gates: int = 12
    seed: int | None = None
    tol: float = 1e-7
    rng: random.Random = field(default=None, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        for g in self.gate_set:
            if g not in GATE_TABLE:
                raise ValueError(
                    f"unknown gate '{g}' in gate_set -- known gates: {sorted(GATE_TABLE)}"
                )
        if self.rng is None:
            self.rng = random.Random(self.seed)


@dataclass
class Failure:
    original: Circuit
    transformed: Circuit
    fidelity: float
    minimized: Circuit | None = None
    minimized_transformed: Circuit | None = None
    minimized_fidelity: float | None = None


def _gate_str(g: Gate) -> str:
    qs = ",".join(str(q) for q in g.qubits)
    if g.params:
        ps = ",".join(f"{p:.4g}" for p in g.params)
        return f"{g.kind}({ps})[{qs}]"
    return f"{g.kind}[{qs}]"


@dataclass
class Report:
    n_checked: int
    n_failed: int
    failures: list[Failure]

    @property
    def ok(self) -> bool:
        return self.n_failed == 0

    def summary(self) -> str:
        lines = [
            f"UnitaryGuard: {self.n_checked} circuits checked, "
            f"{self.n_failed} failed ({self.n_checked - self.n_failed} passed)."
        ]
        if self.n_failed:
            lines.append(
                "FAILED -- transform does not preserve the circuit's unitary "
                "on at least one sampled input."
            )
            for i, f in enumerate(self.failures):
                lines.append(f"\n--- failure #{i + 1} (fidelity={f.fidelity:.6f}) ---")
                target = f.minimized if f.minimized is not None else f.original
                gate_names = ", ".join(_gate_str(g) for g in target.gates)
                lines.append(f"minimal reproduction ({len(target.gates)} gates, "
                              f"{target.n_qubits} qubits): {gate_names}")
                if f.minimized_fidelity is not None:
                    lines.append(f"minimized fidelity = {f.minimized_fidelity:.6f}")
        else:
            lines.append("OK -- no counterexample found in this run.")
        return "\n".join(lines)


def _random_gate(cfg: CheckConfig, circ: Circuit) -> None:
    name = cfg.rng.choice(cfg.gate_set)
    arity, n_params = GATE_TABLE[name]
    qubits = tuple(cfg.rng.sample(range(cfg.n_qubits), arity))
    params = tuple(cfg.rng.uniform(0, 2 * 3.141592653589793) for _ in range(n_params))
    circ.gates.append(Gate(name, qubits, params))


def sample_circuit(cfg: CheckConfig) -> Circuit:
    """Build one random circuit within cfg's vocabulary/qubit count."""
    n_gates = cfg.rng.randint(cfg.min_gates, cfg.max_gates)
    circ = Circuit(cfg.n_qubits)
    for _ in range(n_gates):
        _random_gate(cfg, circ)
    return circ


def circuit_unitary(circ: Circuit) -> "np.ndarray":
    """Build the full 2^n x 2^n unitary of a circuit by applying each gate's
    matrix (matrices.py) directly to its qubit(s), via basis-index action
    (no dense kron intermediate)."""
    dim = 1 << circ.n_qubits
    acc = np.eye(dim, dtype=complex)
    for g in circ.gates:
        m = gate_matrix(g.kind, g.params)
        arity = len(g.qubits)
        if arity == 1:
            step = apply_1q(circ.n_qubits, g.qubits[0], m)
        elif arity == 2:
            step = apply_2q(circ.n_qubits, g.qubits[0], g.qubits[1], m)
        elif arity == 3:
            step = apply_3q(circ.n_qubits, g.qubits[0], g.qubits[1], g.qubits[2], m)
        else:
            raise ValueError(f"gate '{g.kind}' has unsupported arity {arity}")
        acc = step @ acc
    return acc


def equivalent(a: Circuit, b: Circuit, tol: float) -> tuple[bool, float]:
    """Unitary equivalence up to global phase, via process fidelity
    F = |Tr(Ua^dagger . Ub)|^2 / d^2 (standard formula for two unitaries --
    reduces to the same quantity Qiskit's process_fidelity computes for
    this case, so existing `tol` thresholds carry over unchanged from the
    old Qiskit-based implementation).

    Returns (is_equivalent, fidelity). Raises ValueError if the two circuits
    act on a different number of qubits (out of scope -- see DESIGN.md).
    """
    if a.n_qubits != b.n_qubits:
        raise ValueError(
            f"circuits have different qubit counts ({a.n_qubits} vs "
            f"{b.n_qubits}) -- ancilla-widening transforms are out of "
            "scope for this check (see DESIGN.md)."
        )
    ua = circuit_unitary(a)
    ub = circuit_unitary(b)
    d = ua.shape[0]
    tr = np.trace(ua.conj().T @ ub)
    fid = float(np.abs(tr) ** 2) / (d ** 2)
    return (1.0 - fid) <= tol, fid


def _circuit_from_gates(n_qubits: int, gates: list[Gate]) -> Circuit:
    return Circuit(n_qubits, list(gates))


def shrink_failure(
    original: Circuit,
    transform: Transform,
    tol: float,
) -> tuple[Circuit, Circuit, float]:
    """Reduce a failing circuit to a locally-minimal one that still exhibits
    a unitary mismatch after `transform`.

    Fixed-point, single-gate-drop reduction (delta-debugging in spirit):
    repeatedly try removing one gate at a time; keep the removal if the
    reduced circuit still fails. Stops when no single gate can be dropped
    without the failure disappearing.
    """
    gates = list(original.gates)
    changed = True
    while changed and len(gates) > 0:
        changed = False
        i = 0
        while i < len(gates):
            candidate = gates[:i] + gates[i + 1:]
            if len(candidate) == 0:
                i += 1
                continue
            cand_circ = _circuit_from_gates(original.n_qubits, candidate)
            try:
                cand_out = transform(cand_circ)
                still_fails, _fid = equivalent(cand_circ, cand_out, tol)
            except Exception:
                # a transform that errors out on the reduced circuit is not
                # a valid shrink target -- keep the gate
                i += 1
                continue
            if not still_fails:
                gates = candidate
                changed = True
                # do not advance i -- re-check same index against new list
            else:
                i += 1

    minimized = _circuit_from_gates(original.n_qubits, gates)
    minimized_out = transform(minimized)
    _ok, fid = equivalent(minimized, minimized_out, tol)
    return minimized, minimized_out, fid


def check_transform(transform: Transform, cfg: CheckConfig, shrink: bool = True) -> Report:
    """Sample cfg.n_samples circuits, run each through `transform`, and check
    that the transformed circuit is unitarily equivalent to the original.

    Returns a Report; a non-empty Report.failures means `transform` does NOT
    preserve semantics on at least one sampled circuit.
    """
    failures: list[Failure] = []
    for _ in range(cfg.n_samples):
        circ = sample_circuit(cfg)
        out = transform(circ)
        ok, fid = equivalent(circ, out, cfg.tol)
        if ok:
            continue
        failure = Failure(original=circ, transformed=out, fidelity=fid)
        if shrink:
            min_circ, min_out, min_fid = shrink_failure(circ, transform, cfg.tol)
            failure.minimized = min_circ
            failure.minimized_transformed = min_out
            failure.minimized_fidelity = min_fid
        failures.append(failure)

    return Report(n_checked=cfg.n_samples, n_failed=len(failures), failures=failures)

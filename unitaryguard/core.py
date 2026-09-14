"""Core of UnitaryGuard: sample circuits, check unitary equivalence across a
transform, shrink failures to a minimal reproduction.
"""
from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from typing import Callable, Sequence

from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator, process_fidelity

Transform = Callable[[QuantumCircuit], QuantumCircuit]

# Gate name -> (arity, qiskit QuantumCircuit method name, needs_param)
_GATE_TABLE = {
    "h": (1, "h", False),
    "x": (1, "x", False),
    "y": (1, "y", False),
    "z": (1, "z", False),
    "s": (1, "s", False),
    "sdg": (1, "sdg", False),
    "t": (1, "t", False),
    "tdg": (1, "tdg", False),
    "sx": (1, "sx", False),
    "cx": (2, "cx", False),
    "cz": (2, "cz", False),
    "swap": (2, "swap", False),
    "rz": (1, "rz", True),
    "rx": (1, "rx", True),
    "ry": (1, "ry", True),
}


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
            if g not in _GATE_TABLE:
                raise ValueError(
                    f"unknown gate '{g}' in gate_set -- known gates: {sorted(_GATE_TABLE)}"
                )
        if self.rng is None:
            self.rng = random.Random(self.seed)


@dataclass
class Failure:
    original: QuantumCircuit
    transformed: QuantumCircuit
    fidelity: float
    minimized: QuantumCircuit | None = None
    minimized_transformed: QuantumCircuit | None = None
    minimized_fidelity: float | None = None


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
                gate_names = ", ".join(
                    f"{instr.operation.name}({','.join(str(qc.find_bit(q).index) for q in instr.qubits)})"
                    for instr, qc in ((i, target) for i in target.data)
                )
                lines.append(f"minimal reproduction ({target.size()} gates): {gate_names}")
                # qc.draw() emits box-drawing Unicode that crashes on a
                # cp1252 (default Windows) stdout -- degrade gracefully
                # instead of raising UnicodeEncodeError from a print() call
                # the caller doesn't control the encoding of.
                drawing = str(target.draw(output="text"))
                try:
                    drawing.encode(sys.stdout.encoding or "utf-8")
                    lines.append(drawing)
                except (UnicodeEncodeError, LookupError):
                    pass  # the gate list above already conveys the circuit
                if f.minimized_fidelity is not None:
                    lines.append(f"minimized fidelity = {f.minimized_fidelity:.6f}")
        else:
            lines.append("OK -- no counterexample found in this run.")
        return "\n".join(lines)


def _random_gate(cfg: CheckConfig, qc: QuantumCircuit) -> None:
    name = cfg.rng.choice(cfg.gate_set)
    arity, method, needs_param = _GATE_TABLE[name]
    qubits = cfg.rng.sample(range(cfg.n_qubits), arity)
    fn = getattr(qc, method)
    if needs_param:
        theta = cfg.rng.uniform(0, 2 * 3.141592653589793)
        fn(theta, *qubits)
    else:
        fn(*qubits)


def sample_circuit(cfg: CheckConfig) -> QuantumCircuit:
    """Build one random circuit within cfg's vocabulary/qubit count."""
    n_gates = cfg.rng.randint(cfg.min_gates, cfg.max_gates)
    qc = QuantumCircuit(cfg.n_qubits)
    for _ in range(n_gates):
        _random_gate(cfg, qc)
    return qc


def equivalent(a: QuantumCircuit, b: QuantumCircuit, tol: float) -> tuple[bool, float]:
    """Unitary equivalence up to global phase, via process_fidelity.

    Returns (is_equivalent, fidelity). Raises ValueError if the two circuits
    act on a different number of qubits (out of scope for v0.1 -- see
    DESIGN.md).
    """
    if a.num_qubits != b.num_qubits:
        raise ValueError(
            f"circuits have different qubit counts ({a.num_qubits} vs "
            f"{b.num_qubits}) -- ancilla-widening transforms are out of "
            "scope for this check (see DESIGN.md)."
        )
    ua = Operator(a)
    ub = Operator(b)
    fid = process_fidelity(ua, target=ub)
    return (1.0 - fid) <= tol, fid


def _gate_list(qc: QuantumCircuit) -> list:
    return list(qc.data)


def _circuit_from_gate_list(n_qubits: int, gates: list) -> QuantumCircuit:
    qc = QuantumCircuit(n_qubits)
    for instr in gates:
        qc.append(instr.operation, instr.qubits, instr.clbits)
    return qc


def shrink_failure(
    original: QuantumCircuit,
    transform: Transform,
    tol: float,
) -> tuple[QuantumCircuit, QuantumCircuit, float]:
    """Reduce a failing circuit to a locally-minimal one that still exhibits
    a unitary mismatch after `transform`.

    Fixed-point, single-gate-drop reduction (delta-debugging in spirit):
    repeatedly try removing one gate at a time; keep the removal if the
    reduced circuit still fails. Stops when no single gate can be dropped
    without the failure disappearing.
    """
    gates = _gate_list(original)
    changed = True
    while changed and len(gates) > 0:
        changed = False
        i = 0
        while i < len(gates):
            candidate = gates[:i] + gates[i + 1 :]
            if len(candidate) == 0:
                i += 1
                continue
            cand_qc = _circuit_from_gate_list(original.num_qubits, candidate)
            try:
                cand_out = transform(cand_qc)
                still_fails, _fid = equivalent(cand_qc, cand_out, tol)
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

    minimized = _circuit_from_gate_list(original.num_qubits, gates)
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
        qc = sample_circuit(cfg)
        out = transform(qc)
        ok, fid = equivalent(qc, out, cfg.tol)
        if ok:
            continue
        failure = Failure(original=qc, transformed=out, fidelity=fid)
        if shrink:
            min_qc, min_out, min_fid = shrink_failure(qc, transform, cfg.tol)
            failure.minimized = min_qc
            failure.minimized_transformed = min_out
            failure.minimized_fidelity = min_fid
        failures.append(failure)

    return Report(n_checked=cfg.n_samples, n_failed=len(failures), failures=failures)

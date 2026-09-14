"""Exhaustive small-circuit search: complements the random sampler in
core.py with a deterministic mode targeted at exactly the bug class found
twice this project's motivating investigations were built on -- gate-order
and gate-inversion transcription errors (H*S*H vs S*H*S; S vs Sdg swapped).

That class of bug is NOT statistical noise: when the buggy code path exists,
it fails on every circuit that reaches it, 100% of the time, at a fixed
minimal length. Random sampling finds such bugs only with some probability
per run (it has to happen to construct the right small window by chance).
Exhaustive enumeration over all circuits up to a bounded length instead
guarantees finding the smallest counterexample the vocabulary can express,
with no shrinking step needed -- the first failure found, tested shortest
length first, already IS minimal.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Iterator

from qiskit import QuantumCircuit

from .core import CheckConfig, Failure, Report, Transform, _GATE_TABLE, equivalent


def enumerate_circuits(n_qubits: int, gate_set: list[str], length: int) -> Iterator[QuantumCircuit]:
    """Yield every circuit of exactly `length` gates over `gate_set`,
    respecting each gate's arity (qubit targets are ordered tuples of
    distinct qubits, e.g. cx(0,1) and cx(1,0) are both enumerated -- they
    are different gates).

    Parametrized gates (rz/rx/ry) are NOT supported here (a continuous
    parameter can't be exhaustively enumerated) -- use core.check_transform
    for those. Raises ValueError if gate_set contains one.
    """
    for g in gate_set:
        if g not in _GATE_TABLE:
            raise ValueError(f"unknown gate '{g}'")
        arity, _method, needs_param = _GATE_TABLE[g]
        if needs_param:
            raise ValueError(
                f"'{g}' takes a continuous parameter -- exhaustive enumeration "
                "only supports discrete gates (see core.check_transform for "
                "parametrized sampling instead)"
            )

    # each "slot" choice is (gate_name, ordered_qubit_tuple)
    choices = []
    for g in gate_set:
        arity, _method, _ = _GATE_TABLE[g]
        for qubits in itertools.permutations(range(n_qubits), arity):
            choices.append((g, qubits))

    for combo in itertools.product(choices, repeat=length):
        qc = QuantumCircuit(n_qubits)
        for name, qubits in combo:
            _arity, method, _ = _GATE_TABLE[name]
            getattr(qc, method)(*qubits)
        yield qc


@dataclass
class ExhaustiveReport(Report):
    smallest_failing_length: int | None = None
    n_checked_by_length: dict[int, int] | None = None


def check_transform_exhaustive(
    transform: Transform,
    n_qubits: int,
    gate_set: list[str],
    max_length: int,
    tol: float = 1e-7,
    stop_at_first_length_with_failure: bool = True,
) -> ExhaustiveReport:
    """Test EVERY circuit up to `max_length` gates, shortest first.

    By default (`stop_at_first_length_with_failure=True`), stops as soon as
    any length L has at least one failing circuit -- every circuit of that
    length is still checked (so all minimal-length counterexamples at that
    length are reported together), but no longer lengths are attempted,
    since they cannot produce a smaller counterexample. Set to False to
    exhaustively check every length up to max_length regardless.
    """
    n_checked = 0
    n_checked_by_length: dict[int, int] = {}
    failures: list[Failure] = []
    smallest_failing_length: int | None = None

    for length in range(0, max_length + 1):
        length_checked = 0
        length_failures: list[Failure] = []
        for qc in enumerate_circuits(n_qubits, gate_set, length):
            length_checked += 1
            n_checked += 1
            out = transform(qc)
            ok, fid = equivalent(qc, out, tol)
            if not ok:
                length_failures.append(Failure(original=qc, transformed=out, fidelity=fid))
        n_checked_by_length[length] = length_checked
        if length_failures:
            # already minimal by construction: report as both original and
            # "minimized" so Report.summary() prints them directly
            for f in length_failures:
                f.minimized = f.original
                f.minimized_transformed = f.transformed
                f.minimized_fidelity = f.fidelity
            failures.extend(length_failures)
            smallest_failing_length = length
            if stop_at_first_length_with_failure:
                break

    return ExhaustiveReport(
        n_checked=n_checked,
        n_failed=len(failures),
        failures=failures,
        smallest_failing_length=smallest_failing_length,
        n_checked_by_length=n_checked_by_length,
    )

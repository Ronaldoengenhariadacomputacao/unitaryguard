"""Parallel (multi-process) exhaustive checking.

Why processes, not a GPU: the measured bottleneck in exhaustive.py is not
numerical (Operator/process_fidelity on 1-2 qubit matrices is trivial) --
it's Python/Qiskit orchestration overhead per circuit (building a
QuantumCircuit, calling PassManager.run() or transpile()). That overhead is
CPU-bound, single-threaded per call, and the workload is embarrassingly
parallel (every circuit is checked completely independently) -- textbook fit
for a process pool across CPU cores, not for GPU batch linear algebra (there
is no batch to form; each check is one small, independent Python call into a
library that isn't GPU-aware).

Circuits are addressed by integer index (mixed-radix decomposition of the
same enumeration order `itertools.product` uses) so work can be split into
contiguous ranges per worker without materializing the full circuit list
first.
"""
from __future__ import annotations

import importlib
import itertools
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from qiskit import QuantumCircuit

from .core import Failure, _GATE_TABLE, equivalent
from .exhaustive import ExhaustiveReport


def _choices_for(n_qubits: int, gate_set: list[str]) -> list[tuple[str, tuple[int, ...]]]:
    choices = []
    for g in gate_set:
        arity, _method, needs_param = _GATE_TABLE[g]
        if needs_param:
            raise ValueError(f"'{g}' takes a continuous parameter -- not supported here")
        for qubits in itertools.permutations(range(n_qubits), arity):
            choices.append((g, qubits))
    return choices


def _nth_combo(choices: list, length: int, index: int) -> list:
    base = len(choices)
    digits = [0] * length
    rem = index
    for pos in range(length - 1, -1, -1):
        digits[pos] = rem % base
        rem //= base
    return [choices[d] for d in digits]


def _circuit_from_combo(n_qubits: int, combo: list) -> QuantumCircuit:
    qc = QuantumCircuit(n_qubits)
    for name, qubits in combo:
        _arity, method, _ = _GATE_TABLE[name]
        getattr(qc, method)(*qubits)
    return qc


def _load_target(spec: str, factory_args: tuple, factory_kwargs: dict):
    module_name, attr = spec.split(":", 1)
    mod = importlib.import_module(module_name)
    obj = mod
    for part in attr.split("."):
        obj = getattr(obj, part)
    if factory_args or factory_kwargs:
        obj = obj(*factory_args, **factory_kwargs)
    return obj


def _worker_check_range(
    target_spec: str,
    factory_args: tuple,
    factory_kwargs: dict,
    n_qubits: int,
    gate_set: list[str],
    length: int,
    start: int,
    end: int,
    tol: float,
) -> list[tuple]:
    """Runs in a worker process: check circuit indices [start, end) at this
    length. Returns a list of (gate_string_repr, fidelity) for failures --
    plain data only, so it survives the trip back across the process
    boundary without needing QuantumCircuit to be pickled through the pool.
    """
    transform = _load_target(target_spec, factory_args, factory_kwargs)
    choices = _choices_for(n_qubits, gate_set)
    out = []
    for idx in range(start, end):
        combo = _nth_combo(choices, length, idx)
        qc = _circuit_from_combo(n_qubits, combo)
        result = transform(qc)
        ok, fid = equivalent(qc, result, tol)
        if not ok:
            out.append((idx, fid))
    return out


def _split_range(total: int, n_workers: int) -> list[tuple[int, int]]:
    if total == 0:
        return []
    chunk = max(1, (total + n_workers - 1) // n_workers)
    bounds = []
    start = 0
    while start < total:
        end = min(total, start + chunk)
        bounds.append((start, end))
        start = end
    return bounds


@dataclass
class ParallelExhaustiveReport(ExhaustiveReport):
    n_workers: int = 1


def check_transform_exhaustive_parallel(
    target_spec: str,
    n_qubits: int,
    gate_set: list[str],
    max_length: int,
    tol: float = 1e-7,
    n_workers: int | None = None,
    factory_args: tuple = (),
    factory_kwargs: dict | None = None,
    stop_at_first_length_with_failure: bool = True,
) -> ParallelExhaustiveReport:
    """Same guarantee as exhaustive.check_transform_exhaustive (every circuit
    up to max_length is checked, shortest length first), but splits each
    length's search across a process pool.

    `target_spec` is a '<module>:<callable>' string (NOT a live callable --
    it must be importable fresh in each worker process; this is also what
    lets this work for factory functions like `module:make_transform` by
    passing `factory_args`/`factory_kwargs`, since closures generally can't
    be pickled across a process boundary but a spec string always can).
    """
    factory_kwargs = factory_kwargs or {}
    n_workers = n_workers or os.cpu_count() or 1
    choices = _choices_for(n_qubits, gate_set)
    base = len(choices)

    n_checked = 0
    n_checked_by_length: dict[int, int] = {}
    failures: list[Failure] = []
    smallest_failing_length: int | None = None

    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        for length in range(0, max_length + 1):
            total = base ** length
            bounds = _split_range(total, n_workers)
            futures = [
                pool.submit(
                    _worker_check_range,
                    target_spec, factory_args, factory_kwargs,
                    n_qubits, gate_set, length, start, end, tol,
                )
                for start, end in bounds
            ]
            length_failures = []
            failing_indices = [idx_fid for f in futures for idx_fid in f.result()]
            if failing_indices:
                # recompute the actual transformed output for the (usually
                # few) failures only, in this process -- avoids sending
                # QuantumCircuit objects back through the pool for every one
                # of the (many) passing circuits.
                transform = _load_target(target_spec, factory_args, factory_kwargs)
                for idx, fid in failing_indices:
                    combo = _nth_combo(choices, length, idx)
                    qc = _circuit_from_combo(n_qubits, combo)
                    out = transform(qc)
                    length_failures.append(Failure(original=qc, transformed=out, fidelity=fid))

            n_checked += total
            n_checked_by_length[length] = total
            if length_failures:
                for fl in length_failures:
                    fl.minimized = fl.original
                    fl.minimized_fidelity = fl.fidelity
                failures.extend(length_failures)
                smallest_failing_length = length
                if stop_at_first_length_with_failure:
                    break

    return ParallelExhaustiveReport(
        n_checked=n_checked,
        n_failed=len(failures),
        failures=failures,
        smallest_failing_length=smallest_failing_length,
        n_checked_by_length=n_checked_by_length,
        n_workers=n_workers,
    )

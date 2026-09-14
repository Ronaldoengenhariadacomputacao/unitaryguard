# UnitaryGuard

Property-based semantic-equivalence checking for quantum circuit transforms.

Points it at any `QuantumCircuit -> QuantumCircuit` function (a Qiskit pass,
a `PassManager`, a compression step, anything), samples random circuits, and
checks one invariant that almost every transform is supposed to preserve but
almost no test suite checks directly: **does the output implement the same
unitary as the input?** When it finds a circuit where that's not true, it
automatically shrinks it to a small reproduction — the same thing you'd do
by hand while debugging, but for free.

## Why

This project exists because that exact manual process — sample circuits,
compare `Operator()` before/after a transform, shrink the failing case by
hand — found two real, silent correctness bugs in widely-used Clifford+T
tooling:

- Qiskit core's `OptimizeCliffordT` pass (merged fix:
  [Qiskit/qiskit#16729](https://github.com/Qiskit/qiskit/pull/16729)).
- `rsgridsynth`'s `NormalForm` syllable-merge formula (open PR:
  [qiskit-community/rsgridsynth#49](https://github.com/qiskit-community/rsgridsynth/pull/49)).

Both bugs had the same shape: the transform's gate-count/T-count output was
correct, while the circuit's actual unitary silently changed. Neither was
caught by T-count/gate-count/depth checks — only an explicit unitary
comparison catches this class of bug. UnitaryGuard is that check, packaged
so it doesn't have to be reinvented by hand each time. `tests/test_known_bugs.py`
reproduces both bug *shapes* as regression tests and proves the tool catches
them and shrinks each to a small reproduction.

See `DESIGN.md` for the full design rationale and current scope/limitations.

## Install

```bash
pip install -e .
```

## Use as a library

```python
from unitaryguard import CheckConfig, check_transform

def my_pass(qc):
    ...  # your QuantumCircuit -> QuantumCircuit transform
    return transformed_qc

cfg = CheckConfig(
    n_qubits=3,
    gate_set=["h", "s", "sdg", "t", "tdg", "cx"],
    n_samples=500,
    seed=42,
)
report = check_transform(my_pass, cfg)
print(report.summary())
assert report.ok
```

## Use from the CLI

```bash
unitaryguard check mymodule:my_pass --qubits 3 --gates h,s,sdg,t,tdg,cx --samples 500 --seed 42
```

`my_pass` must be an importable `QuantumCircuit -> QuantumCircuit` callable.

### Exhaustive mode (deterministic, targets gate-order/inversion bugs)

```bash
unitaryguard exhaustive mymodule:my_pass --qubits 1 --gates h,s,sdg,t,tdg --max-length 6
```

Tests *every* discrete circuit up to `--max-length` gates (no continuous
parameters), shortest first. A gate-order/conjugation-formula transcription
bug (like both bugs this tool was built to generalize from) is
deterministic, not statistical -- exhaustive search guarantees finding the
smallest counterexample the vocabulary can express, with no separate
shrinking step needed.

Add `--workers N` to split each length's search across a process pool.
Defaults to 1 (sequential) unless you pass it explicitly.

**Measured, not assumed** -- on a 20-logical-core machine (Xeon E5-2666,
figures below are *specific to that machine*, not a universal constant):
parallelism only pays off once the workload is large enough to amortize
each worker's one-time Qiskit import cost (~1.4s/process). On a small
search (1555 circuits, max length 4), throughput peaked at `--workers 4`
(1.6x) and *degraded* past that. On a larger search (9331 circuits, max
length 5), `--workers 8` gave a real 3.3x speedup, plateauing (not
improving further) from 12 workers up to the machine's full 20.

The **principle** generalizes across hardware, the **numbers** don't --
if you're on a 4-core laptop, "8-12 workers" is meaningless (there's no 12
cores to use, and oversubscribing usually hurts, not helps). Re-run the
same small-vs-large comparison on your own machine before picking a
`--workers` value for anything you'll run repeatedly; as a starting point,
try `--workers <your core count>` and only go lower if you see the same
kind of degradation documented above for a small search.

## Current scope (v0.1)

- Transforms that preserve qubit count (most gate-level optimization/
  synthesis passes). Ancilla-widening transforms are not yet supported —
  see `DESIGN.md`.
- Unitary-only transforms — no mid-circuit measurement / classical control
  yet.

## Status

Early prototype, private (not yet published to PyPI).

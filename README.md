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
**Measured, not assumed**: parallelism only pays off once the workload is
large enough to amortize each worker's one-time Qiskit import cost
(~1.4s/process on this machine). On a small search (1555 circuits, max
length 4) against a real Qiskit synthesis pass, throughput peaked at 4
workers (1.6x) and *degraded* past that. On a larger search (9331 circuits,
max length 5), 8-12 workers gave a real 3.3x speedup, plateauing (not
improving further) from 12 to 20 workers. Rule of thumb: don't parallelize a
small `--max-length`; for a large one, start around 8-12 workers rather than
assuming "more is better."

## Current scope (v0.1)

- Transforms that preserve qubit count (most gate-level optimization/
  synthesis passes). Ancilla-widening transforms are not yet supported —
  see `DESIGN.md`.
- Unitary-only transforms — no mid-circuit measurement / classical control
  yet.

## Status

Early prototype, private (not yet published to PyPI).

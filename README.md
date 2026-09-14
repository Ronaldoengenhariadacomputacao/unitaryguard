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

## Current scope (v0.1)

- Transforms that preserve qubit count (most gate-level optimization/
  synthesis passes). Ancilla-widening transforms are not yet supported —
  see `DESIGN.md`.
- Unitary-only transforms — no mid-circuit measurement / classical control
  yet.

## Status

Early prototype, private (not yet published to PyPI).

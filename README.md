# UnitaryGuard

Property-based semantic-equivalence checking for quantum circuit transforms.
**Framework-independent since v0.2** — no Qiskit or other SDK dependency
anywhere (see "Why v0.2 has no Qiskit dependency" below).

Points it at any `Circuit -> Circuit` function (a transform wrapping an
external engine, a compression step, anything), samples random circuits, and
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

See `DESIGN.md` for the full design rationale and current scope/limitations,
and `CASE_STUDIES.md` for every method used to find a real bug so far, each
with a runnable example (random sampling, exhaustive search, cross-validating
the tool's own oracle, and writing a native-language binding to reach code a
wrapper doesn't exercise).

## Why v0.2 has no Qiskit dependency

v0.1 checked equivalence via `qiskit.quantum_info.Operator`, which works
fine when the transform under test is unrelated to Qiskit -- but breaks
down exactly when the transform IS a real Qiskit pass: the code being
tested and the code judging it become the same library, so a shared bug in
Qiskit's own gate-matrix definitions can never be caught, structurally, no
matter how many circuits you sample. v0.2 replaces the Qiskit-based
`QuantumCircuit` representation with a tiny native `Circuit`/`Gate` pair and
a gate-matrix table (`unitaryguard/matrices.py`) derived directly from each
gate's standard mathematical definition, built with `numpy` alone. See
`DESIGN.md` ("v0.2: dropped the Qiskit dependency entirely") for the full
writeup. The real-world case that prompted this: validating AutoQ EngineBR,
an external, from-scratch transpiler -- see that project's own docs for a
worked adapter example (not included in this repo, since it's specific to
that engine's own wire protocol).

## Install

```bash
pip install -e .
```

## Use as a library

```python
from unitaryguard import Circuit, Gate, CheckConfig, check_transform

def my_pass(circ: Circuit) -> Circuit:
    ...  # your Circuit -> Circuit transform (e.g. call an external engine)
    return transformed_circ

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

`Circuit(n_qubits, gates)` and `Gate(kind, qubits, params=())` are plain
dataclasses -- `Gate("cx", (0, 1))`, `Gate("rz", (0,), (1.23,))`. See
`unitaryguard/matrices.py::GATE_TABLE` for the full supported vocabulary.

## Use from the CLI

```bash
unitaryguard check mymodule:my_pass --qubits 3 --gates h,s,sdg,t,tdg,cx --samples 500 --seed 42
```

`my_pass` must be an importable `Circuit -> Circuit` callable.

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

## Current scope (v0.2)

- Transforms that preserve qubit count (most gate-level optimization/
  synthesis passes). Ancilla-widening transforms are not yet supported —
  see `DESIGN.md`.
- Unitary-only transforms — no mid-circuit measurement / classical control
  yet.
- Gate vocabulary: `h,x,y,z,s,sdg,t,tdg,sx` (0-param), `rz,ry,rx,p` (1-param),
  `u` (3-param), `cx,cz,swap` (0-param, 2-qubit), `crz,crx,cry,cp,rzz,rxx,ryy`
  (1-param, 2-qubit) — see `unitaryguard/matrices.py::GATE_TABLE`. No
  multi-parameter 2-qubit gates yet (`cu`, `xx_plus_yy`, ...) and no generic
  arbitrary-unitary sampling (`UnitaryGate`-equivalent) — extending either
  is a matter of adding matrix functions + table entries to `matrices.py`.
- No longer wraps real Qiskit `PassManager`/pass objects directly (that
  capability was removed in v0.2 along with the Qiskit dependency — see
  "Why v0.2 has no Qiskit dependency" above).

## Status

Early prototype, private (not yet published to PyPI). v0.2 (2026-09-21):
dropped Qiskit dependency entirely, see DESIGN.md.

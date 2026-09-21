# UnitaryGuard — design

## What this is

A small, dependency-light tool that checks one property of any quantum
circuit transform (a Qiskit `TransformationPass`, a `PassManager`, or a plain
`QuantumCircuit -> QuantumCircuit` function): **does it preserve the unitary
the circuit implements?**

It generalizes the exact manual process that found two real, silent
correctness bugs in the Qiskit ecosystem — one in Qiskit core's
`OptimizeCliffordT` pass, one in `rsgridsynth`'s `NormalForm` syllable-merge
formula (`rsgridsynth` is used internally by Qiskit's `RossSelingerSynthesis`
plugin). Both bugs had the same shape: the transform changed the circuit's
*gate count/T-count* metrics correctly, while silently changing the
circuit's *unitary*. Neither was caught by that project's existing tests,
because those tests checked gate/T-counts, not semantic equivalence.

## Why this needs to exist as a separate tool, not just "write more tests"

Every project that has this problem (Qiskit included) already has the
primitive it needs (`Operator`, `Operator.equiv()`, `process_fidelity`) — the
missing piece was never the primitive, it was the *habit* and the
*infrastructure* to apply it systematically: sample many circuits, run them
through a transform, check equivalence, and when one fails, automatically
reduce it to the smallest circuit that still reproduces the failure (what we
did by hand to find `SHTT` as the minimal case for the `rsgridsynth` bug).
That reduction step is the part that turns "found the bug once, painfully"
into "any project can run this in CI and get a minimal reproduction for
free."

## Core idea

```
sample N random circuits (within a gate vocabulary and qubit count)
  -> run each through transform(circuit)
  -> compare Operator(circuit) vs Operator(transform(circuit))
  -> if not equivalent (within tolerance, up to global phase):
       shrink the failing circuit to a locally-minimal reproduction
       report it
```

This mirrors property-based testing (Hypothesis, QuickCheck): "generate,
check an invariant, shrink on failure" — specialized for one invariant
(unitary equivalence) that matters for *any* quantum circuit transform,
because it is the one invariant a transform is essentially never allowed to
break, yet the one existing test suites check least directly (they check
gate counts, basis membership, depth — all necessary, none sufficient).

## Scope of this prototype (v0.1)

In scope:
- Random circuit sampling over a configurable gate vocabulary and qubit
  count (`n_qubits` fixed across a run — the transform must not change
  circuit width for this check to apply directly).
- Equivalence check via `qiskit.quantum_info.Operator` +
  `process_fidelity` (phase-invariant) — configurable tolerance.
- Shrinking: iterative fixed-point reduction (drop one gate at a time,
  re-check, keep the drop if the failure still reproduces) — same principle
  as delta-debugging, simple enough to have no dependencies.
- A `Report` object (pass/fail counts, minimized failing circuit + its
  transformed output, fidelity value) and a human-readable printout.
- A CLI (`unitaryguard check <module>:<callable> ...`) so it can be pointed
  at any importable transform without writing a Python harness each time.
- Self-tests that prove the tool actually catches both known bug *shapes*
  (a deliberately reintroduced `S`/`Sdg`-swap pass mirroring the Qiskit bug,
  and a deliberately reintroduced `H*S*H`-vs-`S*H*S` normal-form merge
  mirroring the `rsgridsynth` bug) and shrinks each to a small
  reproduction — this is the tool's own regression suite, and its strongest
  argument for trustworthiness.

Explicitly out of scope for v0.1 (real limitations, not hidden):
- Transforms that change qubit count (ancilla-based synthesis, e.g. MCX
  V-chains) — `Operator` comparison needs equal dimensions; supporting this
  needs an explicit "assume ancillas start at |0>" embedding, not built yet.
- Transforms that change classical-bit behavior (mid-circuit measurement,
  `if_else`/dynamic circuits) — `Operator` doesn't apply directly; needs a
  different equivalence notion (e.g. per-branch check), not built yet.
- Global, non-local shrinking (current shrinker only drops gates from the
  ORIGINAL failing circuit; it doesn't also try to shrink qubit count or
  gate parameters). Good enough to reproduce both known bugs to a near-
  minimal case; a smarter shrinker is a natural v0.2.
- Any integration with Qiskit's own CI — this is a standalone tool first;
  offering it *to* Qiskit (as a callable check or a contributed test) is a
  later step, once it has a track record of catching real things beyond
  this session's two bugs.

## v0.2: dropped the Qiskit dependency entirely

Motivating case (2026-09-21): pointing this tool at an EXTERNAL engine (a
from-scratch transpiler written in a different language, "AutoQ EngineBR")
raised a real question -- if the equivalence oracle (`Operator`/
`process_fidelity`) is Qiskit's own, and the engine under test's output gets
serialized back into a `QuantumCircuit` before being checked, then any
project whose transform IS itself a real Qiskit pass (as `examples/
real_qiskit_passes.py` and part of `demo_pass.py` did in v0.1) creates a
strict circularity: the code being tested and the code judging it are the
same library. A shared bug in Qiskit's own gate-matrix definitions can
never be caught that way -- not "improbable", structurally impossible.

This is a stronger version of the same concern the two founding bugs
(`OptimizeCliffordT`, `rsgridsynth`) already demonstrate the value of
avoiding: those were caught precisely because `Operator()`'s gate-matrix
definitions are simpler, more scrutinized, and did NOT share the specific
bug the transpiler passes had. But relying on that being true in general,
forever, for every future transform someone points this tool at (including
Qiskit's own passes) is exactly the kind of assumption a *validation* tool
should not need to make about its own oracle.

**Fix**: `core.py` now represents circuits with a tiny native `Circuit`/
`Gate` dataclass pair (not `QuantumCircuit`), and `matrices.py` implements
every gate's matrix directly from its standard mathematical definition
(same convention as the wider literature, e.g. Nielsen & Chuang -- not
derived from Qiskit's source), built with numpy alone. `equivalent()`
computes process fidelity `|Tr(Ua^dagger . Ub)|^2 / d^2` directly from
these matrices -- the same quantity `process_fidelity` computed for this
case, so `tol` thresholds are unchanged from v0.1.

**Consequence, deliberately accepted**: this tool can no longer wrap a real
Qiskit `PassManager`/pass directly as a bare `Circuit -> Circuit` callable
(that would need a `QuantumCircuit <-> Circuit` conversion layer, which is
exactly the reintroduced coupling being removed). `examples/
real_qiskit_passes.py` and `examples/ross_selinger_check.py` were removed
for this reason. Testing a real Qiskit pass again in the future would need
an explicit adapter written by the caller, kept outside this package, not
a built-in capability -- consistent with the actual real-world use case
this tool now serves (validating external engines), not the original one
(validating Qiskit-internal transforms with Qiskit's own oracle).

`numpy` replaces `qiskit>=1.0` as the sole runtime dependency.

## Name

`UnitaryGuard` (package: `unitaryguard`). Deliberately generic, since the
whole point is that it is meant to be picked up by any project in the
Qiskit ecosystem (Qiskit itself included), not tied to any one specific
project's naming.

## Relationship to the two bugs

This tool is the direct, reusable output of the methodology used to find:

- Qiskit core's `OptimizeCliffordT` correctness bug (merged fix:
  [Qiskit/qiskit#16729](https://github.com/Qiskit/qiskit/pull/16729)).
- `rsgridsynth`'s `NormalForm` syllable-merge bug (open PR:
  [qiskit-community/rsgridsynth#49](https://github.com/qiskit-community/rsgridsynth/pull/49)).

It is developed as a separate, standalone project so it can be published and
improved independently, for use against any Qiskit-ecosystem transform.

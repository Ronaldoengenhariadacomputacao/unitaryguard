# Case studies — methods that found real bugs, with runnable examples

This document catalogs every distinct **method** UnitaryGuard (or a tool
built directly on top of it) has used to find a real, confirmed bug, with
a concrete, runnable example for each. Unlike `README.md`/`DESIGN.md`
(which describe the tool's design), this file is organized by **method**,
because the same underlying invariant check (unitary equivalence) can be
reached through several different access strategies, and which one works
depends entirely on where the bug actually lives in the target's call
graph -- a negative result through one method is NOT evidence of
correctness for a method that was never tried (see method 4 below for a
concrete case where this distinction mattered).

## Method 1: random sampling against a `Circuit -> Circuit` transform

The core method (`unitaryguard.check_transform`). Sample random circuits,
run each through the transform, compare unitaries, shrink failures.

**Example: catching Qiskit's real `OptimizeCliffordT` bug (2026-09-21)**

Qiskit 2.5.1 has a confirmed, real unitarity bug in `OptimizeCliffordT`
(merged fix: [Qiskit/qiskit#16729](https://github.com/Qiskit/qiskit/pull/16729),
included starting 2.5.2). `autoq_qec/qec_estimator.py`'s
`_transpile_clifford_t(circuit, validate=False)` exercises the buggy path
directly (bypassing its own protective guard):

```python
from qiskit import QuantumCircuit
from unitaryguard import Circuit, Gate, CheckConfig, check_transform
from autoq_qec.qec_estimator import _transpile_clifford_t

def transform_unguarded(circ: Circuit) -> Circuit:
    qc = QuantumCircuit(circ.n_qubits)
    for g in circ.gates:
        getattr(qc, g.kind)(*g.params, *g.qubits) if g.params else getattr(qc, g.kind)(*g.qubits)
    out = _transpile_clifford_t(qc, validate=False)
    return _from_qiskit(out, circ.n_qubits)  # see full adapter in the test scripts

cfg = CheckConfig(n_qubits=1, gate_set=["h","s","sdg","t","tdg","x","rz"],
                   n_samples=300, min_gates=2, max_gates=10, seed=7)
report = check_transform(transform_unguarded, cfg)
```

**Result:** 77/300 circuits failed (25.7%), shrunk to minimal 2-3 gate
reproductions (e.g. `T, T, Rz(5.244)`, fidelity 0.144). Running the SAME
300 circuits through `_transpile_clifford_t(circ, validate=True)` (the
guarded path `autoq_qec` actually uses in production): **0 failures**,
confirming the existing guard genuinely neutralizes the bug, not just
coincidentally.

## Method 2: exhaustive (deterministic) search

`unitaryguard.check_transform_exhaustive` -- tests every discrete circuit
up to a bounded length, guaranteeing the smallest possible counterexample
with no shrinking step needed. Best for gate-order/conjugation-formula
bugs, which are deterministic (fail 100% of the time once the trigger
pattern is reached), not statistical.

**Example:** `tests/test_exhaustive.py::test_exhaustive_finds_sht_bug_deterministically_at_length_4`
finds the rsgridsynth-shaped SHT-merge bug (via the `toy_normal_form.py`
port) at exactly length 4 (`"SHTT"`), matching the real minimal case found
by hand during the original investigation.

## Method 3: cross-validating the tool's OWN oracle against independent implementations

Since v0.2 removed Qiskit as the equivalence oracle (`unitaryguard/matrices.py`
is now hand-derived), the table itself needed independent validation --
the same circularity concern the whole v0.2 redesign exists to avoid,
just pointed inward. Two independent oracles were used:

**3a. [Ket](https://quantumket.org)** (`ket-lang` on PyPI, Rust-based
runtime `libket`, no relation to Qiskit or this project):
`tests/test_cross_validate_ket.py`. 1520 random circuits (3/5/6 qubits,
2 seeds), compared `unitaryguard.circuit_unitary()` against Ket's real
`ket.dump()` statevector. **Result: 0 divergences** (positive result --
strengthens confidence in `matrices.py`).

**3b. Qiskit's `Operator()`** (`tests/test_cross_validate_qiskit.py`,
purely as a third oracle, not a reintroduction of the removed dependency):
same idea, 500 circuits, verified independently on Qiskit 2.5.1 and 2.5.2.

**Result: a real bug was found in the FIRST version of this test's own
adapter** (not in `matrices.py`) -- 9/9 isolated single-gate cases
diverged, one random circuit hit fidelity 0.718638. Root cause: Qiskit is
little-endian (qubit 0 = least significant bit); `unitaryguard`'s own
convention (and Ket's, independently) is the opposite. [Qiskit's own docs
say](https://quantum.cloud.ibm.com/docs/en/guides/bit-ordering) "you might
expect the leftmost bit to be bit 0, whereas it usually represents bit
n-1" -- i.e. Qiskit's own documentation names *leftmost-bit-is-bit-0*
(unitaryguard's/Ket's convention) as the *usual* expectation. Fixed by
reversing qubit indices when building the Qiskit-side circuit; confirmed
with a minimal trace (2 qubits, `X` on qubit 0 alone: unitaryguard lands
on state index 2, Qiskit's `qc.x(0)` lands on index 1, `qc.x(1)` lands on
index 2 -- matching). This is exactly the bug SHAPE UnitaryGuard exists to
catch (silent, deterministic, invisible to any check that isn't a direct
unitary comparison) -- found this time at an integration boundary, by the
tool's own cross-validation methodology, not by a user pointing it at an
external transform.

**Second occurrence, same shape (2026-09-22):** expanding the gate
vocabulary (adding `iswap`, `dcx`, `ecr`, `cu`, `rzx`, `xx_plus_yy`,
`xx_minus_yy`) re-ran into the identical bug class, one level deeper.
Qiskit's whole-circuit little-endian convention was already handled (index
reversal), but for 2-qubit gates whose 4x4 matrix is *not* symmetric under
swapping q0<->q1 (`dcx`, `ecr`, `rzx`, `xx_plus_yy`, `xx_minus_yy`),
reversing only the qubit *index* is not enough -- the argument *order*
passed to Qiskit must also swap, because the gate's local matrix
definition is itself part of what "little-endian" flips. Found the same
way as before: 500-circuit cross-validation caught a real disagreement
(fidelity 0.712 on a random circuit), confirmed at the raw-4x4-matrix
level (`unitaryguard.matrices._xx_plus_yy` matched `XXPlusYYGate.to_matrix()`
exactly -- ruling out `matrices.py`), then bisected gate-by-gate and
qubit-order by qubit-order until the exact swap rule was identified.
Symmetric gates (`cz`, `swap`, `iswap`, `rzz`/`rxx`/`ryy`) and controlled
gates (`cx`, `cy`, `ch`, `csx`, `cu`, `crz`/`crx`/`cry`/`cp`) never needed
this extra swap -- only the non-controlled, asymmetric-under-exchange
gates did. Fixed in the test adapter only (`tests/test_cross_validate_qiskit.py`),
`matrices.py` itself was correct throughout.

**Third occurrence, negative result recorded on purpose (2026-09-22):**
extending the vocabulary again to the 3-qubit gates `ccx`/`cswap`/`ccz`/`rccx`
(the ones AutoQ EngineBR actually emits, as opposed to the 2Q gates above
which it only ever consumes as input) raised the same question one qubit
wider: does plain index reversal still suffice, or does *this* batch also
need the argument-order swap? Checked the same way, before writing the
matrices at all -- derived each gate's matrix from Qiskit's real
`.to_matrix()` output converted via 3-bit index bit-reversal (not the docs,
not memory), cross-checked `ccx`/`cswap`/`ccz` against an independent
first-principles derivation (exact match, diff 0.0), then verified the
resulting `matrices.py` entries against `Operator()` with plain index
reversal and NO argument swap -- all 4 matched exactly (max diff 0.0),
confirmed by ALSO trying the swapped-argument order and observing it fails
(diff 1.0) for the 3 asymmetric ones (`ccx`, `cswap`, `rccx`; `ccz` is
symmetric either way, matching in both orderings since it's diagonal).
This is a genuine negative result worth keeping precisely because the
prior 2Q investigation could have suggested "asymmetric gates always need
the swap" as a rule -- they don't; whether index-reversal alone suffices
depends on the specific gate's structure, not on symmetry-under-exchange
alone, so each new gate batch still needs its own check, not a shortcut
from the last one's conclusion.

## Method 4: writing a minimal native-language binding to reach code the wrapper doesn't exercise

The most important methodological lesson from this session: **a negative
result through a high-level wrapper does not clear the underlying
library** if the wrapper doesn't happen to exercise the specific code path
in question.

**The case:** [rsgridsynth PR #49](https://github.com/qiskit-community/rsgridsynth/pull/49)
("Fix wrong Clifford conjugation formula in SHT syllable merge", still
open/unmerged as of 2026-09-21) is a real, confirmed bug in
`src/normal_form.rs::NormalForm::append_gate` (the `Syllable::SHT` merge
branch uses `H*S*H` instead of the correct `S*H*S`).

**Attempt 1 (negative, and initially misleading):** pointed
`unitaryguard.check_transform` at the bug through Qiskit's own integration
(`transpile(circuit, unitary_synthesis_method="gridsynth", ...)`, which
uses `rsgridsynth` internally): 400 random circuits (`h`+`rz` gate set,
various tolerances), **0 failures**. This does NOT mean the bug doesn't
exist -- Qiskit's plugin apparently synthesizes each `rz` block
independently and never reaches the specific multi-rotation
`NormalForm::append_gate` compression path the PR fixes.

**Confirming the bug is real, at the Rust source level, before writing any
new code:** cloned the PR's own fork
(`Ronaldoengenhariadacomputacao/rsgridsynth`, branch
`fix/sht-merge-shs-not-hsh`), copied *only* the PR's new regression test
file (`tests/normal_form_sht_merge.rs`) onto the unfixed `main` branch, and
ran the crate's own test suite:

```bash
git clone https://github.com/Ronaldoengenhariadacomputacao/rsgridsynth.git
cd rsgridsynth
git checkout fix/sht-merge-shs-not-hsh -- tests/normal_form_sht_merge.rs
cargo test --test normal_form_sht_merge
```

**Result:** 2/3 new tests FAIL on `main`:
`NormalForm::from_gates("SHTT").to_gates() = "SHXSSSW"` (max diff =
1.3065629648763768) -- confirmed at the Rust source level, before any
Python tooling was involved. Same tests: 16/16 pass on the fix branch.

**Attempt 2 (positive -- reaching the actual bug):** since no Python
binding for `rsgridsynth` exists, wrote one -- a small, separate crate
(`rsgridsynth_pybind`, own repo, depends on `rsgridsynth` as a **path
dependency**, never modifies it) exposing `NormalForm::from_gates(...)
.to_gates()` directly via PyO3:

```python
import rsgridsynth_pybind as rg
from unitaryguard import Circuit, Gate, CheckConfig, check_transform

def transform_real_rust_normal_form(circ: Circuit) -> Circuit:
    s = "".join({"h":"H","s":"S","t":"T","x":"X"}[g.kind] for g in circ.gates)
    out = rg.normal_form_compress(s)  # calls the REAL Rust NormalForm
    return gate_string_to_circuit(circ.n_qubits, out)

cfg = CheckConfig(n_qubits=1, gate_set=["h","s","t"], n_samples=300,
                   min_gates=2, max_gates=8, seed=3)
report = check_transform(transform_real_rust_normal_form, cfg, shrink=True)
```

**Result:** 13/300 circuits failed, ALL at fidelity exactly `0.000000`
(total divergence, not numerical noise). Automatic shrinking found several
independent minimal 4-gate reproductions, including `s, h, t, t` --
shorter than the PR's own headline example (`"SHTT"`, also 4 gates, a
different combination) -- found entirely by the tool's generic
sample-and-shrink loop, with no prior knowledge of where the trigger
pattern was.

See `rsgridsynth_pybind/README.md` (sibling directory,
`C:\Users\CentralS\Documents\projeto transpileZig\rsgridsynth_pybind`) for
build instructions.

## Method 5: cross-validating a target against ITSELF (different backends, same tool)

No external oracle needed -- run the same circuit through the same tool's
different internal implementations and compare. Cheapest method to try
(no new dependency, no binding), and tests a surface nobody normally
checks (agreement between a simulator's own backend options).

**Example: Ket's `dense` vs `sparse` vs `dense gpu` simulators (2026-09-21)**

```python
import ket
def run_ket(n_qubits, gates, simulator):
    p = ket.Process(simulator=simulator)
    q = p.alloc(n_qubits)
    # ... apply gates ...
    return ket.dump(q)  # compare across simulator= values for the SAME circuit
```

**First result (misleading at first glance):** with a tight tolerance
(`1 - 1e-6`, the same used for the Ket/Qiskit oracle cross-validation),
23/900 circuit x backend-pair comparisons "failed" -- but EVERY one had
infidelity within `1e-6` of the threshold (max `1.26e-6`), never higher.
**Investigated before concluding anything is broken:** Ket's `dump()`
amplitudes match `float32` rounding exactly (e.g. `1/sqrt(2)` comes back
as `0.7071067690849304`, matching float32's ~7-digit precision, not
float64's ~15-16) -- so ~`1e-6`-level cross-backend noise is the expected
floor for that precision, not a correctness bug. Re-running with
`tol=1e-4` (calibrated for float32): **0/1800 divergences.**

**Why this is worth recording as its own entry, not just a footnote:**
this is the one case in this document where the naive first result would
have been a **false positive** -- claiming a bug that wasn't there. The
discipline that avoided it was the same one used throughout this document:
verify the actual numeric magnitude of a "failure" before reporting it,
not just whether it crossed an arbitrarily-chosen threshold.

## Summary table

| Method | Target | Result |
|---|---|---|
| 1. Random sampling | `autoq_qec._transpile_clifford_t(validate=False)` | 77/300 failed, guard confirmed working |
| 2. Exhaustive search | rsgridsynth-shaped bug (toy port) | Found deterministically at length 4 |
| 3a. Cross-validate oracle | Ket (independent simulator) | 0/1520 divergences (matrices.py confirmed) |
| 3b. Cross-validate oracle | Qiskit `Operator()` | Found a real integration bug (endianness) in the TEST adapter itself |
| 4. Native-language binding | rsgridsynth's real `NormalForm` (PR #49) | 13/300 failed, confirms PR #49 automatically |
| 5. Self cross-validation (different backends) | Ket `dense`/`sparse`/`dense gpu` | 0/1800 real divergences (initial "failures" were float32 noise, not a bug -- see writeup) |

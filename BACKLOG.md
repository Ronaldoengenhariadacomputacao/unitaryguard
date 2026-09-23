# Backlog — future work, not started yet

## rsgridsynth PR #49 — confirmed via real Rust binding (2026-09-21)

**Status:** confirmed real at the Rust source level, not just via the toy
Python port. See `CASE_STUDIES.md` ("Method 4") for the full writeup.

`cargo test` against the PR's own new regression tests, applied to the
unfixed `main` branch: 2/3 fail (`NormalForm::from_gates("SHTT")` gives
`"SHXSSSW"`, max diff 1.31). A new sibling crate, `rsgridsynth_pybind`
(`../rsgridsynth_pybind`, path-dependency on `rsgridsynth`, never modifies
it), exposes `NormalForm::from_gates(...).to_gates()` to Python via PyO3
specifically because Qiskit's own `gridsynth` plugin does NOT exercise
this code path (verified: 400 circuits through the Qiskit wrapper, 0
failures -- a negative result that does NOT clear the bug). Pointing
`check_transform` at the real binding: 13/300 circuits fail, all at
fidelity 0.0, minimal reproductions as short as 4 gates (`s,h,t,t`).

**Next step:** none required from UnitaryGuard's side -- this is now solid
supporting evidence for PR #49 itself (still open/unmerged upstream).
Worth linking this case study from the PR if/when following up on review.

## Extend `matrices.py` gate vocabulary (v0.2 follow-up)

**Status:** DONE for named gates (2026-09-21/22, commits `dbb83e4`,
`3410875`, `82ca96f`). Only the generic arbitrary-unitary case remains.

v0.2 (2026-09-21, see DESIGN.md) replaced the Qiskit-based `Operator()`
equivalence check with a native gate-matrix table. `matrices.py` now
covers: 0/1-parameter 1-qubit gates (incl. `sxdg`), `u`/`r` (multi-param
1-qubit), 0/1-parameter 2-qubit gates (incl. `iswap`, `dcx`, `ecr`, `cy`,
`ch`, `csx`, `rzx`), multi-parameter 2-qubit gates (`cu`, `xx_plus_yy`,
`xx_minus_yy`), and 3-qubit gates (`ccx`, `cswap`, `ccz`, `rccx`). Every
entry was cross-validated against two independent oracles (Ket, Qiskit's
`Operator()`) before being trusted — see `CASE_STUDIES.md` (Method 3 and
its "second"/"third occurrence" notes) for the two qubit-ordering bugs
that surfaced and were fixed during this work (in the *test adapters*,
never in `matrices.py` itself).

Still not covered:
- **Generic arbitrary-unitary gates** (equivalent to Qiskit's
  `UnitaryGate`). Genuinely new code path needed — these aren't a named
  method with a fixed matrix, so `_random_gate` would need a separate
  branch that samples a random unitary of the right dimension (e.g. via
  the QR-decomposition-of-a-random-complex-matrix method, a well-known
  numpy-only technique — no SDK needed) and `matrices.py`/`core.py` would
  need to carry the sampled matrix alongside the gate (params can't hold an
  arbitrary-size matrix in the current `tuple[float,...]` shape).

## Qiskit test-suite bug: broken `assertTrue` in `test_optimize_clifford_t.py`

**Status:** found, confirmed, NOT yet fixed/submitted. Low priority (see
"why not urgent" below) -- revisit when there's room for a small,
uncontroversial contribution.

**What:** `test/python/transpiler/test_optimize_clifford_t.py`, line 43,
inside `test_solovay_kitaev_rx` (parametrized over 10 angles via
`np.linspace(0, 2*pi, 10)`):

```python
self.assertTrue(Operator(transpiled), Operator(optimized))
```

`unittest.TestCase.assertTrue(expr, msg)` treats the second argument as the
failure message, not a value to compare against. `Operator` defines neither
`__bool__` nor `__len__`, so `bool(any Operator instance)` is always `True`
by default Python object truthiness. **This assertion can never fail,
regardless of what `OptimizeCliffordT` actually does** -- confirmed
synthetically (a minimal `assertTrue(1==2, 1==1)` repro correctly fails,
proving the semantics) and against the real repo.

**Fix:** one line --
```python
self.assertTrue(Operator(transpiled).equiv(Operator(optimized)))
```
(matches the correct pattern already used elsewhere in the same codebase,
e.g. `test_clifford_t_passmanager.py` line 218.)

**History:** present since the commit that introduced the entire file,
`4782b9ce` (PR #14433, "CliffordT optimization", merged 2025-05-28) --
confirmed by fetching that exact revision of the file from GitHub. Never
touched since; still present on `main` as of 2026-09-13.

**Why not urgent (re-assessed after checking for overlap):** the actual
real bug this test class was meant to catch (the `S`/`Sdg` swap in
`OptimizeCliffordT`, PR #16729) is already covered by a different,
correctly-written regression test:
`test_clifford_t_passmanager.py::test_clifford_t_transpile_is_unitarily_equivalent`
(added by the same PR that fixed the bug). That test exercises the full
`generate_preset_clifford_t_pass_manager` pipeline at all 4 optimization
levels, on a hand-picked 2-qubit circuit -- the actual known regression is
closed.

The broken test covers a genuinely different (adjacent, not identical) code
path: bare `SolovayKitaev()` + `OptimizeCliffordT()` composition (not the
full preset pass manager), swept across 10 different `RX` angles, 1-qubit
only. That specific combination currently has **zero** active correctness
enforcement -- not a known active vulnerability, just an unguarded path.
Worth fixing as low-risk test hygiene, not as an urgent correctness fix.

**Next step when picked back up:** prepare a 1-line PR against
`Qiskit/qiskit`, same format as the two already-submitted findings (PR
#16729, merged; PR #49 on `qiskit-community/rsgridsynth`, pending review) --
minimal diff, explain the `assertTrue(expr, msg)` misuse, note it was found
independently while auditing Qiskit's own tests with UnitaryGuard-adjacent
methodology (manual code reading here, not the tool itself -- this was
found by reading the real test file, not by running `unitaryguard` against
it).

# Backlog — future work, not started yet

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

"""Example transforms for `unitaryguard check <module>:<callable>`.

Run from the repo root, e.g.:
    unitaryguard check examples.demo_pass:broken_pass_example --qubits 2 --gates h,s,sdg,t,tdg,rz,cx --samples 200

v0.2: UnitaryGuard no longer depends on Qiskit (see BACKLOG.md/DESIGN.md
for why -- the short version: it exists to validate EXTERNAL engines, and
depending on the same SDK the engine under test might also depend on
reintroduces exactly the circularity this tool is for catching). These
examples now use `unitaryguard.Circuit`/`Gate` directly. To point this
tool at a real engine (e.g. a transpiler written in another language),
write a `Circuit -> Circuit` transform that serializes the input circuit
to that engine's own protocol, calls it, and parses the response back into
a `Circuit` -- see the AutoQ EngineBR integration for a worked example of
that shape (a separate project; not included here).
"""
from __future__ import annotations

from unitaryguard import Circuit, Gate


def identity_pass(circ: Circuit) -> Circuit:
    """Trivial correct transform -- useful as a sanity baseline: this
    should NEVER be flagged by check_transform."""
    return circ.copy()


def broken_pass_example(circ: Circuit) -> Circuit:
    """Deliberately broken (for demoing what a caught failure looks like):
    drops the last gate of the circuit."""
    return Circuit(circ.n_qubits, list(circ.gates[:-1]))


def s_sdg_swap_bug(circ: Circuit) -> Circuit:
    """Deliberately broken: silently swaps S and Sdg wherever they occur
    (the real bug SHAPE found in Qiskit's OptimizeCliffordT, PR #16729 --
    see BACKLOG.md). S != Sdg in general, so this breaks unitary
    equivalence on any circuit containing at least one S/Sdg gate."""
    out = Circuit(circ.n_qubits)
    for g in circ.gates:
        if g.kind == "s":
            out.gates.append(Gate("sdg", g.qubits, g.params))
        elif g.kind == "sdg":
            out.gates.append(Gate("s", g.qubits, g.params))
        else:
            out.gates.append(g)
    return out

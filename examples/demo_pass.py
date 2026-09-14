"""Example transforms for `unitaryguard check <module>:<callable>`.

Run from the repo root, e.g.:
    unitaryguard check examples.demo_pass:qiskit_optimize_1q --qubits 2 --gates h,s,sdg,t,tdg,rz,cx --samples 200
"""
from __future__ import annotations

from qiskit import QuantumCircuit
from qiskit.transpiler import PassManager
from qiskit.transpiler.passes import Optimize1qGatesDecomposition


def qiskit_optimize_1q(qc: QuantumCircuit) -> QuantumCircuit:
    """A real Qiskit transpiler pass, wrapped as a transform -- demonstrates
    pointing UnitaryGuard at actual Qiskit infrastructure, not just the toy
    fixtures in tests/."""
    pm = PassManager([Optimize1qGatesDecomposition(basis=["u"])])
    return pm.run(qc)


def broken_pass_example(qc: QuantumCircuit) -> QuantumCircuit:
    """Deliberately broken (for demoing what a caught failure looks like):
    drops the last gate of the circuit."""
    out = QuantumCircuit(qc.num_qubits)
    for instr in qc.data[:-1]:
        out.append(instr.operation, instr.qubits, instr.clbits)
    return out

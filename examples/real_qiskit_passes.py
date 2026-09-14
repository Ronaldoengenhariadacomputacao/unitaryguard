"""Wrappers around real Qiskit transpiler passes, for checking with
`unitaryguard check examples.real_qiskit_passes:<name>`.
"""
from __future__ import annotations

from qiskit import QuantumCircuit
from qiskit.transpiler import PassManager
from qiskit.transpiler.passes import (
    CommutativeCancellation,
    Collect2qBlocks,
    ConsolidateBlocks,
    InverseCancellation,
    Optimize1qGatesDecomposition,
)
from qiskit.circuit.library import SGate, SdgGate, TGate, TdgGate, XGate


def commutative_cancellation(qc: QuantumCircuit) -> QuantumCircuit:
    return PassManager([CommutativeCancellation()]).run(qc)


def inverse_cancellation(qc: QuantumCircuit) -> QuantumCircuit:
    pairs = [(SGate(), SdgGate()), (TGate(), TdgGate()), (XGate(), XGate())]
    return PassManager([InverseCancellation(pairs)]).run(qc)


def collect_consolidate_blocks(qc: QuantumCircuit) -> QuantumCircuit:
    return PassManager([Collect2qBlocks(), ConsolidateBlocks()]).run(qc)


def optimize_1q(qc: QuantumCircuit) -> QuantumCircuit:
    return PassManager([Optimize1qGatesDecomposition(basis=["u"])]).run(qc)


def full_light_pipeline(qc: QuantumCircuit) -> QuantumCircuit:
    return PassManager(
        [
            Collect2qBlocks(),
            ConsolidateBlocks(),
            CommutativeCancellation(),
            Optimize1qGatesDecomposition(basis=["u"]),
        ]
    ).run(qc)

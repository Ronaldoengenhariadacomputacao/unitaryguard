"""Wraps the real RossSelingerSynthesis plugin (Qiskit's actual gridsynth
Clifford+T synthesizer) as a transform: whatever unitary the input circuit
implements gets re-synthesized to Clifford+T at a fixed epsilon, and the
result is checked against the ORIGINAL circuit -- not exact equality (this
is approximate synthesis), but within a tolerance a bit looser than epsilon,
to allow for the algorithm's own approximation error.

Point unitaryguard at `make_transform(epsilon)` with a concrete epsilon:
    unitaryguard.check_transform(make_transform(0.01), cfg)
(there's no zero-arg version because epsilon is a required parameter, not a
bare `QuantumCircuit -> QuantumCircuit` callable -- see examples/demo_pass.py
for the CLI-friendly bare-callable style.)
"""
from __future__ import annotations

from qiskit import QuantumCircuit, transpile
from qiskit.circuit.library import UnitaryGate
from qiskit.quantum_info import Operator


def make_transform(epsilon: float = 0.01):
    def transform(qc: QuantumCircuit) -> QuantumCircuit:
        u = Operator(qc).data
        wrapped = QuantumCircuit(qc.num_qubits)
        wrapped.append(UnitaryGate(u), range(qc.num_qubits))
        out = transpile(
            wrapped,
            basis_gates=["h", "t", "tdg", "s", "sdg", "x", "cx"],
            unitary_synthesis_method="gridsynth",
            unitary_synthesis_plugin_config={"epsilon": epsilon},
            optimization_level=0,
        )
        return out

    return transform


# CLI-friendly default (epsilon=0.05, loose enough that a healthy plugin
# should pass comfortably within unitaryguard's tolerance if --tol is set
# generously, e.g. --tol 0.2)
gridsynth_eps_0_05 = make_transform(0.05)

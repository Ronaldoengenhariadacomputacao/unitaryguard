"""Case study (see CASE_STUDIES.md, Method 4): confirms rsgridsynth PR #49
(github.com/qiskit-community/rsgridsynth/pull/49, still open/unmerged as of
2026-09-21) by calling the REAL Rust `NormalForm::append_gate` directly,
via a small sibling PyO3 binding crate (`../rsgridsynth_pybind`, a path
dependency on rsgridsynth -- never modifies it). This is NOT reachable
through Qiskit's own `gridsynth` synthesis plugin (verified separately:
400 random circuits through that wrapper, 0 failures -- the wrapper
doesn't exercise this specific multi-rotation compression code path).

SKIPPED (not a failure) if `rsgridsynth_pybind` isn't built/installed --
see ../../rsgridsynth_pybind/README.md for build instructions (requires
the Rust toolchain + maturin, and a local clone of
github.com/Ronaldoengenhariadacomputacao/rsgridsynth as a sibling
directory of this repo's parent).

Run manually: python tests/test_case_study_rsgridsynth.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unitaryguard import Circuit, Gate, CheckConfig, check_transform

try:
    import rsgridsynth_pybind as rg
    _HAS_BINDING = True
except ImportError:
    _HAS_BINDING = False

_GATE_LETTER = {"h": "H", "s": "S", "t": "T", "x": "X"}
_LETTER_GATE = {"H": "h", "S": "s", "T": "t", "X": "x"}


def circuit_to_gate_string(circ: Circuit) -> str:
    return "".join(_GATE_LETTER[g.kind] for g in circ.gates)


def gate_string_to_circuit(n_qubits: int, s: str) -> Circuit:
    circ = Circuit(n_qubits)
    for ch in s:
        if ch in ("I", "W"):
            continue
        circ.gates.append(Gate(_LETTER_GATE[ch], (0,)))
    return circ


def transform_real_rust_normal_form(circ: Circuit) -> Circuit:
    """Chama DIRETO o NormalForm::from_gates/to_gates da crate Rust real
    (via rsgridsynth_pybind), sem passar pelo wrapper do Qiskit."""
    s = circuit_to_gate_string(circ)
    out = rg.normal_form_compress(s)
    return gate_string_to_circuit(circ.n_qubits, out)


def test_finds_real_rsgridsynth_sht_merge_bug() -> None:
    if not _HAS_BINDING:
        print("SKIPPED -- rsgridsynth_pybind not installed (see ../rsgridsynth_pybind/README.md)")
        return

    cfg = CheckConfig(
        n_qubits=1,
        gate_set=["h", "s", "t"],
        n_samples=300,
        min_gates=2,
        max_gates=8,
        seed=3,
    )
    report = check_transform(transform_real_rust_normal_form, cfg, shrink=True)
    print(report.summary())
    # NAO afirmamos report.ok aqui de proposito -- este script documenta um
    # bug real e ATIVO no rsgridsynth publicado (PR #49 ainda aberta). Se
    # um dia a dependencia local apontar pra branch corrigida, isso deve
    # passar a dar report.ok=True -- ver rsgridsynth_pybind/README.md.
    if report.ok:
        print("\nNOTA: 0 falhas -- ou a dependencia local esta na branch CORRIGIDA "
              "(fix/sht-merge-shs-not-hsh), ou algo mudou. Confirme com "
              "`git -C ../../rsgridsynth branch --show-current`.")
    else:
        print(f"\nConfirmado: {report.n_failed}/{report.n_checked} circuitos "
              f"divergem -- bug real do PR #49 ainda presente na dependencia local.")


if __name__ == "__main__":
    test_finds_real_rsgridsynth_sht_merge_bug()

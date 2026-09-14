"""CLI: unitaryguard check <module>:<callable> --qubits N --gates h,s,t,cx ..."""
from __future__ import annotations

import argparse
import importlib
import sys

from .core import CheckConfig, check_transform
from .exhaustive import check_transform_exhaustive
from .parallel import check_transform_exhaustive_parallel


def _load_callable(spec: str):
    if ":" not in spec:
        raise SystemExit(f"expected '<module>:<callable>', got '{spec}'")
    module_name, attr = spec.split(":", 1)
    mod = importlib.import_module(module_name)
    obj = mod
    for part in attr.split("."):
        obj = getattr(obj, part)
    if not callable(obj):
        raise SystemExit(f"'{spec}' is not callable")
    return obj


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="unitaryguard")
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="check that a transform preserves circuit unitaries")
    check.add_argument("target", help="'<module>:<callable>' -- a QuantumCircuit -> QuantumCircuit function")
    check.add_argument("--qubits", type=int, default=2, help="number of qubits for sampled circuits")
    check.add_argument(
        "--gates",
        type=str,
        default="h,s,sdg,t,tdg,cx",
        help="comma-separated gate vocabulary to sample from",
    )
    check.add_argument("--samples", type=int, default=200, help="number of random circuits to sample")
    check.add_argument("--min-gates", type=int, default=1)
    check.add_argument("--max-gates", type=int, default=12)
    check.add_argument("--seed", type=int, default=None)
    check.add_argument("--tol", type=float, default=1e-7, help="allowed 1 - fidelity before flagging a failure")
    check.add_argument("--no-shrink", action="store_true", help="skip minimization of failing circuits")

    exhaustive = sub.add_parser(
        "exhaustive",
        help="deterministically test EVERY circuit up to a max length (targets gate-order/"
        "inversion transcription bugs, which are deterministic, not statistical)",
    )
    exhaustive.add_argument("target", help="'<module>:<callable>'")
    exhaustive.add_argument("--qubits", type=int, default=1)
    exhaustive.add_argument("--gates", type=str, default="h,s,t", help="discrete gates only (no rz/rx/ry)")
    exhaustive.add_argument("--max-length", type=int, default=6)
    exhaustive.add_argument("--tol", type=float, default=1e-7)
    exhaustive.add_argument(
        "--all-lengths",
        action="store_true",
        help="check every length up to --max-length even after the first failing length is found",
    )
    exhaustive.add_argument(
        "--workers",
        type=int,
        default=1,
        help="number of worker processes (>1 uses a process pool -- each length's search is "
        "split into contiguous index ranges across workers; default 1 = sequential)",
    )

    calibrate = sub.add_parser(
        "calibrate-workers",
        help="probe this machine's own hardware to find a sensible --workers value, "
        "instead of trusting a number measured on a different machine",
    )
    calibrate.add_argument("target", help="'<module>:<callable>'")
    calibrate.add_argument("--qubits", type=int, default=1)
    calibrate.add_argument("--gates", type=str, default="h,s,sdg,t,tdg,x")
    calibrate.add_argument(
        "--probe-length",
        type=int,
        default=4,
        help="circuit length for the probe run -- pick something that takes a few "
        "seconds sequentially (too small and the whole measurement is noise)",
    )
    calibrate.add_argument("--tol", type=float, default=1e-7)

    args = parser.parse_args(argv)

    if args.cmd == "check":
        transform = _load_callable(args.target)
        cfg = CheckConfig(
            n_qubits=args.qubits,
            gate_set=tuple(g.strip() for g in args.gates.split(",") if g.strip()),
            n_samples=args.samples,
            min_gates=args.min_gates,
            max_gates=args.max_gates,
            seed=args.seed,
            tol=args.tol,
        )
        report = check_transform(transform, cfg, shrink=not args.no_shrink)
        print(report.summary())
        return 0 if report.ok else 1

    if args.cmd == "exhaustive":
        gate_set = [g.strip() for g in args.gates.split(",") if g.strip()]
        if args.workers > 1:
            report = check_transform_exhaustive_parallel(
                args.target,
                n_qubits=args.qubits,
                gate_set=gate_set,
                max_length=args.max_length,
                tol=args.tol,
                n_workers=args.workers,
                stop_at_first_length_with_failure=not args.all_lengths,
            )
        else:
            transform = _load_callable(args.target)
            report = check_transform_exhaustive(
                transform,
                n_qubits=args.qubits,
                gate_set=gate_set,
                max_length=args.max_length,
                tol=args.tol,
                stop_at_first_length_with_failure=not args.all_lengths,
            )
        print(report.summary())
        if report.smallest_failing_length is not None:
            print(f"\nsmallest failing circuit length: {report.smallest_failing_length}")
        print(f"circuits checked by length: {report.n_checked_by_length}")
        return 0 if report.ok else 1

    if args.cmd == "calibrate-workers":
        import os
        import time

        gate_set = [g.strip() for g in args.gates.split(",") if g.strip()]
        max_cores = os.cpu_count() or 1
        candidates = sorted(set(
            w for w in (1, 2, 4, max(1, max_cores // 2), max_cores) if w <= max_cores
        ))
        print(f"this machine reports {max_cores} logical CPUs. Probing --workers in {candidates} "
              f"at length {args.probe_length} against {args.target} ...\n")
        results = []
        for w in candidates:
            t0 = time.time()
            report = check_transform_exhaustive_parallel(
                args.target,
                n_qubits=args.qubits,
                gate_set=gate_set,
                max_length=args.probe_length,
                tol=args.tol,
                n_workers=w,
                stop_at_first_length_with_failure=False,
            )
            dt = time.time() - t0
            rate = report.n_checked / dt if dt > 0 else float("inf")
            results.append((w, dt, rate))
            print(f"  --workers {w:3d}:  {report.n_checked} circuits in {dt:6.2f}s  "
                  f"({rate:8.1f} circuits/s)")

        best = max(results, key=lambda r: r[2])
        print(f"\nfastest on THIS run: --workers {best[0]} ({best[2]:.1f} circuits/s). "
              "Re-run this a couple of times -- process scheduling noise can shift the "
              "winner by 1-2 workers. If --workers 1 (sequential) wins, your probe length "
              "is probably too small for parallelism to pay off; try a larger --probe-length.")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())

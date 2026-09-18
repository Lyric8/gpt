from __future__ import annotations

import argparse
import json
from pathlib import Path

from .accounting import delta, snapshot
from .probes import CHECKS, evaluate, observed_call, scan
from .projection import projection
from .storage import Journal, atomic_write, encode


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage A: no model imports, no budget admission path")
    commands = parser.add_subparsers(dest="command", required=True)
    scan_parser = commands.add_parser("scan")
    scan_parser.add_argument("--bare", type=Path, required=True)
    scan_parser.add_argument("--state", type=Path, required=True)
    scan_parser.add_argument("--protocol", type=Path, required=True)
    probe_parser = commands.add_parser("probe")
    probe_parser.add_argument("--job", choices=sorted(CHECKS), required=True)
    probe_parser.add_argument("--state", type=Path, required=True)
    probe_parser.add_argument("--observation", type=Path, required=True)
    probe_parser.add_argument("--max-age", type=float, default=90)
    snapshot_parser = commands.add_parser("snapshot")
    snapshot_parser.add_argument("--db", type=Path, required=True)
    snapshot_parser.add_argument("--out", type=Path, required=True)
    delta_parser = commands.add_parser("delta")
    delta_parser.add_argument("before", type=Path)
    delta_parser.add_argument("after", type=Path)
    commands.add_parser("projection")
    args = parser.parse_args()
    journal = None
    try:
        if args.command == "snapshot":
            result = snapshot(args.db)
            atomic_write(args.out, encode(result) + b"\n")
        elif args.command == "delta":
            result = delta(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
        elif args.command == "projection":
            result = projection()
        else:
            journal = Journal(args.state)
            job = "inbox" if args.command == "scan" else args.job
            def run():
                if args.command == "scan":
                    return scan(args.bare, journal, json.loads(args.protocol.read_text()))
                return evaluate(job, json.loads(args.observation.read_text()), journal, args.max_age)
            result = observed_call(job, run, journal)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return result.get("exit_code", 0)
    except Exception as exc:
        # Includes initialization and disk failures, unlike a try placed after
        # Journal creation. Error is never converted to NO_NEW_EVENT.
        print(json.dumps({"exit_code": 20, "status": "ERROR", "error_class": type(exc).__name__, "model_calls": 0}))
        return 20


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .accounting import delta, snapshot
from .artifacts import Artifacts, atomic_write, canonical
from .batch import run_read_batch


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes token control: deterministic local utilities")
    commands = parser.add_subparsers(dest="action", required=True)
    snap = commands.add_parser("snapshot"); snap.add_argument("--db", required=True); snap.add_argument("--out", required=True)
    diff = commands.add_parser("delta"); diff.add_argument("before"); diff.add_argument("after")
    batch = commands.add_parser("batch"); batch.add_argument("manifest"); batch.add_argument("--artifacts", required=True); batch.add_argument("--cwd", required=True)
    read = commands.add_parser("read"); read.add_argument("sha256"); read.add_argument("--artifacts", required=True); read.add_argument("--offset", type=int, default=0); read.add_argument("--length", type=int, default=4096)
    args = parser.parse_args()
    try:
        if args.action == "snapshot":
            result = snapshot(args.db)
            atomic_write(Path(args.out), canonical(result))
            print(json.dumps(result["totals"], ensure_ascii=False))
        elif args.action == "delta":
            result = delta(json.loads(Path(args.before).read_text()), json.loads(Path(args.after).read_text()))
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.action == "batch":
            result = run_read_batch(json.loads(Path(args.manifest).read_text()), Artifacts(args.artifacts), cwd=args.cwd)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["success"] else 1
        elif args.action == "read":
            if args.offset < 0 or not 0 < args.length <= 8192:
                raise ValueError("offset >= 0, length 1..8192")
            data = Artifacts(args.artifacts).read(args.sha256)
            part = data[args.offset:args.offset+args.length]
            print(json.dumps({"sha256": args.sha256, "offset_bytes": args.offset,
                              "total_bytes": len(data), "returned_bytes": len(part),
                              "has_more": args.offset+len(part) < len(data),
                              "text": part.decode("utf-8", errors="replace")}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .artifacts import digest
from .governor import IntegrityError

KEY = ("session_id", "model", "billing_provider", "billing_base_url", "billing_mode", "task")
COUNTERS = ("api_call_count", "input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens")
COSTS = ("estimated_cost_usd", "actual_cost_usd")


def snapshot(db: str | Path) -> dict[str, Any]:
    """Read cumulative rows in ONE read transaction; respect a live WAL.

    Do NOT filter lifetime aggregate rows by last_seen to derive interval usage.
    Take two snapshots and difference the counters by their complete primary key.
    """
    path = Path(db).resolve(strict=True)
    c = sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=ro", uri=True, timeout=10,
                        isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA query_only=ON")
        c.execute("BEGIN")
        info = [dict(r) for r in c.execute("PRAGMA table_info(session_model_usage)")]
        fields = {r["name"] for r in info}
        required = set(KEY + COUNTERS)
        if not required.issubset(fields):
            raise IntegrityError("unsupported usage schema, missing: " + str(sorted(required-fields)))
        columns = list(KEY + COUNTERS) + [x for x in COSTS + ("cost_status", "cost_source") if x in fields]
        rows = [dict(r) for r in c.execute("SELECT " + ",".join(columns) + " FROM session_model_usage")]
        c.commit()
    finally:
        c.close()
    for row in rows:
        for field in COUNTERS:
            value = row[field]
            if type(value) is not int or value < 0:
                raise IntegrityError("invalid usage counter: " + field)
    return {"captured_at": datetime.now(timezone.utc).isoformat(), "schema_sha256": digest(info),
            "rows": rows, "totals": totals(rows)}


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = {field: sum(r.get(field, 0) for r in rows) for field in COUNTERS}
    result["prompt_tokens"] = result["input_tokens"] + result["cache_read_tokens"] + result["cache_write_tokens"]
    result["gross_tokens"] = result["prompt_tokens"] + result["output_tokens"]
    for field in COSTS:
        known = [r[field] for r in rows if r.get(field) is not None]
        result[field] = sum(known) if known else None
        result[field + "_known_rows"] = len(known)
    return result


def delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if before["schema_sha256"] != after["schema_sha256"]:
        raise IntegrityError("usage schema changed between snapshots")
    def indexed(s: dict[str, Any]) -> dict[tuple[Any, ...], dict[str, Any]]:
        out = {}
        for row in s["rows"]:
            key = tuple(row[k] for k in KEY)
            if key in out:
                raise IntegrityError("duplicate usage attribution key")
            out[key] = row
        return out
    old, new = indexed(before), indexed(after)
    if old.keys() - new.keys():
        raise IntegrityError("usage rows disappeared: deletion/rotation/DB replacement must be reconciled")
    differences = []
    for key, row in new.items():
        previous = old.get(key, {})
        out = {k: row[k] for k in KEY}
        for field in COUNTERS:
            value = row[field] - previous.get(field, 0)
            if value < 0:
                raise IntegrityError("counter decreased; cannot report savings from a reset")
            out[field] = value
        for field in COSTS:
            # A previously unknown price becoming known may backfill the entire
            # lifetime row, not this interval. Keep it UNKNOWN, never fabricate delta.
            a = previous.get(field, 0 if not previous else None)
            b = row.get(field)
            out[field] = b - a if a is not None and b is not None and b >= a else None
        differences.append(out)
    return {"from": before["captured_at"], "to": after["captured_at"],
            "rows": differences, "totals": totals(differences),
            "note": "Compare matched accepted business work, including retries/compaction/fallback; costs can be backfilled."}

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .storage import encode, sha256

KEY = ("session_id", "model", "billing_provider", "billing_base_url", "billing_mode", "task")
COUNTERS = ("api_call_count", "input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens")
COSTS = ("estimated_cost_usd", "actual_cost_usd")


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = {key: sum(row[key] for row in rows) for key in COUNTERS}
    # Match the Hermes ledger's disjoint input buckets. Do NOT apply this
    # formula to a provider's inclusive prompt_tokens field without normalization.
    result["prompt_tokens"] = sum(result[k] for k in ("input_tokens", "cache_read_tokens", "cache_write_tokens"))
    result["gross_tokens"] = result["prompt_tokens"] + result["output_tokens"]
    for key in COSTS:
        values = [row[key] for row in rows if row.get(key) is not None]
        result[key] = sum(values) if values else None
        result[key + "_known_rows"] = len(values)
    return result


def snapshot(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    db = sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=ro", uri=True, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        schema = [dict(row) for row in db.execute("PRAGMA table_info(session_model_usage)")]
        fields = {row["name"] for row in schema}
        if not set(KEY + COUNTERS) <= fields:
            raise ValueError("unsupported usage schema; do not guess counters")
        columns = list(KEY + COUNTERS) + [key for key in COSTS if key in fields]
        originals = [dict(row) for row in db.execute("SELECT " + ",".join(columns) + " FROM session_model_usage")]
        db.commit()
    finally:
        db.close()
    rows, seen = [], set()
    for row in originals:
        key = sha256(encode([row[name] for name in KEY]))
        if key in seen:
            raise ValueError("duplicate attribution key")
        seen.add(key)
        if any(type(row[name]) is not int or row[name] < 0 for name in COUNTERS):
            raise ValueError("invalid token counter")
        # Full key participates in identity but potential credential-bearing
        # provider URLs/task text are not written into snapshot artifacts.
        rows.append({"key": key, "session_key": sha256(encode(row["session_id"])),
                     "task_key": sha256(encode(row["task"])),
                     **{name: row[name] for name in COUNTERS},
                     **{name: row.get(name) for name in COSTS}})
    rows.sort(key=lambda row: row["key"])
    return {"captured_at": datetime.now(timezone.utc).isoformat(),
            "schema_sha256": sha256(encode(schema)), "rows": rows, "totals": totals(rows)}


def delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if before["schema_sha256"] != after["schema_sha256"]:
        raise ValueError("usage schema changed")
    old = {row["key"]: row for row in before["rows"]}
    new = {row["key"]: row for row in after["rows"]}
    if len(old) != len(before["rows"]) or len(new) != len(after["rows"]) or old.keys() - new.keys():
        raise ValueError("duplicate/disappeared usage rows; possible reset or rotation")
    rows = []
    for key, row in new.items():
        previous = old.get(key, {})
        record = {name: row[name] for name in ("key", "session_key", "task_key")}
        for field in COUNTERS:
            value = row[field] - previous.get(field, 0)
            if value < 0:
                raise ValueError("counter decreased; cannot claim savings")
            record[field] = value
        for field in COSTS:
            earlier = previous.get(field, 0 if not previous else None)
            later = row.get(field)
            record[field] = later - earlier if earlier is not None and later is not None and later >= earlier else None
        rows.append(record)
    return {"from": before["captured_at"], "to": after["captured_at"], "rows": rows, "totals": totals(rows),
            "cost_caveat": "Cost backfills can be lifetime repricing, not interval spend; invoice reconciliation is separate.",
            "workload_caveat": "Compare equal accepted work, completed obligations and notification latency; never lifetime totals."}

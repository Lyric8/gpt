#!/usr/bin/env python3
"""Source-pinned installer. No network, no service restart, no credential access.

check: creates complete candidate source files in a new private staging folder.
apply: requires stopped gateway/sender; backs up source and SQLite first.
rollback: restores source only, never rewinds a database containing ACKs.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time

PINNED = {
    "gateway/platforms/base.py": "3ad1ea18d4f3d4110a8bf6d77ecf077077d00696",
    "gateway/platforms/weixin.py": "8c2b18b76589a15627e3343afc34ce6951245d7b",
    "gateway/delivery_ledger.py": "16f463307663eec1d5250ab1ee10660d651d44c4",
}
NEW_FILES = ("gateway/reliable_outbox.py", "gateway/reliable_weixin.py", "gateway/wx_outbox_cli.py")
RUN_PATH = "gateway/run.py"


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def function(source: str, name: str) -> ast.AST:
    matches = [n for n in ast.walk(ast.parse(source))
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(matches) != 1:
        raise ValueError("expected_one_function:"+name)
    return matches[0]


def enter(source: str, name: str, body: str) -> str:
    fn = function(source, name)
    first = fn.body[0]
    has_doc = isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str)
    line = first.end_lineno if has_doc else first.lineno - 1
    indent = " " * (fn.col_offset + 4)
    inserted = "".join(indent + text + "\n" if text else "\n" for text in body.splitlines())
    lines = source.splitlines(keepends=True)
    return "".join(lines[:line]) + inserted + "".join(lines[line:])


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("source_anchor_mismatch:"+old[:80])
    return source.replace(old, new, 1)


def edit_sources(sources: dict[str, str]) -> dict[str, str]:
    base = sources["gateway/platforms/base.py"]
    # Queue the complete raw final response before any media extraction/send.
    anchor = "            if not response:\n                logger.debug(\"[%s] Handler returned empty/None response for %s\", self.name, event.source.chat_id)"
    inserted = """            from gateway import reliable_weixin as _wx_reliable
            if response and _wx_reliable.enabled(self):
                await _wx_reliable.capture_final(self, event, session_key, response)
                response = None  # processing complete != provider delivery complete
"""
    base = replace_once(base, anchor, inserted + anchor)
    base = enter(base, "_send_with_retry", """from gateway import reliable_weixin as _wx_reliable
if _wx_reliable.enabled(self):
    return await _wx_reliable.submit_method(self, "_send_with_retry", locals())""")
    wx = sources["gateway/platforms/weixin.py"]
    for name in ("send", "send_document", "send_voice", "send_video", "send_image_file", "send_image"):
        wx = enter(wx, name, f'''from gateway import reliable_weixin as _wx_reliable
if _wx_reliable.enabled(self):
    return await _wx_reliable.submit_method(self, "{name}", locals())''')
    for name in ("_send_file", "_send_text_chunk", "_send_text_chunk_locked"):
        wx = enter(wx, name, '''from gateway import reliable_weixin as _wx_reliable
if _wx_reliable.enabled(self):
    raise RuntimeError("raw_weixin_send_forbidden_use_outbox")''')
    wx = enter(wx, "send_weixin_direct", '''from gateway import reliable_weixin as _wx_reliable
if _wx_reliable.enabled():
    return await _wx_reliable.enqueue_direct(extra=extra, token=token, chat_id=chat_id,
                                              message=message, media_files=media_files)''')
    anchor = "        _LIVE_ADAPTERS[self._token] = self\n"
    wx = replace_once(wx, anchor, anchor + '''        from gateway import reliable_weixin as _wx_reliable
        await _wx_reliable.start(self)
''')
    wx = enter(wx, "disconnect", '''from gateway import reliable_weixin as _wx_reliable
await _wx_reliable.stop(self)''')
    run = sources[RUN_PATH]
    fn = function(run, "_claim_pending_obligations")
    original = ast.get_source_segment(run, fn)
    if "sweep_recoverable" not in original or "_clear_resume_pending_for_claimed_obligations" not in original:
        raise ValueError("unrecognized_startup_resume_barrier")
    run = enter(run, "_claim_pending_obligations", '''from gateway import reliable_weixin as _wx_reliable
await _wx_reliable.restore_before_resume(self)''')
    # Preserve original ledger API for every other platform. Capacity cleanup
    # must NEVER select unresolved rows. New Outbox rows live in other tables.
    ledger = sources["gateway/delivery_ledger.py"]
    anchor = """SELECT obligation_id FROM delivery_obligations
                         ORDER BY CASE state"""
    ledger = replace_once(ledger, anchor, """SELECT obligation_id FROM delivery_obligations
                         WHERE state IN ('delivered', 'abandoned')
                         ORDER BY CASE state""")
    # New and old replay engines must never own the same Weixin obligation.
    # Existing rows require the explicit, same-transaction legacy import.
    ledger = replace_once(ledger,
        "WHERE state IN ('pending', 'attempting', 'failed')",
        "WHERE state IN ('pending', 'attempting', 'failed') AND platform <> 'weixin'")
    ledger = replace_once(ledger,
        "WHERE state='failed' AND platform=?",
        "WHERE state='failed' AND platform=? AND platform <> 'weixin'")
    return {"gateway/platforms/base.py": base, "gateway/platforms/weixin.py": wx,
            "gateway/delivery_ledger.py": ledger, RUN_PATH: run}


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".wx-install-")
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        dfd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def require_stopped(units: list[str], *, user: bool) -> None:
    if not units:
        raise ValueError("explicit_gateway_and_sender_units_required")
    for unit in units:
        use_user = user
        if unit.startswith(("user:", "system:")):
            manager, unit = unit.split(":", 1)
            use_user = manager == "user"
        result = subprocess.run(["systemctl", *(["--user"] if use_user else []), "show", unit,
                                 "--property=LoadState,ActiveState,MainPID", "--no-pager"],
                                capture_output=True, text=True, check=True)
        data = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if data.get("LoadState") != "loaded" or data.get("ActiveState") not in {"inactive", "failed"} or data.get("MainPID") != "0":
            raise RuntimeError("service_not_confirmed_stopped:"+unit)


def make_stage(root: Path, stage: Path) -> dict:
    stage.mkdir(mode=0o700, parents=True, exist_ok=False)
    manifest = {"version": 1, "root": str(root.resolve()), "files": {}, "created": time.time()}
    sources = {}
    for path in (*PINNED, RUN_PATH):
        data = (root/path).read_bytes()
        sha = blob_sha(data)
        if path in PINNED and sha != PINNED[path]:
            raise ValueError("pinned_blob_mismatch:"+path+":"+sha)
        manifest["files"][path] = {"before": hashlib.sha256(data).hexdigest()}
        sources[path] = data.decode("utf-8")
    candidates = edit_sources(sources)
    package = Path(__file__).resolve().parent
    for path in NEW_FILES:
        if (root/path).exists():
            raise ValueError("new_file_already_exists:"+path)
        candidates[path] = (package/path).read_text(encoding="utf-8")
        manifest["files"][path] = {"before": None}
    for path, text in candidates.items():
        compile(text, str(root/path), "exec")
        data = text.encode("utf-8")
        manifest["files"][path]["after"] = hashlib.sha256(data).hexdigest()
        atomic_write(stage/path, data)
    atomic_write(stage/"manifest.json", json.dumps(manifest, indent=2).encode())
    return manifest


def backup_db(path: Path, destination: Path) -> None:
    if not path.exists():
        return
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    os.chmod(destination, 0o600)


def apply(stage: Path, hermes_home: Path, units: list[str], *, user: bool) -> Path:
    require_stopped(units, user=user)
    manifest = json.loads((stage/"manifest.json").read_text())
    root = Path(manifest["root"])
    # Verify the entire set BEFORE the first mutation.
    for path, item in manifest["files"].items():
        actual = hashlib.sha256((root/path).read_bytes()).hexdigest() if (root/path).exists() else None
        if actual != item["before"] or hashlib.sha256((stage/path).read_bytes()).hexdigest() != item["after"]:
            raise ValueError("stale_or_modified_stage:"+path)
    backup = hermes_home/"reliability-backups"/(time.strftime("%Y%m%dT%H%M%S")+"-"+os.urandom(4).hex())
    backup.mkdir(mode=0o700, parents=True)
    for path, item in manifest["files"].items():
        if item["before"] is not None:
            atomic_write(backup/path, (root/path).read_bytes(), (root/path).stat().st_mode & 0o777)
    cfg = hermes_home/"reliable-weixin.json"
    manifest["config_existed"] = cfg.exists()
    if cfg.exists():
        atomic_write(backup/"reliable-weixin.json", cfg.read_bytes())
    backup_db(hermes_home/"state.db", backup/"state.db.pre-install")
    atomic_write(backup/"manifest.json", json.dumps(manifest, indent=2).encode())
    # Failure at any point leaves services stopped; use this complete backup.
    for path in manifest["files"]:
        atomic_write(root/path, (stage/path).read_bytes(), 0o644)
    atomic_write(cfg, b'{"enabled":true,"gap_seconds":20}\n')
    print("BACKUP="+str(backup))
    print("SOURCE_INSTALLED_SERVICES_NOT_STARTED")
    return backup


def rollback(backup: Path, hermes_home: Path, units: list[str], *, user: bool) -> None:
    require_stopped(units, user=user)
    db = hermes_home/"state.db"
    if db.exists():
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            exists = c.execute("SELECT 1 FROM sqlite_master WHERE name='wx_outbox_messages'").fetchone()
            pending = c.execute("SELECT COUNT(*) FROM wx_outbox_messages WHERE state<>'accepted'").fetchone()[0] if exists else 0
        finally:
            c.close()
        if pending:
            raise RuntimeError(f"rollback_refused_pending_obligations:{pending}; keep services stopped, fix/restore the new sender and drain first")
    manifest = json.loads((backup/"manifest.json").read_text())
    root = Path(manifest["root"])
    for path, item in manifest["files"].items():
        actual = hashlib.sha256((root/path).read_bytes()).hexdigest() if (root/path).exists() else None
        if actual not in (item["before"], item["after"]):
            raise ValueError("source_changed_since_install:"+path)
    for path, item in manifest["files"].items():
        if item["before"] is None:
            (root/path).unlink(missing_ok=True)
        else:
            atomic_write(root/path, (backup/path).read_bytes(), (backup/path).stat().st_mode & 0o777)
    cfg = hermes_home/"reliable-weixin.json"
    if manifest.get("config_existed"):
        atomic_write(cfg, (backup/"reliable-weixin.json").read_bytes())
    else:
        cfg.unlink(missing_ok=True)
    print("SOURCE_ROLLED_BACK_DB_NOT_REWOUND_SERVICES_NOT_STARTED")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=("check", "apply", "rollback"))
    p.add_argument("--root", type=Path)
    p.add_argument("--stage", type=Path)
    p.add_argument("--home", type=Path, default=Path.home()/".hermes")
    p.add_argument("--backup", type=Path)
    p.add_argument("--stopped-unit", action="append", default=[])
    p.add_argument("--user-systemd", action="store_true")
    a = p.parse_args()
    if a.operation == "check":
        if not a.root or not a.stage:
            p.error("check requires --root and a NEW --stage")
        make_stage(a.root, a.stage)
        print("STAGE_COMPILED_NOT_INSTALLED="+str(a.stage))
    elif a.operation == "apply":
        if not a.stage:
            p.error("apply requires --stage")
        apply(a.stage, a.home, a.stopped_unit, user=a.user_systemd)
    else:
        if not a.backup:
            p.error("rollback requires --backup")
        rollback(a.backup, a.home, a.stopped_unit, user=a.user_systemd)


if __name__ == "__main__":
    main()

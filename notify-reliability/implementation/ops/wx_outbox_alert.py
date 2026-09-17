#!/usr/bin/env python3
"""Durable Weixin outbox alert spool, Git-backed sender, and dead-man heartbeat.

This module deliberately does not import the Weixin sender and never uses the
Weixin Outbox for alert delivery.  It is designed for user-systemd oneshot
units and uses only the Python standard library.

Commands:
  observe   Run wx_outbox_cli watchdog, update incident state, atomically spool
            OPEN/UPDATE/RECOVERED events, and return the watchdog health status.
  drain     Deliver pending events through the existing chat-push.sh adapter.
            Failed pushes remain on disk for retry.
  heartbeat Ping an external dead-man URL supplied only through EnvironmentFile.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request
import uuid

TZ8 = timezone(timedelta(hours=8))
SERVICE = "wx-outbox-watchdog"
UPDATE_INTERVAL_S = 10 * 60
HEALTHY_RECOVERY_TICKS = 2
DISK_FLOOR_BYTES = 512 * 1024 * 1024
HEARTBEAT_MAX_AGE_S = 30.0
PENDING_MAX_AGE_S = 120.0

FAILURE_REASON = {
    "watchdog_failed": "health command failed or returned an unclassified result",
    "account_paused": "outbox account is paused",
    "queue_stalled": "oldest pending outbox work exceeded the health threshold",
    "disk_low": "free disk space is below the outbox safety floor",
    "clock_anomaly": "outbox clock anomaly was detected",
    "sender_unhealthy": "outbox sender heartbeat or blocked state is unhealthy",
}
CRITICAL_FAILURES = {"watchdog_failed", "account_paused", "disk_low", "sender_unhealthy"}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def now_iso(epoch: float | None = None) -> str:
    if epoch is None:
        epoch = time.time()
    return datetime.fromtimestamp(epoch, TZ8).isoformat(timespec="seconds")


def parse_iso(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


def file_timestamp(value: str) -> str:
    dt = datetime.fromisoformat(value).astimezone(TZ8)
    return dt.strftime("%Y-%m-%dT%H%M%S+0800")


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    ensure_private_dir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".wx-alert-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
        fsync_dir(path.parent)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return default


def spool_root() -> Path:
    home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    return Path(os.environ.get("WX_ALERT_SPOOL", str(home / "cache" / "wx-outbox-alerts")))


def state_path(root: Path) -> Path:
    return root / "state.json"


def lock_path(root: Path, name: str) -> Path:
    return root / f".{name}.lock"


def open_lock(root: Path, name: str) -> Any:
    ensure_private_dir(root)
    path = lock_path(root, name)
    f = path.open("a+b")
    os.chmod(path, 0o600)
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


def stable_host_id() -> str:
    explicit = os.environ.get("WX_ALERT_HOST_ID", "").strip()
    if explicit:
        material = explicit
    else:
        try:
            material = Path("/etc/machine-id").read_text(encoding="utf-8").strip()
        except OSError:
            material = socket.gethostname()
    digest = hashlib.sha256(("hermes-host\0" + material).encode("utf-8")).hexdigest()
    return "host-" + digest[:16]


def masked_account_id() -> str:
    account = os.environ.get("WX_ACCOUNT_ID", "").strip()
    if not account:
        return ""
    digest = hashlib.sha256(("weixin-account\0" + account).encode("utf-8")).hexdigest()
    return "acct-" + digest[:16]


def dedupe_key(host_id: str, failure_class: str, account_id: str) -> str:
    material = SERVICE + "\0" + host_id + "\0" + failure_class + "\0" + account_id
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def health_command() -> list[str]:
    home = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
    root = Path(os.environ.get("HERMES_ROOT", str(home / "hermes-agent")))
    python = os.environ.get("HERMES_PYTHON", str(root / "venv" / "bin" / "python"))
    account = os.environ.get("WX_ACCOUNT_ID", "").strip()
    if not account:
        raise RuntimeError("WX_ACCOUNT_ID is required")
    profile = os.environ.get("WX_PROFILE", "default")
    return [python, "-m", "gateway.wx_outbox_cli", "--db", str(home / "state.db"),
            "--account", account, "--profile", profile, "watchdog"]


def run_health() -> tuple[int, dict[str, Any]]:
    try:
        cmd = health_command()
        root = Path(os.environ.get("HERMES_ROOT", str(Path.home() / ".hermes" / "hermes-agent")))
        completed = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                                   timeout=15, check=False)
        payload: dict[str, Any] | None = None
        for line in reversed(completed.stdout.splitlines()):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                payload = candidate
                break
        if payload is None:
            payload = {"healthy": False, "error_class": "malformed_health_output"}
        return completed.returncode, payload
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError):
        return 2, {"healthy": False, "error_class": "health_execution_failed"}


def int_count(counts: Any, name: str) -> int:
    if not isinstance(counts, dict):
        return 0
    try:
        return max(0, int(counts.get(name, 0) or 0))
    except (TypeError, ValueError):
        return 0


def float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def metrics(payload: dict[str, Any]) -> dict[str, Any]:
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    pending = sum(int_count(counts, key) for key in ("preparing", "queued", "sending", "retry", "pending"))
    blocked = int_count(counts, "blocked")
    return {
        "queue_oldest_age_s": float_or_none(payload.get("oldest_pending_seconds")),
        "pending_count": pending,
        "blocked_count": blocked,
    }


def classify_failures(returncode: int, payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    if bool(payload.get("paused")):
        failures.append("account_paused")
    if bool(payload.get("clock_anomaly")):
        failures.append("clock_anomaly")
    disk = float_or_none(payload.get("disk_free_bytes"))
    if disk is not None and disk < DISK_FLOOR_BYTES:
        failures.append("disk_low")
    heartbeat = float_or_none(payload.get("heartbeat_age_seconds"))
    if heartbeat is None or heartbeat >= HEARTBEAT_MAX_AGE_S or int_count(counts, "blocked") > 0:
        failures.append("sender_unhealthy")
    oldest = float_or_none(payload.get("oldest_pending_seconds"))
    if oldest is not None and oldest >= PENDING_MAX_AGE_S:
        failures.append("queue_stalled")
    healthy = payload.get("healthy") is True
    if (returncode != 0 or not healthy) and not failures:
        failures.append("watchdog_failed")
    return sorted(set(failures))


def event_paths(root: Path) -> list[Path]:
    result: list[Path] = []
    for directory in (root / "pending", root / "sent"):
        if directory.is_dir():
            result.extend(directory.glob("*.json"))
    return result


def history_incidents(root: Path) -> dict[str, dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in event_paths(root):
        event = load_json(path, None)
        if isinstance(event, dict) and event.get("schema_version") == 1:
            try:
                parse_iso(str(event["observed_at"]))
            except (KeyError, TypeError, ValueError):
                continue
            events.append(event)
    events.sort(key=lambda e: (parse_iso(str(e["observed_at"])), str(e.get("alert_id", ""))))
    active: dict[str, dict[str, Any]] = {}
    for event in events:
        key = str(event.get("dedupe_key", ""))
        if not key:
            continue
        state = event.get("state")
        if state == "OPEN":
            active[key] = {
                "first_seen_at": event["first_seen_at"],
                "failure_class": event["failure_class"],
                "account_id": event.get("account_id", ""),
                "last_event_at": event["observed_at"],
                "update_seq": 0,
                "healthy_streak": 0,
            }
        elif state == "UPDATE" and key in active:
            active[key]["last_event_at"] = event["observed_at"]
            active[key]["update_seq"] = max(int(active[key].get("update_seq", 0)),
                                            int(event.get("update_seq", 0) or 0))
        elif state == "RECOVERED":
            active.pop(key, None)
    return active


def load_state(root: Path) -> dict[str, Any]:
    saved = load_json(state_path(root), {})
    if not isinstance(saved, dict):
        saved = {}
    active = history_incidents(root)
    saved_incidents = saved.get("incidents") if isinstance(saved.get("incidents"), dict) else {}
    for key, incident in active.items():
        previous = saved_incidents.get(key)
        if isinstance(previous, dict) and previous.get("first_seen_at") == incident.get("first_seen_at"):
            incident["healthy_streak"] = max(0, int(previous.get("healthy_streak", 0) or 0))
    return {
        "schema_version": 1,
        "last_healthy_at": saved.get("last_healthy_at"),
        "incidents": active,
    }


def write_state(root: Path, state: dict[str, Any]) -> None:
    atomic_write(state_path(root), (json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def make_event(*, failure_class: str, state: str, first_seen_at: str,
               observed_at: str, last_healthy_at: str | None, health: dict[str, Any],
               update_seq: int = 0) -> dict[str, Any]:
    host_id = stable_host_id()
    account_id = masked_account_id()
    key = dedupe_key(host_id, failure_class, account_id)
    m = metrics(health)
    return {
        "schema_version": 1,
        "alert_id": str(uuid.uuid4()),
        "dedupe_key": key,
        "state": state,
        "severity": "critical" if failure_class in CRITICAL_FAILURES else "warning",
        "failure_class": failure_class,
        "host_id": host_id,
        "service": SERVICE,
        "account_id": account_id or None,
        "first_seen_at": first_seen_at,
        "observed_at": observed_at,
        "last_healthy_at": last_healthy_at,
        "queue_oldest_age_s": m["queue_oldest_age_s"],
        "pending_count": m["pending_count"],
        "blocked_count": m["blocked_count"],
        "reason": FAILURE_REASON[failure_class],
        "update_seq": update_seq,
    }


def spool_event(root: Path, event: dict[str, Any]) -> Path:
    ensure_private_dir(root / "pending")
    ensure_private_dir(root / "sent")
    alert_id = str(event["alert_id"])
    pending = root / "pending" / f"{alert_id}.json"
    sent = root / "sent" / f"{alert_id}.json"
    if sent.exists() or pending.exists():
        return pending if pending.exists() else sent
    atomic_write(pending, (json.dumps(event, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return pending


def observe() -> int:
    root = spool_root()
    ensure_private_dir(root)
    holder = open_lock(root, "observe")
    if holder is None:
        print(canonical({"operation": "observe", "skipped": "already_running"}))
        return 0
    try:
        epoch = time.time()
        observed_at = now_iso(epoch)
        state = load_state(root)
        returncode, health = run_health()
        failures = classify_failures(returncode, health)
        current_keys: set[str] = set()
        last_healthy_at = state.get("last_healthy_at")

        for failure_class in failures:
            host_id = stable_host_id()
            account_id = masked_account_id()
            key = dedupe_key(host_id, failure_class, account_id)
            current_keys.add(key)
            incident = state["incidents"].get(key)
            if incident is None:
                first_seen_at = observed_at
                event = make_event(failure_class=failure_class, state="OPEN",
                                   first_seen_at=first_seen_at, observed_at=observed_at,
                                   last_healthy_at=last_healthy_at, health=health)
                spool_event(root, event)
                state["incidents"][key] = {
                    "first_seen_at": first_seen_at,
                    "failure_class": failure_class,
                    "account_id": account_id,
                    "last_event_at": observed_at,
                    "update_seq": 0,
                    "healthy_streak": 0,
                }
            else:
                incident["healthy_streak"] = 0
                elapsed = epoch - parse_iso(str(incident["last_event_at"]))
                if elapsed >= UPDATE_INTERVAL_S:
                    seq = int(incident.get("update_seq", 0) or 0) + 1
                    event = make_event(failure_class=failure_class, state="UPDATE",
                                       first_seen_at=str(incident["first_seen_at"]),
                                       observed_at=observed_at, last_healthy_at=last_healthy_at,
                                       health=health, update_seq=seq)
                    spool_event(root, event)
                    incident["last_event_at"] = observed_at
                    incident["update_seq"] = seq

        for key in list(state["incidents"]):
            if key in current_keys:
                continue
            incident = state["incidents"][key]
            incident["healthy_streak"] = int(incident.get("healthy_streak", 0) or 0) + 1
            if incident["healthy_streak"] >= HEALTHY_RECOVERY_TICKS:
                failure_class = str(incident["failure_class"])
                event = make_event(failure_class=failure_class, state="RECOVERED",
                                   first_seen_at=str(incident["first_seen_at"]),
                                   observed_at=observed_at, last_healthy_at=last_healthy_at,
                                   health=health, update_seq=int(incident.get("update_seq", 0) or 0))
                spool_event(root, event)
                del state["incidents"][key]

        if not failures:
            state["last_healthy_at"] = observed_at
        write_state(root, state)
        print(canonical({"operation": "observe", "healthy": not failures,
                         "failure_classes": failures, "active_incidents": len(state["incidents"])}))
        return 0 if not failures else 2
    finally:
        holder.close()


def render_event(event: dict[str, Any]) -> str:
    fields = [
        "schema_version", "alert_id", "dedupe_key", "state", "severity", "failure_class",
        "host_id", "service", "account_id", "first_seen_at", "observed_at", "last_healthy_at",
        "queue_oldest_age_s", "pending_count", "blocked_count", "reason", "update_seq",
    ]
    title = "Weixin Outbox recovered" if event.get("state") == "RECOVERED" else "Weixin Outbox remote alert"
    lines = [f"时间：{event['observed_at']}　作者：Hermes Monitor", "", f"# {title}", ""]
    for field in fields:
        value = event.get(field)
        if value is None:
            text = "null"
        elif isinstance(value, bool):
            text = "true" if value else "false"
        else:
            text = str(value).replace("\n", " ").replace("\r", " ")
        lines.append(f"{field}: {text}")
    lines.append("")
    lines.append("transport: github-chat-control-plane")
    lines.append("weixin_outbox_used: false")
    lines.append("")
    return "\n".join(lines)


def target_path(event: dict[str, Any]) -> str:
    state = str(event.get("state"))
    failure = str(event.get("failure_class", "watchdog_failed")).replace("_", "-")
    subject = f"wx-outbox-recovered-{failure}" if state == "RECOVERED" else f"wx-outbox-alert-{failure}"
    return f"chat/to-gpt/{file_timestamp(str(event['observed_at']))}-{subject}.md"


def push_event(root: Path, event: dict[str, Any]) -> bool:
    script = Path(os.environ.get("CHAT_PUSH_SCRIPT", str(Path.home() / ".hermes" / "scripts" / "chat-push.sh")))
    style = os.environ.get("CHAT_PUSH_STYLE", "path-file").strip().lower()
    if not script.is_file():
        return False
    markdown = render_event(event)
    run_dir = root / "run"
    ensure_private_dir(run_dir)
    fd, name = tempfile.mkstemp(prefix="alert-", suffix=".md", dir=run_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(markdown)
            f.flush()
            os.fsync(f.fileno())
        path = target_path(event)
        if style == "path-file":
            cmd = [str(script), path, name]
            stdin_data = None
        elif style == "file-path":
            cmd = [str(script), name, path]
            stdin_data = None
        elif style == "stdin-path":
            cmd = [str(script), path]
            stdin_data = markdown
        else:
            return False
        try:
            completed = subprocess.run(cmd, input=stdin_data, text=True,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       timeout=45, check=False)
            return completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def archive_sent(root: Path, pending: Path) -> None:
    destination = root / "sent" / pending.name
    ensure_private_dir(destination.parent)
    os.replace(pending, destination)
    os.chmod(destination, 0o600)
    fsync_dir(destination.parent)
    fsync_dir(pending.parent)


def drain() -> int:
    root = spool_root()
    ensure_private_dir(root)
    ensure_private_dir(root / "pending")
    ensure_private_dir(root / "sent")
    holder = open_lock(root, "sender")
    if holder is None:
        print(canonical({"operation": "drain", "skipped": "already_running"}))
        return 0
    sent = 0
    try:
        for path in sorted((root / "pending").glob("*.json")):
            event = load_json(path, None)
            if not isinstance(event, dict) or event.get("schema_version") != 1 or not event.get("alert_id"):
                print(canonical({"operation": "drain", "failed": "invalid_spool_event"}))
                return 2
            if not push_event(root, event):
                print(canonical({"operation": "drain", "delivered": sent,
                                 "pending": len(list((root / "pending").glob("*.json")))}))
                return 2
            archive_sent(root, path)
            sent += 1
        print(canonical({"operation": "drain", "delivered": sent, "pending": 0}))
        return 0
    finally:
        holder.close()


def heartbeat() -> int:
    url = os.environ.get("HEALTHCHECKS_PING_URL", "").strip()
    if not url.startswith("https://"):
        print(canonical({"operation": "heartbeat", "healthy": False,
                         "error_class": "missing_or_non_https_ping_url"}))
        return 2
    timeout = float(os.environ.get("HEALTHCHECKS_TIMEOUT_SECONDS", "10"))
    request = urllib.request.Request(url, headers={"User-Agent": "hermes-wx-outbox-monitor/1"})
    try:
        with urllib.request.urlopen(request, timeout=max(1.0, min(timeout, 30.0))) as response:
            status = int(getattr(response, "status", 200))
            response.read(1)
        if 200 <= status < 300:
            print(canonical({"operation": "heartbeat", "healthy": True}))
            return 0
        print(canonical({"operation": "heartbeat", "healthy": False,
                         "error_class": "unexpected_status"}))
        return 2
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
        # Never print the URL: it contains the external monitor secret.
        print(canonical({"operation": "heartbeat", "healthy": False,
                         "error_class": type(exc).__name__}))
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("observe", "drain", "heartbeat"))
    args = parser.parse_args()
    if args.command == "observe":
        return observe()
    if args.command == "drain":
        return drain()
    return heartbeat()


if __name__ == "__main__":
    raise SystemExit(main())

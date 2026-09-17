#!/usr/bin/env python3
"""Safe path-file adapter for Hermes' commit-message-only chat-push.sh.

Interface exposed to wx_outbox_alert.py:
    chat_push_path_file_adapter.py <chat-relative-path> <payload-file>

The host backend has a different interface:
    chat-push.sh "<commit message>"

This adapter materializes the payload atomically into the dedicated chat
checkout, invokes the backend with only a commit message, then verifies the
exact payload bytes from the remote chat branch. A backend return code of zero
is never sufficient evidence of delivery.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile

MAX_PAYLOAD_BYTES = 1024 * 1024
DEFAULT_REPO_ROOT = "/home/ubuntu/src/gpt"
DEFAULT_BRANCH = "chat"
DEFAULT_REMOTE = "origin"

RC_OK = 0
RC_CONFIG = 20
RC_INPUT = 21
RC_MATERIALIZE = 22
RC_CONFLICT = 23
RC_BACKEND = 24
RC_VERIFY = 25


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def validated_target(relative: str) -> PurePosixPath | None:
    target = PurePosixPath(relative)
    parts = target.parts
    if target.is_absolute() or len(parts) < 3:
        return None
    if any(part in ("", ".", "..") for part in parts):
        return None
    if parts[0:2] != ("chat", "to-gpt"):
        return None
    if target.suffix != ".md":
        return None
    return target


def run_quiet(argv: list[str], *, text: bool = False, capture_stdout: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=45,
        check=False,
        text=text,
    )


def checkout_is_branch(repo: Path, branch: str) -> bool:
    try:
        result = run_quiet(
            ["git", "-C", str(repo), "symbolic-ref", "--quiet", "--short", "HEAD"],
            text=True,
            capture_stdout=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == branch


def materialize(repo: Path, target: PurePosixPath, payload: bytes) -> int:
    destination = repo.joinpath(*target.parts)
    parent = destination.parent
    if not parent.is_dir() or destination.is_symlink():
        return RC_CONFIG

    try:
        if destination.exists():
            if not destination.is_file():
                return RC_CONFLICT
            return RC_OK if destination.read_bytes() == payload else RC_CONFLICT

        fd, temporary = tempfile.mkstemp(prefix=".wx-alert-chat-", dir=parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), 0o644)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, destination)
            except FileExistsError:
                if destination.is_symlink() or not destination.is_file():
                    return RC_CONFLICT
                return RC_OK if destination.read_bytes() == payload else RC_CONFLICT
            os.chmod(destination, 0o644)
            fsync_dir(parent)
            return RC_OK
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    except OSError:
        return RC_MATERIALIZE


def commit_message(target: PurePosixPath) -> str:
    subject = target.stem
    if len(subject) > 96:
        subject = subject[:96]
    return f"chat: deliver {subject}"


def backend_push(backend: Path, target: PurePosixPath) -> bool:
    try:
        result = run_quiet([str(backend), commit_message(target)])
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def remote_matches(repo: Path, remote: str, branch: str,
                   target: PurePosixPath, payload: bytes) -> bool:
    try:
        fetched = run_quiet(["git", "-C", str(repo), "fetch", "--quiet", remote, branch])
        if fetched.returncode != 0:
            return False
        shown = run_quiet(
            ["git", "-C", str(repo), "show", f"refs/remotes/{remote}/{branch}:{target.as_posix()}"],
            capture_stdout=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return shown.returncode == 0 and shown.stdout == payload


def deliver(relative: str, payload_file: str) -> int:
    target = validated_target(relative)
    if target is None:
        return RC_INPUT

    payload_path = Path(payload_file)
    backend = Path(os.environ.get(
        "CHAT_PUSH_BACKEND",
        str(Path.home() / ".hermes" / "scripts" / "chat-push.sh"),
    ))
    repo = Path(os.environ.get("CHAT_REPO_ROOT", DEFAULT_REPO_ROOT))
    remote = os.environ.get("CHAT_PUSH_REMOTE", DEFAULT_REMOTE).strip()
    branch = os.environ.get("CHAT_PUSH_BRANCH", DEFAULT_BRANCH).strip()

    if not backend.is_file() or not repo.is_dir() or not remote or not branch:
        return RC_CONFIG
    if not checkout_is_branch(repo, branch):
        return RC_CONFIG

    try:
        if not payload_path.is_file():
            return RC_INPUT
        stat = payload_path.stat()
        if stat.st_size < 1 or stat.st_size > MAX_PAYLOAD_BYTES:
            return RC_INPUT
        payload = payload_path.read_bytes()
    except OSError:
        return RC_INPUT

    result = materialize(repo, target, payload)
    if result != RC_OK:
        return result

    if not backend_push(backend, target):
        return RC_BACKEND
    if not remote_matches(repo, remote, branch, target, payload):
        return RC_VERIFY
    return RC_OK


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        return RC_INPUT
    return deliver(args[0], args[1])


if __name__ == "__main__":
    raise SystemExit(main())

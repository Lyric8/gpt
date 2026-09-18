#!/usr/bin/env python3
"""Publish complete source and an immutable v3 notice on an authenticated host.

Uses isolated Git indexes, not checkout, so historical >255-byte filenames in
unrelated relay paths do not block delivery. No force-push, no main-worktree edits.
Running this helper is a user-side action, NOT evidence publication happened here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

BRANCH = "gpt/20260918-token-audit"
DESTINATION = "projects/hermes-token-control"


def git(repo: Path, *args: str, data: bytes | None = None,
        index: Path | None = None) -> bytes:
    env = os.environ.copy()
    if index is not None:
        env["GIT_INDEX_FILE"] = str(index)
    r = subprocess.run(["git", "-C", str(repo), *args], input=data,
                       capture_output=True, timeout=180, env=env)
    if r.returncode:
        raise RuntimeError("git operation failed: " + r.stderr[-3000:].decode(errors="replace"))
    return r.stdout


def text(repo: Path, *args: str, **kwargs) -> str:
    return git(repo, *args, **kwargs).decode().strip()


def remote_sha(repo: Path, branch: str) -> str | None:
    result = text(repo, "ls-remote", "--heads", "origin", "refs/heads/" + branch)
    return result.split()[0] if result else None


def fetch_base(repo: Path, branch: str, fallback: str) -> str:
    ref = branch if remote_sha(repo, branch) else fallback
    git(repo, "fetch", "--no-tags", "origin", "refs/heads/" + ref)
    return text(repo, "rev-parse", "FETCH_HEAD")


def publish_files(repo: Path, branch: str, base: str, files: dict[str, bytes], *,
                  replace_prefix: str | None, message: str) -> str:
    """Make one multi-file commit without touching the caller's real index.

    Only replace_prefix (when explicitly supplied) may lose old files. All other
    paths are preserved from base. A concurrent branch update rejects our push;
    it is never resolved by force-pushing or silently overwriting other work.
    """
    for path in files:
        if path.startswith("/") or ".." in path.split("/") or "\0" in path:
            raise ValueError("invalid repository path")
        if replace_prefix and not path.startswith(replace_prefix.rstrip("/") + "/"):
            raise ValueError("file outside the explicitly replaceable subtree")
    with tempfile.TemporaryDirectory(prefix="hermes-token-index-") as temp:
        index = Path(temp) / "index"  # must not exist before read-tree
        git(repo, "read-tree", base, index=index)
        records: list[bytes] = []
        if replace_prefix:
            for path in git(repo, "ls-tree", "-rz", "--name-only", base,
                            "--", replace_prefix.rstrip("/") + "/").split(b"\0"):
                if path:
                    records.append(b"0 " + b"0" * 40 + b"\t" + path + b"\0")
        for path, content in sorted(files.items()):
            sha = text(repo, "hash-object", "-w", "--stdin", data=content)
            records.append(b"100644 " + sha.encode() + b"\t" + path.encode() + b"\0")
        git(repo, "update-index", "-z", "--index-info", data=b"".join(records), index=index)
        tree = text(repo, "write-tree", index=index)
        if tree == text(repo, "rev-parse", base + "^{tree}"):
            sha = base
        else:
            sha = text(repo, "-c", "user.name=ChatGPT Artifact Delivery",
                       "-c", "user.email=artifact-delivery@localhost",
                       "commit-tree", tree, "-p", base, data=(message + "\n").encode())
        git(repo, "push", "origin", sha + ":refs/heads/" + branch)
        if remote_sha(repo, branch) != sha:
            raise RuntimeError("remote HEAD changed after push; reconcile before reporting delivery")
        git(repo, "fetch", "--no-tags", "origin", "refs/heads/" + branch)
        for path, content in files.items():
            if git(repo, "show", "FETCH_HEAD:" + path) != content:
                raise RuntimeError("remote file read-back mismatch: " + path)
        return sha


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="authenticated Lyric8/gpt clone or bare repository")
    args = parser.parse_args()
    repo = Path(args.repo).resolve(strict=True)
    source = Path(__file__).resolve().parents[1]
    # Read the configured URL literally: local Git URL rewriting may be intentional.
    remote = text(repo, "config", "--get", "remote.origin.url")
    if remote not in {"https://github.com/Lyric8/gpt.git", "https://github.com/Lyric8/gpt",
                      "git@github.com:Lyric8/gpt.git", "ssh://git@github.com/Lyric8/gpt.git"}:
        raise RuntimeError("origin is not the approved repository; refusing publication")
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=source)
    if result.returncode:
        raise RuntimeError("tests failed; nothing published")
    files = {}
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if any(p in {".git", "__pycache__", ".venv"} or p.endswith(".egg-info") for p in relative.parts):
            continue
        if path.is_symlink():
            raise RuntimeError("source symlinks are not allowed: " + str(relative))
        if path.is_file() and path.suffix not in {".zip", ".pyc"}:
            files[DESTINATION + "/" + relative.as_posix()] = path.read_bytes()
    base = fetch_base(repo, BRANCH, "hermes/20260918-token-audit")
    code_sha = publish_files(repo, BRANCH, base, files, replace_prefix=DESTINATION,
                             message="Deliver tested Hermes token control and audit plan")
    print(json.dumps({"stage": "CODE_PUBLISHED", "artifact_commit": code_sha}), flush=True)
    chat_base = fetch_base(repo, "chat", "chat")
    expected = json.loads((source / "config/protocol-snapshot.json").read_text())
    for path, sha in expected.items():
        if text(repo, "rev-parse", chat_base + ":" + path) != sha:
            raise RuntimeError("chat protocol changed: code published; plan requires protocol re-review")
    delivery_id = hashlib.sha256(("hermes-token-audit-20260918:" + code_sha).encode()).hexdigest()
    existing = []
    for raw_path in git(repo, "ls-tree", "-rz", "--name-only", chat_base,
                        "--", "chat/to-hermes/").split(b"\0"):
        if raw_path.endswith(b".md"):
            path = raw_path.decode()
            content = git(repo, "show", chat_base + ":" + path)
            if ("delivery_id=" + delivery_id).encode() in content:
                existing.append((path, content))
    if len(existing) > 1:
        raise RuntimeError("duplicate delivery identity; reconcile before proceeding")
    if existing:
        relative, notice = existing[0]
    else:
        now = datetime.now(timezone(timedelta(hours=8)))
        relative = "chat/to-hermes/" + now.strftime("%Y-%m-%dT%H%M%S+0800") + "-hermes-token-control-plan.md"
        header = ("slot=direct\nstatus=IMPLEMENTED_NOT_DEPLOYED\n"
                  "request_id=hermes-token-audit-20260918\n"
                  f"delivery_id={delivery_id}\nartifact_branch={BRANCH}\nartifact_commit={code_sha}\n"
                  f"artifact_path={DESTINATION}\n时间：{now.isoformat(timespec='seconds')}　作者：ChatGPT\n\n"
                  "这是当前直接对话的独立交付，不伪造 inbox source/claim/completion。"
                  "服务器尚未部署，不能据此标记节省目标已经验收。\n\n")
        notice = (header + (source / "docs/PLAN.md").read_text()).encode()
        if git(repo, "ls-tree", "--name-only", chat_base, "--", relative).strip():
            raise RuntimeError("immutable notice filename collision")
    chat_sha = publish_files(repo, "chat", chat_base, {relative: notice}, replace_prefix=None,
                             message="Deliver immutable Hermes token audit implementation plan")
    print(json.dumps({"status": "PUBLISHED_NOT_DEPLOYED", "artifact_branch": BRANCH,
                      "artifact_commit": code_sha, "chat_commit": chat_sha,
                      "plan_path": relative,
                      "plan_blob": text(repo, "hash-object", "--stdin", data=notice)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

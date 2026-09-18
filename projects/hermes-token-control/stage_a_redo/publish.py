"""Publish this verified source package using the host's existing Git auth.

No checkout, force push, credentials in arguments, production changes or chat
protocol writes. Only projects/hermes-token-control/stage_a_redo is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
PREFIX = "projects/hermes-token-control/stage_a_redo/"


def verified_files() -> dict[str, bytes]:
    result = {}
    for line in (PACKAGE / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or Path(name).is_absolute() or ".." in Path(name).parts or name in result:
            raise ValueError("invalid package manifest")
        path = PACKAGE / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("invalid package file")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("package checksum mismatch")
        result[name] = data
    result["SHA256SUMS"] = (PACKAGE / "SHA256SUMS").read_bytes()
    actual = {str(path.relative_to(PACKAGE)) for path in PACKAGE.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
    if actual != set(result):
        raise ValueError("unmanifested or missing files")
    return result


def publish(repo: Path, branch: str) -> dict:
    files = verified_files()
    if subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "stage_a_redo/tests"],
                      cwd=PACKAGE.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                      timeout=120, check=False).returncode:
        raise RuntimeError("package tests failed")
    private_ref = "refs/stage-a-publish/" + uuid.uuid4().hex
    env = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="stage-a-publish-") as directory:
        env["GIT_INDEX_FILE"] = str(Path(directory) / "index")
        def git(*args: str, data: bytes | None = None) -> bytes:
            result = subprocess.run(["git", "-C", str(repo), *args], input=data,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    env=env, timeout=90, check=False)
            if result.returncode:
                raise RuntimeError("git operation failed; inspect locally without disclosing credentials")
            return result.stdout
        git("check-ref-format", "refs/heads/" + branch)
        expected = {}
        for name, data in files.items():
            expected[PREFIX + name] = git("hash-object", "-w", "--stdin", data=data).decode().strip()
        def fetch() -> str:
            git("fetch", "--no-tags", "origin", "+refs/heads/" + branch + ":" + private_ref)
            return git("rev-parse", private_ref).decode().strip()
        def listing(commit: str) -> dict[str, str]:
            output = {}
            for record in git("ls-tree", "-rz", commit, "--", PREFIX).split(b"\0"):
                if record:
                    meta, path = record.split(b"\t", 1)
                    mode, kind, sha = meta.decode().split()
                    if mode != "100644" or kind != "blob":
                        raise ValueError("unexpected existing release object")
                    output[path.decode()] = sha
            return output
        try:
            for attempt in range(2):
                base = fetch()
                current = listing(base)
                if current == expected:
                    return {"status": "ALREADY_PUBLISHED_VERIFIED", "commit": base, "files_verified": len(files), "branch": branch}
                if any(path not in expected or expected[path] != sha for path, sha in current.items()):
                    raise RuntimeError("release path already contains different bytes; refusing overwrite")
                git("read-tree", base)
                for path, sha in expected.items():
                    git("update-index", "--add", "--cacheinfo", "100644," + sha + "," + path)
                tree = git("write-tree").decode().strip()
                commit = git("commit-tree", tree, "-p", base,
                             data=b"token-control: add tested no-hard-gate Stage A redo\n").decode().strip()
                try:
                    git("push", "origin", commit + ":refs/heads/" + branch)
                except RuntimeError:
                    if attempt == 0:
                        continue
                    raise
                remote = fetch()
                if listing(remote) != expected:
                    raise RuntimeError("push returned but remote source bytes differ; not verified")
                return {"status": "PUBLISHED_VERIFIED_NOT_DEPLOYED", "commit": commit,
                        "observed_remote_commit": remote, "branch": branch, "files_verified": len(files)}
            raise RuntimeError("publication exhausted")
        finally:
            git("update-ref", "-d", private_ref)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--branch", default="gpt/20260918-token-audit")
    args = parser.parse_args()
    try:
        print(json.dumps(publish(args.repo.resolve(strict=True), args.branch), sort_keys=True))
        return 0
    except Exception as exc:
        # Exact subprocess stderr remains local/private and is never exported.
        print(json.dumps({"status": "PUBLISH_FAILED", "error_class": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

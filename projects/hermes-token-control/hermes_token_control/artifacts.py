from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    """Durable local POSIX file replacement; fail on I/O errors, never truncate old data."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
        dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Artifacts:
    """Content-addressed evidence. Root must be private, on durable LOCAL storage."""
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    def put(self, data: bytes) -> dict[str, Any]:
        sha = hashlib.sha256(data).hexdigest()
        path = self.root / sha[:2] / sha
        if path.exists():
            if path.is_symlink() or path.read_bytes() != data:
                raise RuntimeError("content-addressed artifact collision/corruption")
        else:
            atomic_write(path, data)
        return {"sha256": sha, "bytes": len(data), "path": str(path)}

    def put_json(self, value: Any) -> dict[str, Any]:
        return self.put(canonical(value))

    def read(self, sha: str) -> bytes:
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("invalid artifact SHA-256")
        path = self.root / sha[:2] / sha
        if path.is_symlink():
            raise RuntimeError("artifact symlink refused")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise RuntimeError("artifact integrity failure")
        return data

    def envelope(self, data: bytes, *, max_preview_bytes: int = 4096) -> dict[str, Any]:
        if max_preview_bytes < 0 or max_preview_bytes > 8192:
            raise ValueError("preview limit must be between 0 and 8192 bytes")
        ref = self.put(data)  # Persist BEFORE replacing the visible representation.
        preview = data[:max_preview_bytes].decode("utf-8", errors="replace")
        return {"artifact": ref, "preview": preview,
                "truncated": len(data) > max_preview_bytes,
                "instruction": "Preview is not complete evidence. Read artifact ranges for details."}

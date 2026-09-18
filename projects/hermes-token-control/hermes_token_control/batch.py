from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .artifacts import Artifacts, canonical


def _one(spec: dict[str, Any], store: Artifacts, cwd: Path) -> dict[str, Any]:
    argv = spec.get("argv")
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) for a in argv):
        raise ValueError("argv must be a nonempty string array; shell text is not accepted")
    timeout = float(spec.get("timeout_seconds", 120))
    cap = int(spec.get("max_output_bytes", 32 * 1024 * 1024))
    if not 0 < timeout <= 3600 or not 1 <= cap <= 128 * 1024 * 1024:
        raise ValueError("invalid command resource limits")
    started = time.monotonic()
    stopped = None
    with tempfile.TemporaryDirectory(prefix="hbatch-", dir=store.root) as temp:
        out_path, err_path = Path(temp) / "stdout", Path(temp) / "stderr"
        with out_path.open("wb") as out, err_path.open("wb") as err:
            process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=err, start_new_session=True, shell=False)
            try:
                while process.poll() is None:
                    if time.monotonic() - started > timeout:
                        stopped = "TIMEOUT"
                    elif out_path.stat().st_size + err_path.stat().st_size > cap:
                        stopped = "OUTPUT_QUOTA_EXCEEDED"
                    if stopped:
                        os.killpg(process.pid, signal.SIGKILL)
                        break
                    time.sleep(0.025)
                code = process.wait()
            finally:
                # Kill remaining descendants; background subprocesses would invalidate
                # the evidence snapshot and must not outlive this bounded read batch.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            out.flush(); err.flush()
            os.fsync(out.fileno()); os.fsync(err.fileno())
        if out_path.stat().st_size + err_path.stat().st_size > cap:
            stopped = stopped or "OUTPUT_QUOTA_EXCEEDED"
        stdout = store.envelope(out_path.read_bytes(), max_preview_bytes=512)
        stderr = store.envelope(err_path.read_bytes(), max_preview_bytes=512)
    return {"id": spec["id"], "exit_code": code, "success": code == 0 and stopped is None,
            "stopped": stopped, "elapsed_seconds": round(time.monotonic()-started, 4),
            "complete": stopped is None, "stdout": stdout, "stderr": stderr}


def run_read_batch(specs: list[dict[str, Any]], store: Artifacts, *, cwd: str | Path,
                   workers: int = 4) -> dict[str, Any]:
    """ONLY reviewed independent observations/tests. This is not a security sandbox.

    Never batch dependent writes, mutation+verification, remote lease operations,
    or commands requiring separate authorization. Review argv at the tool boundary.
    """
    if not specs or len(specs) > 64 or not 1 <= workers <= 4:
        raise ValueError("batch requires 1..64 commands, 1..4 workers")
    ids = [s.get("id") for s in specs]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("command ids must be unique nonempty strings")
    if any(s.get("independent_read_only") is not True for s in specs):
        raise ValueError("only explicitly reviewed independent reads are accepted")
    path = Path(cwd).resolve(strict=True)
    if not path.is_dir():
        raise ValueError("working directory is not a directory")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, s, store, path) for s in specs]
        results = []
        for spec, future in zip(specs, futures):
            try:
                results.append(future.result())
            except Exception as exc:
                ref = store.put_json({"id": spec["id"], "error": type(exc).__name__, "detail": str(exc)})
                results.append({"id": spec["id"], "success": False, "complete": False,
                                "error": type(exc).__name__, "artifact": ref})
    manifest = store.put_json({"results": results, "expected_count": len(specs)})
    # Constant-size-per-command status envelope. Full output never travels through the LLM.
    return {"manifest": manifest, "expected_count": len(specs), "observed_count": len(results),
            "success": all(r["success"] for r in results),
            "results": [{k: r[k] for k in ("id", "success", "complete", "exit_code", "stopped", "artifact") if k in r}
                        for r in results],
            "failed_ids": [r["id"] for r in results if not r["success"]]}

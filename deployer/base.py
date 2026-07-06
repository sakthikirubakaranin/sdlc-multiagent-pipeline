"""Base deployer — shared subprocess runner with live log streaming."""
from __future__ import annotations
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional


LogCallback = Callable[[str], None]


class DeployError(Exception):
    pass


def run_cmd(
    cmd: list[str],
    cwd: Optional[Path] = None,
    env: Optional[dict] = None,
    log_cb: Optional[LogCallback] = None,
    timeout: int = 900,
) -> int:
    """
    Run a shell command, streaming each output line to log_cb.
    Returns the exit code. Raises DeployError on non-zero exit.
    """
    merged_env = {**os.environ, **(env or {})}
    log = log_cb or (lambda msg: print(msg))

    log(f"$ {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=merged_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def _stream():
        for line in proc.stdout:
            log(line.rstrip())

    t = threading.Thread(target=_stream, daemon=True)
    t.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise DeployError(f"Command timed out after {timeout}s: {' '.join(cmd)}")

    t.join(timeout=5)

    if proc.returncode != 0:
        raise DeployError(f"Command failed (exit {proc.returncode}): {' '.join(cmd)}")

    return proc.returncode


def check_tool(name: str) -> bool:
    """Return True if `name` CLI tool is on PATH."""
    import shutil
    return shutil.which(name) is not None


def prerequisite_check(tools: list[str]) -> dict[str, bool]:
    return {t: check_tool(t) for t in tools}

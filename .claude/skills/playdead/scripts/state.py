"""Tiny persistence layer for what's currently playing.

State lives under ``$PLAYDEAD_HOME`` (default ``~/.playdead``) so playback
commands issued in separate process invocations can find the running player.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def home() -> Path:
    root = os.environ.get("PLAYDEAD_HOME")
    path = Path(root).expanduser() if root else Path.home() / ".playdead"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_file() -> Path:
    return home() / "state.json"


def ipc_socket() -> Path:
    return home() / "mpv.sock"


def control_file() -> Path:
    return home() / "control.json"


def worker_log() -> Path:
    return home() / "worker.log"


def load() -> Dict[str, Any]:
    try:
        return json.loads(state_file().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(state: Dict[str, Any]) -> None:
    state_file().write_text(json.dumps(state, indent=2))


def clear() -> None:
    for p in (state_file(), control_file(), ipc_socket()):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def is_running() -> Optional[Dict[str, Any]]:
    """Return current state if a player process is still alive, else ``None``."""
    state = load()
    pid = state.get("pid")
    if not pid:
        return None
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError):
        return None
    return state

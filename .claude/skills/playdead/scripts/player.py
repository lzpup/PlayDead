"""Local audio playback for PlayDead.

Two backends:

  * **mpv** (preferred) — native playlists plus a JSON IPC socket, so
    play/pause/next/prev/status all work cleanly while it runs in the
    background.
  * **sequential fallback** — for boxes without mpv. A small background worker
    (see ``run_worker``) plays one stream at a time with ffplay/cvlc and obeys
    next/prev/stop via a control file. No pause/seek.

All playback happens on the *local* machine; nothing here touches the network
beyond the player streaming the archive.org URLs it is handed.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

import state

# Single-file players that can stream an http(s) URL, best first.
_SINGLE_FILE = [
    ("ffplay", ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ("cvlc", ["cvlc", "--play-and-exit", "--intf", "dummy"]),
    ("mpv", ["mpv", "--no-video", "--really-quiet"]),
]


def detect_player() -> Optional[str]:
    """Return the best available playback backend, or ``None``."""
    if shutil.which("mpv"):
        return "mpv"
    for name, _ in _SINGLE_FILE:
        if shutil.which(name):
            return "sequential"
    return None


def available_players() -> List[str]:
    names = ["mpv", "ffplay", "cvlc", "vlc"]
    return [n for n in names if shutil.which(n)]


# ---------------------------------------------------------------------------
# Starting playback
# ---------------------------------------------------------------------------

def play(playlist: List[Dict[str, Any]], meta: Dict[str, Any], start: int = 0) -> Dict[str, Any]:
    """Stop anything playing, then start ``playlist`` on the best backend."""
    stop()
    if not playlist:
        raise RuntimeError("nothing to play: empty playlist")

    backend = detect_player()
    if backend is None:
        raise RuntimeError(
            "no audio player found. Install one of: mpv (recommended), ffmpeg "
            "(ffplay), or vlc."
        )

    if backend == "mpv":
        st = _start_mpv(playlist, start)
    else:
        st = _start_sequential(playlist, start)

    st.update(
        {
            "identifier": meta.get("identifier", ""),
            "title": meta.get("title", ""),
            "date": meta.get("date", ""),
            "venue": meta.get("venue", ""),
            "source_type": meta.get("source_type", ""),
            "playlist": playlist,
            "started_at": time.time(),
        }
    )
    state.save(st)
    return st


def _start_mpv(playlist: List[Dict[str, Any]], start: int) -> Dict[str, Any]:
    sock = str(state.ipc_socket())
    try:
        state.ipc_socket().unlink()
    except FileNotFoundError:
        pass
    urls = [t["url"] for t in playlist]
    cmd = [
        "mpv",
        "--no-video",
        "--no-terminal",
        "--really-quiet",
        f"--input-ipc-server={sock}",
        f"--playlist-start={max(0, start)}",
        *urls,
    ]
    log = open(state.worker_log(), "ab")
    proc = subprocess.Popen(
        cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True
    )
    return {"backend": "mpv", "pid": proc.pid, "ipc_socket": sock, "index": start}


def _start_sequential(playlist: List[Dict[str, Any]], start: int) -> Dict[str, Any]:
    # Reset control channel, then spawn this module's worker entrypoint.
    try:
        state.control_file().unlink()
    except FileNotFoundError:
        pass
    log = open(state.worker_log(), "ab")
    cmd = [sys.executable, os.path.abspath(__file__), "--worker", str(start)]
    proc = subprocess.Popen(
        cmd,
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ},
    )
    return {"backend": "sequential", "pid": proc.pid, "index": start}


# ---------------------------------------------------------------------------
# Transport controls
# ---------------------------------------------------------------------------

def _backend() -> Optional[str]:
    st = state.is_running()
    return st.get("backend") if st else None


def pause() -> str:
    backend = _backend()
    if backend == "mpv":
        _mpv_command(["cycle", "pause"])
        return "toggled pause"
    if backend == "sequential":
        return "pause/resume needs mpv; the sequential player can't pause"
    return "nothing is playing"


def nxt() -> str:
    backend = _backend()
    if backend == "mpv":
        _mpv_command(["playlist-next", "force"])
        return "skipped to next track"
    if backend == "sequential":
        _send_control("next")
        return "skipped to next track"
    return "nothing is playing"


def prev() -> str:
    backend = _backend()
    if backend == "mpv":
        _mpv_command(["playlist-prev", "force"])
        return "went to previous track"
    if backend == "sequential":
        _send_control("prev")
        return "went to previous track"
    return "nothing is playing"


def stop() -> str:
    st = state.load()
    backend = st.get("backend")
    if backend == "mpv":
        try:
            _mpv_command(["quit"], socket_path=st.get("ipc_socket"))
        except Exception:  # noqa: BLE001 - fall through to SIGTERM
            pass
    elif backend == "sequential":
        _send_control("stop")
    pid = st.get("pid")
    if pid:
        _terminate(int(pid))
    state.clear()
    return "stopped" if backend else "nothing was playing"


def _terminate(pid: int) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(pid), sig)
        except ProcessLookupError:
            return
        except OSError:
            try:
                os.kill(pid, sig)
            except OSError:
                return
        time.sleep(0.3)
        try:
            os.kill(pid, 0)
        except OSError:
            return


def status() -> Dict[str, Any]:
    st = state.is_running()
    if not st:
        return {"playing": False}
    playlist = st.get("playlist", [])
    index = st.get("index", 0)

    out: Dict[str, Any] = {
        "playing": True,
        "backend": st.get("backend"),
        "identifier": st.get("identifier"),
        "title": st.get("title"),
        "date": st.get("date"),
        "venue": st.get("venue"),
        "source_type": st.get("source_type"),
        "track_count": len(playlist),
    }
    if st.get("backend") == "mpv":
        index = _mpv_get("playlist-pos", default=index) or 0
        out["paused"] = bool(_mpv_get("pause", default=False))
        pos = _mpv_get("time-pos")
        if pos is not None:
            out["position_sec"] = round(float(pos), 1)
    else:
        index = state.load().get("index", index)
    out["index"] = index
    if 0 <= index < len(playlist):
        out["now_playing"] = playlist[index].get("title")
    return out


# ---------------------------------------------------------------------------
# mpv JSON IPC
# ---------------------------------------------------------------------------

def _mpv_command(command: List[Any], socket_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    sock_path = socket_path or state.load().get("ipc_socket") or str(state.ipc_socket())
    payload = json.dumps({"command": command}).encode() + b"\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            s.connect(sock_path)
            s.sendall(payload)
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
            for line in buf.splitlines():
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "error" in msg:  # the reply (events lack an "error" key)
                    return msg
    except (OSError, socket.timeout):
        return None
    return None


def _mpv_get(prop: str, default: Any = None) -> Any:
    reply = _mpv_command(["get_property", prop])
    if reply and reply.get("error") == "success":
        return reply.get("data", default)
    return default


# ---------------------------------------------------------------------------
# Sequential fallback: control channel + worker
# ---------------------------------------------------------------------------

def _send_control(cmd: str) -> None:
    prev = {}
    try:
        prev = json.loads(state.control_file().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    seq = int(prev.get("seq", 0)) + 1
    state.control_file().write_text(json.dumps({"cmd": cmd, "seq": seq}))


def _single_file_cmd() -> List[str]:
    for name, base in _SINGLE_FILE:
        if shutil.which(name):
            return base
    raise RuntimeError("no single-file player available")


def run_worker(start: int) -> None:
    """Background loop for the sequential backend. Not used with mpv."""
    base_cmd = _single_file_cmd()
    last_seq = 0
    index = start

    def read_playlist() -> List[Dict[str, Any]]:
        return state.load().get("playlist", [])

    def poll_control():
        nonlocal last_seq
        try:
            ctl = json.loads(state.control_file().read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        if int(ctl.get("seq", 0)) > last_seq:
            last_seq = int(ctl.get("seq", 0))
            return ctl.get("cmd")
        return None

    while True:
        playlist = read_playlist()
        if not playlist or index < 0:
            index = 0
        if index >= len(playlist):
            break  # reached the end of the show

        st = state.load()
        st["index"] = index
        state.save(st)

        proc = subprocess.Popen(
            base_cmd + [playlist[index]["url"]],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )

        advance = 1
        while proc.poll() is None:
            cmd = poll_control()
            if cmd == "stop":
                proc.terminate()
                state.clear()
                return
            if cmd == "next":
                proc.terminate()
                advance = 1
                break
            if cmd == "prev":
                proc.terminate()
                advance = -1
                break
            time.sleep(0.4)
        index += advance

    state.clear()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--worker":
        start_index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        run_worker(start_index)

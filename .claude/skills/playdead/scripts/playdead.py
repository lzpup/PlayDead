#!/usr/bin/env python3
"""PlayDead — a command-line jukebox for Grateful Dead tapes on archive.org.

This is the single entrypoint the skill drives. Claude translates natural
language ("play the Cornell show", "next song") into these subcommands:

    playdead.py search "<query>"        find shows (ranked, best first)
    playdead.py best   "<date|query>"   resolve the best recording, print it
    playdead.py show   <identifier>     show details + tracklist
    playdead.py play   "<target>"       resolve + start playing locally
    playdead.py pause | next | prev | stop | status | queue

A "target" may be a date (1977-05-08, 5/8/77), an archive.org identifier, a
famous-show nickname ("cornell"), or free text ("Veneta 1972 soundboard").

Add --json to any command for machine-readable output.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

import archive
import famous_shows
import player
import state


# ---------------------------------------------------------------------------
# Target resolution
# ---------------------------------------------------------------------------

def resolve_target(target: str) -> Dict[str, Any]:
    """Resolve a free-form target string to a chosen show dict.

    Order: explicit identifier > famous-show alias > date > free text.
    Returns a show dict (at least ``identifier``); raises on no match.
    """
    target = target.strip()
    if archive.is_identifier(target):
        return {"identifier": target, "title": target}

    alias = famous_shows.resolve_alias(target)
    if alias:
        date, venue = alias
        show = archive.best_tape(query=venue, date=date)
        if show:
            return show

    date = archive.parse_date(target)
    show = archive.best_tape(query=target if not date else None, date=date)
    if show:
        return show
    raise SystemExit(f"no Grateful Dead show found for: {target!r}")


def _ensure_show_meta(show: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch metadata + build the playlist for a resolved show."""
    ident = show["identifier"]
    md = archive.get_metadata(ident)
    item = md.get("metadata", {})
    playlist = archive.build_playlist(md)
    if not playlist:
        raise SystemExit(f"no playable audio files in '{ident}'")
    meta = {
        "identifier": ident,
        "title": show.get("title") or item.get("title", ident),
        "date": show.get("date") or _first(item.get("date", "")),
        "venue": show.get("venue") or _first(item.get("venue", "")),
        "source_type": show.get("source_type") or archive.classify_source({"identifier": ident, "title": item.get("title", "")}),
    }
    return {"meta": meta, "playlist": playlist}


def _first(v: Any) -> Any:
    return v[0] if isinstance(v, list) and v else v


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_search(args) -> Dict[str, Any]:
    shows = archive.search_shows(query=args.query, rows=args.rows)
    shows.sort(key=lambda s: s["score"], reverse=True)
    return {"count": len(shows), "results": shows}


def cmd_best(args) -> Dict[str, Any]:
    show = resolve_target(args.target)
    return {"best": show}


def cmd_show(args) -> Dict[str, Any]:
    show = resolve_target(args.target)
    info = _ensure_show_meta(show)
    return {**info["meta"], "tracks": info["playlist"]}


def cmd_play(args) -> Dict[str, Any]:
    show = resolve_target(args.target)
    info = _ensure_show_meta(show)
    st = player.play(info["playlist"], info["meta"], start=args.track)
    return {
        "started": True,
        "backend": st["backend"],
        "title": info["meta"]["title"],
        "date": info["meta"]["date"],
        "venue": info["meta"]["venue"],
        "source_type": info["meta"]["source_type"],
        "track_count": len(info["playlist"]),
        "now_playing": info["playlist"][min(args.track, len(info["playlist"]) - 1)]["title"],
    }


def cmd_pause(_args) -> Dict[str, Any]:
    return {"message": player.pause()}


def cmd_next(_args) -> Dict[str, Any]:
    return {"message": player.nxt()}


def cmd_prev(_args) -> Dict[str, Any]:
    return {"message": player.prev()}


def cmd_stop(_args) -> Dict[str, Any]:
    return {"message": player.stop()}


def cmd_status(_args) -> Dict[str, Any]:
    return player.status()


def cmd_queue(_args) -> Dict[str, Any]:
    st = state.is_running() or state.load()
    return {
        "title": st.get("title"),
        "index": st.get("index", 0),
        "tracks": st.get("playlist", []),
    }


# ---------------------------------------------------------------------------
# Human-readable rendering
# ---------------------------------------------------------------------------

def render(command: str, data: Dict[str, Any]) -> str:
    if command == "search":
        return _render_show_list(data["results"])
    if command == "best":
        return _render_show_line(data["best"], prefix="Best tape: ")
    if command == "show":
        lines = [
            f"{data.get('title')}  [{data.get('source_type')}]",
            f"{data.get('date')}  {data.get('venue')}",
            f"{data.get('identifier')}",
            "",
        ]
        for i, t in enumerate(data.get("tracks", [])):
            lines.append(f"  {i + 1:2d}. {t['title']}")
        return "\n".join(lines)
    if command in ("play",):
        return (
            f"▶ Now playing: {data['title']}\n"
            f"  {data['date']}  {data['venue']}  [{data['source_type']}]\n"
            f"  {data['track_count']} tracks via {data['backend']} — first up: {data['now_playing']}"
        )
    if command == "status":
        if not data.get("playing"):
            return "Nothing is playing."
        line = f"♪ {data.get('now_playing')}  ({data.get('title')})"
        extra = []
        if data.get("paused"):
            extra.append("paused")
        if data.get("index") is not None:
            extra.append(f"track {data['index'] + 1}/{data.get('track_count')}")
        return line + ("  [" + ", ".join(extra) + "]" if extra else "")
    if command == "queue":
        lines = [f"Queue: {data.get('title')}"]
        idx = data.get("index", 0)
        for i, t in enumerate(data.get("tracks", [])):
            mark = "→" if i == idx else " "
            lines.append(f" {mark} {i + 1:2d}. {t['title']}")
        return "\n".join(lines)
    return data.get("message", json.dumps(data))


def _render_show_list(shows: List[Dict[str, Any]]) -> str:
    if not shows:
        return "No shows found."
    lines = [f"Found {len(shows)} show(s):", ""]
    for s in shows:
        lines.append(_render_show_line(s))
    return "\n".join(lines)


def _render_show_line(s: Dict[str, Any], prefix: str = "") -> str:
    rating = f"{s.get('avg_rating', 0):.1f}★" if s.get("avg_rating") else "—"
    return (
        f"{prefix}{s.get('date', '????'):10}  [{s.get('source_type', '?'):6}] "
        f"{rating:5}  {s.get('venue') or s.get('title', '')}\n"
        f"           {s.get('identifier')}"
    )


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    # A shared parent so --json works either before or after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    # SUPPRESS default so a subparser's copy doesn't clobber --json given earlier.
    common.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS,
        help="emit JSON instead of text",
    )

    p = argparse.ArgumentParser(prog="playdead", description=__doc__, parents=[common])
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", parents=[common], help="search the GratefulDead collection")
    s.add_argument("query")
    s.add_argument("--rows", type=int, default=25)
    s.set_defaults(func=cmd_search)

    b = sub.add_parser("best", parents=[common], help="resolve the best tape for a date/query")
    b.add_argument("target")
    b.set_defaults(func=cmd_best)

    sh = sub.add_parser("show", parents=[common], help="show details + tracklist")
    sh.add_argument("target")
    sh.set_defaults(func=cmd_show)

    pl = sub.add_parser("play", parents=[common], help="resolve and start playing locally")
    pl.add_argument("target")
    pl.add_argument("--track", type=int, default=0, help="0-based track to start on")
    pl.set_defaults(func=cmd_play)

    for name, fn, help_ in [
        ("pause", cmd_pause, "toggle pause (mpv only)"),
        ("next", cmd_next, "skip to next track"),
        ("prev", cmd_prev, "go to previous track"),
        ("stop", cmd_stop, "stop playback"),
        ("status", cmd_status, "what's playing now"),
        ("queue", cmd_queue, "show the current playlist"),
    ]:
        sp = sub.add_parser(name, parents=[common], help=help_)
        sp.set_defaults(func=fn)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        data = args.func(args)
    except archive.ArchiveError as exc:
        _emit(args, {"error": str(exc)}, is_error=True)
        return 2
    except SystemExit as exc:
        if isinstance(exc.code, str):
            _emit(args, {"error": exc.code}, is_error=True)
            return 2
        raise
    _emit(args, data, command=args.command)
    return 0


def _emit(args, data: Dict[str, Any], command: str = "", is_error: bool = False) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2))
    elif is_error:
        print(f"Error: {data['error']}", file=sys.stderr)
    else:
        print(render(command, data))


if __name__ == "__main__":
    raise SystemExit(main())

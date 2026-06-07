"""The seam between Claude and deadstream.

`TOOLS` is the list of tool definitions handed to the Anthropic API. `dispatch`
executes one tool call against a `DeadStream` instance and returns a JSON string
for the `tool_result` block. Nothing here knows about the agent loop, and the
agent loop knows nothing about deadstream — this module is the only thing that
bridges the two.
"""

from __future__ import annotations

import json

from playdead.player import DeadStream

TOOLS = [
    {
        "name": "list_shows",
        "description": (
            "List Grateful Dead shows available on archive.org for a given year "
            "and (optionally) month, with venue, average listener rating, and a "
            "composite quality score. Results are sorted best-first. Call this to "
            "decide which date is the 'best' show in a period before playing it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "Four-digit year, e.g. 1977"},
                "month": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 12,
                    "description": "Month 1-12. Omit to require a year-wide search "
                    "(currently month is required for a bounded result).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max shows to return (default 10).",
                },
            },
            "required": ["year", "month"],
        },
    },
    {
        "name": "play_show",
        "description": (
            "Load the highest-rated recording for an exact date and start playback. "
            "Pass a date you chose from list_shows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Show date as YYYY-MM-DD, e.g. 1977-05-08",
                }
            },
            "required": ["date"],
        },
    },
    {
        "name": "playback_control",
        "description": "Control the active player: pause, resume, stop, skip tracks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["pause", "resume", "stop", "next", "previous"],
                }
            },
            "required": ["action"],
        },
    },
    {
        "name": "now_playing",
        "description": "Report the currently loaded tape and track, if any.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def dispatch(player: DeadStream, name: str, args: dict) -> str:
    """Run one tool call and return a JSON string for the tool_result block."""
    try:
        result = _run(player, name, args)
        return json.dumps(result, default=str)
    except Exception as exc:  # surface failures to Claude rather than crashing
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})


def _run(player: DeadStream, name: str, args: dict):
    if name == "list_shows":
        limit = args.get("limit", 10)
        shows = player.shows_in_month(args["year"], args["month"])
        return [s.as_dict() for s in shows[:limit]]

    if name == "play_show":
        return player.play_show(args["date"]).as_dict()

    if name == "playback_control":
        return {"status": player.control(args["action"])}

    if name == "now_playing":
        return player.now_playing()

    raise ValueError(f"unknown tool: {name}")

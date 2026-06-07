"""Interactive REPL for PlayDead.

    python -m playdead.cli

Type requests in plain language; Ctrl-C or "quit" to exit.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY first.", file=sys.stderr)
        return 1

    try:
        from playdead.agent import PlayDeadAgent
    except ImportError as exc:
        print(f"Missing dependency: {exc}\nTry: pip install -r requirements.txt", file=sys.stderr)
        return 1

    agent = PlayDeadAgent()
    print("🌹⚡💀 PlayDead — ask for a show (Ctrl-C to quit)")

    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text.lower() in {"quit", "exit"}:
            return 0
        try:
            print(agent.ask(text))
        except Exception as exc:  # keep the REPL alive on transient errors
            print(f"  ! {type(exc).__name__}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())

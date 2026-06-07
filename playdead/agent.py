"""The natural-language layer.

A manual Claude tool-use loop: send the conversation, run any tools Claude
asks for, feed the results back, repeat until it produces a final reply. The
manual loop (vs. the SDK tool runner) keeps the seam explicit — you can see
exactly where deadstream gets called — and makes it easy to add confirmation
gates or logging around playback actions later.
"""

from __future__ import annotations

import anthropic

from playdead.player import DeadStream
from playdead.tools import TOOLS, dispatch

MODEL = "claude-opus-4-8"

SYSTEM = """\
You are PlayDead, a Grateful Dead tape DJ. The user asks for shows in plain
language ("play the best tape from May 1977", "skip this one", "what's on?")
and you drive a real archive.org player through your tools.

How to choose a show:
- "Best" means highest composite score; when scores are close, prefer the
  higher average listener rating, then the more storied venue.
- Resolve fuzzy references to a concrete date with list_shows BEFORE play_show.
  Never guess a date — look it up.
- If the user names an exact date, you can play it directly.

Keep replies short and in a tape-trader's voice. When you start a show, name
the date and venue and add one line of color if it's a famous run (e.g. Cornell
'77, Europe '72). Don't dump raw tool output.
"""


class PlayDeadAgent:
    """Stateful conversation wrapper around the Claude tool-use loop."""

    def __init__(self, player: DeadStream | None = None, model: str = MODEL) -> None:
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.player = player or DeadStream()
        self.model = model
        self.messages: list[dict] = []

    def ask(self, user_text: str) -> str:
        """Send one user turn; return Claude's final natural-language reply."""
        self.messages.append({"role": "user", "content": user_text})

        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                thinking={"type": "adaptive"},
                system=SYSTEM,
                tools=TOOLS,
                messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return _final_text(response)

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = dispatch(self.player, block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
            self.messages.append({"role": "user", "content": tool_results})


def _final_text(response) -> str:
    return "\n".join(b.text for b in response.content if b.type == "text").strip()

---
name: playdead
description: >-
  Play, search, and control Grateful Dead concert recordings ("tapes") streamed
  from the Internet Archive (archive.org), with natural-language control on the
  user's local machine. Use whenever the user wants to listen to the Grateful
  Dead — e.g. "play the Cornell '77 show", "play 5/8/77", "put on a soundboard
  from 1972", "find the best Dark Star", "next song", "what's playing", "pause",
  "stop the music".
---

# PlayDead — Grateful Dead time machine

PlayDead turns natural language into Grateful Dead playback. You (Claude)
interpret what the user means, then call the bundled `playdead.py` CLI, which
searches archive.org, picks the best recording, and drives a **local** audio
player.

## When to use this skill

Trigger on any request to listen to, find, or control Grateful Dead music:
playing a show by date/venue/nickname, browsing tapes, or transport controls
(next, previous, pause, stop, status).

## Prerequisites (local machine)

- **Python 3.8+** (no third-party packages required — standard library only).
- **An audio player.** `mpv` is strongly recommended because it enables
  pause / next / previous / status. Without it, PlayDead falls back to
  `ffplay` (from ffmpeg) or `cvlc` (VLC), which support play / next / prev /
  stop but **not** pause/seek.
  - macOS: `brew install mpv`
  - Debian/Ubuntu: `sudo apt install mpv`
- **Network access to archive.org.**

If no player is found, tell the user which one to install (prefer `mpv`).

## How to drive it

Run the CLI from the skill's `scripts/` directory. Add `--json` whenever you
need to parse the result; omit it to show the user friendly text.

```
python scripts/playdead.py <command> [args] [--json]
```

### Commands

| Intent (what the user says) | Command |
| --- | --- |
| "play the Cornell show", "play 5/8/77", "put on Veneta '72" | `play "<target>"` |
| "play the second set" / start mid-show | `play "<target>" --track N` (0-based) |
| "find soundboards from 1977", "search Dark Star 1973" | `search "<query>"` |
| "what's the best version of 2/13/70?" | `best "<date or query>"` |
| "show me the setlist", "what's on this tape?" | `show "<target>"` |
| "next song" / "skip" | `next` |
| "go back" / "previous" | `prev` |
| "pause" / "resume" | `pause` |
| "stop" | `stop` |
| "what's playing?" | `status` |
| "show the queue / setlist" | `queue` |

A **`<target>`** can be:
- a date — `1977-05-08`, `5/8/77`, `5-8-1977`
- an archive.org identifier — `gd1977-05-08.sbd.hicks.4982.sbeok.shnf`
- a famous-show nickname — `cornell`, `veneta`, `watkins glen`
- free text — `"Barton Hall 1977 soundboard"`, `"Veneta 1972"`

### Translating natural language

1. **Map nicknames and partial dates to a target.** You already know the
   canon (Cornell = 5/8/77 Barton Hall; Veneta/Sunshine Daydream = 8/27/72;
   Europe '72; Closing of Winterland = 12/31/78, etc.). Pass the most specific
   target you can — a date is best. The CLI also resolves common nicknames on
   its own, so passing `"cornell"` works too.
2. **"Best" / "good" / unspecified recording** → just use `play "<date>"`.
   The CLI ranks results and auto-picks the best tape (soundboards and
   matrices beat audience tapes; then ratings, then popularity).
3. **Specific lineage** ("soundboard", "matrix", "audience") → include the word
   in the query, e.g. `search "1972-08-27 soundboard"`, then `play` the chosen
   identifier.
4. **Browsing** → use `search`, summarize the top few, and offer to play one.
5. **Transport controls** map directly to `next`/`prev`/`pause`/`stop`/`status`.

### Examples

User: *"Play the Cornell show."*
```
python scripts/playdead.py play "cornell"
```

User: *"Put on a soundboard from May 8th 1977, start at track 5."*
```
python scripts/playdead.py play "1977-05-08 soundboard" --track 4
```

User: *"What are the best-rated 1972 shows?"*
```
python scripts/playdead.py search "1972" --json
```
Then summarize the top results (they come back ranked best-first).

User: *"Next song" / "what's playing?" / "stop"*
```
python scripts/playdead.py next
python scripts/playdead.py status
python scripts/playdead.py stop
```

## Notes & gotchas

- Playback runs in the background and persists across CLI calls (state lives in
  `~/.playdead/`, overridable with `$PLAYDEAD_HOME`). So `play` in one call and
  `next`/`status`/`stop` in later calls all refer to the same session.
- Only one show plays at a time; `play` stops any current playback first.
- pause/seek require `mpv`. If `status` shows backend `sequential` and the user
  asks to pause, explain that pausing needs `mpv` installed.
- If a search returns nothing, widen it (drop the lineage word, try the year,
  or confirm the date with the user).
- All audio streams from archive.org to the user's machine; PlayDead never
  downloads full shows to disk.

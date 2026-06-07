# PlayDead 💀🌹

A Grateful Dead time machine you talk to in plain English. PlayDead is a
**Claude Code skill** that searches [archive.org](https://archive.org)'s
legendary GratefulDead collection, picks the best recording, and streams it on
your **local machine** — driven entirely by natural language.

> "Play the Cornell show." · "Put on a soundboard from 8/27/72." ·
> "What's the best-rated '77 tape?" · "Next song." · "What's playing?"

## How it works

```
You (natural language)
      │
      ▼
Claude  ──reads──▶  .claude/skills/playdead/SKILL.md   (NL → command mapping)
      │
      ▼
playdead.py  ──▶  archive.org  (search + best-tape ranking + stream URLs)
      │
      ▼
local audio player (mpv / ffplay / vlc)  ──▶  🔊
```

Claude does the language understanding; the bundled `playdead.py` CLI does the
deterministic work. "Best tape" selection favors **soundboards and matrices**
over audience recordings, then weighs ratings and popularity — the way a
Deadhead would choose.

## Requirements

- **Python 3.8+** — standard library only, no `pip install` needed.
- **An audio player** (install one):
  - **`mpv`** *(recommended)* — enables pause / next / previous / status.
    `brew install mpv` · `sudo apt install mpv`
  - or `ffplay` (from ffmpeg) / `cvlc` (VLC) — support play / next / prev /
    stop, but not pause.
- **Network access to archive.org.**

## Using it with Claude Code

Once the skill is on your skill path (it lives in `.claude/skills/playdead/`),
just ask Claude to play the Dead. Claude invokes the skill and the right
commands automatically.

## Using the CLI directly

```bash
cd .claude/skills/playdead/scripts

python3 playdead.py play "cornell"               # famous-show nickname
python3 playdead.py play "1977-05-08"            # by date
python3 playdead.py play "Veneta 1972 soundboard"  # free text + lineage
python3 playdead.py search "1972" --json         # browse, best-first
python3 playdead.py best "1970-05-02"            # just resolve the best tape
python3 playdead.py show "cornell"               # details + setlist

python3 playdead.py status      # what's playing
python3 playdead.py next        # skip
python3 playdead.py prev        # back
python3 playdead.py pause       # toggle (mpv)
python3 playdead.py queue       # the loaded setlist
python3 playdead.py stop
```

A **target** can be a date (`1977-05-08`, `5/8/77`), an archive.org identifier
(`gd1977-05-08.sbd.hicks.4982.sbeok.shnf`), a nickname (`cornell`, `veneta`),
or free text. Add `--json` to any command for machine-readable output.

Playback runs in the background; state lives in `~/.playdead/` (override with
`$PLAYDEAD_HOME`), so `play` and later `next`/`status`/`stop` share one session.

## Project layout

```
.claude/skills/playdead/
  SKILL.md              # what Claude reads: when to use + NL → command mapping
  scripts/
    playdead.py         # CLI entrypoint (search/best/show/play/transport)
    archive.py          # archive.org search, best-tape ranking, playlists
    player.py           # local playback: mpv (IPC) + sequential fallback
    state.py            # background-playback state under ~/.playdead/
    famous_shows.py     # nickname → date/venue lookups
tests/
  test_playdead.py      # offline tests for the non-network logic
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Covers date parsing, best-tape ranking, playlist building, nickname
resolution, and state persistence — the parts that don't need the network or a
player.

## Notes

- Audio streams from archive.org; PlayDead never downloads whole shows to disk.
- One show plays at a time — `play` stops anything already playing.
- pause/seek require `mpv`.

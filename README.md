# PlayDead

Natural-language control for Grateful Dead tapes on archive.org.

> *"Play the best tape from May 1977"* → Claude picks the date → [deadstream]
> fetches the highest-rated recording and plays it.

PlayDead is the glue between two pieces:

| Layer | What it does | Library |
|-------|--------------|---------|
| **Playback** | Browse the GD collection on archive.org, score tapes, stream audio | [`deadstream`](https://github.com/eichblatt/deadstream) (the `timemachine` package) |
| **Language** | Turn "best tape from May '77" into a concrete date + action | Claude (Anthropic API) via tool use |

The language layer never streams audio and the playback layer never talks to
an LLM. They meet at four tools (`list_shows`, `play_show`, `playback_control`,
`now_playing`) that Claude calls. That seam is the whole project.

## How it fits together

```
You ──"play the best tape from May 1977"──▶ agent.py (Claude + tools)
                                                │
                          list_shows(1977, 5) ──┤  Claude reasons over
                          play_show("1977-05-08")  ratings & venues,
                                                │   then acts
                                                ▼
                                          player.py (DeadStream adapter)
                                                │
                                                ▼
                              timemachine.GDArchive / GDPlayer ──▶ archive.org
```

## Layout

```
playdead/
  player.py    # DeadStream adapter — wraps timemachine's GDArchive + GDPlayer
  tools.py     # Anthropic tool schemas + dispatch onto a DeadStream instance
  agent.py     # The natural-language layer: a manual Claude tool-use loop
  cli.py       # Interactive REPL ("> play the best tape from May 1977")
```

## Quick start

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python -m playdead.cli
```

```
🌹⚡💀 PlayDead — ask for a show
> play the best tape from May 1977
  ▶ Cornell '77 — Barton Hall, Cornell University, Ithaca, NY (1977-05-08)
    avg rating 4.96 · the famous one
> pause
  ⏸ paused
> what's playing?
  Scarlet Begonias → Fire on the Mountain
```

## A note on `deadstream` / `timemachine`

`deadstream` was built for a Raspberry-Pi "time machine" appliance, so its
`setup.py` pulls in hardware deps (`RPi.GPIO`, `gpiozero`, `adafruit-blinka`).
The two modules PlayDead actually touches — `Archivary` (metadata/scoring) and
`GD` (an `mpv`-backed player) — don't need the GPIO stack, but importing the
package can. On a non-Pi machine, install just what you need:

```bash
pip install python-mpv requests tenacity   # runtime deps of GD + Archivary
pip install "git+https://github.com/eichblatt/deadstream.git#egg=timemachine"
```

`player.py` isolates every `timemachine` call behind one adapter class, so if
you'd rather drive the archive.org API and `mpv` directly (no GPIO at all), you
only reimplement `player.py` — `tools.py` and `agent.py` are untouched.

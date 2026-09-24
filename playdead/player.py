"""DeadStream — a thin adapter over the `timemachine` (deadstream) library.

This is the *only* file that imports `timemachine`. Everything Claude does goes
through the small, stable surface defined here:

    shows_in_month(year, month) -> list[ShowInfo]   # browse + score
    play_show(date)             -> ShowInfo          # load best tape, play
    control(action)             -> str               # pause/resume/stop/next/previous
    now_playing()               -> dict              # current tape + track

If you'd rather not depend on the Pi-oriented `timemachine` package, reimplement
this class against the archive.org API + `mpv` directly; the agent and tool
layers don't care how it's backed.

Reference for the underlying API:
    timemachine.Archivary.GDArchive — .best_tape(date), .dates, .tape_dates
    timemachine.GD.GDPlayer         — .insert_tape, .play, .pause, .stop, .next, .prev
    GDTape                          — .compute_score(), .venue(), .avg_rating, .tracks()
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass


@dataclass
class ShowInfo:
    """A single Grateful Dead recording, summarized for the language layer."""

    date: str           # "YYYY-MM-DD"
    venue: str          # "venue, city, state"
    avg_rating: float   # archive.org average user rating (0-5)
    score: float        # deadstream's composite ranking score
    identifier: str     # archive.org item identifier

    def as_dict(self) -> dict:
        return asdict(self)


class DeadStream:
    """Wraps a deadstream `GDArchive` + `GDPlayer` for one collection.

    Loading the archive downloads/caches the tape index on first use, so it is
    deferred until the first call rather than done in ``__init__``.
    """

    def __init__(self, collection: str = "GratefulDead") -> None:
        self.collection = collection
        self._archive = None   # timemachine.Archivary.GDArchive
        self._player = None    # timemachine.GD.GDPlayer
        self._gd = None        # the timemachine.GD module

    # -- lazy library wiring ------------------------------------------------

    @property
    def archive(self):
        if self._archive is None:
            from timemachine import Archivary, config

            # timemachine reads options (e.g. PLAY_LOSSLESS) from config.optd,
            # which is empty until something populates it. Use its defaults.
            if not config.optd:
                # Off a Pi (e.g. macOS) there's no /etc/os-release, so
                # os_version is None and default_options() can't compare it.
                if config.os_version is None:
                    config.os_version = 0
                config.optd = config.default_options()

            # Loads the tape index for the collection (network on first run).
            self._archive = Archivary.GDArchive(collection_list=[self.collection])
        return self._archive

    @property
    def _gd_module(self):
        if self._gd is None:
            from timemachine import GD

            # GDPlayer() runs `sudo service pulseaudio stop/restart` on every
            # init — meant for the Pi appliance. Elsewhere it's a password
            # prompt (or failure) per show, so make those calls no-ops.
            if not sys.platform.startswith("linux"):
                GD.GDPlayer.stop_pulse_audio = lambda self: None
                GD.GDPlayer.restart_pulse_audio = lambda self: None

            self._gd = GD
        return self._gd

    # -- browsing & scoring -------------------------------------------------

    def shows_in_month(self, year: int, month: int) -> list[ShowInfo]:
        """Best tape for each show date in the given month, best score first."""
        prefix = f"{year:04d}-{month:02d}"
        dates = [d for d in self.archive.dates if d.startswith(prefix)]
        shows = [self._summarize(self.archive.best_tape(d)) for d in dates]
        shows.sort(key=lambda s: s.score, reverse=True)
        return shows

    def best_show_on(self, date: str) -> ShowInfo:
        """Summarize the best-scored tape for an exact date ("YYYY-MM-DD")."""
        return self._summarize(self.archive.best_tape(date))

    # -- playback -----------------------------------------------------------

    def play_show(self, date: str) -> ShowInfo:
        """Load the best tape for `date` into the player and start playback."""
        tape = self.archive.best_tape(date)
        self._player = self._gd_module.GDPlayer(tape)
        self._player.play()
        return self._summarize(tape)

    def control(self, action: str) -> str:
        """Drive the active player. Returns a short human-readable status."""
        if self._player is None:
            return "nothing loaded — play a show first"

        actions = {
            "pause": (self._player.pause, "⏸ paused"),
            "resume": (self._player.play, "▶ resumed"),
            "stop": (self._player.stop, "⏹ stopped"),
            "next": (self._player.next, "⏭ next track"),
            "previous": (self._player.prev, "⏮ previous track"),
        }
        if action not in actions:
            return f"unknown action: {action!r}"
        fn, status = actions[action]
        fn()
        return status

    def now_playing(self) -> dict:
        """Best-effort snapshot of what's loaded and the current track."""
        if self._player is None:
            return {"playing": False}

        tape = getattr(self._player, "tape", None)
        info: dict = {"playing": True}
        if tape is not None:
            info.update(self._summarize(tape).as_dict())

        # GDPlayer track bookkeeping isn't part of the documented surface, so
        # probe defensively rather than assume an attribute name.
        track = (
            getattr(self._player, "current_track", None)
            or getattr(self._player, "now_playing", None)
        )
        if callable(track):
            track = track()
        if track is not None:
            info["track"] = str(track)
        return info

    # -- internal -----------------------------------------------------------

    @staticmethod
    def _summarize(tape) -> ShowInfo:
        try:
            venue = tape.venue()
        except Exception:
            venue = "unknown venue"
        return ShowInfo(
            date=getattr(tape, "date", ""),
            venue=venue,
            avg_rating=float(getattr(tape, "avg_rating", 0) or 0),
            score=float(tape.compute_score()),
            identifier=getattr(tape, "identifier", ""),
        )

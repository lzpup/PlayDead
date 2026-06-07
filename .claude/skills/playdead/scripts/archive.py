"""Talk to the Internet Archive (archive.org) about Grateful Dead shows.

Pure standard library so the skill runs anywhere Python 3.8+ is installed, with
no `pip install` step. Two public endpoints are used:

  * advancedsearch.php  -> search the GratefulDead collection
  * metadata/<id>       -> file list for a chosen recording

Nothing here plays audio; it only resolves *what* to play and the stream URLs.
"""
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

BASE = "https://archive.org"
COLLECTION = "GratefulDead"
USER_AGENT = "PlayDead/0.1 (+https://github.com/lzpup/PlayDead) Grateful Dead archive player"
TIMEOUT = 30

# Fields worth requesting from the search index.
SEARCH_FIELDS = [
    "identifier",
    "title",
    "date",
    "venue",
    "coverage",
    "avg_rating",
    "num_reviews",
    "downloads",
    "source",
    "year",
]


class ArchiveError(RuntimeError):
    """Raised when archive.org cannot be reached or returns nonsense."""


def _get_json(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - surface a clean message to the skill
        raise ArchiveError(f"could not reach archive.org: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ArchiveError("archive.org returned a non-JSON response") from exc


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_SLASH = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")


def parse_date(text: str) -> Optional[str]:
    """Pull a show date out of free text, returning ``YYYY-MM-DD`` or ``None``.

    Handles ``1977-05-08``, ``5/8/77``, ``5-8-1977`` and similar. Two-digit
    years are mapped into the Dead's active span (1965-1995).
    """
    if not text:
        return None
    m = _ISO.search(text)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        return _fmt(y, mo, d)
    m = _SLASH.search(text)
    if m:
        mo, d, y = (int(g) for g in m.groups())
        if y < 100:
            y += 1900 if y >= 60 else 2000
        return _fmt(y, mo, d)
    return None


def _fmt(y: int, mo: int, d: int) -> Optional[str]:
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search_shows(
    query: Optional[str] = None,
    date: Optional[str] = None,
    year: Optional[int] = None,
    rows: int = 30,
) -> List[Dict[str, Any]]:
    """Search the GratefulDead collection. Returns normalised show dicts."""
    clauses = [f"collection:({COLLECTION})"]
    free = (query or "").strip()

    # A date embedded in the free-text query takes precedence.
    if not date and free:
        found = parse_date(free)
        if found:
            date = found
            free = _ISO.sub("", _SLASH.sub("", free)).strip()

    if date:
        clauses.append(f"date:[{date} TO {date}]")
    if year:
        clauses.append(f"year:{int(year)}")
    if free:
        # Quote-escape stray Lucene specials but keep it a loose text match.
        safe = re.sub(r'[:\[\]{}"]', " ", free).strip()
        if safe:
            clauses.append(f"({safe})")

    params = [("q", " AND ".join(clauses)), ("rows", str(rows)), ("output", "json")]
    params += [("fl[]", f) for f in SEARCH_FIELDS]
    params += [("sort[]", "downloads desc")]
    url = f"{BASE}/advancedsearch.php?" + urllib.parse.urlencode(params)

    data = _get_json(url)
    docs = data.get("response", {}).get("docs", [])
    return [_normalise(d) for d in docs]


def _normalise(doc: Dict[str, Any]) -> Dict[str, Any]:
    def first(v: Any) -> Any:
        return v[0] if isinstance(v, list) and v else v

    date = first(doc.get("date")) or ""
    if isinstance(date, str) and "T" in date:
        date = date.split("T", 1)[0]

    show = {
        "identifier": first(doc.get("identifier")) or "",
        "title": first(doc.get("title")) or "",
        "date": date,
        "venue": first(doc.get("venue")) or "",
        "coverage": first(doc.get("coverage")) or "",
        "avg_rating": _as_float(doc.get("avg_rating")),
        "num_reviews": _as_int(doc.get("num_reviews")),
        "downloads": _as_int(doc.get("downloads")),
        "source": first(doc.get("source")) or "",
    }
    show["source_type"] = classify_source(show)
    show["score"] = score_show(show)
    return show


def _as_float(v: Any) -> float:
    try:
        return float(v[0] if isinstance(v, list) else v)
    except (TypeError, ValueError):
        return 0.0


def _as_int(v: Any) -> int:
    try:
        return int(float(v[0] if isinstance(v, list) else v))
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# "Best tape" heuristics
# ---------------------------------------------------------------------------

_SOURCE_BASE = {"MATRIX": 3.5, "SBD": 4.0, "FM": 3.0, "AUD": 1.0, "UNKNOWN": 2.0}


def classify_source(show: Dict[str, Any]) -> str:
    """Guess recording lineage from identifier/title/source text.

    Deadheads strongly prefer soundboards (SBD) and matrices over audience
    (AUD) recordings, so this label drives most of the ranking.
    """
    blob = " ".join(
        str(show.get(k, "")) for k in ("identifier", "title", "source")
    ).lower()
    if "matrix" in blob or ".mtx" in blob:
        return "MATRIX"
    if "sbd" in blob or "soundboard" in blob or "board" in blob:
        return "SBD"
    if "fm" in blob and "fmaud" not in blob:
        return "FM"
    if "aud" in blob or "audience" in blob or "fob" in blob:
        return "AUD"
    return "UNKNOWN"


def score_show(show: Dict[str, Any]) -> float:
    """Higher is better. Lineage dominates, then ratings, then popularity."""
    base = _SOURCE_BASE.get(show.get("source_type") or classify_source(show), 2.0)
    rating = float(show.get("avg_rating") or 0.0)
    reviews = int(show.get("num_reviews") or 0)
    downloads = int(show.get("downloads") or 0)
    return (
        base * 2.0
        + rating
        + min(reviews, 50) * 0.02
        + math.log10(downloads + 1) * 0.5
    )


def best_tape(
    query: Optional[str] = None,
    date: Optional[str] = None,
    year: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Return the single highest-scoring recording matching the criteria."""
    shows = search_shows(query=query, date=date, year=year, rows=50)
    if not shows:
        return None
    return max(shows, key=lambda s: s["score"])


# ---------------------------------------------------------------------------
# Metadata + playlist
# ---------------------------------------------------------------------------

_IDENTIFIER = re.compile(r"^gd\d{2,4}[-.]\d{1,2}[-.]\d{1,2}", re.IGNORECASE)


def is_identifier(text: str) -> bool:
    return bool(_IDENTIFIER.match(text.strip()))


def get_metadata(identifier: str) -> Dict[str, Any]:
    data = _get_json(f"{BASE}/metadata/{urllib.parse.quote(identifier)}")
    if not data or not data.get("files"):
        raise ArchiveError(f"no files found for '{identifier}'")
    return data


# Preferred playable formats, best first. MP3 is the most portable derivative.
_AUDIO_EXTS = (".mp3", ".ogg", ".flac")


def build_playlist(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Turn item metadata into an ordered list of ``{title, url, ...}`` tracks."""
    ident = metadata.get("metadata", {}).get("identifier", "")
    files = metadata.get("files", [])

    chosen_ext = None
    for ext in _AUDIO_EXTS:
        if any(str(f.get("name", "")).lower().endswith(ext) for f in files):
            chosen_ext = ext
            break
    if not chosen_ext:
        return []

    picked = [f for f in files if str(f.get("name", "")).lower().endswith(chosen_ext)]
    picked.sort(key=_track_sort_key)

    playlist: List[Dict[str, Any]] = []
    for f in picked:
        name = f.get("name", "")
        playlist.append(
            {
                "title": f.get("title") or _title_from_name(name),
                "url": f"{BASE}/download/{urllib.parse.quote(ident)}/{urllib.parse.quote(name)}",
                "track": _as_int(f.get("track")),
                "length": f.get("length", ""),
            }
        )
    return playlist


def _track_sort_key(f: Dict[str, Any]):
    track = f.get("track")
    try:
        n = int(str(track).split("/")[0])
    except (TypeError, ValueError):
        n = 10_000  # untracked files sort after numbered ones, then by name
    return (n, str(f.get("name", "")))


def _title_from_name(name: str) -> str:
    stem = re.sub(r"\.[a-z0-9]+$", "", name, flags=re.IGNORECASE)
    stem = stem.replace("_", " ").strip()
    return stem or name

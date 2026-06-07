"""A small dictionary of legendary Grateful Dead shows by nickname.

Claude usually already knows that "Cornell" means 5/8/77, but baking a few
aliases in lets the scripts resolve nicknames on their own and keeps behaviour
deterministic. Each entry maps to a date and the venue (used as a search hint).
"""
from __future__ import annotations

import re
from typing import Dict, Optional, Tuple

# alias -> (date YYYY-MM-DD, venue hint)
FAMOUS: Dict[str, Tuple[str, str]] = {
    "cornell": ("1977-05-08", "Barton Hall Cornell University"),
    "barton hall": ("1977-05-08", "Barton Hall Cornell University"),
    "veneta": ("1972-08-27", "Old Renaissance Faire Grounds Veneta Oregon"),
    "sunshine daydream": ("1972-08-27", "Old Renaissance Faire Grounds Veneta Oregon"),
    "watkins glen": ("1973-07-28", "Grand Prix Racecourse Watkins Glen"),
    "englishtown": ("1977-09-03", "Raceway Park Englishtown"),
    "winterland closing": ("1978-12-31", "Winterland San Francisco"),
    "closing of winterland": ("1978-12-31", "Winterland San Francisco"),
    "harpur college": ("1970-05-02", "Harpur College Binghamton"),
    "fillmore east": ("1971-04-29", "Fillmore East New York"),
    "bickershaw": ("1972-05-07", "Bickershaw Festival England"),
    "rfk 1973": ("1973-06-10", "RFK Stadium Washington DC"),
    "dicks picks veneta": ("1972-08-27", "Old Renaissance Faire Grounds Veneta Oregon"),
}


def resolve_alias(text: str) -> Optional[Tuple[str, str]]:
    """Return ``(date, venue)`` if the text mentions a known famous show."""
    if not text:
        return None
    key = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    key = re.sub(r"\s+", " ", key).strip()
    # exact match first, then substring containment
    if key in FAMOUS:
        return FAMOUS[key]
    for alias, value in FAMOUS.items():
        if alias in key:
            return value
    return None

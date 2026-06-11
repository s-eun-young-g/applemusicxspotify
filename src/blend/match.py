"""Cross-service track matching.

The hard part of a Spotify×Apple blend: the same song has different IDs (and often
slightly different titles) on each service. The only universal id is ISRC, which
Spotify exposes but Apple's local XML does not — so the workhorse is fuzzy
matching on a normalized (artist, title) key, with ISRC used as a fast path when
both sides happen to have it.

Normalization strips the cruft that differs between catalogs — featured artists,
remaster/version tags, edition suffixes, punctuation, case — so "Motion Sickness"
matches "Motion Sickness (feat. X) - 2017 Remaster".
"""

from __future__ import annotations

import re
import unicodedata

from .profile import Track

# Parenthetical/bracketed noise: (feat. …), [Remastered], (2009 Version), (Live)…
_BRACKETS = re.compile(r"[\(\[].*?[\)\]]")
# Trailing "- Remastered 2011", "- Single Version", "- Live", etc.
_DASH_TAIL = re.compile(r"\s-\s.*$")
_FEAT = re.compile(r"\b(feat|ft|featuring|with)\.?\b.*$", re.IGNORECASE)
_NONWORD = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """Collapse a title or artist to a stable matching token."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower()
    text = _BRACKETS.sub(" ", text)
    text = _DASH_TAIL.sub(" ", text)
    text = _FEAT.sub(" ", text)
    text = _NONWORD.sub(" ", text)
    return " ".join(text.split())


def track_key(track: Track) -> tuple[str, str]:
    """The fuzzy identity of a track: (normalized artist, normalized title)."""
    return (normalize(track.artist), normalize(track.title))


def index(tracks: list[Track]) -> dict:
    """Build a lookup from both ISRC and normalized key to a track."""
    by_isrc: dict[str, Track] = {}
    by_key: dict[tuple[str, str], Track] = {}
    for t in tracks:
        if t.isrc:
            by_isrc.setdefault(t.isrc, t)
        by_key.setdefault(track_key(t), t)
    return {"isrc": by_isrc, "key": by_key}


def match_tracks(a: list[Track], b: list[Track]) -> list[tuple[Track, Track]]:
    """Return (track_a, track_b) pairs that refer to the same song.

    ISRC first (exact), then the normalized (artist, title) key."""
    idx_b = index(b)
    pairs: list[tuple[Track, Track]] = []
    seen_b: set[int] = set()
    for ta in a:
        tb = None
        if ta.isrc and ta.isrc in idx_b["isrc"]:
            tb = idx_b["isrc"][ta.isrc]
        else:
            tb = idx_b["key"].get(track_key(ta))
        if tb is not None and id(tb) not in seen_b:
            pairs.append((ta, tb))
            seen_b.add(id(tb))
    return pairs

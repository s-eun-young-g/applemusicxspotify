"""The universal taste profile — the interchange format the whole tool turns on.

A Profile is a weighted snapshot of one person's listening, produced from *either*
Apple Music (local, via apple.py) or Spotify (OAuth, via spotify.py). Everything
downstream — matching, scoring, blending — operates on Profiles, never on a
platform-specific shape. That decoupling is what lets Apple×Apple work today with
zero Spotify dependency, and Spotify×Apple drop in later behind the same type.

`weight` is a 0..1 affinity: how much this person likes the artist/track relative
to the rest of their library. Apple derives it from play count + rating; Spotify
from top-list rank. Keeping both on the same 0..1 scale is what makes a
cross-platform blend meaningful.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class Track:
    title: str
    artist: str
    album: str = ""
    duration_ms: int = 0
    isrc: str | None = None       # universal id; Spotify has it, Apple-local rarely does
    play_count: int = 0
    weight: float = 0.0           # 0..1 affinity


@dataclass
class Artist:
    name: str
    weight: float = 0.0           # 0..1 affinity
    genres: list[str] = field(default_factory=list)


@dataclass
class Profile:
    source: str                   # "apple" | "spotify"
    user: str
    tracks: list[Track] = field(default_factory=list)
    artists: list[Artist] = field(default_factory=list)
    genres: dict[str, float] = field(default_factory=dict)   # genre -> 0..1 weight

    # -- serialization ------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "schema": 1,
            "source": self.source,
            "user": self.user,
            "tracks": [asdict(t) for t in self.tracks],
            "artists": [asdict(a) for a in self.artists],
            "genres": self.genres,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        return cls(
            source=d.get("source", "unknown"),
            user=d.get("user", "anon"),
            tracks=[Track(**t) for t in d.get("tracks", [])],
            artists=[Artist(**a) for a in d.get("artists", [])],
            genres=dict(d.get("genres", {})),
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "Profile":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


def normalize_weights(values: dict[str, float]) -> dict[str, float]:
    """Scale a name->raw-score map into 0..1 by its maximum (so the top item is
    1.0). Returns {} for empty/all-zero input."""
    if not values:
        return {}
    top = max(values.values())
    if top <= 0:
        return {k: 0.0 for k in values}
    return {k: v / top for k, v in values.items()}

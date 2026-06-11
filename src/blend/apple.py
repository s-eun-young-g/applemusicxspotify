"""Read an Apple Music library into a Profile — fully local, no account needed.

WHY THE XML
-----------
The Music app keeps its data in a binary `Library.musicdb`, but it can export a
plain-text plist: Music ▸ File ▸ Library ▸ Export Library… , or turn on
Music ▸ Settings ▸ Advanced ▸ "Share Library XML with other applications" to get
`~/Music/Music/Music Library.xml`. That plist is parseable with the standard
library's `plistlib` — no AppleScript, no developer account. (AppleScript is only
needed later for *writing* a playlist back; see playlist.py.)

AFFINITY
--------
Apple gives us strong taste signal that Spotify doesn't expose: play count,
rating (0–100, i.e. stars×20), and "loved". We fold those into a single raw
affinity per track, then normalize so the most-loved track is 1.0.
"""

from __future__ import annotations

import os
import plistlib

from .profile import Artist, Profile, Track, normalize_weights

# Default locations Music writes the shared XML to, newest layout first.
_DEFAULT_PATHS = [
    "~/Music/Music/Music Library.xml",
    "~/Music/iTunes/iTunes Music Library.xml",
    "~/Music/iTunes/iTunes Library.xml",
]


def default_library_path() -> str | None:
    for p in _DEFAULT_PATHS:
        full = os.path.expanduser(p)
        if os.path.exists(full):
            return full
    return None


def _affinity(raw: dict) -> float:
    """Combine the signals Apple stores into one raw 'how much do they like it'.
    Play count dominates; rating and loved nudge it up so a cherished but
    rarely-played track still counts."""
    plays = raw.get("Play Count", 0) or 0
    stars = (raw.get("Rating", 0) or 0) / 20.0          # 0..5
    loved = 3.0 if raw.get("Loved") else 0.0
    return float(plays) + 2.0 * stars + loved


def profile_from_plist(data: dict, user: str) -> Profile:
    """Build a Profile from an already-parsed iTunes/Music library plist."""
    raw_tracks = data.get("Tracks", {}) or {}

    affinities: dict[int, float] = {}
    tracks: list[Track] = []
    artist_raw: dict[str, float] = {}
    artist_genres: dict[str, set[str]] = {}
    genre_raw: dict[str, float] = {}

    for tid, t in raw_tracks.items():
        title = t.get("Name")
        artist = t.get("Artist") or t.get("Album Artist")
        if not title or not artist:
            continue                      # skip videos / podcasts / broken rows
        aff = _affinity(t)
        affinities[tid] = aff
        genre = (t.get("Genre") or "").strip().lower()
        tracks.append(Track(
            title=title,
            artist=artist,
            album=t.get("Album", "") or "",
            duration_ms=int(t.get("Total Time", 0) or 0),
            isrc=None,                    # Apple-local XML doesn't carry ISRC
            play_count=int(t.get("Play Count", 0) or 0),
            weight=aff,                   # raw for now; normalized below
        ))
        artist_raw[artist] = artist_raw.get(artist, 0.0) + aff
        if genre:
            artist_genres.setdefault(artist, set()).add(genre)
            genre_raw[genre] = genre_raw.get(genre, 0.0) + aff

    # Normalize all three weight spaces to 0..1.
    track_norm = normalize_weights({i: a for i, a in enumerate(t.weight for t in tracks)})
    for i, tr in enumerate(tracks):
        tr.weight = round(track_norm.get(i, 0.0), 4)
    tracks.sort(key=lambda t: t.weight, reverse=True)

    artist_norm = normalize_weights(artist_raw)
    artists = [
        Artist(name=name, weight=round(w, 4), genres=sorted(artist_genres.get(name, ())))
        for name, w in sorted(artist_norm.items(), key=lambda kv: kv[1], reverse=True)
    ]

    genres = {g: round(w, 4) for g, w in
              sorted(normalize_weights(genre_raw).items(), key=lambda kv: kv[1], reverse=True)}

    return Profile(source="apple", user=user, tracks=tracks, artists=artists, genres=genres)


def read_library(path: str, user: str) -> Profile:
    """Parse an exported Apple Music library XML file into a Profile."""
    with open(path, "rb") as f:
        data = plistlib.load(f)
    return profile_from_plist(data, user)

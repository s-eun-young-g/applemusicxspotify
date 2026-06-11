"""Blend two profiles: a compatibility score and a shared playlist.

No audio features are involved (Spotify removed them for new apps in 2024); the
blend is built purely from *overlap* — shared artists, shared genres, shared
tracks — which is also exactly what makes a cross-platform blend honest: those
three signals exist identically on both services.

Score = 0.5·artist overlap + 0.3·genre similarity + 0.2·shared-track volume,
on 0..100. The playlist is the songs you both already love, plus a few of each
person's favourites that sit in the *other's* top genres — the "you'd probably
like this" introductions that make a blend feel like a handshake.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .match import match_tracks, normalize, track_key
from .profile import Profile

_W_ARTISTS, _W_GENRES, _W_TRACKS = 0.5, 0.3, 0.2
_TOP_GENRES = 5            # how many of each person's genres count as "their taste"
_DEFAULT_LIMIT = 30        # blend playlist size


@dataclass
class BlendResult:
    users: tuple[str, str]
    score: int
    breakdown: dict[str, float]
    shared_artists: list[str]
    shared_tracks: list[str]
    playlist: list[dict] = field(default_factory=list)   # {title, artist, origin}

    def summary(self) -> str:
        a, b = self.users
        lines = [
            f"Blend: {a} × {b}",
            f"Compatibility: {self.score}/100",
            f"  artists {self.breakdown['artists']:.2f}  "
            f"genres {self.breakdown['genres']:.2f}  "
            f"tracks {self.breakdown['tracks']:.2f}",
            "",
            f"Shared artists ({len(self.shared_artists)}): "
            + (", ".join(self.shared_artists[:8]) or "—"),
            f"Shared tracks ({len(self.shared_tracks)}): "
            + (", ".join(self.shared_tracks[:6]) or "—"),
            "",
            f"Blend playlist ({len(self.playlist)} tracks):",
        ]
        for t in self.playlist:
            tag = {"shared": "♥"}.get(t["origin"], f"→{t['origin']}")
            lines.append(f"  {tag:>6}  {t['artist']} — {t['title']}")
        return "\n".join(lines)


def _weighted_jaccard(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    num = sum(min(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    den = sum(max(a.get(k, 0.0), b.get(k, 0.0)) for k in keys)
    return num / den if den else 0.0


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    if not keys:
        return 0.0
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = sum(v * v for v in a.values()) ** 0.5
    nb = sum(v * v for v in b.values()) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _artist_weights(p: Profile) -> dict[str, float]:
    return {normalize(ar.name): ar.weight for ar in p.artists if ar.name}


def _artist_genres(p: Profile) -> dict[str, list[str]]:
    return {normalize(ar.name): ar.genres for ar in p.artists}


def blend(a: Profile, b: Profile, limit: int = _DEFAULT_LIMIT) -> BlendResult:
    aw, bw = _artist_weights(a), _artist_weights(b)
    artist_score = _weighted_jaccard(aw, bw)
    genre_score = _cosine(a.genres, b.genres)

    pairs = match_tracks(a.tracks, b.tracks)
    # Fraction of the smaller library that's shared: identical -> 1.0, and for the
    # asymmetric Spotify-top-50 × big-Apple-library case it reads as "how much of
    # the shorter list shows up in the other."
    smaller = min(len(a.tracks), len(b.tracks))
    track_score = min(1.0, len(pairs) / smaller) if smaller else 0.0

    score = round(100 * (_W_ARTISTS * artist_score
                         + _W_GENRES * genre_score
                         + _W_TRACKS * track_score))

    # Shared artists, strongest mutual affinity first.
    shared_names = set(aw) & set(bw)
    name_label = {normalize(ar.name): ar.name for ar in (*a.artists, *b.artists)}
    shared_artists = sorted(
        shared_names, key=lambda n: min(aw[n], bw[n]), reverse=True)
    shared_artists = [name_label.get(n, n) for n in shared_artists]

    playlist = _build_playlist(a, b, pairs, limit)
    shared_tracks = [f"{ta.artist} — {ta.title}" for ta, _ in pairs]

    return BlendResult(
        users=(a.user, b.user),
        score=score,
        breakdown={"artists": artist_score, "genres": genre_score, "tracks": track_score},
        shared_artists=shared_artists,
        shared_tracks=shared_tracks,
        playlist=playlist,
    )


def _build_playlist(a: Profile, b: Profile, pairs, limit: int) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(track, origin: str) -> None:
        k = track_key(track)
        if k in seen:
            return
        seen.add(k)
        out.append({"title": track.title, "artist": track.artist, "origin": origin,
                    "isrc": track.isrc, "duration_ms": track.duration_ms})

    # 1) Songs you both love, strongest combined affinity first.
    for ta, tb in sorted(pairs, key=lambda p: (p[0].weight + p[1].weight), reverse=True):
        add(ta, "shared")

    # 2) Introductions: each person's top tracks that live in the other's top genres.
    def introduce(src: Profile, dst: Profile) -> None:
        dst_top = {g for g, _ in sorted(dst.genres.items(),
                                        key=lambda kv: kv[1], reverse=True)[:_TOP_GENRES]}
        genres_of = _artist_genres(src)
        for t in src.tracks:                       # tracks are pre-sorted by weight
            if len(out) >= limit:
                return
            tg = set(genres_of.get(normalize(t.artist), ()))
            if tg & dst_top:
                add(t, src.user)

    while len(out) < limit:
        before = len(out)
        introduce(a, b)
        introduce(b, a)
        if len(out) == before:                     # nothing left to add
            break

    return out[:limit]

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


# ---------------------------------------------------------------------------
# Group (multi-person) blend.
# ---------------------------------------------------------------------------

@dataclass
class GroupBlendResult:
    members: list[str]
    score: int                              # mean of all pairwise compatibilities
    pairwise: dict[str, int]                # "alice × bob" -> score
    cohesion: dict[str, float]              # artists / genres, generalized to N
    shared_by_all: list[str]                # artists every member has
    playlist: list[dict]                    # {title, artist, origin, members}

    def summary(self) -> str:
        lines = [
            f"Group blend: {', '.join(self.members)}",
            f"Group compatibility: {self.score}/100  "
            f"(artists {self.cohesion['artists']:.2f}, genres {self.cohesion['genres']:.2f})",
            "",
            "Pairwise:",
        ]
        for pair, s in sorted(self.pairwise.items(), key=lambda kv: kv[1], reverse=True):
            lines.append(f"  {s:>3}  {pair}")
        lines += [
            "",
            f"Liked by everyone ({len(self.shared_by_all)} artists): "
            + (", ".join(self.shared_by_all[:8]) or "—"),
            "",
            f"Group playlist ({len(self.playlist)} tracks):",
        ]
        for t in self.playlist:
            tag = "♥ all" if t["origin"] == "all" else (
                f"{t['members']}/{len(self.members)}" if t["members"] > 1 else f"→{t['origin']}")
            lines.append(f"  {tag:>7}  {t['artist']} — {t['title']}")
        return "\n".join(lines)


def _generalized_jaccard(maps: list[dict[str, float]]) -> float:
    keys = set().union(*maps) if maps else set()
    if not keys:
        return 0.0
    num = sum(min(m.get(k, 0.0) for m in maps) for k in keys)
    den = sum(max(m.get(k, 0.0) for m in maps) for k in keys)
    return num / den if den else 0.0


def group_blend(profiles: list[Profile], limit: int = _DEFAULT_LIMIT) -> GroupBlendResult:
    """Blend three or more people: a group score (mean of pairwise) plus a
    playlist that leads with tracks the most members share, then fills with each
    person's favourites in the group's common genres."""
    n = len(profiles)
    if n < 2:
        raise ValueError("a group blend needs at least two profiles")

    pairwise: dict[str, int] = {}
    scores: list[int] = []
    for i in range(n):
        for j in range(i + 1, n):
            s = blend(profiles[i], profiles[j]).score
            pairwise[f"{profiles[i].user} × {profiles[j].user}"] = s
            scores.append(s)
    group_score = round(sum(scores) / len(scores)) if scores else 0

    maps = [_artist_weights(p) for p in profiles]
    artist_cohesion = _generalized_jaccard(maps)
    genre_cohesion = _generalized_jaccard([p.genres for p in profiles])

    label = {normalize(a.name): a.name for p in profiles for a in p.artists}
    everyone = [k for k in set().union(*maps) if all(k in m for m in maps)]
    everyone.sort(key=lambda k: min(m[k] for m in maps), reverse=True)
    shared_by_all = [label[k] for k in everyone]

    playlist = _group_playlist(profiles, limit)
    return GroupBlendResult(
        members=[p.user for p in profiles],
        score=group_score,
        pairwise=pairwise,
        cohesion={"artists": artist_cohesion, "genres": genre_cohesion},
        shared_by_all=shared_by_all,
        playlist=playlist,
    )


def _group_playlist(profiles: list[Profile], limit: int) -> list[dict]:
    n = len(profiles)
    # How many members have each track, and the best-known version of it.
    occ: dict[tuple, dict] = {}
    for p in profiles:
        local: set[tuple] = set()
        for t in p.tracks:
            k = track_key(t)
            if k in local:
                continue
            local.add(k)
            e = occ.setdefault(k, {"count": 0, "weight": 0.0, "track": t})
            e["count"] += 1
            e["weight"] += t.weight
            if t.weight > e["track"].weight:
                e["track"] = t

    out: list[dict] = []
    seen: set[tuple] = set()

    def add(track, origin, members):
        k = track_key(track)
        if k in seen:
            return
        seen.add(k)
        out.append({"title": track.title, "artist": track.artist,
                    "origin": origin, "members": members})

    # 1) Tracks shared by the most members first (everyone > most > some).
    shared = sorted((e for e in occ.values() if e["count"] >= 2),
                    key=lambda e: (e["count"], e["weight"]), reverse=True)
    for e in shared:
        if len(out) >= limit:
            break
        add(e["track"], "all" if e["count"] == n else "shared", e["count"])

    # 2) Fill with introductions: each member's top tracks in the group's genres.
    group_genres: dict[str, float] = {}
    for p in profiles:
        for g, w in p.genres.items():
            group_genres[g] = group_genres.get(g, 0.0) + w
    top = {g for g, _ in sorted(group_genres.items(), key=lambda kv: kv[1],
                                reverse=True)[:_TOP_GENRES]}
    pools = []
    for p in profiles:
        gmap = _artist_genres(p)
        pools.append((p.user, [t for t in p.tracks
                               if set(gmap.get(normalize(t.artist), ())) & top]))
    cursor = [0] * len(pools)
    while len(out) < limit:
        progressed = False
        for i, (uname, pool) in enumerate(pools):
            while cursor[i] < len(pool):
                t = pool[cursor[i]]
                cursor[i] += 1
                if track_key(t) not in seen:
                    add(t, uname, 1)
                    progressed = True
                    break
            if len(out) >= limit:
                break
        if not progressed:
            break
    return out[:limit]

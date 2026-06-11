# blend — Apple Music × Spotify

A music **blend** for the pairs Spotify won't do for you.

Spotify already blends Spotify×Spotify (its native *Blend*). The gap is everything
else: **Apple×Apple** (Apple Music has no blend at all) and **Spotify×Apple**
(cross-platform). This fills it.

```bash
pip install -e .

# build a taste profile from your Apple Music library (fully local, no account)
blend apple --user sofia -o sofia.json

# blend two profiles
blend mix sofia.json friend.json
```

```
Blend: alice × bob
Compatibility: 51/100
  artists 0.30  genres 0.94  tracks 0.40

Shared artists (2): Phoebe Bridgers, Mitski
Shared tracks (2): Phoebe Bridgers — Motion Sickness, Mitski — Nobody

Blend playlist (7 tracks):
       ♥  Phoebe Bridgers — Motion Sickness     ← you both love it
       ♥  Mitski — Nobody
  →alice  Big Thief — Paul                       ← alice's pick, in bob's genres
    →bob  Fleet Foxes — White Winter Hymnal      ← bob's pick, in alice's genres
```

Try it now with the bundled examples:

```bash
blend mix examples/alice.json examples/bob.json
```

## How it works

```
Apple Music library XML ─┐
                          ├─► profile.json ──► blend(A, B) ──► score + playlist
Spotify (OAuth) [M1] ────┘     (universal)
```

A **profile** is a weighted snapshot of one person's taste (artists, tracks,
genres, each scored 0–1). It can come from Apple or Spotify; the blend only ever
sees profiles, so both platforms — and both blend directions — share one path.

- **Apple Music** is read locally from the library XML via Python's `plistlib`
  (play counts, ratings, *loved* → affinity). No developer account, nothing
  leaves your machine.
- **Blend score** = `0.5·artist overlap + 0.3·genre similarity + 0.2·shared-track
  volume`. No "audio features" — Spotify removed those for new apps in 2024 — so
  the blend is built purely from overlap, which is exactly what's comparable
  across services anyway.
- **Matching across services** keys on a normalized `artist + title` (stripping
  `feat.`, remaster/version tags, punctuation), with ISRC as a fast path when both
  sides have it.

### Getting your Apple Music XML

`blend apple` auto-finds it if present. To create it: **Music ▸ File ▸ Library ▸
Export Library…**, or turn on **Music ▸ Settings ▸ Advanced ▸ "Share Library XML
with other applications"**, then pass `--xml /path/to/Library.xml`.

## Status & roadmap

- **M0 — Apple×Apple (done):** local library → profile, blend score + playlist,
  CLI, tests.
- **M1 — Spotify reader:** OAuth (PKCE) → profile. Because Spotify caps new apps
  at 5 users and reserves unlimited access for registered businesses, this uses a
  **bring-your-own client ID** model: each person creates their own free Spotify
  app (one-time, ~2 min) and authorizes locally on a `127.0.0.1` loopback — so
  there's no shared user cap and no server ever holds anyone's tokens.
- **M2 — playlist export:** push the blend to Spotify (`playlist-modify`) and to
  Apple Music (via AppleScript).
- **M3 — UX:** a small web visualizer for two uploaded profiles.

## Why no "audio vibe" blend

Spotify deprecated `audio-features`, `audio-analysis`, `recommendations`, and
`related-artists` for new apps on 2024-11-27. A new app simply can't use them, so
this blend is honest about working from overlap (shared artists / genres / tracks)
rather than danceability/energy.

## Tests

```bash
python -m pytest -q
```

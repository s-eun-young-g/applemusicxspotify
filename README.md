# blend — Apple Music × Spotify

A music **blend** for the pairs Spotify won't do for you.

Spotify already blends Spotify×Spotify (its native *Blend*). The gap is everything
else: **Apple×Apple** (Apple Music has no blend at all) and **Spotify×Apple**
(cross-platform). This fills it.

```bash
pip install -e .

# build a taste profile from your Apple Music library (fully local, no account)
blend apple --user sofia -o sofia.json

# …or from Spotify (bring your own free client ID — see below)
blend spotify --user friend --client-id <your-id> -o friend.json

# blend any two profiles — Apple×Apple or Spotify×Apple
blend mix sofia.json friend.json

# …or three or more — a group blend (pairwise matrix + group playlist)
blend mix sofia.json friend.json third.json

# …and turn the blend into a real playlist
blend mix sofia.json friend.json --to-spotify --client-id <your-id>
blend mix sofia.json friend.json --to-apple        # macOS, into your Music app

# transfer any existing playlist between services (no blending)
blend transfer --from spotify --to apple --playlist "My Mix" --client-id <your-id>
blend transfer --from apple --to spotify --playlist "My Mix" --client-id <your-id>
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

## No terminal? Use the web GUI

After installing, one command turns the whole thing into a webpage — read your
library, connect Spotify, see the blend, make the playlist, all point-and-click:

```bash
pip install 'blend[web]'
blend serve            # opens http://127.0.0.1:8000 in your browser
```

It runs **entirely on your machine** — that's what lets it read your local Apple
library and keeps Spotify's loopback login working with no shared user cap. The
browser is just a friendlier front end over the same engine. (You still install
once and bring your own Spotify client ID — those floors are set by Apple's local
data and Spotify's policy, not by the UI.)

The rest of this guide covers the equivalent CLI steps.

## Walkthrough: from zero to a blended playlist (CLI)

### 0. Install (once)

```bash
git clone https://github.com/s-eun-young-g/applemusicxspotify.git
cd applemusicxspotify
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Every new terminal session, re-activate: `cd applemusicxspotify && source .venv/bin/activate`.

### 1. Make your own profile

Each person needs **one** profile file. Use whichever service you listen on.

**Option A — Apple Music** (local, no account, nothing leaves your Mac):

1. In the Music app, either turn on **Settings (⌘,) ▸ Advanced ▸ "Share Library
   XML with other applications"**, or use **File ▸ Library ▸ Export Library…** and
   save `Library.xml` into the project folder.
2. Build the profile:
   ```bash
   blend apple --user sofia
   ```
   This writes `sofia.json`. If it can't find the library, point at it directly:
   ```bash
   blend apple --user sofia --xml /path/to/Library.xml
   ```

**Option B — Spotify** (bring your own free client ID):

1. Create an app at <https://developer.spotify.com/dashboard> → **Create app**.
2. Add this **exact** Redirect URI: `http://127.0.0.1:8888/callback`, check **Web
   API**, and **Save**.
3. Copy the **Client ID** from the app's Settings.
4. Build the profile:
   ```bash
   blend spotify --user sofia --client-id YOUR_CLIENT_ID
   ```
   A browser opens once → **Agree** → it writes `sofia.json`. The token is cached
   at `~/.config/blend/spotify-token.json` (no client secret, no server).
   Tip: `export SPOTIFY_CLIENT_ID=YOUR_CLIENT_ID` to skip the flag from then on.

### 2. Get a second profile

A blend needs **two**. Either:

- **A friend** runs step 1 on their machine and sends you their `name.json`, or
- **Yourself, cross-platform** — make both an Apple and a Spotify profile and blend
  them against each other (a fun check of how your two libraries compare):
  ```bash
  blend apple   --user me-apple
  blend spotify --user me-spotify --client-id YOUR_CLIENT_ID
  ```

Drop both `.json` files in the project folder.

### 3. Blend

```bash
blend mix sofia.json friend.json
```

Prints the compatibility score and the blend playlist. `--limit N` sets the size;
`-o blend.json` saves the result.

### 4. Turn it into a real playlist

**Spotify:**
```bash
blend mix sofia.json friend.json --to-spotify --client-id YOUR_CLIENT_ID --name "Our Blend"
```
Prints the new playlist's URL and lists any tracks it couldn't find. Add
`--public` to make it shareable.

**Apple Music** (macOS):
```bash
blend mix sofia.json friend.json --to-apple --name "Our Blend"
```
The first run asks for permission — **System Settings ▸ Privacy & Security ▸
Automation ▸ enable Terminal → Music** — then re-run. The playlist appears in your
Music app. (Only songs already in your library can be added.)

### Troubleshooting

| Symptom | Fix |
|---|---|
| "couldn't find an Apple Music library XML" | Pass `--xml /path/to/Library.xml`. Auto-detect checks `~/Music/Music/` and the current folder. |
| Spotify `INVALID_CLIENT` / redirect mismatch | The app's Redirect URI must be **exactly** `http://127.0.0.1:8888/callback`. |
| Spotify export 403 | Re-run once — the consent screen now includes playlist permission. |
| `--to-apple` adds nothing | Those songs aren't in your local library; only owned/library tracks can be added to a Music playlist. |

> **Privacy:** your `Library.xml` and the generated `*.json` profiles are
> git-ignored — they stay on your machine and won't be committed.

## How it works

```
Apple Music library XML ─┐
                          ├─► profile.json ──► blend(A, B) ──► score + playlist
Spotify  (OAuth)  ───────┘     (universal)
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
- **Why bring-your-own client ID?** Spotify caps a new app at 5 users and reserves
  unlimited access for registered businesses, so each person uses their own free
  app and authorizes locally — no shared cap, no server holding anyone's tokens.

## Status & roadmap

- **M0 — Apple×Apple (done):** local library → profile, blend score + playlist,
  CLI, tests.
- **M1 — Spotify reader (done):** PKCE loopback OAuth, bring-your-own client ID →
  the same profile shape, so **Spotify×Apple** blends fall out for free (matched
  on ISRC + normalized title). No server, no shared user cap, no client secret.
- **M2 — playlist export (done):** `blend mix … --to-spotify` resolves each track
  (ISRC-exact when possible) and creates a Spotify playlist; `--to-apple`
  generates an AppleScript that builds the playlist from your local Music library.
- **M3 — local web GUI (done):** `blend serve` — a point-and-click localhost page
  over the same engine (optional `blend[web]` extra). Runs locally, so it keeps
  Apple-library access and the no-cap Spotify loopback login.
- **M4 — group blend (done):** `blend mix` takes 2+ profiles; 3+ produces a group
  score (mean of pairwise), a pairwise matrix, "liked by everyone," and a group
  playlist that leads with the most-shared tracks. Works in the CLI and web GUI.
- **M5 — playlist transfer (done):** `blend transfer --from … --to …` copies an
  existing playlist between Spotify and Apple Music (reads the source, resolves
  each track on the target — ISRC-exact when possible). CLI and web GUI.
- **M6 — wider reach (ideas):** a packaged double-click Mac app, and/or a free
  static page to drag two `profile.json`s in and share a blend.

## Why no "audio vibe" blend

Spotify deprecated `audio-features`, `audio-analysis`, `recommendations`, and
`related-artists` for new apps on 2024-11-27. A new app simply can't use them, so
this blend is honest about working from overlap (shared artists / genres / tracks)
rather than danceability/energy.

## Tests

```bash
python -m pytest -q
```

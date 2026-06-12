"""Turn a blend into a real, playable playlist — on Spotify or Apple Music.

A blend's tracklist is just (title, artist, isrc) — it has no platform IDs, since
it's built from two profiles that may come from either service. So exporting means
*resolving* each track on the target platform:

  * Spotify — search the Web API (exact via `isrc:` when available, else
    `track:/artist:`), collect URIs, create a playlist, add them.
  * Apple Music — generate an AppleScript that finds each track in the user's
    local library by name+artist and copies it into a new playlist.

The query-building and AppleScript generation are pure functions (unit-tested);
the network call and `osascript` invocation are thin wrappers exercised live.
"""

from __future__ import annotations

import shutil
import subprocess

from . import spotify as sp


def _default_name(result) -> str:
    people = getattr(result, "users", None) or getattr(result, "members", None) or ["A", "B"]
    return "blend: " + " × ".join(people)


# ---------------------------------------------------------------------------
# Spotify (Web API).
# ---------------------------------------------------------------------------

def search_query(entry: dict) -> str:
    """Build the Spotify search query for one blend entry — ISRC is exact."""
    if entry.get("isrc"):
        return f"isrc:{entry['isrc']}"
    title = entry["title"].replace('"', " ").strip()
    artist = entry["artist"].replace('"', " ").strip()
    return f"track:{title} artist:{artist}"


def pick_uri(search_json: dict) -> str | None:
    items = ((search_json.get("tracks") or {}).get("items") or [])
    return items[0]["uri"] if items else None


def spotify_create(client_id: str, name: str, entries: list[dict],
                   public: bool = False, description: str = "made with blend") -> dict:
    """Resolve a list of {title, artist, isrc?} on Spotify and create a playlist.
    Returns url / added / missed. The reusable primitive behind blend export AND
    playlist transfer."""
    token = sp._valid_token(client_id, sp._SCOPES)
    me = sp._api_get(token, "/me", {})

    uris: list[str] = []
    missed: list[str] = []
    for entry in entries:
        res = sp._api_get(token, "/search",
                          {"q": search_query(entry), "type": "track", "limit": 1})
        uri = pick_uri(res)
        if uri:
            uris.append(uri)
        else:
            missed.append(f"{entry['artist']} — {entry['title']}")

    playlist = sp._api_post(token, f"/users/{me['id']}/playlists", {
        "name": name, "public": public, "description": description,
    })
    for i in range(0, len(uris), 100):          # Spotify adds <=100 at a time
        sp._api_post(token, f"/playlists/{playlist['id']}/tracks",
                     {"uris": uris[i:i + 100]})

    return {
        "url": (playlist.get("external_urls") or {}).get("spotify", ""),
        "added": len(uris),
        "missed": missed,
    }


def spotify_export(result, client_id: str,
                   name: str | None = None, public: bool = False) -> dict:
    """Create a Spotify playlist from a (pairwise or group) blend result."""
    return spotify_create(
        client_id, name or _default_name(result), result.playlist, public=public,
        description=f"Compatibility {result.score}/100 — made with blend")


# ---------------------------------------------------------------------------
# Apple Music (AppleScript).
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def apple_script(name: str, entries: list[dict]) -> str:
    """Generate an AppleScript that builds the playlist from the local library.

    Only tracks already in the user's Music library can be added (you can't script
    a song you don't own into a playlist); misses are silently skipped."""
    lines = [
        'tell application "Music"',
        f'  if not (exists user playlist "{_esc(name)}") then '
        f'make new user playlist with properties {{name:"{_esc(name)}"}}',
        f'  set blendList to user playlist "{_esc(name)}"',
    ]
    for e in entries:
        t, a = _esc(e["title"]), _esc(e["artist"])
        lines.append(
            f'  set hits to (every track of library playlist 1 '
            f'whose name is "{t}" and artist is "{a}")')
        lines.append('  if hits is not {} then duplicate (item 1 of hits) to blendList')
    lines.append("end tell")
    return "\n".join(lines)


def apple_create(name: str, entries: list[dict]) -> dict:
    """Create an Apple Music playlist from a list of {title, artist} via
    AppleScript (macOS). The reusable primitive behind blend export AND transfer."""
    if shutil.which("osascript") is None:
        raise RuntimeError("osascript not found — Apple Music export needs macOS.")
    script = apple_script(name, entries)
    proc = subprocess.run(["osascript", "-e", script],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"AppleScript failed: {proc.stderr.strip()}")
    return {"playlist": name, "attempted": len(entries)}


def apple_export(result, name: str | None = None) -> dict:
    """Create an Apple Music playlist from a (pairwise or group) blend result."""
    return apple_create(name or _default_name(result), result.playlist)


# ---------------------------------------------------------------------------
# Transfer a playlist between services (independent of blending).
# ---------------------------------------------------------------------------

def spotify_to_apple(client_id: str, playlist: str, new_name: str | None = None) -> dict:
    """Copy a Spotify playlist into Apple Music. `playlist` is a name, URL, or id."""
    token = sp._valid_token(client_id, sp._SCOPES)
    pid = sp.resolve_playlist_id(token, playlist)
    entries = sp.playlist_tracks(token, pid)
    if not entries:
        raise RuntimeError("that Spotify playlist has no tracks")
    info = apple_create(new_name or f"{playlist} (from Spotify)", entries)
    info["source_tracks"] = len(entries)
    return info


def apple_to_spotify(xml_path: str, playlist_name: str, client_id: str,
                     new_name: str | None = None, public: bool = False) -> dict:
    """Copy an Apple Music playlist (from the library XML) onto Spotify."""
    from .apple import read_library_playlists
    playlists = read_library_playlists(xml_path)
    tracks = playlists.get(playlist_name)
    if tracks is None:                          # case-insensitive fallback
        for name, ts in playlists.items():
            if name.lower() == playlist_name.lower():
                tracks = ts
                break
    if not tracks:
        avail = ", ".join(sorted(playlists)) or "none found"
        raise RuntimeError(f"no Apple playlist named {playlist_name!r} "
                           f"(available: {avail})")
    entries = [{"title": t.title, "artist": t.artist, "isrc": t.isrc} for t in tracks]
    info = spotify_create(client_id, new_name or f"{playlist_name} (from Apple Music)",
                          entries, public=public, description="Transferred from Apple Music")
    info["source_tracks"] = len(entries)
    return info

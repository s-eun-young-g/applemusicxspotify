"""Read a Spotify account into a Profile via OAuth — no server, no shared cap.

WHY THIS SHAPE
--------------
Spotify now caps a new app at 5 users and reserves unlimited access for
registered businesses, so a hosted multi-user app is a dead end for a hobby
project. The way around it is **bring-your-own client ID**: each person creates
their own free Spotify app (one-time, ~2 min) and is its sole user. Auth happens
locally with PKCE on a 127.0.0.1 loopback redirect, so no client secret is needed
and no server ever holds anyone's tokens.

WHAT WE READ
------------
`/me/top/tracks` and `/me/top/artists` (scope `user-top-read`). Tracks carry ISRC
(the universal id that lets a Spotify track match an Apple one) and artists carry
genres. We do NOT touch audio-features / recommendations — Spotify removed those
for new apps in 2024 — which is fine, since the blend is overlap-based anyway.

TESTABILITY
-----------
`profile_from_spotify()` is a pure function over the raw API JSON, so it's fully
unit-tested. The HTTP/auth layer around it is thin and exercised manually with a
real client ID.
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from .profile import Artist, Profile, Track, normalize_weights

_AUTH_URL = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API = "https://api.spotify.com/v1"
# One consent covers both reading taste and writing a blend playlist back.
_SCOPES = "user-top-read playlist-modify-public playlist-modify-private"
_DEFAULT_REDIRECT = "http://127.0.0.1:8888/callback"
_CACHE = os.path.expanduser("~/.config/blend/spotify-token.json")


# ---------------------------------------------------------------------------
# Pure profile builder (unit-tested).
# ---------------------------------------------------------------------------

def profile_from_spotify(top_tracks: list[dict], top_artists: list[dict],
                         user: str) -> Profile:
    """Turn raw /me/top/{tracks,artists} JSON items into a Profile.

    Affinity comes from list position: rank 0 is the strongest, scaled to 0..1."""
    artist_weight: dict[str, float] = {}
    artist_genres: dict[str, list[str]] = {}

    n_art = max(len(top_artists), 1)
    for i, a in enumerate(top_artists):
        name = a.get("name")
        if not name:
            continue
        w = (n_art - i) / n_art
        artist_weight[name] = max(artist_weight.get(name, 0.0), w)
        artist_genres[name] = list(a.get("genres") or [])

    tracks: list[Track] = []
    n_tr = max(len(top_tracks), 1)
    for i, t in enumerate(top_tracks):
        name = t.get("name")
        arts = t.get("artists") or []
        if not name or not arts:
            continue
        primary = arts[0].get("name", "")
        w = (n_tr - i) / n_tr
        tracks.append(Track(
            title=name,
            artist=primary,
            album=(t.get("album") or {}).get("name", "") or "",
            duration_ms=int(t.get("duration_ms", 0) or 0),
            isrc=(t.get("external_ids") or {}).get("isrc"),
            play_count=0,
            weight=round(w, 4),
        ))
        if primary and primary not in artist_weight:
            artist_weight[primary] = w
            artist_genres.setdefault(primary, [])

    artists = [
        Artist(name=n, weight=round(w, 4), genres=sorted(set(artist_genres.get(n, []))))
        for n, w in sorted(artist_weight.items(), key=lambda kv: kv[1], reverse=True)
    ]

    genre_raw: dict[str, float] = {}
    for n, w in artist_weight.items():
        for g in artist_genres.get(n, []):
            genre_raw[g] = genre_raw.get(g, 0.0) + w
    genres = {g: round(v, 4) for g, v in
              sorted(normalize_weights(genre_raw).items(), key=lambda kv: kv[1], reverse=True)}

    tracks.sort(key=lambda t: t.weight, reverse=True)
    return Profile(source="spotify", user=user, tracks=tracks, artists=artists, genres=genres)


# ---------------------------------------------------------------------------
# PKCE helpers.
# ---------------------------------------------------------------------------

def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ---------------------------------------------------------------------------
# HTTP layer (thin; exercised manually with a real client ID).
# ---------------------------------------------------------------------------

def _post_form(url: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode("ascii")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Spotify token error {exc.code}: {exc.read().decode()}") from exc


def _api_get(token: str, path: str, params: dict) -> dict:
    url = f"{_API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Spotify API error {exc.code} on {path}: "
                           f"{exc.read().decode()}") from exc


def _api_post(token: str, path: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{_API}{path}", data=data, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Spotify API error {exc.code} on {path}: "
                           f"{exc.read().decode()}") from exc


def _capture_code(redirect_uri: str, expected_state: str, open_browser) -> str:
    """Run a one-shot loopback server, open the browser, return the auth code."""
    parsed = urllib.parse.urlparse(redirect_uri)
    holder: dict[str, str] = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            holder["code"] = (q.get("code") or [""])[0]
            holder["state"] = (q.get("state") or [""])[0]
            holder["error"] = (q.get("error") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>blend: you can close this tab.</h2>")
            done.set()

        def log_message(self, *_):  # silence
            pass

    server = http.server.HTTPServer((parsed.hostname, parsed.port or 80), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    open_browser()
    done.wait(timeout=300)
    server.shutdown()

    if holder.get("error"):
        raise RuntimeError(f"Spotify authorization denied: {holder['error']}")
    if holder.get("state") != expected_state:
        raise RuntimeError("OAuth state mismatch — possible CSRF, aborting.")
    if not holder.get("code"):
        raise RuntimeError("No authorization code received (timed out?).")
    return holder["code"]


def authorize(client_id: str, redirect_uri: str = _DEFAULT_REDIRECT,
              scopes: str = _SCOPES) -> dict:
    """Run the full PKCE browser flow and return a token dict."""
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)
    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": state,
    }
    url = f"{_AUTH_URL}?{urllib.parse.urlencode(auth_params)}"
    print(f"blend: opening Spotify authorization in your browser…\n  {url}")
    code = _capture_code(redirect_uri, state, lambda: webbrowser.open(url))
    token = _post_form(_TOKEN_URL, {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
    })
    return _stamp(token)


def refresh(client_id: str, refresh_token: str) -> dict:
    token = _post_form(_TOKEN_URL, {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    })
    token.setdefault("refresh_token", refresh_token)
    return _stamp(token)


def _stamp(token: dict) -> dict:
    token["expires_at"] = time.time() + int(token.get("expires_in", 3600)) - 60
    return token


# ---------------------------------------------------------------------------
# Token cache + orchestration.
# ---------------------------------------------------------------------------

def _load_cache() -> dict | None:
    try:
        with open(_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save_cache(token: dict) -> None:
    os.makedirs(os.path.dirname(_CACHE), exist_ok=True)
    with open(_CACHE, "w", encoding="utf-8") as f:
        json.dump(token, f)


def _valid_token(client_id: str, scopes: str = _SCOPES) -> str:
    """Return a usable access token covering `scopes`, reusing/refreshing the
    cache when possible and re-authorizing only if it lacks a needed scope."""
    required = set(scopes.split())
    token = _load_cache()
    if token and required <= set((token.get("scope") or "").split()):
        if token.get("expires_at", 0) > time.time():
            return token["access_token"]
        if token.get("refresh_token"):
            token = refresh(client_id, token["refresh_token"])
            _save_cache(token)
            return token["access_token"]
    token = authorize(client_id, scopes=scopes)
    _save_cache(token)
    return token["access_token"]


def fetch_top(token: str, time_range: str = "medium_term", limit: int = 50):
    tracks = _api_get(token, "/me/top/tracks",
                      {"time_range": time_range, "limit": limit}).get("items", [])
    artists = _api_get(token, "/me/top/artists",
                       {"time_range": time_range, "limit": limit}).get("items", [])
    return tracks, artists


def read_spotify(client_id: str, user: str, time_range: str = "medium_term") -> Profile:
    """Authorize (or reuse cache), fetch top tracks/artists, build a Profile."""
    token = _valid_token(client_id)
    tracks, artists = fetch_top(token, time_range=time_range)
    return profile_from_spotify(tracks, artists, user)

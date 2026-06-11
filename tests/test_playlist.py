"""Export layer: pure query/AppleScript builders + a monkeypatched Spotify export.

Live Spotify/osascript calls aren't hit here; the orchestration is tested by
stubbing the thin HTTP layer."""

from blend import playlist
from blend.blend import BlendResult


def _result():
    return BlendResult(
        users=("alice", "bob"), score=72, breakdown={},
        shared_artists=["Phoebe Bridgers"], shared_tracks=[],
        playlist=[
            {"title": "Motion Sickness", "artist": "Phoebe Bridgers",
             "origin": "shared", "isrc": "USABC1700001", "duration_ms": 240000},
            {"title": "Paul", "artist": "Big Thief",
             "origin": "alice", "isrc": None, "duration_ms": 260000},
        ],
    )


# -- pure builders ----------------------------------------------------------

def test_search_query_prefers_isrc():
    assert playlist.search_query({"isrc": "USABC1700001",
                                  "title": "x", "artist": "y"}) == "isrc:USABC1700001"
    q = playlist.search_query({"isrc": None, "title": "Paul", "artist": "Big Thief"})
    assert q == "track:Paul artist:Big Thief"


def test_pick_uri():
    assert playlist.pick_uri({"tracks": {"items": [{"uri": "spotify:track:1"}]}}) \
        == "spotify:track:1"
    assert playlist.pick_uri({"tracks": {"items": []}}) is None


def test_apple_script_generation_and_escaping():
    script = playlist.apple_script('Blend "Mix"', _result().playlist)
    assert script.startswith('tell application "Music"')
    assert script.rstrip().endswith("end tell")
    assert '\\"Mix\\"' in script                 # quote in the name is escaped
    assert script.count("duplicate (item 1 of hits)") == 2   # one per track
    assert 'name is "Motion Sickness"' in script


# -- orchestration (HTTP stubbed) ------------------------------------------

def test_spotify_export_resolves_creates_and_adds(monkeypatch):
    calls = {"posts": []}

    monkeypatch.setattr(playlist.sp, "_valid_token", lambda cid, scopes=None: "tok")

    def fake_get(token, path, params):
        if path == "/me":
            return {"id": "user123"}
        if path == "/search":
            # the ISRC track resolves; "Paul" doesn't
            if params["q"].startswith("isrc:"):
                return {"tracks": {"items": [{"uri": "spotify:track:abc"}]}}
            return {"tracks": {"items": []}}
        raise AssertionError(path)

    def fake_post(token, path, body):
        calls["posts"].append((path, body))
        if path.endswith("/playlists"):
            return {"id": "pl1", "external_urls": {"spotify": "https://open.spotify.com/pl1"}}
        return {"snapshot_id": "s1"}

    monkeypatch.setattr(playlist.sp, "_api_get", fake_get)
    monkeypatch.setattr(playlist.sp, "_api_post", fake_post)

    info = playlist.spotify_export(_result(), "client", name="My Blend", public=True)

    assert info["url"] == "https://open.spotify.com/pl1"
    assert info["added"] == 1
    assert info["missed"] == ["Big Thief — Paul"]
    # created one playlist with the given name + visibility, then added tracks
    create = next(b for p, b in calls["posts"] if p == "/users/user123/playlists")
    assert create["name"] == "My Blend" and create["public"] is True
    add = next(b for p, b in calls["posts"] if p.endswith("/tracks"))
    assert add["uris"] == ["spotify:track:abc"]

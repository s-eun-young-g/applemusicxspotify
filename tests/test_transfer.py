from blend import playlist
from blend import spotify as sp
from blend.apple import playlists_from_plist
from blend.profile import Track

# -- Apple: read playlists from the library plist ---------------------------

PLIST = {
    "Tracks": {
        "1": {"Name": "Motion Sickness", "Artist": "Phoebe Bridgers", "Total Time": 240000},
        "2": {"Name": "Paul", "Artist": "Big Thief"},
    },
    "Playlists": [
        {"Name": "Library", "Master": True, "Playlist Items": [{"Track ID": 1}]},
        {"Name": "Downloaded", "Distinguished Kind": 31, "Playlist Items": [{"Track ID": 1}]},
        {"Name": "Chill", "Playlist Items": [{"Track ID": 1}, {"Track ID": 2}]},
        {"Name": "Empty", "Playlist Items": []},
    ],
}


def test_playlists_skip_system_and_empty():
    pls = playlists_from_plist(PLIST)
    assert set(pls) == {"Chill"}                       # Library/Downloaded/Empty dropped
    assert [t.title for t in pls["Chill"]] == ["Motion Sickness", "Paul"]


# -- Spotify: resolve a playlist reference ----------------------------------

def test_resolve_playlist_from_url_uri_id():
    pid = "37i9dQZF1DXcBWIGoYBM5M"
    assert sp.resolve_playlist_id(None, f"https://open.spotify.com/playlist/{pid}?si=x") == pid
    assert sp.resolve_playlist_id(None, f"spotify:playlist:{pid}") == pid
    assert sp.resolve_playlist_id(None, pid) == pid    # raw 22-char id


def test_resolve_playlist_by_name(monkeypatch):
    monkeypatch.setattr(sp, "list_playlists", lambda t: [{"id": "abc", "name": "My Mix"}])
    assert sp.resolve_playlist_id("tok", "my mix") == "abc"


def test_playlist_tracks_parses_items(monkeypatch):
    monkeypatch.setattr(sp, "_api_get", lambda t, p, par: {
        "items": [{"track": {"name": "S", "artists": [{"name": "A"}],
                             "external_ids": {"isrc": "USX1"}}}],
        "next": None})
    assert sp.playlist_tracks("tok", "pid") == [{"title": "S", "artist": "A", "isrc": "USX1"}]


# -- Transfer orchestration (HTTP/osascript stubbed) ------------------------

def test_spotify_to_apple(monkeypatch):
    monkeypatch.setattr(playlist.sp, "_valid_token", lambda c, s=None: "tok")
    monkeypatch.setattr(playlist.sp, "resolve_playlist_id", lambda t, p: "pid")
    monkeypatch.setattr(playlist.sp, "playlist_tracks",
                        lambda t, pid: [{"title": "S", "artist": "A", "isrc": None}])
    monkeypatch.setattr(playlist, "apple_create",
                        lambda name, entries: {"playlist": name, "attempted": len(entries)})
    info = playlist.spotify_to_apple("cid", "My Mix")
    assert info["source_tracks"] == 1
    assert info["playlist"] == "My Mix (from Spotify)"


def test_apple_to_spotify(monkeypatch):
    import blend.apple as apple_mod
    monkeypatch.setattr(apple_mod, "read_library_playlists",
                        lambda path: {"My Mix": [Track("S", "A")]})
    monkeypatch.setattr(playlist, "spotify_create",
                        lambda cid, name, entries, public=False, description="":
                        {"url": "https://sp/pl", "added": len(entries), "missed": []})
    info = playlist.apple_to_spotify("/lib.xml", "My Mix", "cid", new_name="Copy")
    assert info["url"] == "https://sp/pl"
    assert info["source_tracks"] == 1


def test_apple_to_spotify_missing_playlist(monkeypatch):
    import blend.apple as apple_mod
    monkeypatch.setattr(apple_mod, "read_library_playlists", lambda path: {"Other": [Track("S", "A")]})
    import pytest
    with pytest.raises(RuntimeError):
        playlist.apple_to_spotify("/lib.xml", "Nope", "cid")

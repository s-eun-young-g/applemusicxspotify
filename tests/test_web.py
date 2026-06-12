"""Web API routes, via Flask's test client. Skipped if Flask isn't installed."""

import plistlib
import shutil

import pytest

pytest.importorskip("flask")

from blend.web import create_app


@pytest.fixture
def client(tmp_path):
    # seed the profiles dir with the bundled examples
    here = __import__("os").path.dirname(__file__)
    ex = __import__("os").path.join(here, "..", "examples")
    for name in ("alice.json", "bob.json", "carol.json"):
        shutil.copy(__import__("os").path.join(ex, name), tmp_path / name)
    app = create_app(str(tmp_path))
    app.config["PROFILES_DIR_TMP"] = str(tmp_path)
    return app.test_client()


def test_index_serves_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"blend" in r.data and b"<script>" in r.data


def test_state_lists_profiles(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    names = {p["name"] for p in r.get_json()["profiles"]}
    assert {"alice", "bob"} <= names


def test_blend_route(client):
    r = client.post("/api/blend", json={"a": "alice", "b": "bob", "limit": 10})
    assert r.status_code == 200
    data = r.get_json()
    assert 0 < data["score"] <= 100
    assert "Phoebe Bridgers" in data["shared_artists"]
    assert len(data["playlist"]) <= 10


def test_apple_route_reads_uploaded_xml(client, tmp_path):
    lib = tmp_path / "lib.xml"
    with open(lib, "wb") as f:
        plistlib.dump({"Tracks": {"1": {"Name": "S", "Artist": "A", "Genre": "indie",
                                         "Play Count": 3, "Total Time": 1000}}}, f)
    r = client.post("/api/profile/apple", json={"user": "carol", "xml": str(lib)})
    assert r.status_code == 200
    assert r.get_json()["tracks"] == 1
    # now it shows up in state
    assert any(p["name"] == "carol" for p in client.get("/api/state").get_json()["profiles"])


def test_apple_route_errors_without_library(client):
    r = client.post("/api/profile/apple", json={"user": "x", "xml": "/nope/nope.xml"})
    assert r.status_code == 400
    assert "library" in r.get_json()["error"].lower()


def test_export_spotify_requires_client_id(client):
    r = client.post("/api/export/spotify", json={"a": "alice", "b": "bob"})
    assert r.status_code == 400


def test_group_blend_route(client):
    r = client.post("/api/blend", json={"profiles": ["alice", "bob", "carol"], "limit": 5})
    assert r.status_code == 200
    data = r.get_json()
    assert data["mode"] == "group"
    assert data["pairwise"] and len(data["pairwise"]) == 3


def test_transfer_route_validates(client):
    assert client.post("/api/transfer", json={"src": "spotify", "dst": "spotify",
                                              "playlist": "x", "client_id": "c"}).status_code == 400
    assert client.post("/api/transfer", json={"src": "spotify", "dst": "apple",
                                              "playlist": ""}).status_code == 400
    assert client.post("/api/transfer", json={"src": "spotify", "dst": "apple",
                                              "playlist": "x"}).status_code == 400  # no client id

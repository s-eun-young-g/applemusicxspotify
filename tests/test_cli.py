import json
import plistlib

from blend.cli import main

PLIST = {
    "Tracks": {
        "1": {"Name": "Motion Sickness", "Artist": "Phoebe Bridgers",
              "Genre": "Indie", "Play Count": 50, "Total Time": 240000},
        "2": {"Name": "Paul", "Artist": "Big Thief",
              "Genre": "Folk", "Play Count": 20, "Total Time": 260000},
    }
}


def _write_plist(tmp_path):
    p = tmp_path / "lib.xml"
    with open(p, "wb") as f:
        plistlib.dump(PLIST, f)
    return p


def test_apple_then_mix(tmp_path, capsys):
    lib = _write_plist(tmp_path)
    out_a = tmp_path / "alice.json"
    rc = main(["apple", "--user", "alice", "--xml", str(lib), "-o", str(out_a)])
    assert rc == 0 and out_a.exists()

    # a second profile (bob) reusing the same library so they overlap
    out_b = tmp_path / "bob.json"
    rc = main(["apple", "--user", "bob", "--xml", str(lib), "-o", str(out_b)])
    assert rc == 0

    blend_out = tmp_path / "blend.json"
    rc = main(["mix", str(out_a), str(out_b), "-o", str(blend_out)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Compatibility:" in out
    data = json.loads(blend_out.read_text())
    assert data["score"] == 100          # identical libraries
    assert data["users"] == ["alice", "bob"]


def test_apple_missing_library_is_reported(tmp_path, capsys):
    rc = main(["apple", "--user", "x", "--xml", str(tmp_path / "nope.xml")])
    assert rc != 0


def test_spotify_without_client_id_explains_setup(capsys, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    rc = main(["spotify", "--user", "sofia"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "client ID" in err and "127.0.0.1:8888/callback" in err

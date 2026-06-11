import plistlib

from blend.apple import profile_from_plist, read_library

PLIST = {
    "Tracks": {
        "1": {"Name": "Motion Sickness", "Artist": "Phoebe Bridgers",
              "Genre": "Indie", "Play Count": 50, "Total Time": 240000, "Rating": 100},
        "2": {"Name": "Scott Street", "Artist": "Phoebe Bridgers",
              "Genre": "Indie", "Play Count": 10, "Total Time": 300000},
        "3": {"Name": "The Suburbs", "Artist": "Arcade Fire",
              "Genre": "Rock", "Play Count": 5, "Total Time": 200000, "Loved": True},
        "4": {"Name": "A Home Video", "Total Time": 100000},   # no Artist -> skipped
    }
}


def _profile():
    return profile_from_plist(PLIST, user="sofia")


def test_skips_rows_without_title_or_artist():
    p = _profile()
    assert len(p.tracks) == 3


def test_weights_normalized_and_sorted():
    p = _profile()
    # most-played + 5-star track is the strongest, weight 1.0, sorted first
    assert p.tracks[0].title == "Motion Sickness"
    assert p.tracks[0].weight == 1.0
    assert all(p.tracks[i].weight >= p.tracks[i + 1].weight for i in range(len(p.tracks) - 1))


def test_artist_and_genre_aggregation():
    p = _profile()
    top_artist = p.artists[0]
    assert top_artist.name == "Phoebe Bridgers"   # two tracks, high plays
    assert top_artist.weight == 1.0
    assert "indie" in top_artist.genres
    assert "indie" in p.genres and "rock" in p.genres
    assert p.genres["indie"] == 1.0               # indie outweighs rock


def test_apple_local_has_no_isrc():
    p = _profile()
    assert all(t.isrc is None for t in p.tracks)


def test_read_library_from_file(tmp_path):
    path = tmp_path / "lib.xml"
    with open(path, "wb") as f:
        plistlib.dump(PLIST, f)
    p = read_library(str(path), "sofia")
    assert p.source == "apple" and p.user == "sofia"
    assert len(p.tracks) == 3

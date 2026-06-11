from blend.profile import Artist, Profile, Track, normalize_weights


def test_profile_json_round_trip(tmp_path):
    p = Profile(
        source="apple", user="sofia",
        tracks=[Track("Song", "Artist", "Album", 200000, None, 12, 0.8)],
        artists=[Artist("Artist", 1.0, ["indie"])],
        genres={"indie": 1.0},
    )
    path = tmp_path / "p.json"
    p.save(str(path))
    back = Profile.load(str(path))
    assert back.user == "sofia"
    assert back.tracks[0].title == "Song"
    assert back.tracks[0].weight == 0.8
    assert back.artists[0].genres == ["indie"]
    assert back.genres == {"indie": 1.0}


def test_normalize_weights():
    assert normalize_weights({"a": 5, "b": 10}) == {"a": 0.5, "b": 1.0}
    assert normalize_weights({}) == {}
    assert normalize_weights({"a": 0, "b": 0}) == {"a": 0.0, "b": 0.0}

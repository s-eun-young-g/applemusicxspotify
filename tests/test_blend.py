from blend.blend import blend
from blend.profile import Artist, Profile, Track


def _profile(user, artists, genres, tracks):
    return Profile(
        source="apple", user=user,
        artists=[Artist(n, w, g) for n, w, g in artists],
        genres=genres,
        tracks=[Track(t, a, weight=w) for t, a, w in tracks],
    )


A = _profile(
    "alice",
    [("Phoebe Bridgers", 1.0, ["indie"]), ("Big Thief", 0.6, ["folk"])],
    {"indie": 1.0, "folk": 0.6},
    [("Motion Sickness", "Phoebe Bridgers", 1.0), ("Paul", "Big Thief", 0.6)],
)
B = _profile(
    "bob",
    [("Phoebe Bridgers", 1.0, ["indie"]), ("Drake", 0.5, ["rap"])],
    {"indie": 1.0, "rap": 0.5},
    [("Motion Sickness", "Phoebe Bridgers", 1.0), ("One Dance", "Drake", 0.5)],
)


def test_identical_profiles_score_high():
    r = blend(A, A)
    assert r.score >= 90
    assert r.breakdown["artists"] == 1.0


def test_disjoint_profiles_score_zero():
    x = _profile("x", [("Q", 1.0, ["jazz"])], {"jazz": 1.0}, [("J", "Q", 1.0)])
    y = _profile("y", [("R", 1.0, ["metal"])], {"metal": 1.0}, [("M", "R", 1.0)])
    r = blend(x, y)
    assert r.score == 0
    assert r.playlist == []


def test_blend_finds_shared_artist_and_track():
    r = blend(A, B)
    assert "Phoebe Bridgers" in r.shared_artists
    assert any("Motion Sickness" in s for s in r.shared_tracks)
    assert 0 < r.score < 100
    shared = [t for t in r.playlist if t["origin"] == "shared"]
    assert any(t["title"] == "Motion Sickness" for t in shared)


def test_introductions_pull_from_each_others_genres():
    # alice loves folk; bob has a folk-genre artist track to introduce to alice.
    folk_b = _profile(
        "bob",
        [("Phoebe Bridgers", 1.0, ["indie"]), ("Fleet Foxes", 0.9, ["folk"])],
        {"indie": 1.0, "folk": 0.9},
        [("Motion Sickness", "Phoebe Bridgers", 1.0),
         ("White Winter Hymnal", "Fleet Foxes", 0.9)],
    )
    r = blend(A, folk_b, limit=10)
    origins = {t["origin"] for t in r.playlist}
    # bob's folk track should be introduced to alice (alice has folk in top genres)
    assert "bob" in origins


def test_playlist_respects_limit():
    r = blend(A, B, limit=1)
    assert len(r.playlist) <= 1

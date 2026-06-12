import pytest

from blend.blend import group_blend
from blend.profile import Artist, Profile, Track


def mk(user, arts, genres, tracks):
    return Profile("apple", user,
                   artists=[Artist(n, w, g) for n, w, g in arts],
                   genres=genres,
                   tracks=[Track(t, a, weight=w) for t, a, w in tracks])


A = mk("alice", [("Phoebe Bridgers", 1.0, ["indie"]), ("Big Thief", 0.6, ["folk"])],
       {"indie": 1.0, "folk": 0.6},
       [("Motion Sickness", "Phoebe Bridgers", 1.0), ("Paul", "Big Thief", 0.6)])
B = mk("bob", [("Phoebe Bridgers", 1.0, ["indie"]), ("Mitski", 0.7, ["indie"])],
       {"indie": 1.0},
       [("Motion Sickness", "Phoebe Bridgers", 1.0), ("Nobody", "Mitski", 0.7)])
C = mk("carol", [("Phoebe Bridgers", 0.9, ["indie"]), ("Fleet Foxes", 0.8, ["folk"])],
       {"indie": 0.9, "folk": 0.8},
       [("Motion Sickness", "Phoebe Bridgers", 0.9),
        ("White Winter Hymnal", "Fleet Foxes", 0.8)])


def test_group_blend_three_people():
    g = group_blend([A, B, C])
    assert g.members == ["alice", "bob", "carol"]
    assert 0 <= g.score <= 100
    assert len(g.pairwise) == 3                  # 3 pairs for 3 people
    assert "Phoebe Bridgers" in g.shared_by_all  # everyone has her


def test_group_playlist_leads_with_all_shared_track():
    g = group_blend([A, B, C])
    first = g.playlist[0]
    assert first["title"] == "Motion Sickness"
    assert first["origin"] == "all"
    assert first["members"] == 3


def test_group_score_is_mean_of_pairwise():
    g = group_blend([A, B, C])
    assert g.score == round(sum(g.pairwise.values()) / len(g.pairwise))


def test_group_needs_two_profiles():
    with pytest.raises(ValueError):
        group_blend([A])


def test_two_profiles_via_group_matches_pairwise_pairs():
    g = group_blend([A, B])
    assert len(g.pairwise) == 1

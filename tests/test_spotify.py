"""The pure Spotify profile builder + a cross-platform (Spotify×Apple) blend.

Live OAuth isn't tested here (it needs a real client ID); profile_from_spotify is
pure over the raw API JSON, so it carries the coverage."""

from blend.blend import blend
from blend.profile import Artist, Profile, Track
from blend.spotify import _pkce_pair, profile_from_spotify

# Shapes mirror Spotify's /me/top/{tracks,artists} responses.
TOP_ARTISTS = [
    {"name": "Phoebe Bridgers", "genres": ["indie", "indie pop"]},
    {"name": "Big Thief", "genres": ["indie folk"]},
    {"name": "Drake", "genres": ["rap", "hip hop"]},
]
TOP_TRACKS = [
    {"name": "Motion Sickness", "duration_ms": 240000,
     "artists": [{"name": "Phoebe Bridgers"}], "album": {"name": "Stranger"},
     "external_ids": {"isrc": "USABC1700001"}},
    {"name": "Paul", "duration_ms": 260000,
     "artists": [{"name": "Big Thief"}], "album": {"name": "Masterpiece"},
     "external_ids": {"isrc": "USXYZ1600002"}},
]


def test_profile_from_spotify_shape():
    p = profile_from_spotify(TOP_TRACKS, TOP_ARTISTS, "sofia")
    assert p.source == "spotify" and p.user == "sofia"
    # rank 0 artist is the strongest
    assert p.artists[0].name == "Phoebe Bridgers"
    assert p.artists[0].weight == 1.0
    # genres aggregated and normalized
    assert "indie" in p.genres
    # tracks carry ISRC and are rank-weighted
    assert p.tracks[0].title == "Motion Sickness"
    assert p.tracks[0].isrc == "USABC1700001"
    assert p.tracks[0].weight >= p.tracks[1].weight


def test_track_artist_supplements_artist_list():
    # a track whose artist isn't in top_artists should still appear as an artist
    tracks = [{"name": "Solo", "artists": [{"name": "Newcomer"}],
               "album": {"name": "X"}, "duration_ms": 1000, "external_ids": {}}]
    p = profile_from_spotify(tracks, [], "x")
    assert any(a.name == "Newcomer" for a in p.artists)


def test_cross_platform_blend_matches_on_isrc_and_title():
    spotify_p = profile_from_spotify(TOP_TRACKS, TOP_ARTISTS, "sofia")
    # an Apple profile: same songs, ISRC on one, plain title on the other
    apple_p = Profile(
        source="apple", user="alex",
        artists=[Artist("Phoebe Bridgers", 1.0, ["indie"]),
                 Artist("Big Thief", 0.8, ["indie folk"])],
        genres={"indie": 1.0, "indie folk": 0.8},
        tracks=[
            Track("Motion Sickness", "Phoebe Bridgers", isrc="USABC1700001", weight=1.0),
            Track("Paul - Remaster", "Big Thief", weight=0.8),   # match by title
        ],
    )
    r = blend(spotify_p, apple_p)
    assert "Phoebe Bridgers" in r.shared_artists
    assert len(r.shared_tracks) == 2          # one via ISRC, one via normalized title
    assert r.score > 0


def test_pkce_pair_is_valid():
    verifier, challenge = _pkce_pair()
    assert 43 <= len(verifier) <= 128
    assert "=" not in challenge and "+" not in challenge and "/" not in challenge

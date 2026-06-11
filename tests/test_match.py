from blend.match import match_tracks, normalize, track_key
from blend.profile import Track


def test_normalize_strips_cruft():
    assert normalize("Motion Sickness") == "motion sickness"
    assert normalize("Motion Sickness (feat. Conor Oberst)") == "motion sickness"
    assert normalize("Bohemian Rhapsody - 2011 Remaster") == "bohemian rhapsody"
    assert normalize("Café del Mar [Live]") == "cafe del mar"
    assert normalize("FEELING feat. someone") == "feeling"


def test_track_key_matches_across_title_variants():
    a = Track("Motion Sickness", "Phoebe Bridgers")
    b = Track("Motion Sickness (feat. X) - 2017 Remaster", "Phoebe Bridgers")
    assert track_key(a) == track_key(b)


def test_match_by_normalized_key():
    a = [Track("Motion Sickness", "Phoebe Bridgers"),
         Track("Only One", "Nobody")]
    b = [Track("Motion Sickness - Remaster", "Phoebe Bridgers")]
    pairs = match_tracks(a, b)
    assert len(pairs) == 1
    assert pairs[0][0].title.startswith("Motion Sickness")


def test_match_by_isrc_takes_precedence():
    a = [Track("Song", "Artist A", isrc="USABC1234567")]
    b = [Track("Totally Different Title", "Artist B", isrc="USABC1234567")]
    pairs = match_tracks(a, b)
    assert len(pairs) == 1   # matched on ISRC despite different text


def test_no_false_matches():
    a = [Track("Song One", "Artist A")]
    b = [Track("Song Two", "Artist B")]
    assert match_tracks(a, b) == []

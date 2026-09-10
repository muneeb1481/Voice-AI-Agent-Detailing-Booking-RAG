from app.services.zip_lookup import state_from_zip


def test_known_zips_map_to_correct_state():
    assert state_from_zip("38103") == "TN"  # Memphis
    assert state_from_zip("21015") == "MD"  # Bel Air, MD — the reported live-call case
    assert state_from_zip("10001") == "NY"  # Manhattan
    assert state_from_zip("90210") == "CA"  # Beverly Hills
    assert state_from_zip("60601") == "IL"  # Chicago
    assert state_from_zip("98101") == "WA"  # Seattle
    assert state_from_zip("02108") == "MA"  # Boston
    assert state_from_zip("33101") == "FL"  # Miami


def test_zip_plus_four_still_works():
    assert state_from_zip("38103-1234") == "TN"


def test_none_or_short_zip_returns_none():
    assert state_from_zip(None) is None
    assert state_from_zip("") is None
    assert state_from_zip("12") is None


def test_unrecognized_prefix_returns_none_rather_than_guessing():
    assert state_from_zip("00000") is None

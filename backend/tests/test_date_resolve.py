from datetime import timedelta

from app.services.date_resolve import resolve_relative_date
from app.services.timezones import local_now


def test_today_and_tomorrow():
    today = local_now("TN").date()
    assert resolve_relative_date("today", "TN") == today
    assert resolve_relative_date("tomorrow", "TN") == today + timedelta(days=1)


def test_weekday_name_resolves_to_nearest_upcoming_occurrence():
    today = local_now("TN").date()
    for name in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        resolved = resolve_relative_date(name, "TN")
        assert resolved is not None
        assert resolved > today or resolved.weekday() != today.weekday()
        assert resolved.strftime("%A").lower() == name
        # Must be within the next 7 days, never further.
        assert (resolved - today).days <= 7


def test_next_weekday_same_as_plain_weekday():
    today = local_now("TN").date()
    plain = resolve_relative_date("friday", "TN")
    nxt = resolve_relative_date("next friday", "TN")
    assert plain == nxt
    assert plain > today


def test_in_n_days():
    today = local_now("TN").date()
    assert resolve_relative_date("in 3 days", "TN") == today + timedelta(days=3)


def test_unrecognized_phrase_returns_none():
    assert resolve_relative_date("whenever works", "TN") is None
    assert resolve_relative_date("", "TN") is None

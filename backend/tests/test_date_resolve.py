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


def test_explicit_month_day_both_orders():
    """The reported gap: a caller stating an explicit date ("12 September")
    was met with "could you confirm the exact date" even though it already was
    one — resolve_relative_date only handled relative phrases before this."""
    today = local_now("TN").date()
    expected_year = today.year if (9, 12) >= (today.month, today.day) else today.year + 1
    from datetime import date as date_cls

    expected = date_cls(expected_year, 9, 12)
    assert resolve_relative_date("12 September", "TN") == expected
    assert resolve_relative_date("September 12", "TN") == expected
    assert resolve_relative_date("Sept 12th", "TN") == expected
    assert resolve_relative_date("12th of September", "TN") == expected


def test_explicit_date_already_passed_this_year_rolls_to_next_year():
    today = local_now("TN").date()
    from datetime import date as date_cls, timedelta as td_cls

    past = today - td_cls(days=1)
    resolved = resolve_relative_date(f"{past.day} {past.strftime('%B')}", "TN")
    assert resolved is not None
    assert resolved >= today


def test_invalid_calendar_date_returns_none_not_a_guess():
    assert resolve_relative_date("February 30", "TN") is None

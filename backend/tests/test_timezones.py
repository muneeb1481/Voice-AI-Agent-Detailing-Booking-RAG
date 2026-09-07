from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.timezones import local_now, timezone_for_state


def test_known_state_maps_to_correct_zone():
    assert timezone_for_state("CA").key == "America/Los_Angeles"
    assert timezone_for_state("TN").key == "America/Chicago"
    assert timezone_for_state("NY").key == "America/New_York"


def test_unknown_or_missing_state_falls_back_to_eastern():
    assert timezone_for_state(None).key == "America/New_York"
    assert timezone_for_state("XX").key == "America/New_York"


def test_lowercase_state_still_resolves():
    assert timezone_for_state("ca").key == "America/Los_Angeles"


def test_local_now_reflects_the_chosen_zone():
    now_pacific = local_now("CA")
    assert now_pacific.tzinfo.key == "America/Los_Angeles"


def test_same_utc_instant_is_a_different_local_hour_by_state(client, auth):
    """The actual point of this feature: 9am is 9am in the customer's own state,
    not 9am UTC — so the same UTC instant should be valid business hours for one
    state and invalid for another."""
    # 16:00 UTC is ~11am Central (valid, 8-18) but ~9am Pacific (also valid) —
    # pick an instant that's valid Eastern/Central but past close on the Pacific
    # coast: 23:00 UTC is 6pm Central (edge of closing) and 3pm Pacific (fine) —
    # use late UTC evening where Central is closed but the difference is provable
    # via the actual rejection/acceptance rather than guessing at exact clock math.
    tz_ny = ZoneInfo("America/New_York")
    tz_la = ZoneInfo("America/Los_Angeles")

    # A time that is 9am in New York tomorrow — should be valid for an NY booking.
    ny_9am = (datetime.now(tz_ny) + timedelta(days=2)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Eastern Customer",
            "customer_phone": "+12125550001",
            "state": "NY",
            "zip_code": "10001",
            "starts_at": ny_9am.isoformat(),
            "duration_minutes": 60,
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text

    # The exact same UTC instant is 6am in Los Angeles — before business hours
    # there, so it should be rejected for a CA booking even though it's the
    # identical moment in time that was just accepted for NY.
    la_local_hour = ny_9am.astimezone(tz_la).hour
    assert la_local_hour < 8  # sanity check the test's own premise

    resp2 = client.post(
        "/api/bookings",
        json={
            "customer_name": "Pacific Customer",
            "customer_phone": "+13105550002",
            "state": "CA",
            "zip_code": "90001",
            "starts_at": ny_9am.isoformat(),
            "duration_minutes": 60,
        },
        headers=auth,
    )
    assert resp2.status_code == 400

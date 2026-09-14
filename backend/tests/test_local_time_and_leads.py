"""The caller's spoken time is the job state's local time, end to end — and a
caller who says yes before picking a time is saved as a callback lead."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.timezones import parse_clock_time

CENTRAL = ZoneInfo("America/Chicago")
EASTERN = ZoneInfo("America/New_York")
CALLER = "+12145550123"


def _day(days: int = 3, tz=CENTRAL) -> str:
    return (datetime.now(tz) + timedelta(days=days)).date().isoformat()


def _service_id(client, auth, name="Interior & Exterior Detailing"):
    services = client.get("/api/services", headers=auth).json()
    return next(s["id"] for s in services if s["name"] == name)


def _wrapped(name: str, arguments: dict, number: str | None = CALLER) -> dict:
    message = {
        "type": "tool-calls",
        "toolCallList": [{"id": "call_1", "function": {"name": name, "arguments": arguments}}],
    }
    if number:
        message["call"] = {"customer": {"number": number}}
    return {"message": message}


def _result(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["results"][0]["result"]


def test_parse_clock_time_variants():
    assert parse_clock_time("3 PM").hour == 15
    assert parse_clock_time("3:30pm").minute == 30
    assert parse_clock_time("10 a.m.").hour == 10
    assert parse_clock_time("15:00").hour == 15
    assert parse_clock_time("12 pm").hour == 12
    assert parse_clock_time("12 am").hour == 0
    assert parse_clock_time("whenever") is None


def test_afternoon_slot_is_reported_available(client):
    """The reported bug: 3 PM was open but the agent said it wasn't, because only
    the first 8 (morning, UTC) slots came back."""
    result = _result(
        client.post(
            "/api/vapi/list_slots",
            json=_wrapped("list_slots", {"state": "TX", "day": _day(), "time": "3 PM"}),
        )
    )
    assert "3:00 PM" in result["open_times"]
    assert result["requested_time_available"] is True


def test_closing_is_5pm_local(client):
    result = _result(
        client.post(
            "/api/vapi/list_slots",
            json=_wrapped("list_slots", {"state": "TX", "day": _day(), "time": "4:30 PM"}),
        )
    )
    # 90 min default can't start after 3:30 PM and still finish by 5.
    assert result["open_times"][-1] == "3:30 PM"
    assert result["requested_time_available"] is False
    assert "other time" in result["requested_time_note"]


def test_booked_3pm_texas_is_stored_as_3pm_texas(client, auth):
    """Caller says 3 PM in Dallas — stored instant must be 3 PM Central, whatever
    offset (or none, or a bogus Z) the agent attached."""
    service_id = _service_id(client, auth)
    day = _day()
    result = _result(
        client.post(
            "/api/vapi/book_appointment",
            json=_wrapped(
                "book_appointment",
                {
                    "customer_name": "Dallas Caller",
                    "state": "TX",
                    "zip_code": "75201",
                    "date": day,
                    "time": "3 PM",
                    "service_id": service_id,
                    "vehicle": "Toyota Camry",
                    "address": "1 Elm St",
                },
            ),
        )
    )
    assert result["time"] == "3:00 PM"
    assert result["date"] == day

    row = client.get("/api/bookings", headers=auth).json()[0]
    stored = datetime.fromisoformat(row["starts_at"].replace("Z", "+00:00"))
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    local = stored.astimezone(CENTRAL)
    assert (local.hour, local.minute) == (15, 0)
    assert row["customer"]["phone"] == CALLER  # from caller ID, never asked for


def test_z_suffixed_time_is_still_the_callers_local_time(client, auth):
    service_id = _service_id(client, auth)
    day = _day(4, EASTERN)
    _result(
        client.post(
            "/api/vapi/book_appointment",
            json=_wrapped(
                "book_appointment",
                {
                    "customer_name": "Maryland Caller",
                    "zip_code": "21015",  # MD -> Eastern
                    "starts_at": f"{day}T10:00:00Z",
                    "service_id": service_id,
                    "vehicle": "Honda Civic",
                    "address": "2 Oak St",
                },
            ),
        )
    )
    row = client.get("/api/bookings", headers=auth).json()[0]
    assert row["state"] == "MD"
    stored = datetime.fromisoformat(row["starts_at"].replace("Z", "+00:00"))
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=timezone.utc)
    assert stored.astimezone(EASTERN).hour == 10


def test_web_call_without_caller_id_asks_for_phone(client, auth):
    result = _result(
        client.post(
            "/api/vapi/save_lead",
            json=_wrapped("save_lead", {"customer_phone": "{{customer.number}}"}, number=None),
        )
    )
    assert isinstance(result, str) and "phone number" in result


def test_lead_saved_before_time_then_confirmed_by_booking(client, auth):
    service_id = _service_id(client, auth)
    lead = _result(
        client.post(
            "/api/vapi/save_lead",
            json=_wrapped(
                "save_lead",
                {"zip_code": "75201", "vehicle": "Toyota Camry", "service_id": service_id},
            ),
        )
    )
    assert lead["status"] == "pending"
    assert lead["price_cents"] is not None

    # Call drops here -> shop sees it as needing a callback, with no time.
    pending = client.get("/api/bookings", params={"status": "pending"}, headers=auth).json()
    assert len(pending) == 1 and pending[0]["starts_at"] is None
    assert client.get("/api/stats", headers=auth).json()["needs_callback"] == 1

    # Saving again in the same call updates the same lead, no duplicate.
    again = _result(
        client.post(
            "/api/vapi/save_lead",
            json=_wrapped("save_lead", {"customer_name": "Sam Lee", "service_id": service_id}),
        )
    )
    assert again["lead_id"] == lead["lead_id"]

    booked = _result(
        client.post(
            "/api/vapi/book_appointment",
            json=_wrapped(
                "book_appointment",
                {
                    "customer_name": "Sam Lee",
                    "zip_code": "75201",
                    "date": _day(),
                    "time": "11 AM",
                    "service_id": service_id,
                    "vehicle": "Toyota Camry",
                    "address": "3 Pine St",
                },
            ),
        )
    )
    assert booked["booking_id"] == lead["lead_id"]  # the lead became the appointment
    rows = client.get("/api/bookings", headers=auth).json()
    assert len(rows) == 1 and rows[0]["status"] == "scheduled"
    assert client.get("/api/stats", headers=auth).json()["needs_callback"] == 0


def test_admin_move_schedules_a_lead(client, auth):
    service_id = _service_id(client, auth)
    lead = _result(
        client.post(
            "/api/vapi/save_lead",
            json=_wrapped("save_lead", {"state": "TX", "service_id": service_id, "vehicle": "Camry"}),
        )
    )
    blocked = client.patch(
        f"/api/bookings/{lead['lead_id']}/status", json={"status": "done"}, headers=auth
    )
    assert blocked.status_code == 400

    start = (datetime.now(CENTRAL) + timedelta(days=3)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    moved = client.patch(
        f"/api/bookings/{lead['lead_id']}/reschedule",
        json={"starts_at": start.isoformat()},
        headers=auth,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "scheduled"
    assert moved.json()["ends_at"] is not None

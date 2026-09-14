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


def _book_args(service_id, **over):
    base = {
        "zip_code": "75201",
        "date": _day(),
        "time": "11 AM",
        "service_id": service_id,
        "vehicle": "Toyota Camry",
    }
    base.update(over)
    return base


def test_placeholder_name_and_city_address_are_sent_back_to_ask(client, auth):
    """Live call: the agent booked customer_name "[Customer Name]" and address
    "Dallas" without ever asking. Nothing may be booked from that."""
    service_id = _service_id(client, auth)
    no_name = _result(client.post("/api/vapi/book_appointment", json=_wrapped(
        "book_appointment", _book_args(service_id, customer_name="[Customer Name]", address="12 Elm St"))))
    assert isinstance(no_name, str) and "name" in no_name.lower()

    city_only = _result(client.post("/api/vapi/book_appointment", json=_wrapped(
        "book_appointment", _book_args(service_id, customer_name="Sam Lee", address="Dallas"))))
    assert isinstance(city_only, str) and "street address" in city_only.lower()
    assert client.get("/api/bookings", headers=auth).json() == []


def test_returning_caller_name_and_address_are_reused(client, auth):
    service_id = _service_id(client, auth)
    first = _result(client.post("/api/vapi/book_appointment", json=_wrapped(
        "book_appointment", _book_args(service_id, customer_name="Sam Lee", address="12 Elm St"))))
    assert "booking_id" in first

    lookup = _result(client.post("/api/vapi/lookup_appointments", json=_wrapped(
        "lookup_appointments", {"phone": "{{customer.number}}"})))
    assert lookup["known_customer"]["name"] == "Sam Lee"
    assert lookup["known_customer"]["address"] == "12 Elm St"

    second = _result(client.post("/api/vapi/book_appointment", json=_wrapped(
        "book_appointment", _book_args(service_id, time="2 PM"))))  # no name/address given
    assert "booking_id" in second
    newest = next(b for b in client.get("/api/bookings", headers=auth).json() if b["id"] == second["booking_id"])
    assert newest["customer"]["name"] == "Sam Lee" and newest["address"] == "12 Elm St"


def test_lookup_with_unresolved_placeholder_never_matches_anyone(client, auth):
    """A web call's literal {{customer.number}} matched old test bookings saved
    under that text and read out someone else's appointments."""
    service_id = _service_id(client, auth)
    client.post("/api/vapi/book_appointment", json={
        **_book_args(service_id, customer_name="Old Test", address="1 Main St"),
        "customer_phone": "{{customer.number}}x",  # legacy bad row shape
    })
    result = _result(client.post("/api/vapi/lookup_appointments", json=_wrapped(
        "lookup_appointments", {"phone": "{{customer.number}}"}, number=None)))
    assert result["count"] == 0 and result["known_customer"] is None


def test_past_closing_error_names_the_latest_start(client, auth):
    service_id = _service_id(client, auth, "Interior Detailing Only")
    result = _result(client.post("/api/vapi/book_appointment", json=_wrapped(
        "book_appointment", _book_args(service_id, time="4 PM", customer_name="Sam Lee", address="12 Elm St"))))
    assert isinstance(result, str)
    assert "closing" in result and " PM" in result
    assert client.get("/api/bookings", headers=auth).json() == []


def test_save_lead_flags_returning_customer(client, auth):
    service_id = _service_id(client, auth)
    fresh = _result(client.post("/api/vapi/save_lead", json=_wrapped("save_lead", {"service_id": service_id})))
    assert fresh["known_customer"] is None

    _result(client.post("/api/vapi/book_appointment", json=_wrapped(
        "book_appointment", _book_args(service_id, customer_name="Sam Lee", address="12 Elm St", lead_id=fresh["lead_id"]))))
    again = _result(client.post("/api/vapi/save_lead", json=_wrapped("save_lead", {"service_id": service_id})))
    assert again["known_customer"]["name"] == "Sam Lee"
    assert again["known_customer"]["address"] == "12 Elm St"
    assert "RETURNING CUSTOMER" in again["note"]


def test_list_services_tells_agent_not_to_read_price_list(client):
    body = client.post("/api/vapi/list_services").json()
    assert "names" in body["note"]


def test_assistant_own_name_is_never_booked_for_a_new_caller(client, auth):
    """Live call: the agent booked a new caller as "Muneeb" — its own greeting name."""
    service_id = _service_id(client, auth)
    lead = _result(client.post("/api/vapi/save_lead", json=_wrapped(
        "save_lead", {"service_id": service_id, "customer_name": "Muneeb"})))
    refused = _result(client.post("/api/vapi/book_appointment", json=_wrapped(
        "book_appointment", _book_args(service_id, customer_name="Muneeb", address="12 Elm St", lead_id=lead["lead_id"]))))
    assert isinstance(refused, str) and "name" in refused.lower()

    booked = _result(client.post("/api/vapi/book_appointment", json=_wrapped(
        "book_appointment", _book_args(service_id, customer_name="Sara Khan", address="12 Elm St", lead_id=lead["lead_id"]))))
    assert "booking_id" in booked
    row = client.get("/api/bookings", headers=auth).json()[0]
    assert row["customer"]["name"] == "Sara Khan"


def test_returning_caller_keeps_saved_name_even_if_agent_sends_its_own(client, auth):
    service_id = _service_id(client, auth)
    _result(client.post("/api/vapi/book_appointment", json=_wrapped(
        "book_appointment", _book_args(service_id, customer_name="Sara Khan", address="12 Elm St"))))
    second = _result(client.post("/api/vapi/book_appointment", json=_wrapped(
        "book_appointment", _book_args(service_id, time="2 PM", customer_name="Muneeb", address="12 Elm St"))))
    assert "booking_id" in second
    names = {b["customer"]["name"] for b in client.get("/api/bookings", headers=auth).json()}
    assert names == {"Sara Khan"}


def test_web_call_replay_phone_from_lead_and_all_missing_reported(client, auth):
    """Replays a live web call: phone given to save_lead only, then book_appointment
    sent no phone, the assistant's own name and a city as the address — and the agent
    told the caller they were booked. Must report name AND address, reuse the phone."""
    service_id = _service_id(client, auth, "Interior Detailing Only")
    lead = _result(client.post("/api/vapi/save_lead", json=_wrapped(
        "save_lead", {"service_id": service_id, "zip_code": "21201", "customer_phone": "94169084342"},
        number=None)))
    assert "NEW CUSTOMER" in lead["note"] and "full name" in lead["note"]

    refused = _result(client.post("/api/vapi/book_appointment", json=_wrapped(
        "book_appointment",
        _book_args(service_id, zip_code="21201", customer_name="Muneeb", address="Baltimore", lead_id=lead["lead_id"]),
        number=None)))
    assert refused.startswith("BOOKING FAILED")
    assert "name" in refused and "street address" in refused
    assert "phone" not in refused  # taken from the lead

    booked = _result(client.post("/api/vapi/book_appointment", json=_wrapped(
        "book_appointment",
        _book_args(service_id, zip_code="21201", customer_name="Sara Khan", address="12 Elm St", lead_id=lead["lead_id"]),
        number=None)))
    assert booked["booking_id"] == lead["lead_id"]
    row = client.get("/api/bookings", headers=auth).json()[0]
    assert (row["customer"]["phone"], row["customer"]["name"], row["status"]) == ("94169084342", "Sara Khan", "scheduled")

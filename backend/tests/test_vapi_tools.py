from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Business hours are validated in the booking's own state's local time — these
# tests default to KY (America/New_York), so times here are built in that zone.
EASTERN = ZoneInfo("America/New_York")


def future(days: int = 2, hour: int = 11) -> str:
    d = datetime.now(EASTERN) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def _service_id(client, auth, name="Interior & Exterior Detailing"):
    services = client.get("/api/services", headers=auth).json()
    return next(s["id"] for s in services if s["name"] == name)


def _book_payload(service_id: str, **over):
    base = {
        "customer_name": "Ray Ortiz",
        "customer_phone": "+15025550188",
        "state": "KY",
        "zip_code": "40202",
        "service_id": service_id,
        "vehicle": "2016 Honda Accord",
        "address": "100 Main St",
        "starts_at": future(),
    }
    base.update(over)
    return base


def test_book_then_lookup_then_cancel(client, auth):
    service_id = _service_id(client, auth)

    booked = client.post("/api/vapi/book_appointment", json=_book_payload(service_id))
    assert booked.status_code == 200, booked.text
    assert booked.json()["price_cents"] is not None
    booking_id = booked.json()["booking_id"]

    found = client.post("/api/vapi/lookup_appointments", json={"phone": "+15025550188"})
    assert found.json()["count"] == 1

    cancelled = client.post("/api/vapi/cancel_appointment", json={"booking_id": booking_id})
    assert cancelled.json()["status"] == "cancelled"

    after = client.post("/api/vapi/lookup_appointments", json={"phone": "+15025550188"})
    assert after.json()["count"] == 0


def test_voice_booking_shares_admin_write_path(client, auth):
    service_id = _service_id(client, auth)
    client.post("/api/vapi/book_appointment", json=_book_payload(service_id))
    listed = client.get("/api/bookings", headers=auth).json()
    assert len(listed) == 1
    assert listed[0]["source"] == "voice"


def test_voice_booking_without_vehicle_is_rejected(client, auth):
    service_id = _service_id(client, auth)
    payload = _book_payload(service_id)
    del payload["vehicle"]
    resp = client.post("/api/vapi/book_appointment", json=payload)
    assert resp.status_code == 422


def test_list_services_tool_returns_pricing(client):
    """The Vapi tool response is deliberately slim — see _price_entry in
    routers/vapi.py — a category with no floor is just the bare cents value,
    not a nested object, to cut real token weight off what gets resent on
    every turn of a call. A floored category (Interior Detailing Only) still
    comes back as {"price_cents", "min_price_cents"}."""
    resp = client.post("/api/vapi/list_services")
    assert resp.status_code == 200
    services = resp.json()["services"]
    assert len(services) > 0
    by_name = {s["name"]: s for s in services}
    assert by_name["Interior & Exterior Detailing"]["prices_by_vehicle_category"]["sedan"] == 20000
    assert by_name["Interior Detailing Only"]["prices_by_vehicle_category"]["sedan"] == {
        "price_cents": 15000,
        "min_price_cents": 15000,
    }
    assert by_name["Boat Detailing"]["price_per_foot_cents"] == 3500
    assert "note" not in by_name["Interior & Exterior Detailing"]


def test_list_slots_tool(client):
    resp = client.post(
        "/api/vapi/list_slots", json={"state": "TN", "day": future(days=6, hour=0)}
    )
    assert resp.status_code == 200
    assert resp.json()["count"] > 0
    assert len(resp.json()["slots"]) <= 8


def test_llm_supplied_garbage_is_rejected(client):
    resp = client.post(
        "/api/vapi/book_appointment",
        json={
            "customer_name": "",
            "customer_phone": "123",
            "state": "atlantis",
            "zip_code": "not-a-zip",
            "starts_at": "sometime next week",
        },
    )
    assert resp.status_code == 422


def _wrapped(name: str, arguments: dict, call_id: str = "call_123") -> dict:
    """Build a real Vapi tool-call request body — see app.services.vapi_protocol."""
    return {
        "message": {
            "type": "tool-calls",
            "toolCallList": [
                {"id": call_id, "function": {"name": name, "arguments": arguments}}
            ],
        }
    }


def test_wrapped_vapi_call_list_services_returns_results_envelope(client):
    """The actual shape a live phone call sends/expects — see the WebFetch-confirmed
    Vapi docs. A flat body (tested above) is only ever sent by our own admin/test
    tooling, never by a real call."""
    resp = client.post("/api/vapi/list_services", json=_wrapped("list_services", {}))
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert body["results"][0]["toolCallId"] == "call_123"
    assert len(body["results"][0]["result"]["services"]) > 0


def test_wrapped_vapi_call_classify_vehicle(client):
    resp = client.post(
        "/api/vapi/classify_vehicle",
        json=_wrapped("classify_vehicle", {"vehicle": "2019 Toyota Tacoma"}, "call_456"),
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["toolCallId"] == "call_456"
    assert result["result"]["category"] == "truck"


def test_wrapped_vapi_call_lookup_appointments_empty(client):
    resp = client.post(
        "/api/vapi/lookup_appointments",
        json=_wrapped("lookup_appointments", {"phone": "+19995550000"}),
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["count"] == 0


def test_wrapped_vapi_call_full_book_then_lookup_then_cancel(client, auth):
    service_id = _service_id(client, auth)

    booked = client.post(
        "/api/vapi/book_appointment",
        json=_wrapped("book_appointment", _book_payload(service_id), "call_book"),
    )
    assert booked.status_code == 200, booked.text
    booking_result = booked.json()["results"][0]["result"]
    assert booking_result["price_cents"] is not None
    booking_id = booking_result["booking_id"]

    found = client.post(
        "/api/vapi/lookup_appointments",
        json=_wrapped("lookup_appointments", {"phone": "+15025550188"}, "call_lookup"),
    )
    assert found.json()["results"][0]["result"]["count"] == 1

    cancelled = client.post(
        "/api/vapi/cancel_appointment",
        json=_wrapped("cancel_appointment", {"booking_id": booking_id}, "call_cancel"),
    )
    assert cancelled.json()["results"][0]["result"]["status"] == "cancelled"


def test_wrapped_vapi_call_domain_error_comes_back_as_200_with_text(client, auth):
    """A real call must never get a bare 422/400 for a domain error — the LLM can't
    read an HTTP status, only the `result` text — so this must be 200 with the
    error message as the result, not raised as an HTTPException."""
    service_id = _service_id(client, auth)
    payload = _book_payload(service_id, starts_at="2020-01-01T09:00:00-05:00")  # in the past
    resp = client.post(
        "/api/vapi/book_appointment", json=_wrapped("book_appointment", payload, "call_err")
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert isinstance(result, str)
    assert "past" in result.lower()


def test_wrapped_vapi_call_invalid_arguments_comes_back_as_200_with_text(client):
    """Same idea for a schema-invalid argument (missing required field) — must
    still be 200 with an explanation, never a bare 422 the LLM can't act on."""
    resp = client.post(
        "/api/vapi/classify_vehicle", json=_wrapped("classify_vehicle", {}, "call_bad")
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert isinstance(result, str)
    assert "invalid arguments" in result.lower()


def test_flat_legacy_shape_still_returns_a_real_422(client):
    """The admin dashboard and this test suite's OWN direct calls must keep their
    existing behavior — a real HTTP 422 on bad input, no results envelope."""
    resp = client.post("/api/vapi/classify_vehicle", json={})
    assert resp.status_code == 422
    assert "results" not in resp.json()


def test_wrapped_call_ignores_spoofed_phone_uses_verified_caller_id(client, auth):
    """The LLM could be tricked into passing a DIFFERENT phone number as the
    lookup_appointments argument — the backend must ignore it and use the real
    verified caller ID from Vapi's own call context instead, so a caller can never
    browse another customer's bookings no matter what the model is told to do."""
    service_id = _service_id(client, auth)
    real_owner_phone = "+15025550188"
    client.post(
        "/api/vapi/book_appointment",
        json=_wrapped(
            "book_appointment", _book_payload(service_id, customer_phone=real_owner_phone)
        ),
    )

    spoofed_request = {
        "message": {
            "type": "tool-calls",
            "toolCallList": [
                {
                    "id": "call_spoof",
                    "function": {
                        "name": "lookup_appointments",
                        # The model was told/tricked into asking about someone else's number.
                        "arguments": {"phone": "+19995551234"},
                    },
                }
            ],
            "call": {"customer": {"number": real_owner_phone}},
        }
    }
    resp = client.post("/api/vapi/lookup_appointments", json=spoofed_request)
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    # Found under the REAL caller's number, not the spoofed argument.
    assert result["count"] == 1


def test_book_appointment_derives_state_from_zip_when_omitted(client, auth):
    """The reported live-call problem: the caller only knew their ZIP, not the
    state name, and the agent had no way to resolve it. state is now optional
    on VoiceBookingCreate — derived server-side from zip_code."""
    service_id = _service_id(client, auth)
    payload = _book_payload(service_id, zip_code="21015")  # Bel Air, MD
    del payload["state"]
    resp = client.post("/api/vapi/book_appointment", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "MD"


def test_list_slots_derives_state_from_zip(client):
    resp = client.post(
        "/api/vapi/list_slots", json={"zip_code": "21015", "day": future(days=6, hour=0)}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] > 0

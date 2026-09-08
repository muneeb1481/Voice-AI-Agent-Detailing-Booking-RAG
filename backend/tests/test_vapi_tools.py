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
    resp = client.post("/api/vapi/list_services")
    assert resp.status_code == 200
    services = resp.json()["services"]
    assert len(services) > 0
    by_name = {s["name"]: s for s in services}
    assert by_name["Interior & Exterior Detailing"]["prices_by_vehicle_category"]["sedan"]["price_cents"] == 20000
    assert by_name["Boat Detailing"]["price_per_foot_cents"] == 3500


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

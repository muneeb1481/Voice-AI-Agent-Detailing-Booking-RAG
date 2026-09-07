from datetime import datetime, timedelta, timezone


def future(days: int = 2, hour: int = 11) -> str:
    d = datetime.now(timezone.utc) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


BOOK = {
    "customer_name": "Ray Ortiz",
    "customer_phone": "+15025550188",
    "market": "louisville",
}


def test_book_then_lookup_then_cancel(client):
    booked = client.post("/api/vapi/book_appointment", json={**BOOK, "starts_at": future()})
    assert booked.status_code == 200, booked.text
    booking_id = booked.json()["booking_id"]

    found = client.post("/api/vapi/lookup_appointments", json={"phone": "+15025550188"})
    assert found.json()["count"] == 1

    cancelled = client.post("/api/vapi/cancel_appointment", json={"booking_id": booking_id})
    assert cancelled.json()["status"] == "cancelled"

    after = client.post("/api/vapi/lookup_appointments", json={"phone": "+15025550188"})
    assert after.json()["count"] == 0


def test_voice_booking_shares_admin_write_path(client, auth):
    client.post("/api/vapi/book_appointment", json={**BOOK, "starts_at": future()})
    listed = client.get("/api/bookings", headers=auth).json()
    assert len(listed) == 1
    assert listed[0]["source"] == "voice"


def test_list_slots_tool(client):
    resp = client.post(
        "/api/vapi/list_slots", json={"market": "memphis", "day": future(days=6, hour=0)}
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
            "market": "atlantis",
            "starts_at": "sometime next week",
        },
    )
    assert resp.status_code == 422

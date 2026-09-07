from datetime import datetime, timedelta, timezone


def future(days: int = 2, hour: int = 10) -> str:
    d = datetime.now(timezone.utc) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def payload(**over):
    base = {
        "customer_name": "Dana Reed",
        "customer_phone": "+19015550142",
        "market": "memphis",
        "starts_at": future(),
        "duration_minutes": 90,
        "vehicle": "2019 Tacoma",
    }
    base.update(over)
    return base


def test_create_and_list(client, auth):
    resp = client.post("/api/bookings", json=payload(), headers=auth)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "scheduled"
    assert body["customer"]["name"] == "Dana Reed"

    listed = client.get("/api/bookings", headers=auth).json()
    assert len(listed) == 1


def test_double_booking_rejected(client, auth):
    client.post("/api/bookings", json=payload(), headers=auth)
    clash = client.post("/api/bookings", json=payload(), headers=auth)
    assert clash.status_code == 409


def test_different_market_can_share_a_slot(client, auth):
    client.post("/api/bookings", json=payload(), headers=auth)
    other = client.post(
        "/api/bookings",
        json=payload(market="nashville", customer_phone="+16155550101"),
        headers=auth,
    )
    assert other.status_code == 201


def test_past_time_rejected(client, auth):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    resp = client.post("/api/bookings", json=payload(starts_at=past), headers=auth)
    assert resp.status_code == 400


def test_outside_business_hours_rejected(client, auth):
    resp = client.post("/api/bookings", json=payload(starts_at=future(hour=3)), headers=auth)
    assert resp.status_code == 400


def test_reschedule(client, auth):
    booking_id = client.post("/api/bookings", json=payload(), headers=auth).json()["id"]
    resp = client.patch(
        f"/api/bookings/{booking_id}/reschedule",
        json={"starts_at": future(days=3, hour=14)},
        headers=auth,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rescheduled"


def test_cancel_then_reschedule_rejected(client, auth):
    booking_id = client.post("/api/bookings", json=payload(), headers=auth).json()["id"]
    client.patch(
        f"/api/bookings/{booking_id}/status", json={"status": "cancelled"}, headers=auth
    )
    resp = client.patch(
        f"/api/bookings/{booking_id}/reschedule",
        json={"starts_at": future(days=4)},
        headers=auth,
    )
    assert resp.status_code == 400


def test_slots_exclude_booked_time(client, auth):
    day = future(days=5, hour=0)
    before = client.get(
        "/api/slots", params={"market": "memphis", "day": day}, headers=auth
    ).json()
    client.post("/api/bookings", json=payload(starts_at=future(days=5, hour=10)), headers=auth)
    after = client.get(
        "/api/slots", params={"market": "memphis", "day": day}, headers=auth
    ).json()
    assert len(after) < len(before)


def test_filter_by_market(client, auth):
    client.post("/api/bookings", json=payload(), headers=auth)
    client.post(
        "/api/bookings",
        json=payload(market="nashville", customer_phone="+16155550101"),
        headers=auth,
    )
    memphis = client.get("/api/bookings", params={"market": "memphis"}, headers=auth).json()
    assert len(memphis) == 1


def test_stats(client, auth):
    client.post("/api/bookings", json=payload(), headers=auth)
    stats = client.get("/api/stats", headers=auth).json()
    assert stats["upcoming"] == 1

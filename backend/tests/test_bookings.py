from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Business hours are validated in the booking's own state's local time — these
# tests default to TN (America/Chicago), so times here are built in that zone.
CENTRAL = ZoneInfo("America/Chicago")


def future(days: int = 2, hour: int = 10) -> str:
    d = datetime.now(CENTRAL) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def payload(**over):
    base = {
        "customer_name": "Dana Reed",
        "customer_phone": "+19015550142",
        "state": "TN",
        "zip_code": "38103",
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


def test_different_state_can_share_a_slot(client, auth):
    client.post("/api/bookings", json=payload(), headers=auth)
    other = client.post(
        "/api/bookings",
        json=payload(state="KY", customer_phone="+16155550101"),
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
        "/api/slots", params={"state": "TN", "day": day}, headers=auth
    ).json()
    client.post("/api/bookings", json=payload(starts_at=future(days=5, hour=10)), headers=auth)
    after = client.get(
        "/api/slots", params={"state": "TN", "day": day}, headers=auth
    ).json()
    assert len(after) < len(before)


def test_filter_by_state(client, auth):
    client.post("/api/bookings", json=payload(), headers=auth)
    client.post(
        "/api/bookings",
        json=payload(state="KY", customer_phone="+16155550101"),
        headers=auth,
    )
    tn = client.get("/api/bookings", params={"state": "TN"}, headers=auth).json()
    assert len(tn) == 1


def test_stats(client, auth):
    client.post("/api/bookings", json=payload(), headers=auth)
    stats = client.get("/api/stats", headers=auth).json()
    assert stats["upcoming"] == 1


def test_state_full_name_normalizes_to_code(client, auth):
    resp = client.post("/api/bookings", json=payload(state="Tennessee"), headers=auth)
    assert resp.status_code == 201, resp.text
    assert resp.json()["state"] == "TN"


def test_invalid_state_rejected(client, auth):
    resp = client.post("/api/bookings", json=payload(state="Atlantis"), headers=auth)
    assert resp.status_code == 422


def test_invalid_zip_rejected(client, auth):
    resp = client.post("/api/bookings", json=payload(zip_code="not-a-zip"), headers=auth)
    assert resp.status_code == 422


def test_detailer_search_is_partial_and_case_insensitive(client, auth):
    booking_id = client.post(
        "/api/bookings", json=payload(detailer="Marcus Reed"), headers=auth
    ).json()["id"]
    found = client.get("/api/bookings", params={"detailer": "marc"}, headers=auth).json()
    assert len(found) == 1
    assert found[0]["id"] == booking_id


def test_assign_detailer_after_booking_created(client, auth):
    booking_id = client.post("/api/bookings", json=payload(), headers=auth).json()["id"]
    resp = client.patch(
        f"/api/bookings/{booking_id}/detailer",
        json={"detailer": "Jordan"},
        headers=auth,
    )
    assert resp.status_code == 200
    assert resp.json()["detailer"] == "Jordan"


def test_price_computed_from_service_and_vehicle_category(client, auth):
    services = client.get("/api/services", headers=auth).json()
    combo = next(s for s in services if s["name"] == "Interior & Exterior Detailing")
    prices = {p["category"]: p["price_cents"] for p in combo["prices"]}

    sedan = client.post(
        "/api/bookings",
        json=payload(service_id=combo["id"], vehicle="Toyota Corolla"),
        headers=auth,
    ).json()
    assert sedan["price_cents"] == prices["sedan"]
    assert sedan["vehicle_category"] == "sedan"

    truck = client.post(
        "/api/bookings",
        json=payload(
            service_id=combo["id"],
            vehicle="Ford F-150",
            customer_phone="+19015550999",
            starts_at=future(days=3),
        ),
        headers=auth,
    ).json()
    assert truck["price_cents"] == prices["truck"]
    assert truck["vehicle_category"] == "truck"
    assert truck["price_cents"] != sedan["price_cents"]  # genuinely different, not base+surcharge


def test_price_override_wins_over_catalog(client, auth):
    booking = client.post(
        "/api/bookings", json=payload(price_cents=5000), headers=auth
    ).json()
    assert booking["price_cents"] == 5000

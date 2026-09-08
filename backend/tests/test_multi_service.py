from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")


def future(days=3, hour=10):
    d = datetime.now(EASTERN) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def test_list_addons_admin(client, auth):
    resp = client.get("/api/addons", headers=auth)
    assert resp.status_code == 200
    names = [a["name"] for a in resp.json()]
    assert "Buffing" in names
    assert "Waxing" in names
    assert "Paint Correction" in names


def test_list_addons_vapi_tool(client):
    resp = client.post("/api/vapi/list_addons")
    assert resp.status_code == 200
    addons = resp.json()["addons"]
    assert any(a["name"] == "Engine Bay Cleaning" for a in addons)


def test_booking_with_base_service_plus_addon(client, auth):
    services = client.get("/api/services", headers=auth).json()
    addons = client.get("/api/addons", headers=auth).json()
    base = next(s for s in services if s["name"] == "Interior + Exterior Full Detail")
    wax = next(a for a in addons if a["name"] == "Waxing")

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Multi Item",
            "customer_phone": "+19015550250",
            "state": "TN",
            "zip_code": "38103",
            "starts_at": future(),
            "service_id": base["id"],
            "vehicle": "Toyota Corolla",
            "addon_ids": [wax["id"]],
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["price_cents"] == base["price_cents"] + wax["price_cents"]
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Waxing"
    assert "Waxing" in body["service_label"]


def test_booking_with_extra_service_and_addon_sums_duration_into_slot(client, auth):
    """The calendar slot must reflect the FULL combined time, not just the base
    service — otherwise the next booking would be scheduled on top of unfinished work."""
    services = client.get("/api/services", headers=auth).json()
    addons = client.get("/api/addons", headers=auth).json()
    base = next(s for s in services if s["name"] == "Full Interior Detail")
    ceramic = next(s for s in services if s["name"] == "Ceramic Coating")
    buff = next(a for a in addons if a["name"] == "Buffing")

    starts = future(days=5, hour=9)
    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Long Job",
            "customer_phone": "+19015550251",
            "state": "TN",
            "zip_code": "38103",
            "starts_at": starts,
            "service_id": base["id"],
            "vehicle": "Honda Civic",
            "extra_service_ids": [ceramic["id"]],
            "addon_ids": [buff["id"]],
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    expected_price = base["price_cents"] + ceramic["price_cents"] + buff["price_cents"]
    assert body["price_cents"] == expected_price
    assert len(body["items"]) == 2

    expected_duration = (
        base["duration_minutes"] + ceramic["duration_minutes"] + buff["duration_minutes"]
    )
    start_dt = datetime.fromisoformat(body["starts_at"])
    end_dt = datetime.fromisoformat(body["ends_at"])
    actual_minutes = int((end_dt - start_dt).total_seconds() // 60)
    assert actual_minutes == expected_duration


def test_price_override_wins_even_with_items(client, auth):
    services = client.get("/api/services", headers=auth).json()
    addons = client.get("/api/addons", headers=auth).json()
    base = services[0]
    wax = next(a for a in addons if a["name"] == "Waxing")

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Override Test",
            "customer_phone": "+19015550252",
            "state": "TN",
            "zip_code": "38103",
            "starts_at": future(days=6),
            "service_id": base["id"],
            "vehicle": "Toyota Corolla",
            "addon_ids": [wax["id"]],
            "price_cents": 1000,
        },
        headers=auth,
    )
    assert resp.status_code == 201
    assert resp.json()["price_cents"] == 1000


def test_large_vehicle_surcharge_applies_to_addons_too(client, auth):
    services = client.get("/api/services", headers=auth).json()
    addons = client.get("/api/addons", headers=auth).json()
    base = services[0]
    wax = next(a for a in addons if a["name"] == "Waxing")

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Truck Owner",
            "customer_phone": "+19015550253",
            "state": "TN",
            "zip_code": "38103",
            "starts_at": future(days=7),
            "service_id": base["id"],
            "vehicle": "Ford F-150",
            "addon_ids": [wax["id"]],
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    expected = (
        base["price_cents"]
        + base["large_vehicle_surcharge_cents"]
        + wax["price_cents"]
        + wax["large_vehicle_surcharge_cents"]
    )
    assert body["price_cents"] == expected


def test_invalid_addon_id_rejected(client, auth):
    services = client.get("/api/services", headers=auth).json()
    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Bad Addon",
            "customer_phone": "+19015550254",
            "state": "TN",
            "zip_code": "38103",
            "starts_at": future(days=8),
            "service_id": services[0]["id"],
            "vehicle": "Toyota Corolla",
            "addon_ids": ["not-a-real-id"],
        },
        headers=auth,
    )
    assert resp.status_code == 400

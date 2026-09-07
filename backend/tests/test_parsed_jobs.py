def test_parse_job_endpoint_extracts_fields(client, auth):
    text = "Alex\n+1234567890\nToyota Corolla\nTN 38103\ninterior exterior\n$200"
    resp = client.post("/api/parse-job", json={"text": text}, headers=auth)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["customer_name"] == "Alex"
    assert body["customer_phone"] == "+1234567890"
    assert body["price_cents"] == 20000


def test_parse_job_requires_admin(client):
    resp = client.post("/api/parse-job", json={"text": "Alex\n+1234567890"})
    assert resp.status_code == 401


def test_create_parsed_booking_saves_with_parser_source(client, auth):
    resp = client.post(
        "/api/bookings/parsed",
        json={
            "customer_name": "Alex",
            "customer_phone": "+1234567890",
            "vehicle": "Toyota Corolla",
            "state": "TN",
            "zip_code": "38103",
            "service_label": "Interior exterior",
            "price_cents": 20000,
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"] == "parser"
    assert body["price_cents"] == 20000
    assert body["status"] == "scheduled"


def test_create_parsed_booking_skips_slot_conflict_check(client, auth):
    """Parsed jobs log what happened; they don't contend for a calendar slot the
    way phone/admin scheduled bookings do."""
    for _ in range(2):
        resp = client.post(
            "/api/bookings/parsed",
            json={"customer_name": "Alex", "customer_phone": "+1234567890"},
            headers=auth,
        )
        assert resp.status_code == 201


def test_create_parsed_booking_invalid_state_falls_back_gracefully(client, auth):
    resp = client.post(
        "/api/bookings/parsed",
        json={
            "customer_name": "Alex",
            "customer_phone": "+1234567890",
            "state": "Not A Real State",
        },
        headers=auth,
    )
    assert resp.status_code == 201
    assert resp.json()["state"] is None


def test_parsed_booking_accepts_starts_at(client, auth):
    from datetime import datetime, timedelta, timezone

    when = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    resp = client.post(
        "/api/bookings/parsed",
        json={
            "customer_name": "Alex",
            "customer_phone": "+1234567890",
            "starts_at": when,
        },
        headers=auth,
    )
    assert resp.status_code == 201
    assert resp.json()["starts_at"][:10] == when[:10]

def test_current_time_deterministic_periods(client):
    """Not asserting a specific value (the clock moves), just that the two
    documented buckets are hit and internally consistent."""
    day = client.post("/api/vapi/current_time", json={"state": "NY"}).json()
    assert day["period"] in ("day", "night")
    if day["period"] == "day":
        assert day["closing_line"] == "Have a nice day!"
    else:
        assert day["closing_line"] == "Have a great evening!"
    assert 0 <= day["hour"] <= 23


def test_current_time_no_state_still_works(client):
    resp = client.post("/api/vapi/current_time", json={})
    assert resp.status_code == 200


def _service_id(client, auth, name="Interior & Exterior Detailing"):
    services = client.get("/api/services", headers=auth).json()
    return next(s["id"] for s in services if s["name"] == name)


def test_cancel_with_reason_is_saved(client, auth):
    service_id = _service_id(client, auth)
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    starts = (datetime.now(ZoneInfo("America/New_York")) + timedelta(days=2)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    booked = client.post(
        "/api/vapi/book_appointment",
        json={
            "customer_name": "Casey Lane",
            "customer_phone": "+16465550100",
            "state": "NY",
            "zip_code": "10001",
            "starts_at": starts.isoformat(),
            "service_id": service_id,
            "vehicle": "Honda Civic",
            "address": "1 Main St",
        },
    )
    booking_id = booked.json()["booking_id"]

    cancelled = client.post(
        "/api/vapi/cancel_appointment",
        json={"booking_id": booking_id, "reason": "found a cheaper detailer nearby"},
    )
    assert cancelled.status_code == 200

    listed = client.get("/api/bookings", headers=auth).json()
    row = next(b for b in listed if b["id"] == booking_id)
    assert row["status"] == "cancelled"
    assert row["cancellation_reason"] == "found a cheaper detailer nearby"


def test_cancel_without_reason_leaves_it_null(client, auth):
    service_id = _service_id(client, auth)
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    starts = (datetime.now(ZoneInfo("America/New_York")) + timedelta(days=3)).replace(
        hour=11, minute=0, second=0, microsecond=0
    )
    booked = client.post(
        "/api/vapi/book_appointment",
        json={
            "customer_name": "Jordan Reyes",
            "customer_phone": "+16465550101",
            "state": "NY",
            "zip_code": "10001",
            "starts_at": starts.isoformat(),
            "service_id": service_id,
            "vehicle": "Toyota Camry",
            "address": "2 Main St",
        },
    )
    booking_id = booked.json()["booking_id"]

    client.post("/api/vapi/cancel_appointment", json={"booking_id": booking_id})

    listed = client.get("/api/bookings", headers=auth).json()
    row = next(b for b in listed if b["id"] == booking_id)
    assert row["cancellation_reason"] is None


def test_call_ended_webhook_stores_transcript(client):
    payload = {
        "message": {
            "type": "end-of-call-report",
            "call": {"id": "call_abc123", "endedReason": "customer-ended-call"},
            "customer": {"number": "+16465550199", "name": "Sam Rivera"},
            "transcript": "AI: Hello, thanks for calling.\nUser: Hi, I'd like to book a wash.",
            "analysis": {"summary": "Customer booked an express wash."},
            "durationSeconds": 132,
        }
    }
    resp = client.post("/api/vapi/call-ended", json=payload)
    assert resp.status_code == 200


def test_call_ended_webhook_survives_unexpected_shape(client):
    """The exact Vapi payload shape can drift — this must never 500, and must
    still keep the raw body even when nothing else parses out."""
    resp = client.post("/api/vapi/call-ended", json={"something": "unexpected"})
    assert resp.status_code == 200


def test_call_transcripts_listed_for_admin(client, auth):
    payload = {
        "message": {
            "call": {"id": "call_xyz"},
            "customer": {"number": "+16465550200"},
            "transcript": "AI: hi\nUser: hi",
        }
    }
    client.post("/api/vapi/call-ended", json=payload)

    resp = client.get("/api/call-transcripts", headers=auth)
    assert resp.status_code == 200
    calls = resp.json()
    assert any(c["call_id"] == "call_xyz" for c in calls)


def test_call_transcripts_require_admin(client):
    assert client.get("/api/call-transcripts").status_code == 401


def test_classify_vehicle_tool_recognizes_car(client):
    resp = client.post("/api/vapi/classify_vehicle", json={"vehicle": "Toyota Corolla"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "sedan"
    assert body["supported"] is True


def test_classify_vehicle_tool_recognizes_motorcycle_as_supported(client):
    """Motorcycles are now a real bookable service, not a rejected category."""
    resp = client.post("/api/vapi/classify_vehicle", json={"vehicle": "Kawasaki Ninja H2R"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "motorcycle"
    assert body["supported"] is True


def test_booking_a_motorcycle_against_a_car_only_service_is_rejected(client, auth):
    """A motorcycle can be booked (via Motorcycle Full Detailing), but not against
    a car service that has no motorcycle row in its price matrix."""
    service_id = _service_id(client, auth)  # Interior & Exterior Detailing — car only
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    starts = (datetime.now(ZoneInfo("America/New_York")) + timedelta(days=2)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    resp = client.post(
        "/api/vapi/book_appointment",
        json={
            "customer_name": "Biker Joe",
            "customer_phone": "+16465550111",
            "state": "NY",
            "zip_code": "10001",
            "starts_at": starts.isoformat(),
            "service_id": service_id,
            "vehicle": "Harley-Davidson Sportster",
            "address": "5 Main St",
        },
    )
    assert resp.status_code == 400
    assert "motorcycle" in resp.json()["detail"].lower()


def test_call_ended_webhook_ignores_non_end_of_call_message_types(client, auth):
    """Vapi's serverMessages can include many intermediate event types
    (conversation-update, status-update, speech-update, etc.) if an assistant
    isn't restricted to just end-of-call-report. This must never persist a row
    for any of those — only a genuine end-of-call-report — otherwise one real
    call floods the admin Calls page with dozens of near-empty duplicate rows."""
    for bad_type in ["conversation-update", "status-update", "speech-update", "tool-calls"]:
        resp = client.post(
            "/api/vapi/call-ended",
            json={"message": {"type": bad_type, "call": {"id": "call_flood_test"}}},
        )
        assert resp.status_code == 200

    calls = client.get("/api/call-transcripts", headers=auth).json()
    assert not any(c["call_id"] == "call_flood_test" for c in calls)

    resp = client.post(
        "/api/vapi/call-ended",
        json={
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "call_flood_test", "endedReason": "customer-ended-call"},
                "durationSeconds": 60,
            }
        },
    )
    assert resp.status_code == 200
    calls = client.get("/api/call-transcripts", headers=auth).json()
    assert sum(1 for c in calls if c["call_id"] == "call_flood_test") == 1


def test_call_ended_webhook_upserts_by_call_id_not_duplicated(client, auth):
    """Vapi has been observed sending end-of-call-report twice for the same
    call (a preliminary one, then a final one with durationSeconds filled in)
    — this must update the same row, not create a second one."""
    preliminary = {
        "message": {
            "type": "end-of-call-report",
            "call": {"id": "call_upsert_test", "endedReason": "customer-ended-call"},
            "customer": {"number": "+16465550300"},
        }
    }
    final = {
        "message": {
            "type": "end-of-call-report",
            "call": {"id": "call_upsert_test", "endedReason": "customer-ended-call"},
            "customer": {"number": "+16465550300"},
            "transcript": "AI: hi\nUser: bye",
            "analysis": {"summary": "Short test call."},
            "durationSeconds": 45,
        }
    }
    client.post("/api/vapi/call-ended", json=preliminary)
    client.post("/api/vapi/call-ended", json=final)

    calls = client.get("/api/call-transcripts", headers=auth).json()
    matching = [c for c in calls if c["call_id"] == "call_upsert_test"]
    assert len(matching) == 1
    assert matching[0]["duration_seconds"] == 45
    assert matching[0]["summary"] == "Short test call."

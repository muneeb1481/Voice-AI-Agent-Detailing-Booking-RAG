from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")


def future(days=3, hour=10):
    d = datetime.now(EASTERN) + timedelta(days=days)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def _service(client, auth, name):
    services = client.get("/api/services", headers=auth).json()
    svc = next(s for s in services if s["name"] == name)
    # Normalize the admin API's list-of-rows shape into a dict for easy lookup —
    # keeps the tests below readable without hand-searching a list every time.
    svc["prices_by_vehicle_category"] = {p["category"]: p for p in svc["prices"]}
    return svc


def _addon(client, auth, name):
    addons = client.get("/api/addons", headers=auth).json()
    return next(a for a in addons if a["name"] == name)


def _sedan_price(service, category="sedan"):
    return service["prices_by_vehicle_category"][category]["price_cents"]


def test_list_addons_admin(client, auth):
    resp = client.get("/api/addons", headers=auth)
    assert resp.status_code == 200
    names = [a["name"] for a in resp.json()]
    assert "Pet Hair Removal" in names
    assert "Waxing Only" in names
    assert "Engine Bay Cleaning" in names


def test_list_addons_vapi_tool(client):
    resp = client.post("/api/vapi/list_addons")
    assert resp.status_code == 200
    addons = resp.json()["addons"]
    assert any(a["name"] == "Headlight Restoration" for a in addons)


def test_booking_with_base_service_plus_addon(client, auth):
    base = _service(client, auth, "Interior & Exterior Detailing")
    wax = _addon(client, auth, "Waxing Only")

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
    assert body["price_cents"] == _sedan_price(base) + wax["price_cents"]
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Waxing Only"
    assert "Waxing Only" in body["service_label"]


def test_booking_with_extra_service_and_addon_sums_duration_into_slot(client, auth):
    """The calendar slot must reflect the FULL combined time, not just the base
    service — otherwise the next booking would be scheduled on top of unfinished work."""
    base = _service(client, auth, "Interior Detailing Only")
    ceramic = _service(client, auth, "Ceramic Coating - 2 Year")
    pet_hair = _addon(client, auth, "Pet Hair Removal")

    # future() builds in Eastern, but the booking's state is TN (Central, 1h
    # behind) — start with enough margin that the Central-time conversion still
    # lands within business hours.
    starts = future(days=5, hour=10)
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
            "addon_ids": [pet_hair["id"]],
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    expected_price = _sedan_price(base) + _sedan_price(ceramic) + pet_hair["price_cents"]
    assert body["price_cents"] == expected_price
    assert len(body["items"]) == 2

    expected_duration = (
        base["duration_minutes"] + ceramic["duration_minutes"] + pet_hair["duration_minutes"]
    )
    start_dt = datetime.fromisoformat(body["starts_at"])
    end_dt = datetime.fromisoformat(body["ends_at"])
    actual_minutes = int((end_dt - start_dt).total_seconds() // 60)
    assert actual_minutes == expected_duration


def test_price_override_wins_even_with_items(client, auth):
    base = _service(client, auth, "Interior & Exterior Detailing")
    wax = _addon(client, auth, "Waxing Only")

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


def test_price_varies_by_vehicle_category(client, auth):
    """The core of this pricing model: the SAME service costs a genuinely
    different amount for a sedan vs a van, not a flat price plus a surcharge."""
    base = _service(client, auth, "Interior & Exterior Detailing")
    sedan_price = base["prices_by_vehicle_category"]["sedan"]["price_cents"]
    van_price = base["prices_by_vehicle_category"]["van"]["price_cents"]
    assert sedan_price == 20000
    assert van_price == 40000
    assert sedan_price != van_price

    resp_sedan = client.post(
        "/api/bookings",
        json={
            "customer_name": "Sedan Owner", "customer_phone": "+19015550260",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=9),
            "service_id": base["id"], "vehicle": "Toyota Corolla",
        },
        headers=auth,
    )
    resp_van = client.post(
        "/api/bookings",
        json={
            "customer_name": "Van Owner", "customer_phone": "+19015550261",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=9, hour=14),
            "service_id": base["id"], "vehicle": "Mercedes Sprinter",
        },
        headers=auth,
    )
    assert resp_sedan.json()["price_cents"] == sedan_price
    assert resp_van.json()["price_cents"] == van_price


def test_service_not_offered_for_category_is_rejected(client, auth):
    """Ceramic Coating is Sedan/SUV/Truck only per the catalog — a coupe should
    be rejected outright, not silently mispriced."""
    ceramic = _service(client, auth, "Ceramic Coating - 3 Year")
    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Coupe Owner", "customer_phone": "+19015550262",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=10),
            "service_id": ceramic["id"], "vehicle": "Ford Mustang",
        },
        headers=auth,
    )
    assert resp.status_code == 400
    assert "coupe" in resp.json()["detail"].lower()


def test_motorcycle_service_is_bookable(client, auth):
    moto = _service(client, auth, "Motorcycle Full Detailing")
    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Biker", "customer_phone": "+19015550263",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=11),
            "service_id": moto["id"], "vehicle": "Kawasaki Ninja H2R",
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["vehicle_category"] == "motorcycle"
    assert resp.json()["price_cents"] == 17000


def test_boat_booking_requires_length(client, auth):
    boat = _service(client, auth, "Boat Detailing")
    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Boat Owner", "customer_phone": "+19015550264",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=12),
            "service_id": boat["id"], "vehicle": "30 foot pontoon boat",
        },
        headers=auth,
    )
    assert resp.status_code == 400
    assert "length" in resp.json()["detail"].lower()


def test_boat_booking_with_length_prices_per_foot(client, auth):
    boat = _service(client, auth, "Boat Detailing")
    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Boat Owner", "customer_phone": "+19015550265",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=13),
            "service_id": boat["id"], "vehicle": "30 foot pontoon boat",
            "vehicle_length_ft": 30,
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["price_cents"] == 30 * 3500


def test_discount_applies_and_repeats_until_floor(client, auth):
    """Repeated $10 objections stack, but the backend clamps at the price floor —
    never trust the agent's arithmetic on money."""
    base = _service(client, auth, "Interior Detailing Only")  # sedan floor == price, no room
    floor = base["prices_by_vehicle_category"]["sedan"]["min_price_cents"]
    price = base["prices_by_vehicle_category"]["sedan"]["price_cents"]
    assert floor == price  # sanity check: sedan interior-only starts already at its floor

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Haggler", "customer_phone": "+19015550266",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=14),
            "service_id": base["id"], "vehicle": "Toyota Corolla",
            "discount_cents": 1000,
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["price_cents"] == floor  # clamped — can't go below the floor
    assert body["discount_cents"] == 0  # nothing to give, already at floor
    assert body["original_price_cents"] == price


def test_discount_applies_partially_when_room_exists(client, auth):
    base = _service(client, auth, "Interior Detailing Only")
    suv_price = base["prices_by_vehicle_category"]["suv"]["price_cents"]
    suv_floor = base["prices_by_vehicle_category"]["suv"]["min_price_cents"]
    assert suv_price > suv_floor  # SUV has $10 of room per the catalog

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "SUV Haggler", "customer_phone": "+19015550267",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=15),
            "service_id": base["id"], "vehicle": "Honda CR-V",
            "discount_cents": 1000,
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["price_cents"] == suv_floor
    assert body["discount_cents"] == suv_price - suv_floor


def test_waxing_only_addon_varies_by_vehicle_category(client, auth):
    wax = _addon(client, auth, "Waxing Only")
    by_category = {p["category"]: p for p in wax["prices"]}
    assert by_category["sedan"]["price_cents"] == 7000
    assert by_category["suv"]["price_cents"] == 7000
    assert by_category["truck"]["price_cents"] == 7000
    assert by_category["van"]["price_cents"] == 10000
    assert by_category["minivan"]["price_cents"] == 10000
    assert all(p["min_price_cents"] == 5000 for p in by_category.values())


def test_waxing_only_addon_prices_higher_for_van(client, auth):
    wax = _addon(client, auth, "Waxing Only")

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Van Waxer", "customer_phone": "+19015550273",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=19),
            "vehicle": "Mercedes Sprinter", "addon_ids": [wax["id"]],
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["price_cents"] == 10000


def test_waxing_only_addon_not_discounted_by_default(client, auth):
    """The floor only matters if a discount is requested — a customer who never
    objects is quoted the full $70, not the insist-only $50."""
    base = _service(client, auth, "Interior & Exterior Detailing")
    wax = _addon(client, auth, "Waxing Only")

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "No Haggle", "customer_phone": "+19015550270",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=16),
            "service_id": base["id"], "vehicle": "Toyota Corolla",
            "addon_ids": [wax["id"]],
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["price_cents"] == _sedan_price(base) + 7000


def test_waxing_only_addon_discount_clamps_at_its_own_floor(client, auth):
    """A big requested discount on a booking that's ONLY the Waxing Only add-on
    (no base service) must still stop at the add-on's own $50 floor."""
    wax = _addon(client, auth, "Waxing Only")

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Wax Haggler", "customer_phone": "+19015550271",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=17),
            "vehicle": "Toyota Corolla",
            "addon_ids": [wax["id"]],
            "discount_cents": 5000,
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["price_cents"] == 5000  # clamped at the $50 floor, not $20
    assert body["discount_cents"] == 2000
    assert body["original_price_cents"] == 7000


def test_pet_hair_addon_has_no_floor_and_can_discount_to_zero(client, auth):
    pet_hair = _addon(client, auth, "Pet Hair Removal")
    assert pet_hair["min_price_cents"] is None

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "No Floor Haggler", "customer_phone": "+19015550272",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=18),
            "vehicle": "Toyota Corolla",
            "addon_ids": [pet_hair["id"]],
            "discount_cents": 7000,
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["price_cents"] == 0


def test_buffing_is_a_standalone_bookable_service(client, auth):
    """Buffing alone (no waxing) must be independently bookable, same price as
    the Buffing & Waxing bundle for that category."""
    buffing = _service(client, auth, "Buffing")
    bundle = _service(client, auth, "Buffing & Waxing")
    assert _sedan_price(buffing) == _sedan_price(bundle) == 20000

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Buffing Only", "customer_phone": "+19015550280",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=20),
            "service_id": buffing["id"], "vehicle": "Toyota Corolla",
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["price_cents"] == 20000


def test_exterior_detailing_is_a_standalone_bookable_service(client, auth):
    """Exterior alone must be bookable, priced the same as Interior Detailing Only
    for that category (mirrored per the shop's instruction)."""
    exterior = _service(client, auth, "Exterior Detailing")
    interior = _service(client, auth, "Interior Detailing Only")
    assert _sedan_price(exterior) == _sedan_price(interior) == 15000

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Exterior Only", "customer_phone": "+19015550281",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=21),
            "service_id": exterior["id"], "vehicle": "Toyota Corolla",
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["price_cents"] == 15000


def test_shampooing_addon_varies_by_vehicle_category(client, auth):
    shampoo = _addon(client, auth, "Shampooing")
    by_category = {p["category"]: p for p in shampoo["prices"]}
    assert by_category["sedan"]["price_cents"] == 5000
    assert by_category["truck"]["price_cents"] == 5000
    assert by_category["minivan"]["price_cents"] == 5000
    assert by_category["suv"]["price_cents"] == 5000
    assert by_category["van"]["price_cents"] == 12000
    assert all(p["min_price_cents"] is None for p in by_category.values())


def test_shampooing_addon_prices_higher_for_van(client, auth):
    shampoo = _addon(client, auth, "Shampooing")

    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Van Shampoo", "customer_phone": "+19015550282",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=22),
            "vehicle": "Mercedes Sprinter", "addon_ids": [shampoo["id"]],
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["price_cents"] == 12000


def test_bundles_still_bookable_alongside_separate_items(client, auth):
    """Interior & Exterior Detailing and Buffing & Waxing remain bookable as
    convenience combos even though their components are now separately bookable."""
    bundle = _service(client, auth, "Interior & Exterior Detailing")
    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Bundle Booker", "customer_phone": "+19015550283",
            "state": "TN", "zip_code": "38103", "starts_at": future(days=23),
            "service_id": bundle["id"], "vehicle": "Toyota Corolla",
        },
        headers=auth,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["price_cents"] == 20000


def test_invalid_addon_id_rejected(client, auth):
    base = _service(client, auth, "Interior & Exterior Detailing")
    resp = client.post(
        "/api/bookings",
        json={
            "customer_name": "Bad Addon",
            "customer_phone": "+19015550254",
            "state": "TN",
            "zip_code": "38103",
            "starts_at": future(days=8),
            "service_id": base["id"],
            "vehicle": "Toyota Corolla",
            "addon_ids": ["not-a-real-id"],
        },
        headers=auth,
    )
    assert resp.status_code == 400

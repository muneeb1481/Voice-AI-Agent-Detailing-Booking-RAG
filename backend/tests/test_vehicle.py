from app.services.vehicle import classify_vehicle, is_large_vehicle


def test_truck_detected():
    assert classify_vehicle("2019 Toyota Tacoma") == "truck"
    assert classify_vehicle("Ford F-150 Lariat") == "truck"


def test_suv_detected():
    assert classify_vehicle("2022 Honda CR-V") == "suv"
    assert classify_vehicle("Jeep Wrangler") == "suv"


def test_sedan_detected():
    assert classify_vehicle("Toyota Corolla") == "sedan"


def test_unknown_vehicle_returns_none():
    assert classify_vehicle("some weird vehicle nobody has heard of xyz") is None


def test_empty_input():
    assert classify_vehicle(None) is None
    assert classify_vehicle("") is None


def test_is_large_vehicle():
    assert is_large_vehicle("truck") is True
    assert is_large_vehicle("suv") is True
    assert is_large_vehicle("sedan") is False
    assert is_large_vehicle(None) is False


def test_motorcycle_detected():
    assert classify_vehicle("Kawasaki Ninja H2R") == "motorcycle"
    assert classify_vehicle("Harley-Davidson Sportster") == "motorcycle"
    assert classify_vehicle("Ducati Panigale") == "motorcycle"


def test_motorcycle_is_unsupported():
    from app.services.vehicle import is_unsupported_vehicle

    assert is_unsupported_vehicle("motorcycle") is True
    assert is_unsupported_vehicle("sedan") is False
    assert is_unsupported_vehicle(None) is False

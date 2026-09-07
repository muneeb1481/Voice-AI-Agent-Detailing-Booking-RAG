def test_login_success(client):
    resp = client.post(
        "/api/auth/login", json={"email": "admin@test.com", "password": "testpass123"}
    )
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"


def test_login_wrong_password(client):
    resp = client.post(
        "/api/auth/login", json={"email": "admin@test.com", "password": "nope"}
    )
    assert resp.status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/api/bookings").status_code == 401


def test_me(client, auth):
    resp = client.get("/api/auth/me", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@test.com"

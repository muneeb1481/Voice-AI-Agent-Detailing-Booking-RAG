def test_list_detailers_seeded(client, auth):
    resp = client.get("/api/detailers", headers=auth)
    assert resp.status_code == 200
    names = [d["name"] for d in resp.json()]
    assert "Marcus" in names


def test_create_detailer(client, auth):
    resp = client.post("/api/detailers", json={"name": "Taylor"}, headers=auth)
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "Taylor"


def test_create_duplicate_detailer_returns_existing(client, auth):
    first = client.post("/api/detailers", json={"name": "Taylor"}, headers=auth).json()
    second = client.post("/api/detailers", json={"name": "Taylor"}, headers=auth).json()
    assert first["id"] == second["id"]


def test_delete_detailer_removes_from_active_list(client, auth):
    created = client.post("/api/detailers", json={"name": "Casey"}, headers=auth).json()
    resp = client.delete(f"/api/detailers/{created['id']}", headers=auth)
    assert resp.status_code == 204
    names = [d["name"] for d in client.get("/api/detailers", headers=auth).json()]
    assert "Casey" not in names


def test_detailers_require_auth(client):
    assert client.get("/api/detailers").status_code == 401

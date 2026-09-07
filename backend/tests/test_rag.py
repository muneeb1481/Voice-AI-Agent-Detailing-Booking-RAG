import io

PRICING = (
    "Ceramic coating for a mid-size sedan is 799 dollars and takes about six hours. "
    "Full interior detail is 189 dollars. Express wash and wax is 79 dollars. "
    "We serve Memphis, Nashville and Louisville with mobile service at no extra "
    "travel fee within 20 miles of downtown. "
) * 30


def upload(client, auth, name: str, body: str):
    return client.post(
        "/api/documents",
        files={"file": (name, io.BytesIO(body.encode()), "text/plain")},
        headers=auth,
    )


def test_upload_creates_chunks(client, auth):
    resp = upload(client, auth, "pricing.txt", PRICING)
    assert resp.status_code == 201, resp.text
    assert resp.json()["chunk_count"] > 1


def test_empty_file_rejected(client, auth):
    resp = upload(client, auth, "empty.txt", "   ")
    assert resp.status_code == 400


def test_delete_removes_chunks(client, auth):
    doc_id = upload(client, auth, "pricing.txt", PRICING).json()["id"]
    assert client.get("/api/stats", headers=auth).json()["chunks"] > 0

    assert client.delete(f"/api/documents/{doc_id}", headers=auth).status_code == 204
    stats = client.get("/api/stats", headers=auth).json()
    assert stats["documents"] == 0
    assert stats["chunks"] == 0  # no stale embeddings survive a deleted doc


def test_ask_with_no_documents_refuses_to_guess(client):
    resp = client.post("/api/vapi/ask", json={"question": "How much is ceramic coating?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["grounded"] is False
    assert body["sources"] == []
    assert "799" not in body["answer"]


def test_ask_retrieves_after_upload(client, auth):
    upload(client, auth, "pricing.txt", PRICING)
    resp = client.post("/api/vapi/ask", json={"question": "ceramic coating price sedan"})
    body = resp.json()
    assert body["grounded"] is True
    assert body["sources"]
    assert "ceramic" in body["answer"].lower()


def test_documents_require_auth(client):
    assert client.get("/api/documents").status_code == 401

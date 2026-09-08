import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = (
    f"sqlite+pysqlite:///{Path(tempfile.gettempdir()) / 'detailing_test.db'}"
)
os.environ["ADMIN_EMAIL"] = "admin@test.com"
os.environ["ADMIN_PASSWORD"] = "testpass123"
os.environ["OPENAI_API_KEY"] = ""
os.environ["VAPI_SECRET"] = ""
# Tests must be deterministic and offline — without this, a real GROQ_API_KEYS or
# KIMI_API_KEY in the developer's .env would make tests silently call the live API.
os.environ["GROQ_API_KEYS"] = ""
os.environ["KIMI_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    from app.seed import seed

    with SessionLocal() as db:
        seed(db)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client):
    resp = client.post(
        "/api/auth/login", json={"email": "admin@test.com", "password": "testpass123"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}

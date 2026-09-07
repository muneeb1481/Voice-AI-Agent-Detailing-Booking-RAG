"""Idempotent seed: admin user + default service catalogue."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AdminUser, Service
from app.security import hash_password

settings = get_settings()

DEFAULT_SERVICES = [
    ("Express Wash & Wax", 60, 7900),
    ("Full Interior Detail", 150, 18900),
    ("Interior + Exterior Full Detail", 240, 29900),
    ("Ceramic Coating", 360, 79900),
    ("Headlight Restoration", 45, 9900),
]


def seed(db: Session) -> None:
    email = settings.admin_email.lower()
    existing = db.execute(select(AdminUser).where(AdminUser.email == email)).scalar_one_or_none()
    if existing is None:
        db.add(AdminUser(email=email, password_hash=hash_password(settings.admin_password)))

    for name, minutes, price in DEFAULT_SERVICES:
        found = db.execute(select(Service).where(Service.name == name)).scalar_one_or_none()
        if found is None:
            db.add(Service(name=name, duration_minutes=minutes, price_cents=price))

    db.commit()

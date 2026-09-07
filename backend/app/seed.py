"""Idempotent seed: admin user + default service catalogue."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AdminUser, Detailer, Service
from app.security import hash_password

settings = get_settings()

# name, duration_minutes, price_cents, large_vehicle_surcharge_cents
DEFAULT_SERVICES = [
    ("Express Wash & Wax", 60, 7900, 0),
    ("Full Interior Detail", 150, 18900, 2000),
    ("Interior + Exterior Full Detail", 240, 29900, 3000),
    ("Ceramic Coating", 360, 79900, 10000),
    ("Headlight Restoration", 45, 9900, 0),
]

DEFAULT_DETAILERS = ["Marcus", "Alexis", "Diego", "Sam", "Riley", "Jordan"]


def seed(db: Session) -> None:
    email = settings.admin_email.lower()
    existing = db.execute(select(AdminUser).where(AdminUser.email == email)).scalar_one_or_none()
    if existing is None:
        db.add(AdminUser(email=email, password_hash=hash_password(settings.admin_password)))

    for name, minutes, price, surcharge in DEFAULT_SERVICES:
        found = db.execute(select(Service).where(Service.name == name)).scalar_one_or_none()
        if found is None:
            db.add(
                Service(
                    name=name,
                    duration_minutes=minutes,
                    price_cents=price,
                    large_vehicle_surcharge_cents=surcharge,
                )
            )

    for name in DEFAULT_DETAILERS:
        found = db.execute(select(Detailer).where(Detailer.name == name)).scalar_one_or_none()
        if found is None:
            db.add(Detailer(name=name))

    db.commit()

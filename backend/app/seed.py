"""Idempotent seed: admin user + the real ShinePro catalog (per-category pricing).

Prices come straight from the ShinePro pricing/service guide. A few numbers had to
be estimated where the guide didn't give one explicitly — each is flagged below.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AddOn, AdminUser, Detailer, Service, ServicePrice
from app.security import hash_password

settings = get_settings()

STANDARD_CATEGORIES = ["sedan", "suv", "truck", "coupe", "van", "minivan"]
# The guide never mentions hatchbacks. Priced the same as sedans as the closest
# reasonable stand-in — revisit if ShinePro wants a different number for these.
HATCHBACK_LIKE_SEDAN = True

# name, duration_minutes, {category: (price_cents, min_price_cents | None)}
DEFAULT_SERVICES: list[tuple[str, int, dict]] = [
    (
        "Interior & Exterior Detailing",
        120,
        {
            "sedan": (20000, None), "suv": (22000, None), "truck": (22000, None),
            "coupe": (20000, None), "van": (40000, None), "minivan": (30000, None),
        },
    ),
    (
        # Duration estimated (the guide doesn't state one for this line alone).
        "Interior Detailing Only",
        90,
        {
            "sedan": (15000, 15000), "suv": (18000, 17000), "truck": (17000, 17000),
            "coupe": (16000, 16000), "van": (25000, 25000), "minivan": (20000, 20000),
        },
    ),
    (
        # Duration estimated to land inside the guide's stated 3-5h combined range
        # when stacked on the 2h base service.
        "Buffing & Waxing",
        150,
        {
            "sedan": (20000, None), "suv": (20000, None), "truck": (20000, None),
            "coupe": (20000, None), "van": (30000, None), "minivan": (20000, None),
        },
    ),
    (
        # The guide states "5-8 hours total" identically for all three correction
        # levels; used the same estimate (6.5h) for each rather than inventing a
        # difference the source doesn't give.
        "Paint Correction Level 1",
        390,
        {
            "sedan": (40000, None), "suv": (40000, None), "truck": (40000, None),
            "coupe": (40000, None), "van": (50000, None), "minivan": (40000, None),
        },
    ),
    (
        "Paint Correction Level 2",
        390,
        {c: (100000, None) for c in STANDARD_CATEGORIES},
    ),
    (
        "Paint Correction Level 3",
        390,
        {c: (150000, None) for c in STANDARD_CATEGORIES},
    ),
]

# Ceramic Coating: only offered for Sedan/SUV/Truck per the guide, flat price
# across those three. Duration estimated within the guide's "2-3 hours" range.
CERAMIC_TIERS = [
    ("Ceramic Coating - 2 Year", 40000),
    ("Ceramic Coating - 3 Year", 80000),
    ("Ceramic Coating - 5 Year", 120000),
]
CERAMIC_ELIGIBLE = ["sedan", "suv", "truck"]
CERAMIC_DURATION = 150

# name, duration_minutes, price_cents — flat, no per-category variance in the guide
DEFAULT_ADDONS = [
    ("Pet Hair Removal", 45, 7000),
    ("Waxing Only", 30, 7000),
    ("Headlight Restoration", 45, 10000),
    ("Headliner Cleaning", 45, 5000),
    ("Engine Bay Cleaning", 30, 7000),
]

# Motorcycle detailing is its own single-category service.
MOTORCYCLE_SERVICE = ("Motorcycle Full Detailing", 90, "motorcycle", 17000)

# Boat/trailer: priced per foot, not per category. Only boats have a stated rate
# in the guide ($35/ft) — trailers use the same rate as a placeholder assumption
# since none was given; adjust if ShinePro has a different trailer rate.
LENGTH_BASED_SERVICES = [
    ("Boat Detailing", 120, 3500),
    ("Trailer Detailing", 90, 3500),
]

# Catalog names from an earlier, flatter pricing model — deactivated (not deleted,
# so past bookings that reference them by ID keep working) now that the real
# per-category catalog above replaces them. Split by table: "Headlight Restoration"
# used to be a flat-priced Service and is now an AddOn with the same name — only
# the stale Service row should be deactivated, not the new AddOn that shares the name.
DEPRECATED_SERVICE_NAMES = {
    "Express Wash & Wax", "Full Interior Detail", "Interior + Exterior Full Detail",
    "Ceramic Coating", "Headlight Restoration",
}
DEPRECATED_ADDON_NAMES = {"Buffing", "Paint Correction", "Waxing"}

DEFAULT_DETAILERS = ["Marcus", "Alexis", "Diego", "Sam", "Riley", "Jordan"]


def _get_or_create_service(db: Session, name: str, duration_minutes: int) -> Service:
    svc = db.execute(select(Service).where(Service.name == name)).scalar_one_or_none()
    if svc is None:
        svc = Service(name=name, duration_minutes=duration_minutes)
        db.add(svc)
        db.flush()
    return svc


def _set_price(db: Session, service: Service, category: str, price_cents: int, min_price_cents: int | None) -> None:
    row = db.execute(
        select(ServicePrice)
        .where(ServicePrice.service_id == service.id)
        .where(ServicePrice.category == category)
    ).scalar_one_or_none()
    if row is None:
        db.add(
            ServicePrice(
                service_id=service.id,
                category=category,
                price_cents=price_cents,
                min_price_cents=min_price_cents,
            )
        )
    else:
        row.price_cents = price_cents
        row.min_price_cents = min_price_cents


def seed(db: Session) -> None:
    email = settings.admin_email.lower()
    existing = db.execute(select(AdminUser).where(AdminUser.email == email)).scalar_one_or_none()
    if existing is None:
        db.add(AdminUser(email=email, password_hash=hash_password(settings.admin_password)))

    # Deactivate the old flat-priced catalog so the new per-category one is what
    # admins and the voice agent actually see, without breaking past bookings.
    for name in DEPRECATED_SERVICE_NAMES:
        old = db.execute(select(Service).where(Service.name == name)).scalar_one_or_none()
        if old is not None and old.active:
            old.active = False
    for name in DEPRECATED_ADDON_NAMES:
        old_addon = db.execute(select(AddOn).where(AddOn.name == name)).scalar_one_or_none()
        if old_addon is not None and old_addon.active:
            old_addon.active = False

    for name, minutes, category_prices in DEFAULT_SERVICES:
        svc = _get_or_create_service(db, name, minutes)
        for category, (price, min_price) in category_prices.items():
            _set_price(db, svc, category, price, min_price)
        if HATCHBACK_LIKE_SEDAN and "sedan" in category_prices:
            price, min_price = category_prices["sedan"]
            _set_price(db, svc, "hatchback", price, min_price)

    for name, price in CERAMIC_TIERS:
        svc = _get_or_create_service(db, name, CERAMIC_DURATION)
        for category in CERAMIC_ELIGIBLE:
            _set_price(db, svc, category, price, None)

    moto_name, moto_minutes, moto_category, moto_price = MOTORCYCLE_SERVICE
    moto_svc = _get_or_create_service(db, moto_name, moto_minutes)
    _set_price(db, moto_svc, moto_category, moto_price, None)

    for name, minutes, per_foot in LENGTH_BASED_SERVICES:
        svc = db.execute(select(Service).where(Service.name == name)).scalar_one_or_none()
        if svc is None:
            db.add(Service(name=name, duration_minutes=minutes, price_per_foot_cents=per_foot))
        elif svc.price_per_foot_cents != per_foot:
            svc.price_per_foot_cents = per_foot

    for name, minutes, price in DEFAULT_ADDONS:
        found = db.execute(select(AddOn).where(AddOn.name == name)).scalar_one_or_none()
        if found is None:
            db.add(AddOn(name=name, duration_minutes=minutes, price_cents=price))

    for name in DEFAULT_DETAILERS:
        found = db.execute(select(Detailer).where(Detailer.name == name)).scalar_one_or_none()
        if found is None:
            db.add(Detailer(name=name))

    db.commit()

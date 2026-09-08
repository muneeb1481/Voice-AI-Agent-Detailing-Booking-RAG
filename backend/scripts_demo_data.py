"""Populate the dev database with believable demo data.

    python scripts_demo_data.py
"""
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal, init_db
from app.models import Document
from app.schemas import BookingCreate
from app.seed import seed
from app.services import booking as booking_service
from app.services.chunking import chunk_text
from app.services.rag import ingest_document

PRICING_DOC = """
SHINEPRO DETAILING - SERVICES AND PRICING GUIDE

Prices vary by vehicle type. Exact prices and floor prices are looked up from the
service catalog when booking (via list_services/list_addons) - this document is
for general questions, not the source of exact numbers to quote.

INTERIOR & EXTERIOR DETAILING - about 2 hours.
Foam wash, wheel and tire cleaning, door jamb and trunk seal cleaning, microfiber
dry outside; full vacuum, dashboard and door panel wipe-down, trim dressing,
interior glass, air freshener inside.
Sedan 200 dollars, SUV 220, Truck 220, Coupe 200, Van 400, Mini Van 300.

INTERIOR DETAILING ONLY - about 90 minutes, same interior work as above without
the exterior wash. Has a minimum price it will never be discounted below: Sedan
150 (floor 150), SUV 180 (floor 170), Truck 170 (floor 170), Coupe 160 (floor 160),
Van 250 (floor 250), Mini Van 200 (floor 200).

BUFFING & WAXING - premium wax protection, 2-3 months durability, about 2.5 hours
combined with a base service (3-5 hours total per the original guide). Sedan 200,
SUV 200, Truck 200, Coupe 200, Van 300, Mini Van 200.
WAXING ONLY (no buffing, an add-on) - 70 dollars flat, any vehicle. Has a stated
floor of 50 dollars - only offered if the customer insists the price is too high,
never quoted as the default price.

PAINT CORRECTION - removes swirl marks and scratches, 5-8 hours depending on level.
Level 1 (minor swirls): 400 dollars most vehicles, 500 for Vans.
Level 2 (moderate scratches, multi-stage polish): 1000 dollars, any vehicle.
Level 3 (deep scratches, 3-stage correction, showroom finish): 1500 dollars, any vehicle.

CERAMIC COATING - only available for Sedan, SUV, and Truck. Nano-ceramic layer,
UV/water/dirt protection, 2-3 hours application.
2 Year (Standard) 400 dollars. 3 Year (Enhanced) 800 dollars. 5 Year (Premium) 1200 dollars.

MOTORCYCLE FULL DETAILING - 170 dollars.

BOAT DETAILING - 35 dollars per foot of boat length.
TRAILER DETAILING - 35 dollars per foot of trailer length.

ADD-ONS (flat price, any vehicle):
Pet Hair Removal 70 dollars - specialized extraction, deep vacuum, odor neutralizing.
Headlight Restoration 100 dollars - oxidation removal, polishing, UV protective coating.
Headliner Cleaning 50 dollars - ceiling interior cleaning and spot treatment.
Engine Bay Cleaning 70 dollars - degreasing and detailing, engine must be cool first.

SERVICE AREA
We are fully mobile and serve customers across the United States.

HOURS AND POLICY
We book appointments from 8am to 6pm, local time to the customer, seven days a week.
We need access to the vehicle and a parking space. We bring our own water and power.

DISCOUNTS
If a customer says the price is too expensive, we can knock 10 dollars off the total
package price (never per individual service) and can repeat that if they still object,
down to the service's minimum price where one exists - never below it.
"""

CUSTOMERS = [
    ("Dana Reed", "+19015550142", "TN", "38103", "2019 Toyota Tacoma", "Marcus"),
    ("Priya Shah", "+16155550118", "TN", "37201", "2022 Tesla Model Y", "Alexis"),
    ("Ray Ortiz", "+15025550188", "KY", "40202", "2016 Honda Accord", "Jordan"),
    ("Tom Whitfield", "+13055550190", "FL", "33101", "2021 Ford F-150", "Diego"),
    ("Nina Alvarez", "+12135550133", "CA", "90012", "2018 Subaru Outback", "Sam"),
    ("Chris Boyd", "+12065550171", "WA", "98101", "2020 Jeep Wrangler", "Riley"),
]


def main() -> None:
    init_db()
    with SessionLocal() as db:
        seed(db)

        if not db.query(Document).count():
            doc = Document(
                title="Services, Pricing & Policy",
                filename="pricing.txt",
                content_type="text/plain",
                size_bytes=len(PRICING_DOC.encode()),
            )
            db.add(doc)
            db.flush()
            ingest_document(db, doc, chunk_text(PRICING_DOC))
            db.commit()
            print(f"Indexed knowledge doc into {doc.chunk_count} chunks.")

        base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        created = 0
        for i, (name, phone, state, zip_code, vehicle, detailer) in enumerate(CUSTOMERS):
            start = (base + timedelta(days=i // 2 + 1)).replace(hour=9 + (i % 2) * 4)
            try:
                booking_service.create_booking(
                    db,
                    BookingCreate(
                        customer_name=name,
                        customer_phone=phone,
                        state=state,
                        zip_code=zip_code,
                        starts_at=start,
                        duration_minutes=90,
                        vehicle=vehicle,
                        detailer=detailer,
                    ),
                    source="voice" if i % 2 == 0 else "admin",
                )
                created += 1
            except Exception as exc:  # slot already taken on a re-run
                print(f"  skipped {name}: {exc}")
        print(f"Created {created} bookings.")


if __name__ == "__main__":
    main()

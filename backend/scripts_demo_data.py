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
SHINEPRO DETAILING - SERVICES AND PRICING

Express Wash and Wax - 79 dollars, about 60 minutes. Exterior hand wash, spray wax,
tire dressing, windows.

Full Interior Detail - 189 dollars, about 2 hours 30 minutes. Full vacuum, steam clean
of carpets and upholstery, leather conditioning, interior glass, air vents.

Interior and Exterior Full Detail - 299 dollars, about 4 hours. Everything in the
express wash plus the full interior detail, plus clay bar decontamination.

Ceramic Coating - 799 dollars, about 6 hours. Paint correction, panel prep, and a
professional grade ceramic coating with a 3 year warranty. SUVs and trucks add 100 dollars.

Headlight Restoration - 99 dollars, about 45 minutes. Both headlights sanded, polished
and UV sealed.

SERVICE AREA
We are fully mobile and serve customers across the United States. There is no travel fee
within 20 miles of your city center. Beyond 20 miles we add 1 dollar per mile.

HOURS AND POLICY
We book appointments from 8am to 6pm, seven days a week. We need access to the vehicle
and a parking space. We bring our own water and power. Cancellations inside 24 hours
are charged a 25 dollar fee. We do not do paintless dent repair or windshield replacement.
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

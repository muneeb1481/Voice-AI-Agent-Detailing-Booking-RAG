from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import AddOn, Booking, BookingStatus, Document, DocumentChunk, Service
from app.schemas import (
    AddOnOut,
    BookingCreate,
    BookingOut,
    BookingReschedule,
    BookingStatusUpdate,
    DashboardStats,
    DetailerUpdate,
    ParsedBookingCreate,
    ParsedJob,
    ParseJobRequest,
    ServiceOut,
    SlotOut,
)
from app.security import current_admin
from app.services import booking as booking_service
from app.services.job_parser import parse_job_text

router = APIRouter(prefix="/api", tags=["bookings"])


@router.get("/bookings", response_model=list[BookingOut])
def list_bookings(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    detailer: str | None = Query(default=None),
    status_filter: BookingStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    _: str = Depends(current_admin),
) -> list[Booking]:
    stmt = select(Booking).options(joinedload(Booking.customer)).order_by(Booking.starts_at)
    if date_from:
        stmt = stmt.where(Booking.starts_at >= date_from)
    if date_to:
        stmt = stmt.where(Booking.starts_at <= date_to)
    if state:
        stmt = stmt.where(Booking.state == state.upper())
    if detailer:
        stmt = stmt.where(Booking.detailer.ilike(f"%{detailer}%"))
    if status_filter:
        stmt = stmt.where(Booking.status == status_filter)
    return list(db.execute(stmt).scalars().unique().all())


@router.post("/bookings", response_model=BookingOut, status_code=201)
def create_booking(
    payload: BookingCreate, db: Session = Depends(get_db), _: str = Depends(current_admin)
) -> Booking:
    return booking_service.create_booking(db, payload, source="admin")


@router.patch("/bookings/{booking_id}/reschedule", response_model=BookingOut)
def reschedule(
    booking_id: str,
    payload: BookingReschedule,
    db: Session = Depends(get_db),
    _: str = Depends(current_admin),
) -> Booking:
    return booking_service.reschedule_booking(
        db, booking_id, payload.starts_at, payload.duration_minutes
    )


@router.patch("/bookings/{booking_id}/status", response_model=BookingOut)
def update_status(
    booking_id: str,
    payload: BookingStatusUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(current_admin),
) -> Booking:
    return booking_service.set_status(db, booking_id, payload.status)


@router.patch("/bookings/{booking_id}/detailer", response_model=BookingOut)
def update_detailer(
    booking_id: str,
    payload: DetailerUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(current_admin),
) -> Booking:
    return booking_service.set_detailer(db, booking_id, payload.detailer)


@router.post("/parse-job", response_model=ParsedJob)
def parse_job(
    payload: ParseJobRequest, _: str = Depends(current_admin)
) -> ParsedJob:
    return ParsedJob(**parse_job_text(payload.text))


@router.post("/bookings/parsed", response_model=BookingOut, status_code=201)
def create_parsed_booking(
    payload: ParsedBookingCreate,
    db: Session = Depends(get_db),
    _: str = Depends(current_admin),
) -> Booking:
    return booking_service.create_parsed_booking(db, payload)


@router.get("/slots", response_model=list[SlotOut])
def slots(
    state: str,
    day: datetime,
    duration_minutes: int = 90,
    db: Session = Depends(get_db),
    _: str = Depends(current_admin),
) -> list[SlotOut]:
    return booking_service.list_slots(db, state.upper(), day, duration_minutes)


@router.get("/services", response_model=list[ServiceOut])
def list_services(
    db: Session = Depends(get_db), _: str = Depends(current_admin)
) -> list[Service]:
    return list(
        db.execute(select(Service).where(Service.active).order_by(Service.name))
        .scalars()
        .all()
    )


@router.get("/addons", response_model=list[AddOnOut])
def list_addons(
    db: Session = Depends(get_db), _: str = Depends(current_admin)
) -> list[AddOn]:
    return list(
        db.execute(select(AddOn).where(AddOn.active).order_by(AddOn.name)).scalars().all()
    )


@router.get("/stats", response_model=DashboardStats)
def stats(db: Session = Depends(get_db), _: str = Depends(current_admin)) -> DashboardStats:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())

    def count(*conditions) -> int:
        stmt = select(func.count()).select_from(Booking)
        for c in conditions:
            stmt = stmt.where(c)
        return db.execute(stmt).scalar_one()

    state_rows = db.execute(
        select(Booking.state, func.count())
        .where(Booking.starts_at >= week_start)
        .where(Booking.state.isnot(None))
        .group_by(Booking.state)
    ).all()
    by_state = {state: n for state, n in state_rows}
    by_status = {
        s.value: count(Booking.status == s, Booking.starts_at >= week_start)
        for s in BookingStatus
    }

    return DashboardStats(
        bookings_today=count(
            Booking.starts_at >= day_start, Booking.starts_at < day_start + timedelta(days=1)
        ),
        bookings_this_week=count(Booking.starts_at >= week_start),
        upcoming=count(
            Booking.starts_at >= now,
            Booking.status.in_([BookingStatus.scheduled, BookingStatus.rescheduled]),
        ),
        cancelled_this_week=count(
            Booking.status == BookingStatus.cancelled, Booking.starts_at >= week_start
        ),
        documents=db.execute(select(func.count()).select_from(Document)).scalar_one(),
        chunks=db.execute(select(func.count()).select_from(DocumentChunk)).scalar_one(),
        by_state=by_state,
        by_status=by_status,
    )

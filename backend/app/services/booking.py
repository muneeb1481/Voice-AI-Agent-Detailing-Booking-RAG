"""One source of truth for booking writes.

The Vapi tools and the admin API both call these functions — never a second write path.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, Customer, Service
from app.schemas import BookingCreate, ParsedBookingCreate, SlotOut
from app.services.timezones import timezone_for_state
from app.services.vehicle import classify_vehicle_smart, is_large_vehicle, is_unsupported_vehicle

BUSINESS_OPEN = time(8, 0)
BUSINESS_CLOSE = time(18, 0)
SLOT_STEP_MINUTES = 30
MAX_DAYS_AHEAD = 60


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def get_or_create_customer(
    db: Session, name: str, phone: str, email: str | None = None
) -> Customer:
    customer = db.execute(select(Customer).where(Customer.phone == phone)).scalar_one_or_none()
    if customer:
        if name and customer.name != name:
            customer.name = name
        if email and not customer.email:
            customer.email = email
        return customer
    customer = Customer(name=name, phone=phone, email=email)
    db.add(customer)
    db.flush()
    return customer


def _overlaps(db: Session, state: str, start: datetime, end: datetime, exclude_id: str | None = None):
    stmt = (
        select(Booking)
        .where(Booking.state == state)
        .where(Booking.status.in_([BookingStatus.scheduled, BookingStatus.rescheduled]))
        .where(Booking.starts_at < end)
        .where(Booking.ends_at > start)
    )
    if exclude_id:
        stmt = stmt.where(Booking.id != exclude_id)
    return db.execute(stmt).scalars().all()


def validate_window(state: str | None, start: datetime, end: datetime) -> None:
    """Business hours are checked in the job's own local time — a slot valid for a
    Tennessee booking and invalid for a California one at the same UTC instant is
    exactly the point: 8am-6pm means the customer's 8am-6pm, not the server's."""
    tz = timezone_for_state(state)
    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)
    now = datetime.now(timezone.utc)

    if start <= now:
        raise _bad_request("That time is in the past. Pick an upcoming time.")
    if start > now + timedelta(days=MAX_DAYS_AHEAD):
        raise _bad_request(f"We only book up to {MAX_DAYS_AHEAD} days ahead.")
    if not (BUSINESS_OPEN <= local_start.time() < BUSINESS_CLOSE):
        raise _bad_request("That is outside business hours (8:00-18:00 local time).")
    if local_end.time() > BUSINESS_CLOSE and local_end.date() == local_start.date():
        raise _bad_request("That appointment would run past closing time.")


def list_slots(
    db: Session,
    state: str,
    day: datetime,
    duration_minutes: int = 90,
) -> list[SlotOut]:
    tz = timezone_for_state(state)
    # `day` names a calendar date; business hours are that date's 8am-6pm in the
    # job's own state, not the server's UTC clock.
    day_start = datetime.combine(day.date(), BUSINESS_OPEN, tzinfo=tz).astimezone(timezone.utc)
    day_end = datetime.combine(day.date(), BUSINESS_CLOSE, tzinfo=tz).astimezone(timezone.utc)
    now = datetime.now(timezone.utc)

    booked = _overlaps(db, state, day_start, day_end)
    slots: list[SlotOut] = []

    cursor = day_start
    step = timedelta(minutes=SLOT_STEP_MINUTES)
    duration = timedelta(minutes=duration_minutes)

    while cursor + duration <= day_end:
        end = cursor + duration
        clash = any(
            _as_utc(b.starts_at) < end and _as_utc(b.ends_at) > cursor for b in booked
        )
        if not clash and cursor > now:
            slots.append(SlotOut(starts_at=cursor, ends_at=end))
        cursor += step
    return slots


def _price_for(
    service: Service | None, vehicle_text: str | None, override_cents: int | None
) -> tuple[str | None, int | None]:
    """Category from the vehicle text, plus the price that category implies.

    An explicit override (parser/manual entry) always wins — the point of letting an
    admin override is that they know the real number better than any inference does.
    """
    category = classify_vehicle_smart(vehicle_text)
    if override_cents is not None:
        return category, override_cents
    if service is None:
        return category, None
    price = service.price_cents
    if is_large_vehicle(category):
        price += service.large_vehicle_surcharge_cents
    return category, price


def create_booking(db: Session, payload: BookingCreate, source: str = "voice") -> Booking:
    start = _as_utc(payload.starts_at)

    duration = payload.duration_minutes
    service = None
    if payload.service_id:
        service = db.get(Service, payload.service_id)
        if service is None:
            raise _bad_request("Unknown service.")
        duration = service.duration_minutes

    end = start + timedelta(minutes=duration)
    validate_window(payload.state, start, end)

    if _overlaps(db, payload.state, start, end):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That slot is already taken. Offer the caller another time.",
        )

    category, price_cents = _price_for(service, payload.vehicle, payload.price_cents)
    if is_unsupported_vehicle(category):
        raise _bad_request(
            "We're sorry, we don't currently offer detailing for motorcycles — only "
            "cars, SUVs, trucks, and vans. Offer to help with anything else, or end the call politely."
        )

    customer = get_or_create_customer(
        db, payload.customer_name, payload.customer_phone, payload.customer_email
    )
    booking = Booking(
        customer_id=customer.id,
        service_id=service.id if service else None,
        state=payload.state,
        zip_code=payload.zip_code,
        detailer=payload.detailer,
        vehicle=payload.vehicle,
        vehicle_category=category,
        address=payload.address,
        notes=payload.notes,
        price_cents=price_cents,
        service_label=payload.service_label or (service.name if service else None),
        starts_at=start,
        ends_at=end,
        status=BookingStatus.scheduled,
        source=source,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def create_parsed_booking(db: Session, payload: ParsedBookingCreate) -> Booking:
    """The paste-and-parse quick-intake path. This records a job, not a slot
    reservation — no business-hours or double-booking check, since the point is to
    log what already happened (or was agreed) rather than contend for a calendar slot.
    """
    start = _as_utc(payload.starts_at) if payload.starts_at else datetime.now(timezone.utc)
    duration = payload.duration_minutes
    end = start + timedelta(minutes=duration)

    category, price_cents = _price_for(None, payload.vehicle, payload.price_cents)

    customer = get_or_create_customer(db, payload.customer_name, payload.customer_phone)
    booking = Booking(
        customer_id=customer.id,
        service_id=None,
        state=payload.state,
        zip_code=payload.zip_code,
        detailer=payload.detailer,
        vehicle=payload.vehicle,
        vehicle_category=category,
        address=payload.address,
        notes=payload.notes,
        price_cents=price_cents,
        service_label=payload.service_label,
        starts_at=start,
        ends_at=end,
        status=BookingStatus.scheduled,
        source="parser",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def set_detailer(db: Session, booking_id: str, detailer: str | None) -> Booking:
    booking = _require(db, booking_id)
    booking.detailer = detailer
    db.commit()
    db.refresh(booking)
    return booking


def reschedule_booking(
    db: Session, booking_id: str, new_start: datetime, duration_minutes: int | None = None
) -> Booking:
    booking = _require(db, booking_id)
    if booking.status == BookingStatus.cancelled:
        raise _bad_request("That appointment is cancelled and cannot be rescheduled.")

    start = _as_utc(new_start)
    minutes = duration_minutes or int(
        (booking.ends_at - booking.starts_at).total_seconds() // 60
    )
    end = start + timedelta(minutes=minutes)
    validate_window(booking.state, start, end)

    if _overlaps(db, booking.state, start, end, exclude_id=booking.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That slot is already taken."
        )

    booking.starts_at = start
    booking.ends_at = end
    booking.status = BookingStatus.rescheduled
    db.commit()
    db.refresh(booking)
    return booking


def cancel_booking(db: Session, booking_id: str, reason: str | None = None) -> Booking:
    booking = _require(db, booking_id)
    booking.status = BookingStatus.cancelled
    if reason:
        booking.cancellation_reason = reason
    db.commit()
    db.refresh(booking)
    return booking


def set_status(db: Session, booking_id: str, new_status: BookingStatus) -> Booking:
    booking = _require(db, booking_id)
    booking.status = new_status
    db.commit()
    db.refresh(booking)
    return booking


def find_by_phone(db: Session, phone: str) -> list[Booking]:
    return list(
        db.execute(
            select(Booking)
            .join(Customer)
            .where(Customer.phone == phone)
            .where(Booking.status.in_([BookingStatus.scheduled, BookingStatus.rescheduled]))
            .order_by(Booking.starts_at)
        )
        .scalars()
        .all()
    )


def _require(db: Session, booking_id: str) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return booking

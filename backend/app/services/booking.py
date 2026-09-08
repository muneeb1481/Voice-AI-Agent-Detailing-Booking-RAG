"""One source of truth for booking writes.

The Vapi tools and the admin API both call these functions — never a second write path.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AddOn, Booking, BookingItem, BookingStatus, Customer, Service, ServicePrice
from app.schemas import BookingCreate, ParsedBookingCreate, SlotOut
from app.services.timezones import timezone_for_state
from app.services.vehicle import classify_vehicle_smart, is_length_based

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


def _service_price(
    db: Session, service: Service, category: str | None, length_ft: float | None
) -> tuple[int, int | None]:
    """The real price for one service given a vehicle category — from the price
    matrix, or length x rate for boat/trailer. Raises rather than guesses when the
    service isn't actually offered for this vehicle (no matrix row = not offered)."""
    if service.price_per_foot_cents is not None:
        if not length_ft:
            raise _bad_request(
                f"We need the length in feet to quote {service.name} — ask the caller "
                "how long their boat/trailer is."
            )
        return round(length_ft * service.price_per_foot_cents), None

    if not service.prices:
        # A simple flat-price service with no category matrix — legacy/simple case.
        return service.price_cents, None

    if category is None:
        raise _bad_request(
            f"We need to know the vehicle type to price {service.name} — ask the "
            "caller what kind of vehicle it is (sedan, SUV, truck, etc.)."
        )

    row = db.execute(
        select(ServicePrice)
        .where(ServicePrice.service_id == service.id)
        .where(ServicePrice.category == category)
    ).scalar_one_or_none()
    if row is None:
        raise _bad_request(
            f"{service.name} isn't offered for a {category} — offer the caller a "
            "different service, or check if a different vehicle type applies."
        )
    return row.price_cents, row.min_price_cents


def _resolve_extras(
    db: Session,
    extra_service_ids: list[str],
    addon_ids: list[str],
    category: str | None,
    length_ft: float | None,
) -> tuple[list[BookingItem], int, int, int]:
    """Extra full services and add-ons stacked on top of a booking's base service —
    each snapshotted (name/price/duration) at booking time, same reasoning as the
    base service's own price snapshot: a later catalog price change shouldn't
    silently rewrite what a past job actually cost.

    Also sums every line item's own price floor (base service's is added by the
    caller) so a discount on the whole package can never be clamped past what's
    actually needed to protect each individually-floored item."""
    items: list[BookingItem] = []
    total_price = 0
    total_duration = 0
    total_floor = 0

    for sid in extra_service_ids:
        svc = db.get(Service, sid)
        if svc is None:
            raise _bad_request("One of the extra services doesn't exist.")
        price, min_price = _service_price(db, svc, category, length_ft)
        items.append(
            BookingItem(
                item_type="service",
                catalog_id=svc.id,
                name=svc.name,
                price_cents=price,
                duration_minutes=svc.duration_minutes,
            )
        )
        total_price += price
        total_duration += svc.duration_minutes
        total_floor += min_price or 0

    for aid in addon_ids:
        addon = db.get(AddOn, aid)
        if addon is None:
            raise _bad_request("One of the add-ons doesn't exist.")
        # Add-ons are flat-priced (the catalog shows no per-category variance for
        # them) — large_vehicle_surcharge_cents only fires if one is explicitly set.
        price = addon.price_cents
        items.append(
            BookingItem(
                item_type="addon",
                catalog_id=addon.id,
                name=addon.name,
                price_cents=price,
                duration_minutes=addon.duration_minutes,
            )
        )
        total_price += price
        total_duration += addon.duration_minutes
        total_floor += addon.min_price_cents or 0

    return items, total_price, total_duration, total_floor


def _apply_discount(
    subtotal: int, requested_discount: int | None, floor_cents: int | None
) -> tuple[int, int]:
    """Clamp the requested discount to the service's price floor — the backend
    decides the real number, never the agent's own arithmetic. Returns
    (final_price_cents, discount_actually_applied_cents)."""
    if not requested_discount:
        return subtotal, 0
    floor = floor_cents if floor_cents is not None else 0
    final = max(subtotal - requested_discount, floor)
    return final, subtotal - final


def create_booking(db: Session, payload: BookingCreate, source: str = "voice") -> Booking:
    start = _as_utc(payload.starts_at)

    duration = payload.duration_minutes
    service = None
    category = classify_vehicle_smart(payload.vehicle)
    base_price = 0
    floor_cents: int | None = None

    if payload.service_id:
        service = db.get(Service, payload.service_id)
        if service is None:
            raise _bad_request("Unknown service.")
        duration = service.duration_minutes
        base_price, floor_cents = _service_price(db, service, category, payload.vehicle_length_ft)

    items, extras_price, extras_duration, extras_floor = _resolve_extras(
        db, payload.extra_service_ids, payload.addon_ids, category, payload.vehicle_length_ft
    )
    duration += extras_duration

    end = start + timedelta(minutes=duration)
    validate_window(payload.state, start, end)

    if _overlaps(db, payload.state, start, end):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That slot is already taken. Offer the caller another time.",
        )

    subtotal = base_price + extras_price
    # Combine every line item's own floor — a discount on the whole package can
    # never be clamped past the point where any individually-floored item would
    # have to go below its own stated minimum.
    combined_floor = (floor_cents or 0) + extras_floor
    if payload.price_cents is not None:
        price_cents = payload.price_cents  # a full manual override always wins outright
        original_price_cents = subtotal if (service or items) else None
        discount_applied = 0
    elif service or items:
        price_cents, discount_applied = _apply_discount(
            subtotal, payload.discount_cents, combined_floor
        )
        original_price_cents = subtotal
    else:
        price_cents = None
        original_price_cents = None
        discount_applied = 0

    labels = [service.name] if service else []
    labels += [i.name for i in items]
    label = payload.service_label or (", ".join(labels) if labels else None)

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
        vehicle_length_ft=payload.vehicle_length_ft,
        address=payload.address,
        notes=payload.notes,
        price_cents=price_cents,
        original_price_cents=original_price_cents,
        discount_cents=discount_applied,
        service_label=label,
        starts_at=start,
        ends_at=end,
        status=BookingStatus.scheduled,
        source=source,
    )
    booking.items = items
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

    category = classify_vehicle_smart(payload.vehicle)
    items, extras_price, extras_duration, extras_floor = _resolve_extras(
        db, payload.extra_service_ids, payload.addon_ids, category, payload.vehicle_length_ft
    )
    duration = payload.duration_minutes + extras_duration
    end = start + timedelta(minutes=duration)

    if payload.price_cents is not None:
        price_cents = payload.price_cents
        original_price_cents = extras_price if items else None
        discount_applied = 0
    elif items:
        price_cents, discount_applied = _apply_discount(
            extras_price, payload.discount_cents, extras_floor
        )
        original_price_cents = extras_price
    else:
        price_cents = None
        original_price_cents = None
        discount_applied = 0

    label = payload.service_label or (", ".join(i.name for i in items) if items else None)

    customer = get_or_create_customer(db, payload.customer_name, payload.customer_phone)
    booking = Booking(
        customer_id=customer.id,
        service_id=None,
        state=payload.state,
        zip_code=payload.zip_code,
        detailer=payload.detailer,
        vehicle=payload.vehicle,
        vehicle_category=category,
        vehicle_length_ft=payload.vehicle_length_ft,
        address=payload.address,
        notes=payload.notes,
        price_cents=price_cents,
        original_price_cents=original_price_cents,
        discount_cents=discount_applied,
        service_label=label,
        starts_at=start,
        ends_at=end,
        status=BookingStatus.scheduled,
        source="parser",
    )
    booking.items = items
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

"""Vapi tool endpoints.

Every tool validates through app.schemas and writes through app.services.booking —
the same code path the admin dashboard uses. The LLM supplies arguments; it never
supplies trust.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from sqlalchemy import select

from app.config import get_settings
from app.db import get_db
from app.models import AddOn, CallLog, CallTranscript, Service
from app.schemas import (
    AskRequest,
    AskResponse,
    ClassifyVehicleResponse,
    CurrentTimeResponse,
    VoiceBookingCreate,
)
from app.security import bearer_scheme
from app.services import booking as booking_service
from app.services.timezones import period_and_closing_line
from app.services.us_states import normalize_state
from app.services import rag

settings = get_settings()
router = APIRouter(prefix="/api/vapi", tags=["vapi"])


def verify_vapi(x_vapi_secret: str | None = Header(default=None)) -> None:
    if not settings.vapi_secret:
        return  # unset in local dev
    if x_vapi_secret != settings.vapi_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad tool secret")


def verify_vapi_or_admin(
    x_vapi_secret: str | None = Header(default=None),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """Accept either the Vapi tool secret (real phone calls) or an admin session
    (the dashboard's Agent Test page) — so testing from the browser doesn't need the
    tool secret baked into the frontend, and a bad/missing tool secret doesn't get
    mistaken for an expired admin login."""
    if not settings.vapi_secret:
        return
    if x_vapi_secret == settings.vapi_secret:
        return
    if creds is not None:
        import jwt  # noqa: PLC0415

        try:
            jwt.decode(creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            return
        except jwt.PyJWTError:
            pass
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad tool secret")


@router.post("/ask", response_model=AskResponse, dependencies=[Depends(verify_vapi_or_admin)])
def ask(payload: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    result = rag.answer(db, payload.question, payload.top_k, payload.state)
    db.add(
        CallLog(question=payload.question, answer=result.answer, tool_name="ask")
    )
    db.commit()
    return result


class ListSlotsArgs(BaseModel):
    state: str = Field(description="US state, name or 2-letter code")
    day: datetime
    duration_minutes: int = Field(default=90, ge=15, le=600)

    @field_validator("state")
    @classmethod
    def _validate_state(cls, v: str) -> str:
        return normalize_state(v)


@router.post("/list_slots", dependencies=[Depends(verify_vapi)])
def list_slots(args: ListSlotsArgs, db: Session = Depends(get_db)) -> dict:
    slots = booking_service.list_slots(db, args.state, args.day, args.duration_minutes)
    return {
        "count": len(slots),
        "slots": [s.starts_at.isoformat() for s in slots[:8]],
    }


@router.post("/list_services", dependencies=[Depends(verify_vapi)])
def list_services(db: Session = Depends(get_db)) -> dict:
    """So the agent can quote a real price before booking — never estimate one.
    Prices genuinely differ by vehicle type: each service lists its price PER
    CATEGORY (a missing category means that service isn't offered for that
    vehicle at all), or a per-foot rate for boat/trailer services."""
    services = db.execute(
        select(Service).where(Service.active).order_by(Service.name)
    ).scalars().all()
    return {
        "services": [
            {
                "service_id": s.id,
                "name": s.name,
                "duration_minutes": s.duration_minutes,
                "price_per_foot_cents": s.price_per_foot_cents,
                "prices_by_vehicle_category": (
                    {p.category: {"price_cents": p.price_cents, "min_price_cents": p.min_price_cents} for p in s.prices}
                    if s.prices
                    else None
                ),
                "flat_price_cents": s.price_cents if not s.prices and s.price_per_foot_cents is None else None,
                "note": (
                    "Priced per foot — you need the vehicle's length to quote this."
                    if s.price_per_foot_cents is not None
                    else "Only offered for the vehicle categories listed in prices_by_vehicle_category — "
                    "if the caller's category isn't a key here, this service isn't available for them."
                    if s.prices
                    else "Same price for every vehicle."
                ),
            }
            for s in services
        ]
    }


@router.post("/list_addons", dependencies=[Depends(verify_vapi)])
def list_addons(db: Session = Depends(get_db)) -> dict:
    """Add-ons stack on top of a base service — waxing, paint correction, pet hair
    removal, engine bay cleaning, headlight restoration, headliner cleaning. Call
    this whenever a caller asks what extras are available, or wants to add something
    beyond the base service.

    NOTE on buffing: there is no standalone "buffing" add-on — buffing is only ever
    sold bundled with waxing, as the "Buffing & Waxing" full SERVICE (from
    list_services). If a caller asks for buffing alone, quote them the Buffing &
    Waxing service price for their vehicle category, not a separate buffing price.

    Most add-ons are flat regardless of vehicle type. Waxing Only is the one
    exception — its price varies by category, same as a full service."""
    addons = db.execute(select(AddOn).where(AddOn.active).order_by(AddOn.name)).scalars().all()
    return {
        "addons": [
            {
                "addon_id": a.id,
                "name": a.name,
                "duration_minutes": a.duration_minutes,
                "prices_by_vehicle_category": (
                    {p.category: {"price_cents": p.price_cents, "min_price_cents": p.min_price_cents} for p in a.prices}
                    if a.prices
                    else None
                ),
                "flat_price_cents": a.price_cents if not a.prices else None,
                "note": (
                    "Only offered for the vehicle categories listed in prices_by_vehicle_category."
                    if a.prices
                    else "Same price for every vehicle."
                ),
            }
            for a in addons
        ]
    }


class ClassifyVehicleArgs(BaseModel):
    vehicle: str = Field(min_length=1, description="Year, make and model, as the caller said it.")


@router.post(
    "/classify_vehicle",
    response_model=ClassifyVehicleResponse,
    dependencies=[Depends(verify_vapi)],
)
def classify_vehicle_endpoint(args: ClassifyVehicleArgs) -> ClassifyVehicleResponse:
    """Check a vehicle BEFORE going through the rest of booking — so a category
    that needs different handling (motorcycle, boat/trailer needing a length,
    or one nothing was recognized for) gets caught in conversation, not as a
    failure at the final book_appointment step."""
    from app.services.vehicle import (  # noqa: PLC0415
        classify_vehicle_smart,
        is_length_based,
        is_unsupported_vehicle,
    )

    category = classify_vehicle_smart(args.vehicle)
    supported = not is_unsupported_vehicle(category)
    length_based = is_length_based(category)

    if not supported:
        note = (
            "This vehicle is not something we detail. Apologize and do not proceed "
            "with list_services or book_appointment for this vehicle."
        )
    elif length_based:
        note = (
            f"This is a {category} — priced per foot, not by category. Ask the caller "
            "for its length in feet and pass it as vehicle_length_ft when booking. "
            "Call list_services to get the per-foot rate."
        )
    elif category is None:
        note = (
            "Could not confidently determine the vehicle's body type. You'll need to "
            "ask the caller directly (sedan, SUV, truck, coupe, van, or minivan) before "
            "you can quote a price — list_services requires a known category."
        )
    else:
        note = f"Recognized as a {category}. Proceed with list_services and booking as normal."

    return ClassifyVehicleResponse(
        vehicle=args.vehicle,
        category=category,
        supported=supported,
        length_based=length_based,
        note=note,
    )


@router.post("/book_appointment", dependencies=[Depends(verify_vapi)])
def book_appointment(args: VoiceBookingCreate, db: Session = Depends(get_db)) -> dict:
    booking = booking_service.create_booking(db, args, source="voice")
    return {
        "booking_id": booking.id,
        "starts_at": booking.starts_at.isoformat(),
        "state": booking.state,
        "status": booking.status.value,
        "price_cents": booking.price_cents,
        "original_price_cents": booking.original_price_cents,
        "discount_cents": booking.discount_cents,
        "vehicle_category": booking.vehicle_category,
        "items": [{"name": i.name, "price_cents": i.price_cents} for i in booking.items],
        "note": (
            "Read price_cents back to the caller as a dollar amount to confirm it — "
            "that's the final total after any discount actually applied (discount_cents "
            "may be less than what you asked for if it hit the price floor)."
        ),
    }


class CurrentTimeArgs(BaseModel):
    state: str | None = None

    @field_validator("state")
    @classmethod
    def _validate_state(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        try:
            return normalize_state(v)
        except ValueError:
            return None


@router.post(
    "/current_time", response_model=CurrentTimeResponse, dependencies=[Depends(verify_vapi)]
)
def current_time(args: CurrentTimeArgs) -> CurrentTimeResponse:
    """Deterministic — the real clock, not the model guessing what time it is.
    Call right before ending a call, so the sign-off matches the caller's actual
    local time of day."""
    period, closing_line, now = period_and_closing_line(args.state)
    return CurrentTimeResponse(
        state=args.state,
        local_time=now.isoformat(),
        hour=now.hour,
        period=period,
        closing_line=closing_line,
    )


class LookupArgs(BaseModel):
    phone: str = Field(min_length=7, max_length=32)


@router.post("/lookup_appointments", dependencies=[Depends(verify_vapi)])
def lookup_appointments(args: LookupArgs, db: Session = Depends(get_db)) -> dict:
    bookings = booking_service.find_by_phone(db, args.phone)
    return {
        "count": len(bookings),
        "appointments": [
            {
                "booking_id": b.id,
                "starts_at": b.starts_at.isoformat(),
                "state": b.state,
                "vehicle": b.vehicle,
            }
            for b in bookings
        ],
    }


class RescheduleArgs(BaseModel):
    booking_id: str
    starts_at: datetime
    duration_minutes: int | None = Field(default=None, ge=15, le=600)


@router.post("/reschedule_appointment", dependencies=[Depends(verify_vapi)])
def reschedule_appointment(args: RescheduleArgs, db: Session = Depends(get_db)) -> dict:
    booking = booking_service.reschedule_booking(
        db, args.booking_id, args.starts_at, args.duration_minutes
    )
    return {"booking_id": booking.id, "starts_at": booking.starts_at.isoformat(), "status": booking.status.value}


class CancelArgs(BaseModel):
    booking_id: str
    reason: str | None = Field(
        default=None,
        description="Why the caller is cancelling, in their own words, if they gave one.",
    )


@router.post("/cancel_appointment", dependencies=[Depends(verify_vapi)])
def cancel_appointment(args: CancelArgs, db: Session = Depends(get_db)) -> dict:
    booking = booking_service.cancel_booking(db, args.booking_id, args.reason)
    return {"booking_id": booking.id, "status": booking.status.value}


@router.post("/call-ended", dependencies=[Depends(verify_vapi)])
async def call_ended(request: Request, db: Session = Depends(get_db)) -> dict:
    """Vapi's end-of-call webhook. Configure this as the Assistant's Server URL
    (with the same X-Vapi-Secret header) so every finished call is saved here for
    an admin to review — not just what got booked, but how the conversation went.

    Payload shape isn't hard-relied on: best-effort field extraction, but the full
    raw body is always stored, so nothing is lost even if a field path is off.
    """
    body = await request.json()
    message = body.get("message", body)  # some Vapi setups nest under "message", some don't

    call = message.get("call", {}) or {}
    customer = message.get("customer", {}) or call.get("customer", {}) or {}
    analysis = message.get("analysis", {}) or {}

    transcript = message.get("transcript")
    if not transcript:
        messages = message.get("artifact", {}).get("messages") or message.get("messages") or []
        if messages:
            transcript = "\n".join(
                f"{m.get('role', '?')}: {m.get('message', m.get('content', ''))}"
                for m in messages
                if isinstance(m, dict)
            )

    db.add(
        CallTranscript(
            call_id=call.get("id") or message.get("callId"),
            phone=customer.get("number"),
            customer_name=customer.get("name"),
            transcript=transcript,
            summary=analysis.get("summary") or message.get("summary"),
            ended_reason=call.get("endedReason") or message.get("endedReason"),
            duration_seconds=message.get("durationSeconds"),
            raw_payload=body,
        )
    )
    db.commit()
    return {"ok": True}

"""Vapi tool endpoints.

Every tool validates through app.schemas and writes through app.services.booking —
the same code path the admin dashboard uses. The LLM supplies arguments; it never
supplies trust.

Every endpoint supports two request/response shapes — see app.services.vapi_protocol
for why: a real Vapi call (wrapped in message.toolCallList, response wrapped in
results) and the flat legacy shape the admin dashboard's Agent Test page and the
test suite use (arguments at the top level, response unwrapped, real HTTP status
codes on error).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from sqlalchemy import select

from app.config import get_settings
from app.db import get_db
from app.models import AddOn, CallLog, CallTranscript, Service
from app.schemas import (
    AskRequest,
    ClassifyVehicleResponse,
    CurrentTimeResponse,
    VoiceBookingCreate,
)
from app.security import bearer_scheme
from app.services import booking as booking_service
from app.services.timezones import period_and_closing_line
from app.services.us_states import normalize_state
from app.services import rag
from app.services.vapi_protocol import parse_tool_call, parse_tool_call_full, tool_response
from app.services.zip_lookup import state_from_zip

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


def _validated(model: type[BaseModel], args_dict: dict, tool_call_id: str | None):
    """Validate `args_dict` against `model`. On failure: a real Vapi call gets a
    200 with the problem described in `result` (so the agent can react to it —
    a raw 422 is invisible to the LLM); the flat/legacy shape keeps raising a
    real HTTPException(422), exactly as FastAPI's automatic body validation did
    before this module existed, since the admin dashboard and test suite expect that."""
    try:
        return model.model_validate(args_dict), None
    except ValidationError as exc:
        if tool_call_id is not None:
            return None, tool_response(f"Invalid arguments: {exc}", tool_call_id)
        # exc.errors() can carry non-JSON-serializable values (e.g. a raw ValueError
        # in 'ctx' from a field_validator) — the string form is always safe to return.
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/ask", dependencies=[Depends(verify_vapi_or_admin)])
async def ask(request: Request, db: Session = Depends(get_db)):
    args_dict, tool_call_id = await parse_tool_call(request)
    payload, early = _validated(AskRequest, args_dict, tool_call_id)
    if early is not None:
        return early

    result = rag.answer(db, payload.question, payload.top_k, payload.state)
    db.add(CallLog(question=payload.question, answer=result.answer, tool_name="ask"))
    db.commit()
    return tool_response(result.model_dump(), tool_call_id)


class ListSlotsArgs(BaseModel):
    state: str | None = Field(
        default=None,
        description="US state, name or 2-letter code. Optional if zip_code is given — "
        "state is derived from the ZIP automatically.",
    )
    zip_code: str | None = Field(
        default=None, description="5-digit ZIP — used to derive state if state isn't given."
    )
    day: datetime
    duration_minutes: int = Field(default=90, ge=15, le=600)

    @field_validator("state")
    @classmethod
    def _validate_state(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        return normalize_state(v)


@router.post("/list_slots", dependencies=[Depends(verify_vapi)])
async def list_slots(request: Request, db: Session = Depends(get_db)):
    args_dict, tool_call_id = await parse_tool_call(request)
    args, early = _validated(ListSlotsArgs, args_dict, tool_call_id)
    if early is not None:
        return early

    state = args.state or state_from_zip(args.zip_code)
    if state is None:
        message = (
            "We need to know what state this is in — ask the caller directly, we "
            "couldn't determine it from the ZIP code alone."
        )
        if tool_call_id is None:
            raise HTTPException(status_code=400, detail=message)
        return tool_response(message, tool_call_id)

    slots = booking_service.list_slots(db, state, args.day, args.duration_minutes)
    result = {
        "count": len(slots),
        "slots": [s.starts_at.isoformat() for s in slots[:8]],
    }
    return tool_response(result, tool_call_id)


def _price_entry(price_cents: int, min_price_cents: int | None) -> dict | int:
    """Most rows have no floor — return the bare cents value then, only the
    (rarer) floored rows pay for the extra object nesting. Cuts real token
    weight off list_services/list_addons, which get resent in full on every
    turn of a call once used — a real cost, not a cosmetic one."""
    if min_price_cents is None:
        return price_cents
    return {"price_cents": price_cents, "min_price_cents": min_price_cents}


@router.post("/list_services", dependencies=[Depends(verify_vapi)])
async def list_services(request: Request, db: Session = Depends(get_db)):
    """So the agent can quote a real price before booking — never estimate one.
    Prices genuinely differ by vehicle type: each service lists its price PER
    CATEGORY (a missing category means that service isn't offered for that
    vehicle at all, unless price_per_foot_cents is set — then it's priced by
    length instead), or a flat_price_cents for a same-price-everywhere service.
    A category value is just the price in cents, UNLESS the service can be
    discounted down to a floor for that category, in which case it's
    {"price_cents", "min_price_cents"} instead."""
    _args_dict, tool_call_id = await parse_tool_call(request)
    services = db.execute(
        select(Service).where(Service.active).order_by(Service.name)
    ).scalars().all()
    out = []
    for s in services:
        item: dict = {"service_id": s.id, "name": s.name, "duration_minutes": s.duration_minutes}
        if s.price_per_foot_cents is not None:
            item["price_per_foot_cents"] = s.price_per_foot_cents
        elif s.prices:
            item["prices_by_vehicle_category"] = {
                p.category: _price_entry(p.price_cents, p.min_price_cents) for p in s.prices
            }
        else:
            item["flat_price_cents"] = s.price_cents
        out.append(item)
    return tool_response({"services": out}, tool_call_id)


@router.post("/list_addons", dependencies=[Depends(verify_vapi)])
async def list_addons(request: Request, db: Session = Depends(get_db)):
    """Add-ons stack on top of a base service — waxing, shampooing, pet hair
    removal, engine bay cleaning, headlight restoration, headliner cleaning. Call
    this whenever a caller asks what extras are available, or wants to add something
    beyond the base service.

    NOTE: Buffing, Interior Detailing, Exterior Detailing, Ceramic Coating, and
    Paint Correction are full SERVICES (from list_services), not add-ons here —
    each is independently bookable at its own price. "Buffing & Waxing" and
    "Interior & Exterior Detailing" also still exist as convenience bundle
    services at their own bundle price. Waxing and Shampooing (this endpoint) are
    the add-ons a caller stacks on top of whatever service they book.

    Most add-ons are flat regardless of vehicle type. Waxing Only and Shampooing
    are the exceptions — their price varies by category, same as a full service."""
    _args_dict, tool_call_id = await parse_tool_call(request)
    addons = db.execute(select(AddOn).where(AddOn.active).order_by(AddOn.name)).scalars().all()
    out = []
    for a in addons:
        item: dict = {"addon_id": a.id, "name": a.name, "duration_minutes": a.duration_minutes}
        if a.prices:
            item["prices_by_vehicle_category"] = {
                p.category: _price_entry(p.price_cents, p.min_price_cents) for p in a.prices
            }
        else:
            item["flat_price_cents"] = a.price_cents
        out.append(item)
    return tool_response({"addons": out}, tool_call_id)


class ClassifyVehicleArgs(BaseModel):
    vehicle: str = Field(min_length=1, description="Year, make and model, as the caller said it.")


@router.post("/classify_vehicle", dependencies=[Depends(verify_vapi)])
async def classify_vehicle_endpoint(request: Request):
    """Check a vehicle BEFORE going through the rest of booking — so a category
    that needs different handling (motorcycle, boat/trailer needing a length,
    or one nothing was recognized for) gets caught in conversation, not as a
    failure at the final book_appointment step."""
    from app.services.vehicle import (  # noqa: PLC0415
        classify_vehicle_smart,
        is_length_based,
        is_unsupported_vehicle,
    )

    args_dict, tool_call_id = await parse_tool_call(request)
    args, early = _validated(ClassifyVehicleArgs, args_dict, tool_call_id)
    if early is not None:
        return early

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

    payload = ClassifyVehicleResponse(
        vehicle=args.vehicle,
        category=category,
        supported=supported,
        length_based=length_based,
        note=note,
    )
    return tool_response(payload.model_dump(), tool_call_id)


@router.post("/book_appointment", dependencies=[Depends(verify_vapi)])
async def book_appointment(request: Request, db: Session = Depends(get_db)):
    args_dict, tool_call_id = await parse_tool_call(request)
    args, early = _validated(VoiceBookingCreate, args_dict, tool_call_id)
    if early is not None:
        return early

    try:
        booking = booking_service.create_booking(db, args, source="voice")
    except HTTPException as exc:
        if tool_call_id is not None:
            return tool_response(str(exc.detail), tool_call_id)
        raise

    result = {
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
    return tool_response(result, tool_call_id)


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


@router.post("/current_time", dependencies=[Depends(verify_vapi)])
async def current_time(request: Request):
    """Deterministic — the real clock, not the model guessing what time it is.
    Call right before ending a call, so the sign-off matches the caller's actual
    local time of day."""
    args_dict, tool_call_id = await parse_tool_call(request)
    args, early = _validated(CurrentTimeArgs, args_dict, tool_call_id)
    if early is not None:
        return early

    period, closing_line, now = period_and_closing_line(args.state)
    payload = CurrentTimeResponse(
        state=args.state,
        local_time=now.isoformat(),
        hour=now.hour,
        period=period,
        closing_line=closing_line,
    )
    return tool_response(payload.model_dump(), tool_call_id)


class LookupArgs(BaseModel):
    phone: str = Field(min_length=7, max_length=32)


@router.post("/lookup_appointments", dependencies=[Depends(verify_vapi)])
async def lookup_appointments(request: Request, db: Session = Depends(get_db)):
    args_dict, tool_call_id, verified_number = await parse_tool_call_full(request)
    args, early = _validated(LookupArgs, args_dict, tool_call_id)
    if early is not None:
        return early

    # Defense-in-depth beyond the system-prompt rule: on a real call, Vapi's own
    # request carries the verified caller ID — never trust an LLM-supplied phone
    # number over it, so no amount of prompt injection can browse another
    # customer's bookings. Falls back to the argument only when no verified
    # number is available (a web test call, or the flat/legacy admin-test shape).
    phone = verified_number or args.phone
    bookings = booking_service.find_by_phone(db, phone)
    result = {
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
    return tool_response(result, tool_call_id)


class RescheduleArgs(BaseModel):
    booking_id: str
    starts_at: datetime
    duration_minutes: int | None = Field(default=None, ge=15, le=600)


@router.post("/reschedule_appointment", dependencies=[Depends(verify_vapi)])
async def reschedule_appointment(request: Request, db: Session = Depends(get_db)):
    args_dict, tool_call_id = await parse_tool_call(request)
    args, early = _validated(RescheduleArgs, args_dict, tool_call_id)
    if early is not None:
        return early

    try:
        booking = booking_service.reschedule_booking(
            db, args.booking_id, args.starts_at, args.duration_minutes
        )
    except HTTPException as exc:
        if tool_call_id is not None:
            return tool_response(str(exc.detail), tool_call_id)
        raise

    result = {
        "booking_id": booking.id,
        "starts_at": booking.starts_at.isoformat(),
        "status": booking.status.value,
    }
    return tool_response(result, tool_call_id)


class CancelArgs(BaseModel):
    booking_id: str
    reason: str | None = Field(
        default=None,
        description="Why the caller is cancelling, in their own words, if they gave one.",
    )


@router.post("/cancel_appointment", dependencies=[Depends(verify_vapi)])
async def cancel_appointment(request: Request, db: Session = Depends(get_db)):
    args_dict, tool_call_id = await parse_tool_call(request)
    args, early = _validated(CancelArgs, args_dict, tool_call_id)
    if early is not None:
        return early

    try:
        booking = booking_service.cancel_booking(db, args.booking_id, args.reason)
    except HTTPException as exc:
        if tool_call_id is not None:
            return tool_response(str(exc.detail), tool_call_id)
        raise

    result = {"booking_id": booking.id, "status": booking.status.value}
    return tool_response(result, tool_call_id)


@router.post("/call-ended", dependencies=[Depends(verify_vapi)])
async def call_ended(request: Request, db: Session = Depends(get_db)) -> dict:
    """Vapi's end-of-call webhook. Configure this as the Assistant's Server URL
    (with the same X-Vapi-Secret header) so every finished call is saved here for
    an admin to review — not just what got booked, but how the conversation went.

    The assistant's serverMessages is restricted to ["end-of-call-report"] so
    this only ever fires once per call, but that's assistant-side config, not a
    guarantee — this handler also checks the message type itself and silently
    no-ops on anything else, so a misconfigured assistant (every other server
    message type: conversation-update, status-update, speech-update, etc.) can
    never flood this table with one near-empty row per turn again.

    Payload shape isn't hard-relied on beyond that type check: best-effort field
    extraction, but the full raw body is always stored, so nothing is lost even
    if a field path is off.
    """
    body = await request.json()
    message = body.get("message", body)  # some Vapi setups nest under "message", some don't

    message_type = message.get("type")
    if message_type is not None and message_type != "end-of-call-report":
        return {"ok": True}

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

    call_id = call.get("id") or message.get("callId")
    fields = dict(
        phone=customer.get("number"),
        customer_name=customer.get("name"),
        transcript=transcript,
        summary=analysis.get("summary") or message.get("summary"),
        ended_reason=call.get("endedReason") or message.get("endedReason"),
        duration_seconds=message.get("durationSeconds"),
        raw_payload=body,
    )

    # Vapi has been observed sending end-of-call-report twice per call (a
    # preliminary one, then a final one with durationSeconds/summary filled
    # in) — upsert by call_id instead of always inserting, so the admin Calls
    # page shows one row per call, not two.
    existing = (
        db.execute(select(CallTranscript).where(CallTranscript.call_id == call_id)).scalar_one_or_none()
        if call_id
        else None
    )
    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
    else:
        db.add(CallTranscript(call_id=call_id, **fields))
    db.commit()
    return {"ok": True}

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
    VoiceLeadCreate,
)
from app.security import bearer_scheme
from app.services import booking as booking_service
from app.services.timezones import (
    describe_local,
    format_clock,
    parse_clock_time,
    period_and_closing_line,
    reinterpret_as_wall_clock,
    to_local,
)
from app.services.us_states import normalize_state
from app.services import rag
from app.services.vapi_protocol import SafeToolRoute, parse_tool_call, parse_tool_call_full, tool_response
from app.services.zip_lookup import state_from_zip

settings = get_settings()
router = APIRouter(prefix="/api/vapi", tags=["vapi"], route_class=SafeToolRoute)


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


class ResolveDateArgs(BaseModel):
    phrase: str = Field(
        min_length=1,
        description="The relative day the caller said, e.g. 'Friday', 'tomorrow', "
        "'next Monday', 'in 3 days'.",
    )
    state: str | None = Field(
        default=None, description="US state, if known — for the caller's correct local 'today'."
    )
    zip_code: str | None = Field(
        default=None, description="5-digit ZIP — used to derive state if state isn't given."
    )


@router.post("/resolve_date", dependencies=[Depends(verify_vapi)])
async def resolve_date(request: Request):
    """Turn a relative day the caller said into a real calendar date — never do
    this math yourself, it's easy to get wrong. Call this whenever the caller
    mentions a day in relative terms (today, tomorrow, a weekday name, "next
    week", "in N days") before calling list_slots or book_appointment."""
    from app.services.date_resolve import resolve_relative_date  # noqa: PLC0415

    args_dict, tool_call_id = await parse_tool_call(request)
    args, early = _validated(ResolveDateArgs, args_dict, tool_call_id)
    if early is not None:
        return early

    state = args.state or state_from_zip(args.zip_code)
    resolved = resolve_relative_date(args.phrase, state)
    if resolved is None:
        result = (
            f"Could not resolve '{args.phrase}' to a specific date — ask the caller to "
            "state the actual date or day of the week plainly."
        )
    else:
        result = {"date": resolved.isoformat(), "day_of_week": resolved.strftime("%A")}
    return tool_response(result, tool_call_id)


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
    time: str | None = Field(
        default=None, description="A specific time the caller asked for, e.g. '3 PM'."
    )
    duration_minutes: int = Field(default=90, ge=15, le=600)

    @field_validator("state")
    @classmethod
    def _validate_state(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        return normalize_state(v)


def _state_unknown(tool_call_id: str | None):
    message = (
        "We need to know what state this is in — ask the caller directly, we "
        "couldn't determine it from the ZIP code alone."
    )
    if tool_call_id is None:
        raise HTTPException(status_code=400, detail=message)
    return tool_response(message, tool_call_id)


@router.post("/list_slots", dependencies=[Depends(verify_vapi)])
async def list_slots(request: Request, db: Session = Depends(get_db)):
    """Every open start time for the day, in the caller's own local time.

    A live call had the agent say 3 PM was taken when it was open: this used to
    return only the first 8 slots (8:00-11:30 AM) and as UTC timestamps, so an
    afternoon time was never in the list. Now all of them come back as spoken
    local times, and a requested `time` gets a direct yes/no."""
    args_dict, tool_call_id = await parse_tool_call(request)
    args, early = _validated(ListSlotsArgs, args_dict, tool_call_id)
    if early is not None:
        return early

    state = args.state or state_from_zip(args.zip_code)
    if state is None:
        return _state_unknown(tool_call_id)

    slots = booking_service.list_slots(db, state, args.day, args.duration_minutes)
    open_times = [format_clock(to_local(s.starts_at, state)) for s in slots]
    result: dict = {
        "date": args.day.date().isoformat(),
        "day_of_week": args.day.strftime("%A"),
        "business_hours": "8 AM to 5 PM",
        "count": len(slots),
        "open_times": open_times,
    }
    if args.time:
        requested = parse_clock_time(args.time)
        if requested is None:
            result["requested_time_note"] = (
                f"Couldn't read '{args.time}' as a time — compare against open_times yourself."
            )
        else:
            spoken = format_clock(datetime.combine(args.day.date(), requested))
            available = spoken in open_times
            result["requested_time"] = spoken
            result["requested_time_available"] = available
            if not available:
                result["requested_time_note"] = (
                    "Not open. Tell the caller that time isn't available and ask what "
                    "other time works for them — don't pick one for them."
                )
    return tool_response(result, tool_call_id)


def _local_start_from_args(args_dict: dict) -> str | None:
    """Accept `date` + `time` ("2026-09-15" + "3 PM") as the preferred way to give a
    start, folding it into `starts_at`. Returns an error message if the time is
    unreadable, else None."""
    if args_dict.get("date") and args_dict.get("time"):
        clock = parse_clock_time(str(args_dict["time"]))
        if clock is None:
            return f"Couldn't read '{args_dict['time']}' as a time — confirm the exact time with the caller."
        args_dict["starts_at"] = f"{str(args_dict['date'])[:10]}T{clock.strftime('%H:%M')}:00"
    return None


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
    return tool_response(
        {
            "note": (
                "Prices are for YOUR reference. If the caller asks what services we "
                "offer, say only the names — never read out a list of prices. Say a "
                "price only for the specific service the caller chose."
            ),
            "services": out,
        },
        tool_call_id,
    )


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


def _looks_like_unresolved_phone_template(phone: str) -> bool:
    """Vapi's {{customer.number}} template is only ever unresolved on a
    dashboard Talk/web-test call (no real caller ID to fill in) — a real phone
    call always substitutes real digits first. If the model still passed the
    literal placeholder text through, never save it as a customer's phone
    number."""
    lowered = phone.strip().lower()
    return "customer.number" in lowered or lowered in {"customer", "number", ""}


_PLACEHOLDER_WORDS = {"customer name", "name", "unknown", "caller", "customer", "n/a", "na", "none", "tbd"}


def _looks_like_placeholder_name(name: str | None) -> bool:
    """A live call booked "[Customer Name]" — the model filled the required field
    with template text instead of asking. Never save that as a real name."""
    cleaned = (name or "").strip().lower()
    return not cleaned or "[" in cleaned or "{" in cleaned or cleaned in _PLACEHOLDER_WORDS


def _looks_like_street_address(address: str | None) -> bool:
    """A real service address has a house/street number — the same live call booked
    the city ("Dallas") as the address, which a detailer can't drive to."""
    cleaned = (address or "").strip()
    return bool(cleaned) and "[" not in cleaned and any(ch.isdigit() for ch in cleaned)


def _error(message: str, tool_call_id: str | None, status_code: int = 400):
    if tool_call_id is None:
        raise HTTPException(status_code=status_code, detail=message)
    return tool_response(message, tool_call_id)


_ASK_FOR_PHONE = (
    "There's no caller ID on this call (a web test call), so the phone number isn't "
    "known — ask the caller directly for their phone number, then call this tool "
    "again with the real digits."
)


def _resolve_phone(args_dict: dict, verified_number: str | None) -> str | None:
    """The caller's phone comes from Vapi's verified caller ID — the agent never
    asks for it. Only a web test call (no caller ID) falls back to what the agent
    passed, and never to unresolved {{customer.number}} placeholder text."""
    if verified_number:
        return verified_number
    supplied = str(args_dict.get("customer_phone") or "")
    if _looks_like_unresolved_phone_template(supplied):
        return None
    return supplied  # a malformed number still fails schema validation normally


@router.post("/book_appointment", dependencies=[Depends(verify_vapi)])
async def book_appointment(request: Request, db: Session = Depends(get_db)):
    args_dict, tool_call_id, verified_number = await parse_tool_call_full(request)

    phone = _resolve_phone(args_dict, verified_number)
    if phone is None:
        return _error(_ASK_FOR_PHONE, tool_call_id)
    args_dict["customer_phone"] = phone

    # Returning caller: reuse the saved name/address when the agent didn't collect
    # a real one. New caller: send the agent back to ask — never book template text.
    # Only for real Vapi calls — the flat admin-test shape keeps plain schema validation.
    known = (booking_service.known_customer_details(db, phone) or {}) if tool_call_id else None
    if known is None:
        pass
    elif _looks_like_placeholder_name(args_dict.get("customer_name")):
        if known.get("name"):
            args_dict["customer_name"] = known["name"]
        else:
            return _error(
                "Nothing was booked yet — you don't have the caller's real name. Ask "
                "\"Can I get your name for the appointment?\", then call book_appointment "
                "again with it. Never pass placeholder text as a name.",
                tool_call_id,
            )
    if known is not None and not _looks_like_street_address(args_dict.get("address")):
        if known.get("address"):
            args_dict["address"] = known["address"]
            args_dict.setdefault("zip_code", known.get("zip_code"))
        else:
            return _error(
                "Nothing was booked yet — you don't have the street address where the "
                "car will be (a city alone isn't enough). Ask \"What's the street address "
                "where we'll be detailing the car?\", then call book_appointment again.",
                tool_call_id,
            )

    bad_time = _local_start_from_args(args_dict)
    if bad_time:
        return _error(bad_time, tool_call_id)

    args, early = _validated(VoiceBookingCreate, args_dict, tool_call_id)
    if early is not None:
        return early

    state = args.state or state_from_zip(args.zip_code)
    if state is None:
        return _state_unknown(tool_call_id)
    # The time the agent passes is always the caller's local wall clock.
    args.starts_at = reinterpret_as_wall_clock(args.starts_at, state)

    lead = booking_service._pending_lead(db, args.lead_id) or booking_service.find_pending_lead(db, phone)
    try:
        booking = booking_service.create_booking(
            db, args, source="voice", lead_id=lead.id if lead else None
        )
    except HTTPException as exc:
        if tool_call_id is not None:
            return tool_response(str(exc.detail), tool_call_id)
        raise

    result = {
        "booking_id": booking.id,
        **describe_local(booking.starts_at, booking.state),
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
            "may be less than what you asked for if it hit the price floor). Say the "
            "day and time exactly as given in day_of_week/time — never add a timezone."
        ),
    }
    return tool_response(result, tool_call_id)


@router.post("/save_lead", dependencies=[Depends(verify_vapi)])
async def save_lead(request: Request, db: Session = Depends(get_db)):
    """Call the moment a caller says yes to going ahead (or says they want to book),
    BEFORE asking for a day/time — so if the call drops, the shop still sees a
    "needs callback" lead with the phone, vehicle, service and quoted price.
    Calling it again in the same call just updates that one lead."""
    args_dict, tool_call_id, verified_number = await parse_tool_call_full(request)
    phone = _resolve_phone(args_dict, verified_number)
    if phone is None:
        return _error(_ASK_FOR_PHONE, tool_call_id)

    args, early = _validated(VoiceLeadCreate, args_dict, tool_call_id)
    if early is not None:
        return early

    # Look up before saving: save_lead itself creates a customer row for this phone.
    known = booking_service.known_customer_details(db, phone)
    if known and not (known.get("name") or known.get("address")):
        known = None
    lead = booking_service.save_lead(db, args, phone)
    result = {
        "lead_id": lead.id,
        "status": lead.status.value,
        "price_cents": lead.price_cents,
        "known_customer": known,
        "note": (
            "Saved as a pending request — nothing is scheduled yet, don't tell the "
            "caller they're booked. Continue: ask what day works for them. Pass this "
            "lead_id to book_appointment once a time is agreed."
            + (
                " RETURNING CUSTOMER: known_customer has their saved details — do NOT ask "
                "for anything it already has (name/address); use those values when booking."
                if known
                else ""
            )
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
    if _looks_like_unresolved_phone_template(phone):
        # A web test call has no caller ID — the raw template text once matched old
        # test bookings saved under that same text, reading another "caller's"
        # appointments aloud. No real number means nothing to look up.
        return tool_response(
            {"count": 0, "appointments": [], "known_customer": None,
             "note": "No caller ID on this call — treat as a new caller."},
            tool_call_id,
        )
    bookings = booking_service.find_by_phone(db, phone)
    result = {
        "known_customer": booking_service.known_customer_details(db, phone),
        "count": len(bookings),
        "appointments": [
            {
                "booking_id": b.id,
                **describe_local(b.starts_at, b.state),
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
    bad_time = _local_start_from_args(args_dict)
    if bad_time:
        return _error(bad_time, tool_call_id)
    args, early = _validated(RescheduleArgs, args_dict, tool_call_id)
    if early is not None:
        return early

    try:
        existing = booking_service._require(db, args.booking_id)
        booking = booking_service.reschedule_booking(
            db,
            args.booking_id,
            reinterpret_as_wall_clock(args.starts_at, existing.state),
            args.duration_minutes,
        )
    except HTTPException as exc:
        if tool_call_id is not None:
            return tool_response(str(exc.detail), tool_call_id)
        raise

    result = {
        "booking_id": booking.id,
        **describe_local(booking.starts_at, booking.state),
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

"""Vapi tool endpoints.

Every tool validates through app.schemas and writes through app.services.booking —
the same code path the admin dashboard uses. The LLM supplies arguments; it never
supplies trust.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from sqlalchemy import select

from app.config import get_settings
from app.db import get_db
from app.models import CallLog, Service
from app.schemas import AskRequest, AskResponse, VoiceBookingCreate
from app.security import bearer_scheme
from app.services import booking as booking_service
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
    result = rag.answer(db, payload.question, payload.top_k)
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
    """So the agent can quote a real price before booking — never estimate one."""
    services = db.execute(
        select(Service).where(Service.active).order_by(Service.name)
    ).scalars().all()
    return {
        "services": [
            {
                "service_id": s.id,
                "name": s.name,
                "duration_minutes": s.duration_minutes,
                "price_cents": s.price_cents,
                "large_vehicle_surcharge_cents": s.large_vehicle_surcharge_cents,
                "note": "large_vehicle_surcharge_cents applies for SUVs, trucks, vans, and minivans",
            }
            for s in services
        ]
    }


@router.post("/book_appointment", dependencies=[Depends(verify_vapi)])
def book_appointment(args: VoiceBookingCreate, db: Session = Depends(get_db)) -> dict:
    booking = booking_service.create_booking(db, args, source="voice")
    return {
        "booking_id": booking.id,
        "starts_at": booking.starts_at.isoformat(),
        "state": booking.state,
        "status": booking.status.value,
        "price_cents": booking.price_cents,
        "vehicle_category": booking.vehicle_category,
        "note": "Read the price_cents total back to the caller as a dollar amount to confirm it.",
    }


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


@router.post("/cancel_appointment", dependencies=[Depends(verify_vapi)])
def cancel_appointment(args: CancelArgs, db: Session = Depends(get_db)) -> dict:
    booking = booking_service.cancel_booking(db, args.booking_id)
    return {"booking_id": booking.id, "status": booking.status.value}

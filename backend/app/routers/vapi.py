"""Vapi tool endpoints.

Every tool validates through app.schemas and writes through app.services.booking —
the same code path the admin dashboard uses. The LLM supplies arguments; it never
supplies trust.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import CallLog, Market
from app.schemas import AskRequest, AskResponse, BookingCreate
from app.services import booking as booking_service
from app.services import rag

settings = get_settings()
router = APIRouter(prefix="/api/vapi", tags=["vapi"])


def verify_vapi(x_vapi_secret: str | None = Header(default=None)) -> None:
    if not settings.vapi_secret:
        return  # unset in local dev
    if x_vapi_secret != settings.vapi_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad tool secret")


@router.post("/ask", response_model=AskResponse, dependencies=[Depends(verify_vapi)])
def ask(payload: AskRequest, db: Session = Depends(get_db)) -> AskResponse:
    result = rag.answer(db, payload.question, payload.top_k)
    db.add(
        CallLog(question=payload.question, answer=result.answer, tool_name="ask")
    )
    db.commit()
    return result


class ListSlotsArgs(BaseModel):
    market: Market
    day: datetime
    duration_minutes: int = Field(default=90, ge=15, le=600)


@router.post("/list_slots", dependencies=[Depends(verify_vapi)])
def list_slots(args: ListSlotsArgs, db: Session = Depends(get_db)) -> dict:
    slots = booking_service.list_slots(db, args.market, args.day, args.duration_minutes)
    return {
        "count": len(slots),
        "slots": [s.starts_at.isoformat() for s in slots[:8]],
    }


@router.post("/book_appointment", dependencies=[Depends(verify_vapi)])
def book_appointment(args: BookingCreate, db: Session = Depends(get_db)) -> dict:
    booking = booking_service.create_booking(db, args, source="voice")
    return {
        "booking_id": booking.id,
        "starts_at": booking.starts_at.isoformat(),
        "market": booking.market.value,
        "status": booking.status.value,
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
                "market": b.market.value,
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

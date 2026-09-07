"""Single source of truth for request/response shapes.

Both the admin API and the Vapi tool endpoints validate through these — the LLM's
parsing is never trusted, the backend owns validation.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import BookingStatus
from app.services.us_states import normalize_state

ZIP_PATTERN = r"^\d{5}(-\d{4})?$"


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth ---
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str


# --- Customers ---
class CustomerOut(ORMModel):
    id: str
    name: str
    phone: str
    email: str | None = None


# --- Bookings ---
class BookingCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=255)
    customer_phone: str = Field(min_length=7, max_length=32)
    customer_email: EmailStr | None = None
    state: str = Field(min_length=2, max_length=20, description="US state, name or 2-letter code")
    zip_code: str = Field(pattern=ZIP_PATTERN, description="5-digit ZIP, or ZIP+4")
    starts_at: datetime
    service_id: str | None = None
    duration_minutes: int = Field(default=90, ge=15, le=600)
    detailer: str | None = None
    vehicle: str | None = None
    address: str | None = None
    notes: str | None = None
    price_cents: int | None = Field(default=None, ge=0, description="Override the catalog price")
    service_label: str | None = None

    @field_validator("state")
    @classmethod
    def _validate_state(cls, v: str) -> str:
        return normalize_state(v)


class VoiceBookingCreate(BookingCreate):
    """What the phone agent must supply — stricter than the admin form. A caller
    can't be booked on vague details: we need a real address+ZIP to show up at, a
    vehicle to price and prep for, and an actual catalog service (so the price
    quoted on the call is the price charged, not a guess)."""

    vehicle: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1)
    service_id: str = Field(min_length=1, description="From list_services — never invented")


class ParsedBookingCreate(BaseModel):
    """Looser than BookingCreate: for the paste-and-parse quick intake flow, where a
    freeform note may not cleanly yield a validated state/ZIP or an appointment time."""

    customer_name: str = Field(min_length=1, max_length=255)
    customer_phone: str = Field(min_length=3, max_length=32)
    starts_at: datetime | None = None
    state: str | None = Field(default=None, max_length=20)
    zip_code: str | None = Field(default=None, max_length=10)
    detailer: str | None = None
    vehicle: str | None = None
    address: str | None = None
    notes: str | None = None
    price_cents: int | None = Field(default=None, ge=0)
    service_label: str | None = None
    duration_minutes: int = Field(default=90, ge=15, le=600)

    @field_validator("state")
    @classmethod
    def _validate_state(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        try:
            return normalize_state(v)
        except ValueError:
            return None  # keep the raw text in `address` instead of failing the save


class BookingReschedule(BaseModel):
    starts_at: datetime
    duration_minutes: int | None = Field(default=None, ge=15, le=600)


class BookingStatusUpdate(BaseModel):
    status: BookingStatus


class DetailerUpdate(BaseModel):
    detailer: str | None = Field(default=None, max_length=255)


class BookingOut(ORMModel):
    id: str
    state: str | None
    zip_code: str | None
    detailer: str | None
    vehicle: str | None
    vehicle_category: str | None
    address: str | None
    notes: str | None
    price_cents: int | None
    service_label: str | None
    starts_at: datetime
    ends_at: datetime
    status: BookingStatus
    source: str
    customer: CustomerOut


class SlotOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
    detailer: str | None = None


# --- Services ---
class ServiceOut(ORMModel):
    id: str
    name: str
    duration_minutes: int
    price_cents: int
    large_vehicle_surcharge_cents: int
    active: bool


# --- Detailers ---
class DetailerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class DetailerOut(ORMModel):
    id: str
    name: str
    active: bool


# --- Documents ---
class DocumentOut(ORMModel):
    id: str
    title: str
    filename: str
    content_type: str
    size_bytes: int
    chunk_count: int
    created_at: datetime


# --- RAG ---
class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=4, ge=1, le=10)
    state: str | None = Field(
        default=None,
        max_length=20,
        description="Caller's state if already known this call, for a locally-correct "
        "'today' — not validated as strictly as a booking's state, a best-effort hint.",
    )

    @field_validator("state")
    @classmethod
    def _normalize_state(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        try:
            return normalize_state(v)
        except ValueError:
            return None  # best-effort hint — an unrecognized value just falls back to default


class RetrievedChunk(BaseModel):
    document_id: str
    document_title: str
    chunk_index: int
    content: str
    score: float


class AskResponse(BaseModel):
    answer: str
    grounded: bool
    sources: list[RetrievedChunk]


# --- Job parser (paste-and-parse quick intake) ---
class ParseJobRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ParsedJob(BaseModel):
    customer_name: str | None = None
    customer_phone: str | None = None
    vehicle: str | None = None
    state: str | None = None
    zip_code: str | None = None
    address: str | None = None
    service_label: str | None = None
    price_cents: int | None = None
    starts_at: datetime | None = None
    notes: str | None = None


# --- Dashboard ---
class DashboardStats(BaseModel):
    bookings_today: int
    bookings_this_week: int
    upcoming: int
    cancelled_this_week: int
    documents: int
    chunks: int
    by_state: dict[str, int]
    by_status: dict[str, int]

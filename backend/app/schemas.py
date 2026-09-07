"""Single source of truth for request/response shapes.

Both the admin API and the Vapi tool endpoints validate through these — the LLM's
parsing is never trusted, the backend owns validation.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import BookingStatus, Market


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
    market: Market
    starts_at: datetime
    service_id: str | None = None
    duration_minutes: int = Field(default=90, ge=15, le=600)
    detailer: str | None = None
    vehicle: str | None = None
    address: str | None = None
    notes: str | None = None


class BookingReschedule(BaseModel):
    starts_at: datetime
    duration_minutes: int | None = Field(default=None, ge=15, le=600)


class BookingStatusUpdate(BaseModel):
    status: BookingStatus


class BookingOut(ORMModel):
    id: str
    market: Market
    detailer: str | None
    vehicle: str | None
    address: str | None
    notes: str | None
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


# --- Dashboard ---
class DashboardStats(BaseModel):
    bookings_today: int
    bookings_this_week: int
    upcoming: int
    cancelled_this_week: int
    documents: int
    chunks: int
    by_market: dict[str, int]
    by_status: dict[str, int]

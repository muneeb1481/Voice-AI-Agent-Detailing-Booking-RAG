from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings

settings = get_settings()


def _vector_column():
    """pgvector on Postgres, JSON fallback so the stack runs on SQLite locally."""
    if settings.uses_postgres:
        from pgvector.sqlalchemy import Vector  # noqa: PLC0415

        return Vector(settings.embedding_dim)
    return JSON


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class BookingStatus(str, enum.Enum):
    scheduled = "scheduled"
    done = "done"
    rescheduled = "rescheduled"
    cancelled = "cancelled"


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(32), index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    bookings: Mapped[list[Booking]] = relationship(back_populates="customer")


class Service(Base):
    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=90)
    # Fallback price when the vehicle's category couldn't be determined at all —
    # real pricing for a known category comes from ServicePrice below, which is
    # the actual source of truth (this catalog has genuinely different prices per
    # vehicle type, not one price plus a flat surcharge).
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    large_vehicle_surcharge_cents: Mapped[int] = mapped_column(Integer, default=0)
    # Per-foot rate for boat/trailer services (cents per foot) — None for every
    # other service, where pricing comes from the category matrix instead.
    price_per_foot_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(default=True)

    prices: Mapped[list[ServicePrice]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )


class ServicePrice(Base):
    """The real price matrix: what a given service costs for a given vehicle
    category. A service with no row here for a category isn't offered for that
    vehicle at all (e.g. Ceramic Coating has no minivan row — it's Sedan/SUV/Truck
    only) — the absence of a row IS the eligibility rule, not a separate flag."""

    __tablename__ = "service_prices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(20), index=True)
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    # The floor this specific (service, category) price can be discounted down to
    # on a call. Null = no stated floor for this line item.
    min_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    service: Mapped[Service] = relationship(back_populates="prices")


class AddOn(Base):
    """A small extra a customer can add to a base service — buffing, waxing, paint
    correction, pet hair removal, engine bay cleaning. Priced and timed separately
    from the base service catalog, since these aren't full detailing packages."""

    __tablename__ = "add_ons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    large_vehicle_surcharge_cents: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(default=True)


class Detailer(Base):
    __tablename__ = "detailers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"), nullable=True)

    # Nullable: a phone/admin booking always has these (schema-enforced there), but a
    # parsed job intake may not cleanly extract a US state/ZIP from freeform text.
    state: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    detailer: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    vehicle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vehicle_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Only set for boat/trailer bookings, where price is length_ft * rate rather
    # than a category lookup.
    vehicle_length_ft: Mapped[float | None] = mapped_column(Float, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # What the service catalog priced this at (or a manual/parsed override), snapshotted
    # at booking time so later catalog price changes don't rewrite past jobs. This is
    # the FINAL price after any discount; original_price_cents keeps the pre-discount
    # total so an admin can see how much was actually knocked off.
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    # Free-text service description for jobs that don't map to a catalog Service
    # (e.g. parsed from "interior exterior" with no matching service_id).
    service_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus), default=BookingStatus.scheduled, index=True
    )

    source: Mapped[str] = mapped_column(String(32), default="voice")  # voice | admin | parser
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    customer: Mapped[Customer] = relationship(back_populates="bookings")
    service: Mapped[Service | None] = relationship()
    # Extra services/add-ons stacked on top of the base service above — e.g. a base
    # "Interior + Exterior Full Detail" plus a "Ceramic Coating" extra service and a
    # "Waxing" add-on, each snapshotted with its own price/duration at booking time.
    items: Mapped[list[BookingItem]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )


class BookingItem(Base):
    __tablename__ = "booking_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    booking_id: Mapped[str] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    item_type: Mapped[str] = mapped_column(String(16))  # "service" | "addon"
    catalog_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)

    booking: Mapped[Booking] = relationship(back_populates="items")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128), default="text/plain")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # delete-orphan is the pairing people forget: dropping a doc must drop its vectors,
    # otherwise the agent keeps citing withdrawn pricing.
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(_vector_column(), nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks")


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    call_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CallTranscript(Base):
    """One row per completed voice call, from Vapi's end-of-call webhook — so an
    admin can see exactly what the agent said, not just infer it from the booking
    that resulted (or didn't)."""

    __tablename__ = "call_transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    call_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The full webhook body, kept as-is — Vapi's exact payload shape can shift, and
    # this guarantees nothing is lost even when a specific field wasn't parsed out.
    raw_payload = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
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
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    # Extra charge for larger vehicles (SUV/truck/van/minivan) — the business rule
    # from the pricing doc ("SUVs and trucks add $100") applied automatically.
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
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # What the service catalog priced this at (or a manual/parsed override), snapshotted
    # at booking time so later catalog price changes don't rewrite past jobs.
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
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

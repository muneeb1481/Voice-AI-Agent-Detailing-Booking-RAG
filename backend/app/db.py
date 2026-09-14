from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {} if settings.uses_postgres else {"check_same_thread": False}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create the pgvector extension (Postgres only) and all tables."""
    from app.models import Base  # noqa: PLC0415  (avoid circular import at module load)

    if settings.uses_postgres:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    if settings.uses_postgres:
        _migrate_postgres()


def _migrate_postgres() -> None:
    """create_all never alters existing tables — apply the pending-lead schema
    changes to an already-deployed database. Every statement is idempotent."""
    # ALTER TYPE ... ADD VALUE can't run inside a transaction block on older Postgres.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'pending'"))
        conn.execute(text("ALTER TABLE bookings ALTER COLUMN starts_at DROP NOT NULL"))
        conn.execute(text("ALTER TABLE bookings ALTER COLUMN ends_at DROP NOT NULL"))


if not settings.uses_postgres:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_enforce_foreign_keys(dbapi_conn, _record):  # pragma: no cover - dev only
        """SQLite ships with FK enforcement off; ON DELETE CASCADE is a no-op without it."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

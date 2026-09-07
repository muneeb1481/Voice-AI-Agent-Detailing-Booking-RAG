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


if not settings.uses_postgres:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_enforce_foreign_keys(dbapi_conn, _record):  # pragma: no cover - dev only
        """SQLite ships with FK enforcement off; ON DELETE CASCADE is a no-op without it."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

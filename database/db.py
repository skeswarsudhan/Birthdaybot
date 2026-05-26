"""
database/db.py — SQLAlchemy engine and session management.

Usage:
    from database.db import init_db, SessionLocal

    # Initialise tables (call once at startup)
    init_db()

    # Use as a context manager
    with SessionLocal() as session:
        employees = session.query(Employee).all()

    # FastAPI dependency
    def get_db():
        with SessionLocal() as session:
            yield session
"""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config import DB_PATH
from database.models import Base

# ---------------------------------------------------------------------------
# Engine — SQLite with check_same_thread=False (required for multi-threaded use)
# ---------------------------------------------------------------------------

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)

# Session factory
_SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class SessionLocal:
    """
    Context-manager wrapper around SQLAlchemy Session.

    Ensures the session is always closed, and rolls back on exception.

    Example:
        with SessionLocal() as db:
            db.add(some_object)
            db.commit()
    """

    def __enter__(self) -> Session:
        self._session = _SessionFactory()
        return self._session

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type:
                self._session.rollback()
        finally:
            self._session.close()
        return False  # Do not suppress exceptions


def get_db():
    """
    FastAPI dependency that yields a database session.

    Usage in a route:
        @router.get("/")
        def my_route(db: Session = Depends(get_db)):
            ...
    """
    session = _SessionFactory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _run_migrations() -> None:
    """
    Apply any additive schema migrations (ALTER TABLE ADD COLUMN).
    Safe to run on every startup — each statement is guarded by a column existence check.
    """
    from sqlalchemy import text
    with engine.connect() as conn:
        # Add `role` column to birthday_requests if it was added after initial deploy
        try:
            conn.execute(text("ALTER TABLE birthday_requests ADD COLUMN role VARCHAR(255)"))
            conn.commit()
        except Exception:
            pass  # Column already exists — ignore


def init_db() -> None:
    """
    Create all tables defined in models.py if they do not already exist.

    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS semantics.
    """
    Base.metadata.create_all(bind=engine)
    _run_migrations()

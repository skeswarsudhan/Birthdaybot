"""
database/models.py — SQLAlchemy ORM models for Birthday Bot.

Three models:
  - Employee         — synced daily from Excel / SharePoint
  - BirthdayRequest  — one per employee per year; tracks the full workflow
  - LogEntry         — event log persisted to SQLite for the dashboard
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import JSON

Base = declarative_base()


class Employee(Base):
    """
    Represents one employee synced from the data source.

    The 'active' flag is set to False when the employee is no longer
    present in the Excel/SharePoint source, rather than deleting the row
    (preserves historical BirthdayRequest records).
    """

    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    dob = Column(Date, nullable=True)  # Full date; month+day used for matching
    timezone = Column(String(64), nullable=False, default="Asia/Kolkata")
    manager_name = Column(String(255), nullable=True)
    manager_email = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    birthday_requests = relationship(
        "BirthdayRequest", back_populates="employee", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Employee id={self.id} name={self.name!r} email={self.email!r}>"


class BirthdayRequest(Base):
    """
    Tracks the full lifecycle of one birthday celebration cycle.

    One record per employee per calendar year.  The unique constraint at the
    DB level prevents duplicate requests even if the scan job runs twice.

    Status flow:
        pending → reminded_once → reminded_twice → received → sent
                                                            → fallback_sent (no manager response)
    """

    __tablename__ = "birthday_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(
        Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    year = Column(Integer, nullable=False)  # Calendar year of this birthday
    token = Column(String(36), nullable=False, unique=True)  # UUID4
    token_expires_at = Column(DateTime, nullable=False)  # Expiry for manager form link

    # Status — one of the values listed below
    status = Column(String(32), nullable=False, default="pending")
    #   pending        — manager email sent, awaiting response
    #   reminded_once  — first reminder sent
    #   reminded_twice — second (final) reminder sent
    #   received       — manager submitted the form
    #   sent           — birthday email sent (with personalisation)
    #   fallback_sent  — birthday email sent (generic fallback, no manager response)

    reminder_count = Column(Integer, nullable=False, default=0)

    # Content collected from manager
    fun_facts = Column(Text, nullable=True)
    personal_message = Column(Text, nullable=True)
    role = Column(String(255), nullable=True)  # Employee's role/title as provided by manager
    photos = Column(JSON, nullable=True)  # List of file path strings

    # Generated content
    ai_generated_message = Column(Text, nullable=True)

    # Timestamps
    manager_submitted_at = Column(DateTime, nullable=True)
    email_sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    employee = relationship("Employee", back_populates="birthday_requests")

    # DB-level uniqueness — prevents duplicate records even under concurrent access
    __table_args__ = (
        UniqueConstraint("employee_id", "year", name="uq_birthday_request_employee_year"),
    )

    def __repr__(self) -> str:
        return (
            f"<BirthdayRequest id={self.id} "
            f"employee_id={self.employee_id} year={self.year} status={self.status!r}>"
        )


class LogEntry(Base):
    """
    Application event log stored in SQLite.

    Written by utils.logger.log_event() and displayed on the dashboard.
    """

    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    level = Column(String(16), nullable=False)   # INFO / WARNING / ERROR
    event = Column(String(255), nullable=False)
    detail = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<LogEntry id={self.id} level={self.level!r} event={self.event!r}>"

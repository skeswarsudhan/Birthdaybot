"""
scheduler/jobs.py — All five APScheduler jobs for Birthday Bot.

Jobs registered:
  1. sync_employees_job     — daily 00:00  — syncs employee data from Excel
  2. scan_birthdays_job     — daily 09:00  — finds upcoming birthdays, emails managers
  3. send_reminders_job     — daily 09:05  — sends reminders to non-responsive managers
  4. send_birthday_emails_job — daily 08:00 — sends birthday emails to employees
  5. daily_digest_job       — daily 20:00  — sends digest to admin

Every job body is wrapped in a try/except — exceptions are logged as ERROR
and never allowed to crash the scheduler silently.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from jinja2 import Environment, FileSystemLoader

import premailer

from ai.generator import generate_birthday_message
from config import (
    DAYS_BEFORE,
    MAX_REMINDERS,
    SCHEDULER_TIMEZONE,
)
from database.db import SessionLocal
from database.models import BirthdayRequest, Employee, LogEntry
from email_engine.collage import build_collage
from email_engine.sender import (
    send_birthday_email,
    send_digest,
    send_manager_reminder,
    send_manager_request,
)
from scheduler.scanner import sync_employees
from utils.logger import log_event
from utils.tokens import generate_token

_TZ = pytz.timezone(SCHEDULER_TIMEZONE)

# Jinja2 env for birthday email template
_EMAIL_TEMPLATES = Path(__file__).parent.parent / "email_engine" / "templates"
_jinja = Environment(loader=FileSystemLoader(str(_EMAIL_TEMPLATES)), autoescape=True)


# ---------------------------------------------------------------------------
# Helper — today's date in the configured timezone
# ---------------------------------------------------------------------------

def _today():
    """Return today's date in the configured scheduler timezone."""
    return datetime.now(tz=_TZ).date()


# ---------------------------------------------------------------------------
# Job 1 — Employee sync
# ---------------------------------------------------------------------------

def sync_employees_job():
    """Sync employee roster from the configured data source into SQLite."""
    try:
        summary = sync_employees()
        log_event(
            "INFO",
            "job_sync_employees",
            detail=str(summary),
        )
    except Exception as exc:
        log_event("ERROR", "job_sync_employees_crashed", detail=str(exc))


# ---------------------------------------------------------------------------
# Job 2 — Birthday scan
# ---------------------------------------------------------------------------

def scan_birthdays_job(days_before_override: int | None = None):
    """
    Scan for upcoming birthdays and email managers if no request exists yet.

    Args:
        days_before_override: Used by test_flow.py to override DAYS_BEFORE.
    """
    try:
        days_before = days_before_override if days_before_override is not None else DAYS_BEFORE
        target_date = _today() + timedelta(days=days_before)
        current_year = _today().year

        manager_emails_sent = 0

        with SessionLocal() as session:
            employees = session.query(Employee).filter(Employee.active == True).all()

            for emp in employees:
                if not emp.dob:
                    continue

                # Check month+day match
                if emp.dob.month != target_date.month or emp.dob.day != target_date.day:
                    continue

                # Check if request already exists for this year
                existing = (
                    session.query(BirthdayRequest)
                    .filter(
                        BirthdayRequest.employee_id == emp.id,
                        BirthdayRequest.year == current_year,
                    )
                    .first()
                )
                if existing:
                    log_event(
                        "INFO",
                        "scan_birthdays_skipped",
                        detail=f"{emp.name} — request already exists for {current_year}",
                    )
                    continue

                # Birthday date this year (for token expiry)
                birthday_this_year = emp.dob.replace(year=current_year)
                # Token expires at midnight the day after the birthday
                token_expires = datetime(
                    birthday_this_year.year,
                    birthday_this_year.month,
                    birthday_this_year.day,
                ) + timedelta(days=1)

                token = generate_token()
                req = BirthdayRequest(
                    employee_id=emp.id,
                    year=current_year,
                    token=token,
                    token_expires_at=token_expires,
                    status="pending",
                    reminder_count=0,
                )
                session.add(req)
                session.flush()  # Get req.id before commit

                ok = send_manager_request(emp, req)
                if ok:
                    manager_emails_sent += 1

                log_event(
                    "INFO",
                    "scan_birthdays_triggered",
                    detail=f"{emp.name} (birthday {birthday_this_year}), email_sent={ok}",
                )

            session.commit()

        log_event(
            "INFO",
            "job_scan_birthdays_complete",
            detail=f"target_date={target_date}, manager_emails_sent={manager_emails_sent}",
        )

    except Exception as exc:
        log_event("ERROR", "job_scan_birthdays_crashed", detail=str(exc))


# ---------------------------------------------------------------------------
# Job 3 — Reminders
# ---------------------------------------------------------------------------

def send_reminders_job():
    """
    Send reminder emails to managers who haven't responded yet.

    Criteria:
      - status in (pending, reminded_once)
      - reminder_count < MAX_REMINDERS
      - employee's birthday is still in the future
    """
    try:
        today = _today()
        current_year = today.year
        reminders_sent = 0

        with SessionLocal() as session:
            requests = (
                session.query(BirthdayRequest)
                .join(Employee)
                .filter(
                    BirthdayRequest.status.in_(["pending", "reminded_once"]),
                    BirthdayRequest.reminder_count < MAX_REMINDERS,
                    Employee.active == True,
                )
                .all()
            )

            for req in requests:
                emp = req.employee
                if not emp or not emp.dob:
                    continue

                birthday_this_year = emp.dob.replace(year=current_year)
                if birthday_this_year <= today:
                    continue  # Birthday already passed — don't nag

                ok = send_manager_reminder(emp, req)
                if ok:
                    req.reminder_count += 1
                    req.status = (
                        "reminded_once" if req.reminder_count == 1 else "reminded_twice"
                    )
                    reminders_sent += 1

            session.commit()

        log_event(
            "INFO",
            "job_send_reminders_complete",
            detail=f"reminders_sent={reminders_sent}",
        )

    except Exception as exc:
        log_event("ERROR", "job_send_reminders_crashed", detail=str(exc))


# ---------------------------------------------------------------------------
# Job 4 — Birthday emails
# ---------------------------------------------------------------------------

def send_birthday_emails_job():
    """
    Send birthday emails to employees whose birthday is today.

    - If manager submitted (status=received): AI-generated message + collage
    - Otherwise (fallback): generic warm message, no collage
    In both cases: mark email_sent_at and update status.
    """
    try:
        today = _today()
        current_year = today.year
        emails_sent = 0

        with SessionLocal() as session:
            requests = (
                session.query(BirthdayRequest)
                .join(Employee)
                .filter(
                    BirthdayRequest.email_sent_at == None,
                    BirthdayRequest.year == current_year,
                    Employee.active == True,
                )
                .all()
            )

            for req in requests:
                emp = req.employee
                if not emp or not emp.dob:
                    continue

                birthday_this_year = emp.dob.replace(year=current_year)
                if birthday_this_year != today:
                    continue  # Not today

                collage_b64 = None
                if req.status == "received":
                    # Generate AI message
                    ai_msg = generate_birthday_message(
                        name=emp.name,
                        department=emp.department or "",
                        fun_facts=req.fun_facts or "",
                        personal_message=req.personal_message or "",
                        role=req.role or "",
                    )
                    req.ai_generated_message = ai_msg

                    # Build collage if photos exist
                    if req.photos:
                        collage_b64 = build_collage(req.photos)

                    # Render birthday email
                    html = _render_birthday_email(
                        name=emp.name,
                        department=emp.department or "the team",
                        role=req.role or "",
                        message=ai_msg,
                        collage_image=collage_b64,
                    )
                    new_status = "sent"
                else:
                    # Fallback — generic message
                    fallback_msg = (
                        f"Today is all about you, {emp.name}! "
                        "The whole team is celebrating everything you bring to "
                        f"{emp.department or 'the team'} every single day. "
                        "We hope this birthday is the start of your best year yet — "
                        "filled with joy, success, and every good thing you deserve. "
                        "Happy Birthday! 🎉"
                    )
                    html = _render_birthday_email(
                        name=emp.name,
                        department=emp.department or "the team",
                        role=req.role or "",
                        message=fallback_msg,
                        collage_image=None,
                    )
                    new_status = "fallback_sent"

                ok = send_birthday_email(emp, req, html, collage_b64=collage_b64)
                if ok:
                    req.email_sent_at = datetime.utcnow()
                    req.status = new_status
                    emails_sent += 1

            session.commit()

        log_event(
            "INFO",
            "job_send_birthday_emails_complete",
            detail=f"emails_sent={emails_sent}",
        )

    except Exception as exc:
        log_event("ERROR", "job_send_birthday_emails_crashed", detail=str(exc))


def send_single_birthday_email_by_req_id(req_id: int):
    """
    Send the final birthday email to a single employee by their BirthdayRequest ID.
    Used for on-demand test execution and the 2-minute test scheduler.
    """
    try:
        with SessionLocal() as session:
            req = session.query(BirthdayRequest).filter(BirthdayRequest.id == req_id).first()
            if not req:
                log_event("ERROR", "single_birthday_email_failed", detail=f"Request {req_id} not found")
                return

            emp = req.employee
            if not emp:
                log_event("ERROR", "single_birthday_email_failed", detail=f"Employee for Request {req_id} not found")
                return

            log_event("INFO", "single_birthday_email_trigger", detail=f"Triggering birthday email for {emp.name} (Request {req_id})")

            collage_b64 = None
            if req.status == "received":
                ai_msg = generate_birthday_message(
                    name=emp.name,
                    department=emp.department or "",
                    fun_facts=req.fun_facts or "",
                    personal_message=req.personal_message or "",
                    role=req.role or "",
                )
                req.ai_generated_message = ai_msg

                if req.photos:
                    collage_b64 = build_collage(req.photos)

                html = _render_birthday_email(
                    name=emp.name,
                    department=emp.department or "the team",
                    role=req.role or "",
                    message=ai_msg,
                    collage_image=collage_b64,
                )
                new_status = "sent"
            else:
                fallback_msg = (
                    f"Today is all about you, {emp.name}! "
                    "The whole team is celebrating everything you bring to "
                    f"{emp.department or 'the team'} every single day. "
                    "We hope this birthday is the start of your best year yet — "
                    "filled with joy, success, and every good thing you deserve. "
                    "Happy Birthday! 🎉"
                )
                html = _render_birthday_email(
                    name=emp.name,
                    department=emp.department or "the team",
                    role=req.role or "",
                    message=fallback_msg,
                    collage_image=None,
                )
                new_status = "fallback_sent"

            ok = send_birthday_email(emp, req, html, collage_b64=collage_b64)
            if ok:
                req.email_sent_at = datetime.utcnow()
                req.status = new_status
                session.commit()
                log_event("INFO", "single_birthday_email_success", detail=f"Sent birthday email to {emp.name}")
            else:
                log_event("ERROR", "single_birthday_email_failed", detail=f"SendGrid rejected email to {emp.name}")
    except Exception as exc:
        log_event("ERROR", "single_birthday_email_crashed", detail=str(exc))


def _render_birthday_email(
    name: str,
    department: str,
    role: str,
    message: str,
    collage_image: str | None,
) -> str:
    """Render and inline the birthday HTML email template."""
    template = _jinja.get_template("birthday_email.html")
    raw = template.render(
        name=name,
        department=department,
        role=role,
        message=message,
        collage_image=collage_image,
    )
    try:
        return premailer.transform(raw, raise_errors=False)
    except Exception:
        return raw


# ---------------------------------------------------------------------------
# Job 5 — Daily digest
# ---------------------------------------------------------------------------

def daily_digest_job():
    """Count today's activity and send a summary to the admin."""
    try:
        today = _today()
        today_str = today.strftime("%Y-%m-%d")

        with SessionLocal() as session:
            # Count log entries for today
            from datetime import time as dt_time
            start_of_day = datetime.combine(today, dt_time.min)

            def count_events(event_prefix: str) -> int:
                return (
                    session.query(LogEntry)
                    .filter(
                        LogEntry.event.like(f"{event_prefix}%"),
                        LogEntry.timestamp >= start_of_day,
                    )
                    .count()
                )

            birthday_scanned = count_events("scan_birthdays_triggered")
            manager_sent = count_events("manager_request_sent")
            reminders = count_events("manager_reminder_sent")
            b_emails = count_events("birthday_email_sent")
            errors = (
                session.query(LogEntry)
                .filter(
                    LogEntry.level == "ERROR",
                    LogEntry.timestamp >= start_of_day,
                )
                .count()
            )

        summary = {
            "date": today_str,
            "birthdays_scanned": birthday_scanned,
            "manager_emails_sent": manager_sent,
            "reminders_sent": reminders,
            "birthday_emails_sent": b_emails,
            "errors": errors,
        }

        send_digest(summary)
        log_event("INFO", "job_daily_digest_sent", detail=str(summary))

    except Exception as exc:
        log_event("ERROR", "job_daily_digest_crashed", detail=str(exc))


# ---------------------------------------------------------------------------
# Scheduler registration
# ---------------------------------------------------------------------------

def start_scheduler() -> BackgroundScheduler:
    """
    Create and start the APScheduler BackgroundScheduler with all 5 jobs.

    Returns:
        The started BackgroundScheduler instance (keep a reference to it).
    """
    scheduler = BackgroundScheduler(timezone=_TZ)

    scheduler.add_job(
        sync_employees_job,
        trigger="cron",
        hour=0, minute=0,
        id="sync_employees",
        name="Sync Employees (midnight)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        scan_birthdays_job,
        trigger="cron",
        hour=9, minute=0,
        id="scan_birthdays",
        name="Scan Birthdays (09:00)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        send_reminders_job,
        trigger="cron",
        hour=9, minute=5,
        id="send_reminders",
        name="Send Reminders (09:05)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        send_birthday_emails_job,
        trigger="cron",
        hour=8, minute=0,
        id="send_birthday_emails",
        name="Send Birthday Emails (08:00)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.add_job(
        daily_digest_job,
        trigger="cron",
        hour=20, minute=0,
        id="daily_digest",
        name="Daily Digest (20:00)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    return scheduler

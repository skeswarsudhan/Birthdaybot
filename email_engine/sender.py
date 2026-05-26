"""
email_engine/sender.py — Transactional email sending via SendGrid HTTP API.

Uses the sendgrid Python SDK — no raw SMTP required, which means it works on
Render's free tier (outbound SMTP on port 587/465 is blocked there).

All four send functions follow the same pattern:
  1. Build Jinja2 template context
  2. Render the HTML template
  3. Run through premailer to inline all CSS (Outlook/Gmail compat)
  4. Send via SendGrid HTTP API
  5. Return True on success, False on failure — never raises

Usage:
    from email_engine.sender import send_manager_request
    ok = send_manager_request(employee, birthday_request)
"""

import base64
from datetime import datetime, timedelta
from pathlib import Path

import premailer
import pytz
from jinja2 import Environment, FileSystemLoader
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    ContentId,
    Disposition,
    FileContent,
    FileName,
    FileType,
    Mail,
    To,
)

from config import (
    ADMIN_EMAIL,
    BASE_URL,
    FROM_EMAIL,
    FROM_NAME,
    MAX_REMINDERS,
    SCHEDULER_TIMEZONE,
    SENDGRID_API_KEY,
)
from utils.logger import log_event

# ---------------------------------------------------------------------------
# Jinja2 setup — loads templates from email_engine/templates/
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _render(template_name: str, context: dict) -> str:
    """
    Render a Jinja2 template and inline all CSS via premailer.

    Args:
        template_name: Filename inside email_engine/templates/.
        context:       Template variables.

    Returns:
        HTML string with inlined CSS ready for sending.
    """
    template = _jinja_env.get_template(template_name)
    raw_html = template.render(**context)
    try:
        inlined = premailer.transform(raw_html, raise_errors=False)
    except Exception:  # noqa: BLE001
        inlined = raw_html  # Fallback to non-inlined if premailer fails
    return inlined


def _days_until(birthday_date) -> int:
    """Return the number of calendar days until the given date."""
    tz = pytz.timezone(SCHEDULER_TIMEZONE)
    today = datetime.now(tz=tz).date()
    delta = birthday_date - today
    return max(delta.days, 0)


def _form_url(token: str) -> str:
    """Construct the manager form URL for the given token."""
    return f"{BASE_URL.rstrip('/')}/submit/{token}"


def _sendgrid_send(
    to: list[str],
    subject: str,
    html: str,
    images: list[tuple[str, bytes]] | None = None,
) -> None:
    """
    Core SendGrid HTTP send helper.

    Args:
        to:      List of recipient email addresses.
        subject: Email subject line.
        html:    HTML email body.
        images:  List of (content_id, image_bytes) tuples for inline images.

    Raises:
        Exception: Any API or connection error — callers handle this.
    """
    from_addr = f"{FROM_NAME} <{FROM_EMAIL}>" if FROM_NAME else FROM_EMAIL

    message = Mail(
        from_email=from_addr,
        to_emails=[To(addr) for addr in to],
        subject=subject,
        html_content=html,
    )

    if images:
        for cid, img_data in images:
            attachment = Attachment(
                FileContent(base64.b64encode(img_data).decode()),
                FileName(f"{cid}.jpg"),
                FileType("image/jpeg"),
                Disposition("inline"),
                ContentId(cid),
            )
            message.add_attachment(attachment)

    client = SendGridAPIClient(SENDGRID_API_KEY)
    response = client.send(message)

    # SendGrid returns 2xx on success; raise on anything else
    if response.status_code not in (200, 202):
        raise RuntimeError(
            f"SendGrid returned HTTP {response.status_code}: {response.body}"
        )


# ---------------------------------------------------------------------------
# Public send functions
# ---------------------------------------------------------------------------

def send_manager_request(employee, birthday_request) -> bool:
    """
    Send the initial manager request email asking for fun facts and photos.

    Args:
        employee:         Employee ORM object.
        birthday_request: BirthdayRequest ORM object.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    birthday_date = employee.dob.replace(year=datetime.now().year) if employee.dob else None
    birthday_str = birthday_date.strftime("%B %d") if birthday_date else "their birthday"
    days_left = _days_until(birthday_date) if birthday_date else 0

    context = {
        "employee_name": employee.name,
        "manager_name": employee.manager_name or "Hi",
        "birthday_date": birthday_str,
        "days_left": days_left,
        "form_url": _form_url(birthday_request.token),
        "deadline": (birthday_date - timedelta(days=2)).strftime("%B %d") if birthday_date else "soon",
    }

    try:
        html = _render("manager_request.html", context)
        _sendgrid_send(
            to=[employee.manager_email],
            subject=f"🎂 Action needed: {employee.name}'s birthday is on {birthday_str}",
            html=html,
        )
        log_event(
            "INFO",
            "manager_request_sent",
            detail=f"employee={employee.name}, manager={employee.manager_email}",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log_event("ERROR", "manager_request_failed", detail=f"{employee.name}: {exc}")
        return False


def send_manager_reminder(employee, birthday_request) -> bool:
    """
    Send a reminder email to the manager if they haven't submitted yet.

    Args:
        employee:         Employee ORM object.
        birthday_request: BirthdayRequest ORM object.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    birthday_date = employee.dob.replace(year=datetime.now().year) if employee.dob else None
    birthday_str = birthday_date.strftime("%B %d") if birthday_date else "their birthday"
    days_left = _days_until(birthday_date) if birthday_date else 0
    reminder_num = birthday_request.reminder_count + 1

    context = {
        "employee_name": employee.name,
        "manager_name": employee.manager_name or "Hi",
        "birthday_date": birthday_str,
        "days_left": days_left,
        "form_url": _form_url(birthday_request.token),
        "reminder_num": reminder_num,
        "max_reminders": MAX_REMINDERS,
    }

    try:
        html = _render("manager_reminder.html", context)
        _sendgrid_send(
            to=[employee.manager_email],
            subject=f"⏰ Reminder #{reminder_num}: {employee.name}'s birthday is in {days_left} days",
            html=html,
        )
        log_event(
            "INFO",
            "manager_reminder_sent",
            detail=f"employee={employee.name}, reminder #{reminder_num}",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log_event("ERROR", "manager_reminder_failed", detail=f"{employee.name}: {exc}")
        return False


def send_birthday_email(
    employee,
    birthday_request,
    html_content: str,
    collage_b64: str | None = None,
) -> bool:
    """
    Send the final birthday email to the employee.

    Args:
        employee:         Employee ORM object.
        birthday_request: BirthdayRequest ORM object.
        html_content:     Pre-rendered HTML string of the birthday email.
        collage_b64:      Optional base64-encoded collage image.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    try:
        images = []
        if collage_b64:
            img_data = base64.b64decode(collage_b64)
            images.append(("collage_image", img_data))

        _sendgrid_send(
            to=[employee.email],
            subject=f"🎉 Happy Birthday, {employee.name.split()[0]}! 🎂",
            html=html_content,
            images=images,
        )
        log_event(
            "INFO",
            "birthday_email_sent",
            detail=f"employee={employee.name}, status={birthday_request.status}",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log_event("ERROR", "birthday_email_failed", detail=f"{employee.name}: {exc}")
        return False


def send_digest(summary_dict: dict) -> bool:
    """
    Send the daily operational digest to the admin.

    Args:
        summary_dict: Dict with keys:
            birthdays_scanned, manager_emails_sent, reminders_sent,
            birthday_emails_sent, errors, date (str)

    Returns:
        True if the digest was sent successfully, False otherwise.
    """
    date_str = summary_dict.get("date", "Today")
    try:
        html = _render("digest.html", summary_dict)
        _sendgrid_send(
            to=[ADMIN_EMAIL],
            subject=f"📊 Birthday Bot Daily Digest — {date_str}",
            html=html,
        )
        log_event("INFO", "digest_sent", detail=f"date={date_str}")
        return True
    except Exception as exc:  # noqa: BLE001
        log_event("ERROR", "digest_failed", detail=str(exc))
        return False

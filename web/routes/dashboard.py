"""
web/routes/dashboard.py — Admin dashboard route.

GET / — Shows three panels:
  1. Upcoming birthdays (next 30 days)
  2. Pending responses (managers who haven't submitted)
  3. Recent log entries (last 30)

Auto-refreshes every 60 seconds via meta refresh.
No authentication — POC only.
"""

from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import pytz

from config import SCHEDULER_TIMEZONE
from database.db import get_db
from database.models import BirthdayRequest, Employee, LogEntry

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_TZ = pytz.timezone(SCHEDULER_TIMEZONE)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """
    Render the admin dashboard with birthday status, pending responses,
    and the last 30 log entries.
    """
    today = datetime.now(tz=_TZ).date()
    current_year = today.year
    lookahead = today + timedelta(days=30)

    # ---- Upcoming birthdays (next 30 days) ----
    all_active = db.query(Employee).filter(Employee.active == True).all()
    upcoming = []
    for emp in all_active:
        if not emp.dob:
            continue
        try:
            bday_this_year = emp.dob.replace(year=current_year)
        except ValueError:
            continue  # Feb 29 in non-leap year

        if today <= bday_this_year <= lookahead:
            days_away = (bday_this_year - today).days
            req = (
                db.query(BirthdayRequest)
                .filter(
                    BirthdayRequest.employee_id == emp.id,
                    BirthdayRequest.year == current_year,
                )
                .first()
            )
            upcoming.append(
                {
                    "name": emp.name,
                    "birthday": bday_this_year.strftime("%B %d"),
                    "days_away": days_away,
                    "department": emp.department or "—",
                    "manager": emp.manager_name or "—",
                    "status": req.status if req else "no_request",
                }
            )

    upcoming.sort(key=lambda x: x["days_away"])

    # ---- Pending responses ----
    pending_requests = (
        db.query(BirthdayRequest)
        .join(Employee)
        .filter(
            BirthdayRequest.status.in_(["pending", "reminded_once", "reminded_twice"]),
            BirthdayRequest.year == current_year,
            Employee.active == True,
        )
        .all()
    )

    pending = []
    for req in pending_requests:
        emp = req.employee
        if not emp or not emp.dob:
            continue
        try:
            bday = emp.dob.replace(year=current_year)
        except ValueError:
            continue
        days_left = (bday - today).days
        pending.append(
            {
                "name": emp.name,
                "birthday_date": bday.strftime("%B %d"),
                "days_left": days_left,
                "reminders_sent": req.reminder_count,
                "status": req.status,
            }
        )

    # ---- Recent logs ----
    log_entries = (
        db.query(LogEntry)
        .order_by(LogEntry.timestamp.desc())
        .limit(30)
        .all()
    )

    logs = [
        {
            "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "level": entry.level,
            "event": entry.event,
            "detail": entry.detail or "",
        }
        for entry in log_entries
    ]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "upcoming": upcoming,
            "pending": pending,
            "logs": logs,
            "today": today.strftime("%B %d, %Y"),
        },
    )


@router.get("/api/trigger-test")
async def trigger_test(
    request: Request,
    email: str = "eswar@rampp.ai",
    manager_email: str = "antigravitymapla@gmail.com",
    db: Session = Depends(get_db)
):
    """
    On-demand E2E test trigger.
    
    1. Creates/Upserts a test employee (if they do not already exist, or updates details).
    2. Sets birthday to today.
    3. Triggers the BirthdayRequest for current calendar year with status 'pending'.
    4. Sends manager request email immediately.
    5. Returns a JSON response with direct manager form link.
    """
    from utils.tokens import generate_token
    from email_engine.sender import send_manager_request
    from utils.logger import log_event
    
    today = datetime.now(tz=_TZ).date()
    current_year = today.year
    
    # 1. Upsert employee
    emp = db.query(Employee).filter(Employee.email == email.lower()).first()
    if not emp:
        emp = Employee(
            name="Test Employee Eswar",
            email=email.lower(),
            dob=today,
            manager_name="Test Manager Mapla",
            manager_email=manager_email.lower(),
            department="Engineering",
            active=True
        )
        db.add(emp)
    else:
        emp.dob = today
        emp.manager_email = manager_email.lower()
        emp.active = True
    db.commit()
    db.refresh(emp)
    
    # 2. Check if a BirthdayRequest already exists for this year
    # Delete it first to let the user run this test cleanly over and over again!
    existing_req = db.query(BirthdayRequest).filter(
        BirthdayRequest.employee_id == emp.id,
        BirthdayRequest.year == current_year
    ).first()
    if existing_req:
        db.delete(existing_req)
        db.commit()
        
    # 3. Create fresh request
    token = generate_token()
    token_expires = datetime.now() + timedelta(days=2) # token valid for 2 days
    
    req = BirthdayRequest(
        employee_id=emp.id,
        year=current_year,
        token=token,
        token_expires_at=token_expires,
        status="pending",
        reminder_count=0
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    
    # 4. Send manager request immediately
    ok = send_manager_request(emp, req)
    
    # Construct direct manager form url
    form_url = f"{str(request.base_url).rstrip('/')}/submit/{token}"
    
    log_event(
        "INFO",
        "api_trigger_test_completed",
        detail=f"employee={email}, manager={manager_email}, email_sent={ok}"
    )
    
    return {
        "success": ok,
        "message": f"Successfully triggered manager request email for {emp.name}.",
        "manager_email_sent_to": manager_email,
        "form_url": form_url,
        "instructions": (
            "1. Open the form_url in your browser.\n"
            "2. Fill in the fun facts and submit.\n"
            "3. Once submitted, the system will trigger the final birthday email "
            "to the employee (eswar@rampp.ai) in exactly 2 minutes."
        )
    }


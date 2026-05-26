"""
web/routes/form.py — Manager birthday form routes.

GET  /submit/{token}  — Show the form (or expired/already-submitted states)
POST /submit/{token}  — Accept form submission with photos
"""

import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from config import UPLOAD_DIR
from database.db import get_db
from database.models import BirthdayRequest, Employee
from utils.logger import log_event
from utils.tokens import is_token_valid

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Max file constraints
MAX_PHOTOS = 5
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}


# ---------------------------------------------------------------------------
# GET /submit/{token}
# ---------------------------------------------------------------------------

@router.get("/submit/{token}", response_class=HTMLResponse)
async def show_form(request: Request, token: str, db: Session = Depends(get_db)):
    """
    Display the manager birthday submission form.

    States:
      - Invalid / expired token → expired.html
      - Already submitted       → thankyou.html (with 'already submitted' message)
      - Valid, pending          → form.html
    """
    req = is_token_valid(token, db)

    if req is None:
        return templates.TemplateResponse("expired.html", {"request": request})

    emp: Employee = db.query(Employee).filter(Employee.id == req.employee_id).first()

    if req.status == "received":
        return templates.TemplateResponse(
            "thankyou.html",
            {
                "request": request,
                "employee_name": emp.name if emp else "the employee",
                "already_submitted": True,
            },
        )

    birthday_str = ""
    if emp and emp.dob:
        birthday_str = emp.dob.strftime("%B %d")

    return templates.TemplateResponse(
        "form.html",
        {
            "request": request,
            "token": token,
            "employee_name": emp.name if emp else "your team member",
            "birthday_date": birthday_str,
            "error": None,
            "fun_facts": "",
            "personal_message": "",
            "role": "",
        },
    )


# ---------------------------------------------------------------------------
# POST /submit/{token}
# ---------------------------------------------------------------------------

@router.post("/submit/{token}", response_class=HTMLResponse)
async def submit_form(
    request: Request,
    background_tasks: BackgroundTasks,
    token: str,
    fun_facts: str = Form(default=""),
    personal_message: str = Form(default=""),
    role: str = Form(default=""),
    photos: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    """
    Process the manager birthday form submission.

    Validates token, saves photos, updates BirthdayRequest record.
    """
    req: BirthdayRequest | None = is_token_valid(token, db)

    if req is None:
        return templates.TemplateResponse("expired.html", {"request": request})

    emp: Employee = db.query(Employee).filter(Employee.id == req.employee_id).first()
    employee_name = emp.name if emp else "the employee"
    birthday_str = emp.dob.strftime("%B %d") if emp and emp.dob else ""

    # ---- Validate photos ----
    valid_photos = [p for p in photos if p.filename and p.filename.strip()]

    if len(valid_photos) > MAX_PHOTOS:
        return templates.TemplateResponse(
            "form.html",
            {
                "request": request,
                "token": token,
                "employee_name": employee_name,
                "birthday_date": birthday_str,
                "error": f"Please upload a maximum of {MAX_PHOTOS} photos.",
            },
        )

    # Check file sizes
    saved_paths: list[str] = []
    upload_dir = Path(UPLOAD_DIR) / token
    upload_dir.mkdir(parents=True, exist_ok=True)

    for i, photo in enumerate(valid_photos, start=1):
        suffix = Path(photo.filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            return templates.TemplateResponse(
                "form.html",
                {
                    "request": request,
                    "token": token,
                    "employee_name": employee_name,
                    "birthday_date": birthday_str,
                    "error": f"Only JPG and PNG files are allowed (got '{photo.filename}').",
                },
            )

        content = await photo.read()
        if len(content) > MAX_FILE_SIZE_BYTES:
            return templates.TemplateResponse(
                "form.html",
                {
                    "request": request,
                    "token": token,
                    "employee_name": employee_name,
                    "birthday_date": birthday_str,
                    "error": f"'{photo.filename}' is too large. Maximum size is 2 MB per photo.",
                },
            )

        filename = f"photo_{i}{suffix}"
        dest = upload_dir / filename
        dest.write_bytes(content)
        saved_paths.append(str(dest))

    # ---- Update BirthdayRequest ----
    req.fun_facts = fun_facts.strip() or None
    req.personal_message = personal_message.strip() or None
    req.role = role.strip() or None
    req.photos = saved_paths if saved_paths else None
    req.status = "received"
    req.manager_submitted_at = datetime.utcnow()
    db.commit()

    # Check if we should trigger an immediate test birthday email delivery
    test_emails = {"antigravitymapla@gmail.com", "eswar@rampp.ai", "eswarsudhanphotography@gmail.com"}
    if emp and emp.email.lower() in test_emails:
        from scheduler.jobs import send_single_birthday_email_by_req_id
        background_tasks.add_task(send_single_birthday_email_by_req_id, req.id)
        log_event(
            "INFO",
            "test_birthday_mail_triggered_immediate",
            detail=f"employee={employee_name}, triggered immediately via background tasks"
        )

    log_event(
        "INFO",
        "form_submitted",
        detail=f"employee={employee_name}, photos={len(saved_paths)}, token={token[:8]}...",
    )

    return templates.TemplateResponse(
        "thankyou.html",
        {
            "request": request,
            "employee_name": employee_name,
            "already_submitted": False,
        },
    )

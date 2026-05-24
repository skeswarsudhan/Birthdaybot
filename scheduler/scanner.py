"""
scheduler/scanner.py — Employee sync from data source to SQLite.

sync_employees() is the single function responsible for keeping the
Employee table in sync with whatever data source is configured.

It is idempotent: safe to run multiple times — duplicates are impossible
because email is a unique index and we do UPDATE on conflict.
"""

from datetime import datetime

from database.db import SessionLocal
from database.models import Employee
from data_source import get_data_source
from utils.logger import log_event


def sync_employees() -> dict:
    """
    Sync employees from the configured data source into SQLite.

    Algorithm:
      1. Fetch all employees from the data source.
      2. For each dict: upsert (update if email exists, else insert).
      3. Any DB employee whose email is NOT in the fetched list is deactivated.

    Returns:
        A summary dict with keys: inserted, updated, deactivated, total_fetched.
    """
    ds = get_data_source()

    try:
        raw_employees = ds.get_employees()
    except Exception as exc:
        log_event("ERROR", "sync_employees_datasource_error", detail=str(exc))
        return {"inserted": 0, "updated": 0, "deactivated": 0, "total_fetched": 0}

    fetched_emails = {emp["email"].lower() for emp in raw_employees}
    inserted = 0
    updated = 0
    deactivated = 0

    with SessionLocal() as session:
        # Build a lookup of existing employees keyed by email
        existing: dict[str, Employee] = {
            e.email.lower(): e
            for e in session.query(Employee).all()
        }

        # Upsert each employee from the data source
        now = datetime.utcnow()
        for emp_data in raw_employees:
            email_key = emp_data["email"].lower()

            if email_key in existing:
                # Update existing record
                db_emp = existing[email_key]
                db_emp.name = emp_data["name"]
                db_emp.dob = emp_data.get("dob")
                db_emp.manager_name = emp_data.get("manager_name", "")
                db_emp.manager_email = emp_data.get("manager_email", "")
                db_emp.department = emp_data.get("department", "")
                db_emp.active = emp_data.get("active", True)
                db_emp.updated_at = now
                updated += 1
            else:
                # Insert new record
                new_emp = Employee(
                    name=emp_data["name"],
                    email=email_key,
                    dob=emp_data.get("dob"),
                    manager_name=emp_data.get("manager_name", ""),
                    manager_email=emp_data.get("manager_email", ""),
                    department=emp_data.get("department", ""),
                    active=emp_data.get("active", True),
                    created_at=now,
                    updated_at=now,
                )
                session.add(new_emp)
                inserted += 1

        # Deactivate employees no longer in the data source
        for email_key, db_emp in existing.items():
            if email_key not in fetched_emails and db_emp.active:
                db_emp.active = False
                db_emp.updated_at = now
                deactivated += 1

        session.commit()

    summary = {
        "inserted": inserted,
        "updated": updated,
        "deactivated": deactivated,
        "total_fetched": len(raw_employees),
    }

    log_event(
        "INFO",
        "sync_employees_complete",
        detail=(
            f"fetched={summary['total_fetched']}, "
            f"inserted={summary['inserted']}, "
            f"updated={summary['updated']}, "
            f"deactivated={summary['deactivated']}"
        ),
    )

    return summary

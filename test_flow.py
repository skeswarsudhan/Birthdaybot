"""
test_flow.py — End-to-end Birthday Bot test script.

Simulates a complete birthday cycle without waiting real days.

Usage:
    python test_flow.py

What it does:
  1. Loads .env and initialises DB
  2. Inserts a fake employee with today as birthday
  3. Runs scan_birthdays_job with DAYS_BEFORE=0 (triggers immediately)
  4. Prints the manager form URL
  5. Waits for you to open the form and submit it
  6. Runs send_birthday_emails_job
  7. Prints where to find the birthday email
  8. Cleans up the test employee (asks for confirmation)

Full test takes ~5 minutes. Check ADMIN_EMAIL inbox after step 6.
"""

import sys
from datetime import date
from pathlib import Path

# Ensure the project root is on sys.path when running as a script
sys.path.insert(0, str(Path(__file__).parent))

# Load environment
import config  # noqa: F401  (loads .env)
from config import ADMIN_EMAIL, BASE_URL, validate_config

validate_config()

from pathlib import Path as _Path
_Path(config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
_Path("logs").mkdir(parents=True, exist_ok=True)

from utils.logger import setup_logging, log_event
setup_logging(_Path("logs"))

from database.db import init_db, SessionLocal
from database.models import BirthdayRequest, Employee

init_db()

from scheduler.jobs import scan_birthdays_job, send_birthday_emails_job
from utils.tokens import is_token_valid

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

TEST_EMAIL = "test.birthday@birthdaybot.local"
TEST_MANAGER_EMAIL = ADMIN_EMAIL  # Reuse admin email for test

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_employee() -> Employee:
    """Insert a test employee whose birthday is today."""
    today = date.today()
    with SessionLocal() as session:
        # Remove any leftover from a previous test run
        existing = session.query(Employee).filter(Employee.email == TEST_EMAIL).first()
        if existing:
            session.delete(existing)
            session.commit()

        emp = Employee(
            name="Test Employee",
            email=TEST_EMAIL,
            dob=today,
            manager_name="Test Manager",
            manager_email=TEST_MANAGER_EMAIL,
            department="Engineering",
            active=True,
        )
        session.add(emp)
        session.commit()
        session.refresh(emp)
        print(f"✅  Test employee created: {emp.name} (dob={emp.dob}, email={emp.email})")
        return emp


def _get_form_url() -> str | None:
    """Look up the form token created by scan_birthdays_job."""
    today = date.today()
    with SessionLocal() as session:
        req = (
            session.query(BirthdayRequest)
            .join(Employee)
            .filter(
                Employee.email == TEST_EMAIL,
                BirthdayRequest.year == today.year,
            )
            .first()
        )
        if req:
            return f"{BASE_URL.rstrip('/')}/submit/{req.token}"
    return None


def _cleanup():
    """Remove the test employee and all associated BirthdayRequests."""
    with SessionLocal() as session:
        emp = session.query(Employee).filter(Employee.email == TEST_EMAIL).first()
        if emp:
            session.delete(emp)
            session.commit()
            print("🗑️   Test employee cleaned up.")
        else:
            print("ℹ️   Test employee not found — nothing to clean up.")


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 60)
    print("  Birthday Bot — End-to-End Test Flow")
    print("=" * 60)

    # Step 1: Create test employee
    print("\n[1/4] Creating test employee with today's birthday...")
    _create_test_employee()

    # Step 2: Run scan job with DAYS_BEFORE=0
    print("\n[2/4] Running scan_birthdays_job (DAYS_BEFORE=0)...")
    scan_birthdays_job(days_before_override=0)

    # Step 3: Show form URL
    form_url = _get_form_url()
    if not form_url:
        print("\n❌  No BirthdayRequest was created. Check logs for errors.")
        _cleanup()
        sys.exit(1)

    print(f"\n[3/4] Manager form URL generated:\n\n    {form_url}\n")
    print(f"    A manager request email was also sent to: {TEST_MANAGER_EMAIL}")
    print(
        "\n    ➡️  Open the URL above in your browser and submit the form."
        "\n       (You can enter any fun facts and optional photos.)"
    )

    input("\n    Press Enter once you've submitted the form to continue...")

    # Step 4: Run birthday email job
    print("\n[4/4] Running send_birthday_emails_job...")
    send_birthday_emails_job()

    print(f"\n✅  Done! Check {ADMIN_EMAIL} for the birthday email.")
    print(f"    Also check the dashboard at {BASE_URL} if the server is running.\n")

    # Cleanup
    answer = input("Clean up the test employee from the database? [Y/n]: ").strip().lower()
    if answer in ("", "y", "yes"):
        _cleanup()
    else:
        print("ℹ️   Test employee left in database.")

    print("\n🎉  Test flow complete!\n")


if __name__ == "__main__":
    main()

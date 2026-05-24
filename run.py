"""
run.py — Birthday Bot entry point.

Startup sequence:
  1. Load .env
  2. Validate all required env vars
  3. Create uploads/ and logs/ directories
  4. Initialise SQLite DB (create tables)
  5. Sync employees from data source
  6. Start APScheduler (5 jobs)
  7. Start Uvicorn web server

All steps after validation are wrapped in a friendly try/except —
no raw tracebacks are shown to the user.
"""

import sys
from pathlib import Path

# ---- Step 1: Load environment ----
# config.py calls load_dotenv() at import time
import config  # noqa: F401  (side effect: loads .env)

# ---- Step 2: Validate config ----
from config import (
    ADMIN_EMAIL,
    BASE_URL,
    LOGS_DIR,
    PORT,
    UPLOAD_DIR,
    validate_config,
)

validate_config()

# ---- Everything below is in a friendly try/except ----
try:
    # ---- Step 3: Create directories ----
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Configure logging (needs LOGS_DIR to exist) ----
    from utils.logger import log_event, setup_logging
    setup_logging(LOGS_DIR)

    # ---- Step 4: Initialise database ----
    from database.db import init_db
    init_db()
    log_event("INFO", "startup", detail="Database initialised")

    # ---- Step 5: Sync employees ----
    print("\n⏳  Syncing employees from data source...")
    from scheduler.scanner import sync_employees
    sync_summary = sync_employees()
    print(
        f"✅  Employees synced — "
        f"inserted={sync_summary['inserted']}, "
        f"updated={sync_summary['updated']}, "
        f"deactivated={sync_summary['deactivated']}, "
        f"total={sync_summary['total_fetched']}"
    )

    # ---- Step 6: Start scheduler ----
    from scheduler.jobs import start_scheduler
    scheduler = start_scheduler()

    job_names = [job.name for job in scheduler.get_jobs()]
    print(f"\n🕐  APScheduler started — {len(job_names)} jobs registered:")
    for name in job_names:
        print(f"    • {name}")

    log_event("INFO", "startup", detail=f"Scheduler started with {len(job_names)} jobs")

    # ---- Step 7: Start Uvicorn ----
    print(f"\n🚀  Birthday Bot is running — open {BASE_URL}\n")
    log_event("INFO", "startup", detail=f"Uvicorn starting on port {PORT}")

    import uvicorn
    from web.app import app

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="warning",   # Suppress Uvicorn access logs for cleaner output
    )

except KeyboardInterrupt:
    print("\n\n👋  Birthday Bot stopped by user. Goodbye!")
    if "scheduler" in dir() and scheduler.running:
        scheduler.shutdown(wait=False)
    sys.exit(0)

except Exception as exc:
    print(f"\n❌  Birthday Bot failed to start:\n    {exc}\n")
    print("    Check logs/ for details or re-run after fixing the issue.\n")
    sys.exit(1)

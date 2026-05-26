"""
config.py — Central configuration for Birthday Bot.

All environment variables are loaded here. Import from this module
everywhere — never call os.getenv() directly in business logic.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root (same directory as config.py)
_env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_env_path)


# ---------------------------------------------------------------------------
# Required variables
# ---------------------------------------------------------------------------

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
FROM_EMAIL: str = os.getenv("FROM_EMAIL", "")
FROM_NAME: str = os.getenv("FROM_NAME", "Birthday Bot")
ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "")
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8080")

# ---------------------------------------------------------------------------
# SMTP settings (kept for optional local/fallback use)
# ---------------------------------------------------------------------------

SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")

# ---------------------------------------------------------------------------
# Optional variables with sensible defaults
# ---------------------------------------------------------------------------

PORT: int = int(os.getenv("PORT", "8080"))
DAYS_BEFORE: int = int(os.getenv("DAYS_BEFORE", "7"))
MAX_REMINDERS: int = int(os.getenv("MAX_REMINDERS", "2"))
EXCEL_PATH: Path = Path(os.getenv("EXCEL_PATH", "employees.xlsx"))
DATA_SOURCE: str = os.getenv("DATA_SOURCE", "excel")
UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", "uploads"))
COMPANY_DOMAIN: str = os.getenv("COMPANY_DOMAIN", "accenture.com")
SCHEDULER_TIMEZONE: str = os.getenv("SCHEDULER_TIMEZONE", "Asia/Kolkata")

# Database path — always sits next to config.py
DB_PATH: str = str(Path(__file__).parent / "birthday_bot.db")

# Logs directory
LOGS_DIR: Path = Path(__file__).parent / "logs"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_REQUIRED_VARS = {
    "GROQ_API_KEY": GROQ_API_KEY,
    "SENDGRID_API_KEY": SENDGRID_API_KEY,
    "FROM_EMAIL": FROM_EMAIL,
    "ADMIN_EMAIL": ADMIN_EMAIL,
}


def validate_config() -> None:
    """
    Check that all required environment variables are set.
    Prints a clear human-readable error and calls sys.exit(1) if any are missing.
    """
    missing = [name for name, value in _REQUIRED_VARS.items() if not value]
    if missing:
        print("\n❌  Birthday Bot cannot start — missing required environment variables:\n")
        for var in missing:
            print(f"    • {var}")
        print(
            "\n    Copy .env.example to .env and fill in the missing values.\n"
            "    See README.md for SMTP setup instructions.\n"
        )
        sys.exit(1)

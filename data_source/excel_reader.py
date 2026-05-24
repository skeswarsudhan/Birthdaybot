"""
data_source/excel_reader.py — Excel-based employee data source (POC implementation).

Reads the employee roster from an Excel file (.xlsx) using pandas + openpyxl.

Expected columns in the spreadsheet:
    Full Name          — Employee display name
    Ent ID             — Enterprise / employee ID  (used to build email if Email ID absent)
    Email ID           — Direct email address (preferred over constructed one if present)
    Birthday CurrentYear — Date of birth in DD/MM/YYYY or MM/DD/YYYY format
    THR/QB             — Department / cost centre
    Supervisor         — Manager name in "Lastname, Firstname" format
    Supervisor Email   — Manager's email address
    Active             — (optional) TRUE/FALSE or Yes/No — defaults to True if absent
"""

import re
from datetime import date
from pathlib import Path

import pandas as pd

from config import COMPANY_DOMAIN, EXCEL_PATH
from data_source.interface import EmployeeDataSource
from utils.logger import logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_email(value: str) -> bool:
    """Return True if the string looks like a valid email address."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, str(value).strip()))


def _parse_date(raw: object) -> date | None:
    """
    Parse a birthday value from the Excel cell.

    Tries these formats in order:
        1. Already a datetime/date object (pandas may parse automatically)
        2. DD/MM/YYYY string
        3. MM/DD/YYYY string

    Returns:
        A date object, or None if parsing fails.
    """
    if isinstance(raw, (date,)):
        return raw
    if hasattr(raw, "date"):
        # pandas Timestamp or datetime
        return raw.date()

    raw_str = str(raw).strip()
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return pd.to_datetime(raw_str, format=fmt).date()
        except (ValueError, TypeError):
            continue

    # Last resort — let pandas guess
    try:
        return pd.to_datetime(raw_str, dayfirst=True, errors="raise").date()
    except Exception:  # noqa: BLE001
        return None


def _parse_active(raw: object) -> bool:
    """
    Parse the optional 'Active' column.

    Truthy values: True, "True", "Yes", "Y", "1", 1
    Falsy values : False, "False", "No", "N", "0", 0, NaN
    Absent column: defaults to True (handled by caller).
    """
    if pd.isna(raw):
        return True
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in ("false", "no", "n", "0")


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class ExcelDataSource(EmployeeDataSource):
    """
    Reads employee data from an Excel (.xlsx) file.

    The path is taken from the EXCEL_PATH environment variable.
    """

    def get_employees(self) -> list[dict]:
        """
        Read the Excel file and return a list of employee dicts.

        Rows that fail date parsing are skipped with a WARNING log.
        Rows with missing required fields (name, email) are also skipped.

        Returns:
            List of dicts with keys:
                name, email, dob, manager_name, manager_email, department, active
        """
        xlsx_path = Path(EXCEL_PATH)
        if not xlsx_path.exists():
            logger.error(f"Excel file not found: {xlsx_path.resolve()}")
            return []

        try:
            df = pd.read_excel(xlsx_path, dtype=str, engine="openpyxl")
        except Exception as exc:
            logger.error(f"Failed to open Excel file '{xlsx_path}': {exc}")
            return []

        logger.info(f"Loaded Excel file: {xlsx_path.resolve()} ({len(df)} rows)")

        # Normalise column names — strip whitespace
        df.columns = [str(c).strip() for c in df.columns]

        employees: list[dict] = []
        skipped = 0

        for idx, row in df.iterrows():
            row_num = idx + 2  # 1-indexed, +1 for header row

            # --- Name ---
            name = str(row.get("Full Name", "")).strip()
            if not name or name.lower() == "nan":
                logger.warning(f"Row {row_num}: missing 'Full Name' — skipped")
                skipped += 1
                continue

            # --- Email ---
            email_id = str(row.get("Email ID", "")).strip()
            ent_id = str(row.get("Ent ID", "")).strip()

            if email_id and email_id.lower() != "nan" and _is_valid_email(email_id):
                email = email_id.lower()
            elif ent_id and ent_id.lower() != "nan":
                email = f"{ent_id.lower()}@{COMPANY_DOMAIN}"
            else:
                logger.warning(f"Row {row_num} ({name!r}): cannot determine email — skipped")
                skipped += 1
                continue

            # --- Date of Birth ---
            raw_dob = row.get("Birthday CurrentYear", None)
            dob = _parse_date(raw_dob)
            if dob is None:
                logger.warning(
                    f"Row {row_num} ({name!r}): "
                    f"could not parse birthday '{raw_dob}' — skipped"
                )
                skipped += 1
                continue

            # --- Supervisor ---
            manager_name = str(row.get("Supervisor", "")).strip()
            if manager_name.lower() == "nan":
                manager_name = ""

            # --- Supervisor Email ---
            manager_email = str(row.get("Supervisor Email", "")).strip()
            if manager_email.lower() == "nan":
                manager_email = ""

            # --- Department ---
            department = str(row.get("THR/QB", "")).strip()
            if department.lower() == "nan":
                department = ""

            # --- Active flag ---
            if "Active" in df.columns:
                active = _parse_active(row.get("Active"))
            else:
                active = True

            employees.append(
                {
                    "name": name,
                    "email": email,
                    "dob": dob,
                    "manager_name": manager_name,
                    "manager_email": manager_email,
                    "department": department,
                    "active": active,
                }
            )

        logger.info(
            f"Excel parsing complete: {len(employees)} valid employees, {skipped} skipped"
        )
        return employees

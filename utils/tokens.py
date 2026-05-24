"""
utils/tokens.py — Token generation and validation helpers.

Tokens are UUID4 strings used to uniquely identify manager form links.
They are stored in the BirthdayRequest table and expire at midnight on
the employee's birthday.
"""

import uuid
from datetime import datetime

import pytz

from config import SCHEDULER_TIMEZONE


def generate_token() -> str:
    """
    Generate a new unique token for a manager form link.

    Returns:
        A UUID4 string (e.g. '550e8400-e29b-41d4-a716-446655440000').
    """
    return str(uuid.uuid4())


def is_token_valid(token: str, db_session) -> "BirthdayRequest | None":
    """
    Validate a token and return the associated BirthdayRequest if valid.

    A token is valid if:
    - It exists in the BirthdayRequest table.
    - Its token_expires_at is in the future (timezone-aware comparison).

    Args:
        token:      The UUID4 token string from the URL.
        db_session: An active SQLAlchemy session.

    Returns:
        The BirthdayRequest record if valid, or None if invalid/expired.
    """
    from database.models import BirthdayRequest  # lazy to avoid circular import

    record: BirthdayRequest | None = (
        db_session.query(BirthdayRequest)
        .filter(BirthdayRequest.token == token)
        .first()
    )

    if record is None:
        return None

    tz = pytz.timezone(SCHEDULER_TIMEZONE)
    now = datetime.now(tz=tz)

    # token_expires_at is stored as a naive UTC datetime — make it aware
    expires = record.token_expires_at
    if expires.tzinfo is None:
        expires = pytz.utc.localize(expires)

    if now > expires:
        return None

    return record

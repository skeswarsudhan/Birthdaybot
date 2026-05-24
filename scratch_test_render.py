import sys
from pathlib import Path

# Ensure project root is in python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scheduler.jobs import _render_birthday_email

html = _render_birthday_email(
    name="Test Name",
    department="Engineering",
    message="Happy Birthday!",
    collage_image="dummy_base64_string",
)

# Look for collage tag
for line in html.splitlines():
    if "collage" in line or "cid:" in line:
        print(line)

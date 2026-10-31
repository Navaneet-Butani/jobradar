"""CSV contact import.

Accepts whatever column names people actually use — `email`, `Email ID`,
`hr_email`, `Contact Email` all resolve to the same field. A row without a
usable email is reported back with its line number rather than silently
dropped, so a 50-row file with 3 typos is fixable in one pass.
"""

import csv
import io
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_ROWS = 2000

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# Header aliases, normalized to lowercase with non-letters stripped.
COLUMN_ALIASES = {
    "email": ("email", "emailid", "emailaddress", "hremail", "contactemail", "mail", "mailid"),
    "contact_name": ("contactname", "name", "hrname", "fullname", "person", "contactperson", "recruitername"),
    "company_name": ("companyname", "company", "organisation", "organization", "employer", "firm"),
    "title": ("title", "designation", "jobtitle", "role", "position"),
    "role_hint": ("rolehint", "interestedrole", "targetrole", "openings", "hiringfor"),
    "notes": ("notes", "note", "comment", "comments", "remarks"),
}


def _normalize(header: str) -> str:
    return re.sub(r"[^a-z]", "", (header or "").lower())


def _map_headers(fieldnames: list[str]) -> dict[str, str]:
    """Map our field name -> the CSV's actual column name."""
    mapping: dict[str, str] = {}
    normalized = {_normalize(name): name for name in fieldnames if name}

    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[field] = normalized[alias]
                break
    return mapping


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def parse_contacts_csv(data: bytes) -> tuple[list[dict], list[str]]:
    """Parse a contacts CSV. Returns (rows, problems).

    Rows are deduplicated by email within the file itself — the last
    occurrence wins, since people tend to correct a row further down.
    """
    problems: list[str] = []

    if not data:
        return [], ["The file is empty."]
    if len(data) > MAX_CSV_BYTES:
        return [], [f"File is larger than {MAX_CSV_BYTES // (1024 * 1024)} MB."]

    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        return [], ["No header row found. The first line must name the columns, e.g. `company,name,email`."]

    mapping = _map_headers(list(reader.fieldnames))
    if "email" not in mapping:
        return [], [
            "No email column found. Name one column `email` (or `Email ID`, `HR Email`, "
            f"`Contact Email`). Columns seen: {', '.join(n for n in reader.fieldnames if n)}."
        ]

    by_email: dict[str, dict] = {}
    for line_number, raw in enumerate(reader, start=2):
        if line_number - 1 > MAX_ROWS:
            problems.append(f"Stopped at {MAX_ROWS} rows — split the file and import the rest separately.")
            break

        email = _clean(raw.get(mapping["email"], ""))
        if not email:
            problems.append(f"Row {line_number}: no email — skipped.")
            continue

        email = email.lower()
        if not EMAIL_RE.match(email):
            problems.append(f"Row {line_number}: '{email}' is not a valid email — skipped.")
            continue

        by_email[email] = {
            "email": email,
            "contact_name": _clean(raw.get(mapping.get("contact_name", ""), "")),
            "company_name": _clean(raw.get(mapping.get("company_name", ""), "")),
            "title": _clean(raw.get(mapping.get("title", ""), "")),
            "role_hint": _clean(raw.get(mapping.get("role_hint", ""), "")),
            "notes": _clean(raw.get(mapping.get("notes", ""), "")),
        }

    rows = list(by_email.values())
    if not rows and not problems:
        problems.append("No data rows found below the header.")

    return rows, problems

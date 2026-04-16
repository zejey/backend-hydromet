"""
Input sanitization utility

Strips HTML tags and dangerous characters from text inputs
to prevent XSS and injection attacks.
"""

import re
from html import escape as html_escape

# Matches HTML tags
_TAG_RE = re.compile(r"<[^>]+>")


def sanitize_string(value: str) -> str:
    """Remove HTML tags and escape special characters."""
    if not value:
        return value
    # Strip HTML tags
    cleaned = _TAG_RE.sub("", value)
    # Escape remaining HTML entities
    cleaned = html_escape(cleaned, quote=True)
    return cleaned.strip()


def sanitize_dict(data: dict, fields: list[str] | None = None) -> dict:
    """
    Sanitize string fields in a dictionary.

    If `fields` is provided, only those keys are sanitized.
    Otherwise all string values are sanitized.
    """
    result = dict(data)
    for key, val in result.items():
        if isinstance(val, str) and (fields is None or key in fields):
            result[key] = sanitize_string(val)
    return result

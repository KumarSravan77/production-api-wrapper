import re
from typing import Any, Tuple


PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    re.compile(r"\b\d{3}-\d{3}-\d{3}\b"),
)


def redact_sensitive(value: Any) -> Tuple[Any, int]:
    """Return a deep-redacted request payload and the number of replacements."""
    if isinstance(value, str):
        count = 0
        for pattern in PATTERNS:
            value, replacements = pattern.subn("[REDACTED]", value)
            count += replacements
        return value, count
    if isinstance(value, list):
        output, count = [], 0
        for item in value:
            redacted, replacements = redact_sensitive(item)
            output.append(redacted)
            count += replacements
        return output, count
    if isinstance(value, dict):
        output, count = {}, 0
        for key, item in value.items():
            redacted, replacements = redact_sensitive(item)
            output[key] = redacted
            count += replacements
        return output, count
    return value, 0

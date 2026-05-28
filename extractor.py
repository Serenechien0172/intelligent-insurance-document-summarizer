import re
from pathlib import Path
from typing import Any

import pdfplumber


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """Extract page text from a PDF with page separators for traceability."""
    pages: list[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"--- Page {index} ---\n{text.strip()}")

    return "\n\n".join(pages).strip()


def extract_policy_fields(text: str) -> dict[str, Any]:
    normalized = _normalize_text(text)

    fields: dict[str, Any] = {
        "policy_number": _first_match(normalized, r"\bPOLICY NUMBER:\s*([A-Z0-9-]+)"),
        "insured_name": _first_match(normalized, r"\bINSURED:\s*([A-Z][A-Z\s.'-]+?)(?=\s+(?:SEX AND AGE|POLICY|RISK CLASS|$))"),
        "effective_date": _first_match(normalized, r"\bPOLICY DATE:\s*([A-Z]+\s+\d{1,2},\s+\d{4})"),
        "expiration_date": _first_match(normalized, r"\bEXPIRATION DATE\s*(?:\(.*?\))?:\s*([A-Z]+\s+\d{1,2},\s+\d{4})"),
        "premium": _extract_premium(normalized),
        "coverage_limits": _extract_coverage_limits(normalized),
        "exclusions": _extract_exclusions(normalized),
    }

    return fields


def generate_summary(fields: dict[str, Any]) -> str:
    parts: list[str] = []

    insured = fields.get("insured_name") or "The insured"
    policy_number = fields.get("policy_number")
    effective_date = fields.get("effective_date")
    expiration_date = fields.get("expiration_date")
    premium = fields.get("premium")
    coverage_limits = fields.get("coverage_limits") or []
    exclusions = fields.get("exclusions") or []

    opening = f"{insured} is covered by"
    if policy_number:
        opening += f" policy {policy_number}"
    else:
        opening += " this policy"
    if effective_date:
        opening += f", effective {effective_date}"
    if expiration_date:
        opening += f" and expiring {expiration_date}"
    opening += "."
    parts.append(opening)

    if premium:
        interval = premium.get("interval")
        amount = premium.get("amount")
        label = f"{interval.lower()} premium" if interval else "premium"
        parts.append(f"The {label} is {amount}.")

    if coverage_limits:
        parts.append("Key coverage limits include " + "; ".join(coverage_limits) + ".")

    if exclusions:
        exclusion_text = "; ".join(item.rstrip(".") for item in exclusions)
        parts.append("Potential exclusions or limiting provisions include " + exclusion_text + ".")
    else:
        parts.append("No explicit exclusions section was detected in the extracted text.")

    return " ".join(parts)


def _normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text


def _first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    return _clean_value(match.group(1))


def _extract_premium(text: str) -> dict[str, str] | None:
    patterns = [
        r"\bINITIAL\s+(MONTHLY|ANNUAL|QUARTERLY|SEMI-ANNUAL)\s+PREMIUM:\s*(\$[\d,]+(?:\.\d{2})?)",
        r"\b(MONTHLY|ANNUAL|QUARTERLY|SEMI-ANNUAL)\s+PREMIUM:\s*(\$[\d,]+(?:\.\d{2})?)",
        r"\bINITIAL\s+PREMIUM:\s*(\$[\d,]+(?:\.\d{2})?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        if len(match.groups()) == 2:
            return {"interval": match.group(1).upper(), "amount": match.group(2)}
        return {"interval": "INITIAL", "amount": match.group(1)}

    return None


def _extract_coverage_limits(text: str) -> list[str]:
    limits: list[str] = []

    face_amount = _first_match(text, r"\bFACE AMOUNT:\s*(\$[\d,]+(?:\.\d{2})?)")
    if face_amount:
        limits.append(f"Face amount: {face_amount}")

    coverage_age = _first_match(text, r"\bCoverage to Age\s+(\d+)")
    if coverage_age:
        limits.append(f"Coverage to age {coverage_age}")

    death_benefit = _first_sentence_after(text, "Death Benefit")
    if death_benefit:
        limits.append(death_benefit)

    return _dedupe(limits)


def _extract_exclusions(text: str) -> list[str]:
    sections = _extract_exclusion_sections(text)
    return _dedupe([section for section in sections if section])


def _extract_exclusion_sections(text: str) -> list[str]:
    lines = text.splitlines()
    sections: list[str] = []

    for index, line in enumerate(lines):
        heading_info = _exclusion_heading(line)
        if not heading_info:
            continue
        heading, initial_body = heading_info

        body_lines: list[str] = []
        if initial_body:
            body_lines.append(initial_body)

        for body_line in lines[index + 1 :]:
            if _is_section_boundary(body_line):
                break
            cleaned = _clean_exclusion_line(body_line)
            if cleaned:
                body_lines.append(cleaned)

        body = _clean_section_body(body_lines)
        if body:
            sections.append(f"{heading}: {body}")

    return sections


def _exclusion_heading(line: str) -> tuple[str, str] | None:
    cleaned = _clean_exclusion_line(line)
    if not cleaned:
        return None

    standalone_headings = {
        "EXCLUSION",
        "EXCLUSIONS",
        "LIMITATION",
        "LIMITATIONS",
        "TERMINATION",
    }

    upper = cleaned.upper()
    if upper in standalone_headings:
        return cleaned.title(), ""

    match = re.match(r"^([A-Z][A-Za-z\s]+(?:Exclusion|Exclusions|Limitation|Limitations))\s*[–-]\s*(.+)$", cleaned)
    if match:
        heading = _clean_value(match.group(1))
        first_line = _clean_value(match.group(2))
        return heading, first_line

    return None


def _is_section_boundary(line: str) -> bool:
    cleaned = _clean_exclusion_line(line)
    if not cleaned:
        return False

    if cleaned.startswith("--- Page "):
        return True

    if re.match(r"^P\d+\w*\s+Page\s+\d+$", cleaned, flags=re.IGNORECASE):
        return True

    if re.match(r"^[A-Z][A-Za-z\s]+[–-]\s+", cleaned):
        return True

    return bool(re.match(r"^[A-Z][A-Z\s]{2,}$", cleaned))


def _clean_exclusion_line(line: str) -> str:
    cleaned = re.sub(r"\s+", " ", line).strip()
    if not cleaned:
        return ""
    if cleaned.startswith("--- Page "):
        return cleaned
    if re.match(r"^P\d+\w*\s+Page\s+\d+$", cleaned, flags=re.IGNORECASE):
        return ""
    return cleaned.replace("f ollowing", "following").replace("suc h", "such")


def _clean_section_body(lines: list[str]) -> str:
    cleaned: list[str] = []
    current = ""

    for line in lines:
        line = line.strip(" ;")
        if line.startswith("•"):
            if current:
                cleaned.append(current.strip(" ;"))
            current = line
            continue

        if current and not current.endswith((".", ";", ":")):
            current = f"{current} {line}"
        else:
            if current:
                cleaned.append(current.strip(" ;"))
            current = line

    if current:
        cleaned.append(current.strip(" ;"))

    return re.sub(r"\s+", " ", "; ".join(cleaned)).strip(" ;")


def _first_sentence_after(text: str, heading: str) -> str | None:
    match = re.search(rf"\b{re.escape(heading)}\b\s*[–-]\s*([^.\n]+(?:\.|$))", text, flags=re.IGNORECASE)
    if not match:
        return None
    return _clean_value(match.group(1))


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result

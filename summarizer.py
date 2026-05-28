import os
from typing import Any, Protocol


class SummarizationProvider(Protocol):
    name: str

    def summarize(self, fields: dict[str, Any], document_text: str) -> str:
        """Return a readable summary for extracted policy fields."""


class LocalSummarizer:
    name = "local"

    def summarize(self, fields: dict[str, Any], document_text: str) -> str:
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


def get_summarizer() -> SummarizationProvider:
    provider_name = os.getenv("SUMMARIZER_PROVIDER", "local").lower()

    if provider_name == "local":
        return LocalSummarizer()

    raise ValueError(
        f"Unsupported summarizer provider '{provider_name}'. "
        "Only 'local' is implemented in this MVP."
    )

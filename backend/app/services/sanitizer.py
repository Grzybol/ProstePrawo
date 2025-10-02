"""Basic personally identifiable information (PII) detection utilities."""
from __future__ import annotations

from dataclasses import dataclass
import re
from collections import defaultdict


PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "pesel": re.compile(r"\b\d{11}\b"),
    "nip": re.compile(r"\b\d{3}-?\d{3}-?\d{2}-?\d{2}\b"),
    "regon": re.compile(r"\b\d{9}(?:\d{5})?\b"),
    "krs": re.compile(r"\bKRS\s*\d{10}\b", re.IGNORECASE),
    "email": re.compile(r"[\w.%-]+@[\w.-]+\.[A-Za-z]{2,}"),
    "phone": re.compile(r"\b\+?\d{2,3}(?:[ -]?\d{2,3}){3,4}\b"),
    "amount": re.compile(r"\b\d+[\s\u00a0]?(?:zł|PLN)\b", re.IGNORECASE),
}


@dataclass(slots=True)
class SanitizationResult:
    """Hold sanitized text together with the detected PII entities."""

    text: str
    entities: dict[str, list[str]]
    secrets: dict[str, dict[str, str]]


def sanitize_text(text: str) -> SanitizationResult:
    """Replace recognised PII tokens with stable placeholders.

    While the project roadmap includes full Presidio integration, the
    lightweight implementation below provides deterministic replacements that
    allow higher pipeline stages (indexing, inference, tests) to reason about
    anonymised text.  Each PII type is replaced with ``<TYPE_i>`` marker.
    """

    entities: dict[str, list[str]] = defaultdict(list)
    secrets: dict[str, dict[str, str]] = defaultdict(dict)
    sanitized = text
    for entity, pattern in PII_PATTERNS.items():
        counter = 0
        matches = list(pattern.finditer(sanitized))
        for match in matches:
            counter += 1
            placeholder = f"<{entity.upper()}_{counter}>"
            value = match.group(0)
            entities[entity].append(placeholder)
            secrets[entity][placeholder] = value
            sanitized = sanitized.replace(value, placeholder, 1)
    return SanitizationResult(text=sanitized, entities=dict(entities), secrets=dict(secrets))

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class UICommand:
    type: str
    priority: str
    headline: str
    detail: str
    target: str
    related_topic: str | None = None


def analyze_rules(
    transcript_chunks: Sequence[dict[str, Any]],
    session_context: dict[str, Any],
    audience_profile: dict[str, Any],
) -> UICommand:
    """Return the non-LLM fallback command.

    The product logic is intentionally LLM-led. This fallback does not try to
    infer jargon, fatigue, or FOMO with keyword rules; it only keeps the UI in a
    valid neutral state when the model is unavailable.
    """
    return neutral_command()


def neutral_command() -> UICommand:
    return UICommand(
        type="neutral",
        priority="low",
        headline="Keep listening",
        detail="No model analysis is available for this time window.",
        target="speaker",
        related_topic=None,
    )

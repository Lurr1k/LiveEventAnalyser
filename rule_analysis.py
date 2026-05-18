from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class UICommand:
    type: str
    priority: str
    headline: str
    detail: str
    target: str
    related_topic: str | None = None


JARGON_TERMS = {
    "agentic",
    "api",
    "backpropagation",
    "benchmark",
    "cap table",
    "compute",
    "diarization",
    "embedding",
    "eval",
    "fine-tuning",
    "inference",
    "latent",
    "llm",
    "moat",
    "multimodal",
    "rag",
    "runway",
    "token",
    "transformer",
    "valuation",
    "vector database",
}

EXPLANATION_MARKERS = {
    "basically",
    "in plain english",
    "in simple terms",
    "means",
    "refers to",
    "stands for",
    "that is",
}

INSIGHT_MARKERS = {
    "key takeaway",
    "what matters",
    "the lesson",
    "you should",
    "founders should",
    "investors should",
    "the opportunity",
    "the mistake",
    "remember that",
    "the important part",
}

TOPIC_STOP_WORDS = {
    "about",
    "actually",
    "again",
    "because",
    "been",
    "being",
    "from",
    "have",
    "into",
    "just",
    "like",
    "more",
    "really",
    "that",
    "their",
    "there",
    "this",
    "what",
    "when",
    "with",
    "would",
    "your",
}

INTENT_KEYWORDS = {
    "ai for business": {"ai", "automation", "business", "customer", "enterprise", "workflow"},
    "creative / marketing tech": {"brand", "content", "creative", "growth", "marketing"},
    "dev tools / infrastructure": {"api", "developer", "infrastructure", "platform", "tooling"},
    "fintech / payments": {"banking", "fintech", "payments", "revenue", "risk"},
    "open track (no theme)": set(),
}


def analyze_rules(
    transcript_chunks: Sequence[dict[str, Any]],
    session_context: dict[str, Any],
    audience_profile: dict[str, Any],
) -> UICommand:
    chunks = [_normalize_chunk(chunk) for chunk in transcript_chunks if _chunk_text(chunk)]
    if not chunks:
        return neutral_command()

    coaching = _audience_aware_coaching(chunks, audience_profile)
    if coaching:
        return coaching

    fatigue = _topic_fatigue(chunks, session_context)
    if fatigue:
        return fatigue

    fomo = _fomo_prompt(chunks, audience_profile)
    if fomo:
        return fomo

    return neutral_command()


def neutral_command() -> UICommand:
    return UICommand(
        type="neutral",
        priority="low",
        headline="Keep listening",
        detail="No immediate speaker intervention is needed.",
        target="speaker",
        related_topic=None,
    )


def _audience_aware_coaching(
    chunks: Sequence[dict[str, str]], audience_profile: dict[str, Any]
) -> UICommand | None:
    beginner_ratio = float(audience_profile.get("beginner_ratio") or 0.0)
    beginner_count = int(
        audience_profile.get("ai_experience_distribution", {}).get("Beginner", 0) or 0
    )
    attendee_count = int(audience_profile.get("attendee_count") or 0)
    beginner_heavy = beginner_ratio >= 0.35 or (
        attendee_count > 0 and beginner_count / attendee_count >= 0.35
    )
    if not beginner_heavy:
        return None

    text = _window_text(chunks[-8:])
    matched_jargon = sorted(term for term in JARGON_TERMS if _contains_term(text, term))
    if not matched_jargon:
        return None

    explained = any(marker in text for marker in EXPLANATION_MARKERS)
    if explained:
        return None

    topic = matched_jargon[0]
    return UICommand(
        type="coaching",
        priority="high",
        headline="Define your terms",
        detail=f"Beginner-heavy audience may need context for {topic}.",
        target="speaker",
        related_topic=topic,
    )


def _topic_fatigue(
    chunks: Sequence[dict[str, str]], session_context: dict[str, Any]
) -> UICommand | None:
    if len(chunks) < 10:
        return None

    terms_by_chunk = [_topic_terms(chunk["text"]) for chunk in chunks[-16:]]
    term_counts = Counter(term for terms in terms_by_chunk for term in terms)
    if not term_counts:
        return None

    topic, _ = term_counts.most_common(1)[0]
    chunk_hits = sum(1 for terms in terms_by_chunk if topic in terms)
    repeated_enough = chunk_hits >= 7 or chunk_hits / len(terms_by_chunk) >= 0.55
    if not repeated_enough:
        return None

    next_item = session_context.get("next_agenda_item")
    if next_item:
        headline = "Move to next topic"
        detail = f"{topic} is repeating; transition toward {next_item}."
    else:
        headline = "Pivot the topic"
        detail = f"{topic} is repeating across the recent transcript."

    return UICommand(
        type="fatigue",
        priority="medium",
        headline=headline,
        detail=detail,
        target="moderator",
        related_topic=topic,
    )


def _fomo_prompt(
    chunks: Sequence[dict[str, str]], audience_profile: dict[str, Any]
) -> UICommand | None:
    latest_text = chunks[-1]["text"].lower()
    has_marker = any(marker in latest_text for marker in INSIGHT_MARKERS)
    has_actionable_shape = bool(
        re.search(r"\b(should|must|need to|key|lesson|mistake|opportunity)\b", latest_text)
    )
    if not has_marker and not has_actionable_shape:
        return None

    topic = _match_intent_topic(latest_text, audience_profile.get("top_intents", []))
    detail_topic = f" for {topic}" if topic else ""
    return UICommand(
        type="fomo",
        priority="medium",
        headline="Share this insight",
        detail=f"Current transcript has a concise takeaway worth surfacing{detail_topic}.",
        target="attendee",
        related_topic=topic,
    )


def _normalize_chunk(chunk: dict[str, Any]) -> dict[str, str]:
    return {
        "timestamp": str(chunk.get("timestamp") or "00:00:00"),
        "speaker": str(chunk.get("speaker") or "Speaker"),
        "text": str(chunk.get("text") or "").strip(),
    }


def _chunk_text(chunk: dict[str, Any]) -> str:
    return str(chunk.get("text") or "").strip()


def _window_text(chunks: Sequence[dict[str, str]]) -> str:
    return " ".join(chunk["text"] for chunk in chunks).lower()


def _contains_term(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9-]){re.escape(term)}(?![a-z0-9-])", text))


def _topic_terms(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z0-9-]{3,}", text.lower())
    return [word for word in words if word not in TOPIC_STOP_WORDS]


def _match_intent_topic(text: str, intents: Iterable[str]) -> str | None:
    text_words = set(re.findall(r"[a-z][a-z0-9]+", text.lower()))
    for intent in intents:
        normalized_intent = str(intent).lower()
        keywords = INTENT_KEYWORDS.get(normalized_intent)
        if keywords is None:
            keywords = set(re.findall(r"[a-z][a-z0-9]+", normalized_intent))
        if keywords and text_words.intersection(keywords):
            return str(intent)
    return None

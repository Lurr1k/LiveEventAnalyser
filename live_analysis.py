from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

from audience import build_audience_profile as build_session_audience_profile
from data_loading import (
    load_attendees as load_attendees_dataframe,
    load_sessions as load_session_metadata,
    normalize_transcript_chunk as normalize_raw_transcript_chunk,
)
from rule_analysis import UICommand, analyze_rules


DEFAULT_MODEL = "gpt-5.4-mini"

SYSTEM_PROMPT = """You are the live analysis engine for a real-time speaker HUD.

Analyze only the supplied rolling transcript, session metadata, agenda, and audience profile.
Do not invent facts, names, audience traits, or claims that are not present in the input.

Return exactly one UI command as JSON. The command must help a speaker or moderator act now.
Use "neutral" when no useful action is needed.

Rules:
- headline must be 3-7 words.
- detail must be one short sentence.
- priority should be high only for urgent clarity, fatigue, or strong FOMO moments.
- coaching means audience-aware clarity or engagement advice.
- fatigue means the same topic is lingering or repeating.
- fomo means a concise shareable insight for absent or adjacent-interest attendees.
- neutral means keep listening.
"""

UI_COMMAND_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "name": "ui_command",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "type": {"type": "string", "enum": ["coaching", "fatigue", "fomo", "neutral"]},
            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            "headline": {"type": "string", "minLength": 1, "maxLength": 80},
            "detail": {"type": "string", "minLength": 1, "maxLength": 220},
            "target": {"type": "string", "enum": ["speaker", "moderator", "attendee"]},
            "related_topic": {"type": ["string", "null"], "maxLength": 80},
        },
        "required": ["type", "priority", "headline", "detail", "target", "related_topic"],
    },
}

@dataclass(frozen=True)
class TranscriptChunk:
    timestamp: str
    speaker: str
    text: str


@dataclass
class RollingTranscript:
    max_chunks: int = 24
    chunks: deque[TranscriptChunk] = field(default_factory=deque)

    def append(self, chunk: TranscriptChunk) -> None:
        self.chunks.append(chunk)
        while len(self.chunks) > self.max_chunks:
            self.chunks.popleft()

    def text(self) -> str:
        return "\n".join(
            f"[{chunk.timestamp}] {chunk.speaker}: {chunk.text}" for chunk in self.chunks
        )


def load_attendees(path: str | Path):
    return load_attendees_dataframe(path)


def load_sessions(path_or_dir: str | Path) -> list[dict[str, Any]]:
    return load_session_metadata(path_or_dir)


def build_audience_profile(
    attendees: Iterable[dict[str, str]], session_id: str, room: str | None = None
) -> dict[str, Any]:
    return build_session_audience_profile(attendees, session_id, room)


def normalize_transcript_chunk(raw_chunk: dict[str, Any] | str) -> TranscriptChunk:
    normalized = normalize_raw_transcript_chunk(raw_chunk)
    return TranscriptChunk(
        timestamp=normalized["timestamp"],
        speaker=normalized["speaker"],
        text=normalized["text"],
    )


def rule_based_analyze(
    rolling: RollingTranscript,
    session_context: dict[str, Any],
    audience_profile: dict[str, Any],
) -> UICommand:
    return analyze_rules(
        [asdict(chunk) for chunk in rolling.chunks],
        session_context,
        audience_profile,
    )


async def analyze_with_gpt54_mini(
    rolling: RollingTranscript,
    session_context: dict[str, Any],
    audience_profile: dict[str, Any],
    *,
    client: Any | None = None,
    model: str = DEFAULT_MODEL,
    timeout_seconds: float = 8.0,
    use_llm: bool = True,
) -> UICommand:
    fallback = rule_based_analyze(rolling, session_context, audience_profile)
    if not rolling.chunks or not use_llm:
        return fallback

    if client is None:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI()
        except ImportError:
            return fallback
        except Exception:
            return fallback

    payload = {
        "session_context": session_context,
        "audience_profile": audience_profile,
        "rolling_transcript": rolling.text(),
        "fallback_signal": asdict(fallback),
    }

    try:
        response = await asyncio.wait_for(
            client.responses.create(
                model=model,
                instructions=SYSTEM_PROMPT,
                input=json.dumps(payload, ensure_ascii=False),
                text={"format": UI_COMMAND_SCHEMA},
                temperature=0.2,
            ),
            timeout=timeout_seconds,
        )
        data = json.loads(response.output_text)
        return _coerce_ui_command(data, fallback)
    except Exception:
        return fallback


async def analyze_live_text_flow(
    live_chunks: AsyncIterator[dict[str, Any] | str],
    session_context: dict[str, Any],
    audience_profile: dict[str, Any],
    *,
    client: Any | None = None,
    model: str = DEFAULT_MODEL,
    max_window_chunks: int = 24,
    analysis_interval_seconds: float = 5.0,
    min_analysis_interval_seconds: float | None = None,
    use_llm: bool = True,
) -> AsyncIterator[UICommand]:
    rolling = RollingTranscript(max_chunks=max_window_chunks)
    chunk_queue: asyncio.Queue[dict[str, Any] | str | None] = asyncio.Queue()
    interval = min_analysis_interval_seconds or analysis_interval_seconds
    next_analysis_at = time.monotonic() + interval
    received_count = 0
    analyzed_count = 0
    producer_errors: list[BaseException] = []

    async def collect_chunks() -> None:
        try:
            async for raw_chunk in live_chunks:
                await chunk_queue.put(raw_chunk)
        except BaseException as exc:
            producer_errors.append(exc)
        finally:
            await chunk_queue.put(None)

    producer = asyncio.create_task(collect_chunks())
    stream_open = True

    try:
        while stream_open or not chunk_queue.empty():
            timeout = max(0.0, next_analysis_at - time.monotonic())
            try:
                raw_chunk = await asyncio.wait_for(chunk_queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                if rolling.chunks and received_count > analyzed_count:
                    yield await analyze_with_gpt54_mini(
                        rolling,
                        session_context,
                        audience_profile,
                        client=client,
                        model=model,
                        use_llm=use_llm,
                    )
                    analyzed_count = received_count
                next_analysis_at = time.monotonic() + interval
                continue

            if raw_chunk is None:
                stream_open = False
                continue

            chunk = normalize_transcript_chunk(raw_chunk)
            if not chunk.text:
                continue

            rolling.append(chunk)
            received_count += 1

        if rolling.chunks and received_count > analyzed_count:
            yield await analyze_with_gpt54_mini(
                rolling,
                session_context,
                audience_profile,
                client=client,
                model=model,
                use_llm=use_llm,
            )
        if producer_errors:
            raise producer_errors[0]
    finally:
        if not producer.done():
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer


async def stream_transcript_file(
    path: str | Path, *, delay_seconds: float = 0.2
) -> AsyncIterator[str]:
    """Demo source that replays the provided session transcript markdown line by line."""
    transcript_started = False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## Transcript"):
            transcript_started = True
            continue
        if not transcript_started or not line.startswith("["):
            continue
        yield line
        await asyncio.sleep(delay_seconds)


def _coerce_ui_command(data: dict[str, Any], fallback: UICommand) -> UICommand:
    try:
        command = UICommand(
            type=data["type"],
            priority=data["priority"],
            headline=data["headline"],
            detail=data["detail"],
            target=data["target"],
            related_topic=data.get("related_topic"),
        )
    except KeyError:
        return fallback

    if command.type not in {"coaching", "fatigue", "fomo", "neutral"}:
        return fallback
    if command.priority not in {"low", "medium", "high"}:
        return fallback
    if command.target not in {"speaker", "moderator", "attendee"}:
        return fallback
    return command

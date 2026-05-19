from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

from .audience import build_audience_profile as build_session_audience_profile
from .data_loading import (
    load_attendees as load_attendees_dataframe,
    load_sessions as load_session_metadata,
    normalize_transcript_chunk as normalize_raw_transcript_chunk,
)
from .rule_analysis import UICommand, analyze_rules


DEFAULT_MODEL = "gpt-5.4-mini"

SYSTEM_PROMPT = """You are the live analysis engine for a real-time speaker HUD.

Analyze only the supplied rolling transcript, transcript window metadata, session metadata, agenda, audience profile, and FOMO context.
Do not invent facts, names, audience traits, or claims that are not present in the input.

Return exactly one UI command as JSON. The command must help a speaker or moderator act now.
Use "neutral" when no useful action is needed.

Rules:
- headline must be 3-7 words.
- detail must be one short sentence.
- priority should be high only for urgent clarity, fatigue, or strong FOMO moments.
- coaching means audience-aware clarity or engagement advice.
- fatigue means the current discussion appears to be lingering, looping, or blocking agenda progress based on the transcript window and agenda context.
- for fatigue, prefer next_agenda_item when it exists.
- fomo means a concise shareable insight for absent or adjacent-interest attendees based on the current transcript window and audience intent context.
- for fomo, write detail as a short notification-style snippet grounded in the transcript.
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
            "related_topic": {"type": ["string", "null"], "maxLength": 80},
        },
        "required": ["type", "priority", "headline", "detail", "related_topic"],
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

    def as_dicts(self) -> list[dict[str, str]]:
        return [asdict(chunk) for chunk in self.chunks]

    def window_metadata(self) -> dict[str, Any]:
        timestamps = [chunk.timestamp for chunk in self.chunks]
        oldest_timestamp = timestamps[0] if timestamps else None
        newest_timestamp = timestamps[-1] if timestamps else None
        duration_seconds = _timestamp_delta_seconds(oldest_timestamp, newest_timestamp)
        return {
            "chunk_count": len(self.chunks),
            "max_window_chunks": self.max_chunks,
            "oldest_timestamp": oldest_timestamp,
            "newest_timestamp": newest_timestamp,
            "transcript_duration_seconds": duration_seconds,
        }


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
        rolling.as_dicts(),
        session_context,
        audience_profile,
    )


def build_llm_payload(
    rolling: RollingTranscript,
    session_context: dict[str, Any],
    audience_profile: dict[str, Any],
    fallback: UICommand,
    *,
    analysis_interval_seconds: float = 5.0,
) -> dict[str, Any]:
    agenda_context = {
        "agenda": session_context.get("agenda", []),
        "current_agenda_item": session_context.get("current_agenda_item"),
        "next_agenda_item": session_context.get("next_agenda_item"),
    }
    transcript_window = {
        "chunks": rolling.as_dicts(),
        "text": rolling.text(),
        "metadata": rolling.window_metadata(),
    }
    fomo_context = {
        "top_intents": audience_profile.get("top_intents", []),
        "intent_distribution": audience_profile.get("intent_distribution", {}),
        "attendee_count": audience_profile.get("attendee_count", 0),
        "current_window_text": transcript_window["text"],
        "snippet_requirements": {
            "source": "current transcript window only",
            "style": "short notification-style summary",
            "do_not_invent_names": True,
            "intended_audience": "attendees with adjacent interests",
        },
    }
    return {
        "session_context": session_context,
        "agenda_context": agenda_context,
        "audience_profile": audience_profile,
        "fomo_context": fomo_context,
        "transcript_window": transcript_window,
        "analysis_context": {
            "analysis_interval_seconds": analysis_interval_seconds,
            "fatigue_decision_owner": "model",
            "fomo_decision_owner": "model",
            "backend_keyword_detection": False,
        },
        "fallback_signal": asdict(fallback),
    }


async def analyze_with_gpt54_mini(
    rolling: RollingTranscript,
    session_context: dict[str, Any],
    audience_profile: dict[str, Any],
    *,
    client: Any | None = None,
    model: str = DEFAULT_MODEL,
    timeout_seconds: float = 8.0,
    use_llm: bool = True,
    analysis_interval_seconds: float = 5.0,
    on_error: Any | None = None,
    on_success: Any | None = None,
) -> UICommand:
    fallback = rule_based_analyze(rolling, session_context, audience_profile)
    if not rolling.chunks or not use_llm:
        return fallback

    if client is None:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI()
        except ImportError:
            _notify_analysis_error(on_error, "openai package is not installed")
            return fallback
        except Exception as exc:
            _notify_analysis_error(on_error, str(exc))
            return fallback

    payload = build_llm_payload(
        rolling,
        session_context,
        audience_profile,
        fallback,
        analysis_interval_seconds=analysis_interval_seconds,
    )

    try:
        response = await asyncio.wait_for(
            client.responses.create(
                model=os.getenv("OPENAI_MODEL", model),
                instructions=SYSTEM_PROMPT,
                input=json.dumps(payload, ensure_ascii=False),
                text={"format": UI_COMMAND_SCHEMA},
                temperature=0.2,
            ),
            timeout=timeout_seconds,
        )
        if not response.output_text:
            _notify_analysis_error(on_error, "OpenAI returned an empty output_text.")
            return fallback
        data = json.loads(response.output_text)
        _notify_analysis_success(on_success)
        return _coerce_ui_command(data, fallback)
    except Exception as exc:
        _notify_analysis_error(on_error, str(exc))
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
    on_analysis_error: Any | None = None,
    on_analysis_success: Any | None = None,
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
                        analysis_interval_seconds=interval,
                        on_error=on_analysis_error,
                        on_success=on_analysis_success,
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
                analysis_interval_seconds=interval,
                on_error=on_analysis_error,
                on_success=on_analysis_success,
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
            related_topic=data.get("related_topic"),
        )
    except KeyError:
        return fallback

    if command.type not in {"coaching", "fatigue", "fomo", "neutral"}:
        return fallback
    if command.priority not in {"low", "medium", "high"}:
        return fallback
    return command


def _timestamp_delta_seconds(start: str | None, end: str | None) -> int | None:
    start_seconds = _parse_timestamp_seconds(start)
    end_seconds = _parse_timestamp_seconds(end)
    if start_seconds is None or end_seconds is None:
        return None
    return max(0, end_seconds - start_seconds)


def _parse_timestamp_seconds(timestamp: str | None) -> int | None:
    if not timestamp:
        return None
    parts = str(timestamp).split(":")
    if len(parts) != 3:
        return None
    try:
        hours, minutes, seconds = (int(float(part)) for part in parts)
    except ValueError:
        return None
    return hours * 3600 + minutes * 60 + seconds


def _notify_analysis_error(callback: Any | None, message: str) -> None:
    if callback is None:
        return
    callback(message)


def _notify_analysis_success(callback: Any | None) -> None:
    if callback is None:
        return
    callback()

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from .data_loading import normalize_transcript_chunk


ConnectionStatus = Literal["disconnected", "waiting", "receiving"]

@dataclass(frozen=True)
class IngestedTranscriptChunk:
    timestamp: str
    speaker: str
    text: str
    received_at: float
    sequence: int

    def as_transcript_chunk(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "speaker": self.speaker,
            "text": self.text,
        }


@dataclass(frozen=True)
class TopicState:
    current_topic: str | None = None
    topic_chunk_count: int = 0
    topic_elapsed_seconds: float = 0.0


@dataclass
class TranscriptIngestionState:
    max_window_chunks: int = 24
    queue_maxsize: int = 256
    status: ConnectionStatus = "disconnected"
    last_error: str | None = None
    _queue: asyncio.Queue[IngestedTranscriptChunk | None] = field(init=False, repr=False)
    _rolling_window: deque[IngestedTranscriptChunk] = field(default_factory=deque, repr=False)
    _sequence: int = field(default=0, init=False, repr=False)
    _first_chunk_received_at: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._queue = asyncio.Queue(maxsize=self.queue_maxsize)

    def connect(self) -> None:
        self.status = "waiting"
        self.last_error = None

    def disconnect(self) -> None:
        self.status = "disconnected"
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._queue.put_nowait(None)

    async def push(self, raw_chunk: dict[str, Any] | str) -> IngestedTranscriptChunk | None:
        if self.status == "disconnected":
            self.connect()

        normalized = normalize_transcript_chunk(raw_chunk)
        if not normalized["text"]:
            return None

        self._sequence += 1
        chunk = IngestedTranscriptChunk(
            timestamp=normalized["timestamp"],
            speaker=normalized["speaker"],
            text=normalized["text"],
            received_at=time.monotonic(),
            sequence=self._sequence,
        )
        self._append_to_window(chunk)
        await self._queue.put(chunk)
        self.status = "receiving"
        return chunk

    async def chunks(self) -> AsyncIterator[dict[str, str]]:
        self.connect()
        while self.status != "disconnected":
            try:
                chunk = await self._queue.get()
            except asyncio.CancelledError:
                self.disconnect()
                raise
            if chunk is None:
                break
            yield chunk.as_transcript_chunk()

    def latest_chunk(self) -> dict[str, str] | None:
        if not self._rolling_window:
            return None
        return self._rolling_window[-1].as_transcript_chunk()

    def rolling_window(self) -> list[dict[str, str]]:
        return [chunk.as_transcript_chunk() for chunk in self._rolling_window]

    def topic_state(self) -> TopicState:
        if self._first_chunk_received_at is None:
            elapsed = 0.0
        else:
            elapsed = max(0.0, time.monotonic() - self._first_chunk_received_at)
        return TopicState(
            current_topic=None,
            topic_chunk_count=len(self._rolling_window),
            topic_elapsed_seconds=elapsed,
        )

    def snapshot(self) -> dict[str, Any]:
        topic = self.topic_state()
        return {
            "status": self.status,
            "last_error": self.last_error,
            "latest_chunk": self.latest_chunk(),
            "rolling_window": self.rolling_window(),
            "topic": {
                "current_topic": topic.current_topic,
                "topic_chunk_count": topic.topic_chunk_count,
                "topic_elapsed_seconds": topic.topic_elapsed_seconds,
            },
        }

    def _append_to_window(self, chunk: IngestedTranscriptChunk) -> None:
        self._rolling_window.append(chunk)
        if self._first_chunk_received_at is None:
            self._first_chunk_received_at = chunk.received_at
        while len(self._rolling_window) > self.max_window_chunks:
            self._rolling_window.popleft()


async def replay_transcript_file(
    path: str | Path,
    ingestion_state: TranscriptIngestionState,
    *,
    delay_seconds: float = 0.2,
) -> None:
    """Demo connector that pushes transcript markdown lines into ingestion state."""
    ingestion_state.connect()
    try:
        async for raw_chunk in iter_transcript_file(path, delay_seconds=delay_seconds):
            if ingestion_state.status == "disconnected":
                break
            await ingestion_state.push(raw_chunk)
    except Exception as exc:
        ingestion_state.status = "disconnected"
        ingestion_state.last_error = str(exc)
        raise
    finally:
        ingestion_state.disconnect()


async def iter_transcript_file(
    path: str | Path, *, delay_seconds: float = 0.2
) -> AsyncIterator[str]:
    transcript_started = False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## Transcript"):
            transcript_started = True
            continue
        if not transcript_started or not line.startswith("["):
            continue
        yield line
        await asyncio.sleep(delay_seconds)


async def iter_manual_chunks(
    queue: asyncio.Queue[dict[str, Any] | str],
) -> AsyncIterator[dict[str, Any] | str]:
    while True:
        yield await queue.get()



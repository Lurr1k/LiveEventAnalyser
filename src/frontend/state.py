from __future__ import annotations

import asyncio
import queue
import threading
import time
from typing import Any, Literal

from backend.elevenlabs_live import first_audio_chunk, stream_elevenlabs_audio_chunks
from backend.live_analysis import analyze_live_text_flow
from backend.live_ingestion import TranscriptIngestionState, iter_transcript_file


TranscriptSource = Literal["browser_mic", "elevenlabs_live", "demo_markdown"]


class SessionStateManager:
    """
    Runs the async backend pipeline in a background thread and exposes a
    Streamlit-friendly state snapshot.
    """

    def __init__(self):
        self.thread = None
        self.loop = None
        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()

        self.ingestion_state: TranscriptIngestionState | None = None
        self.transcript_chunks: list[dict[str, str]] = []
        self.latest_command = None
        self.is_running = False
        self.error = None
        self.source: TranscriptSource = "browser_mic"
        self.ingestion_status = "disconnected"
        self.ingestion_error = None
        self.analysis_status = "idle"
        self.analysis_error = None
        self.last_model_response_at: float | None = None
        self.audio_chunk_count = 0
        self.last_audio_chunk_at: float | None = None
        self.elevenlabs_connected = False
        self.last_elevenlabs_event_type: str | None = None
        self.last_elevenlabs_event_at: float | None = None
        self.elevenlabs_close_error: str | None = None
        self.elevenlabs_connection_attempts = 0
        self.audio_queue: queue.Queue[bytes | None] | None = None

    def start(
        self,
        session: dict[str, Any],
        profile: dict[str, Any],
        *,
        source: TranscriptSource = "browser_mic",
    ):
        self.stop()
        self.stop_event.clear()

        self.ingestion_state = TranscriptIngestionState(max_window_chunks=50)
        self.transcript_chunks = []
        self.latest_command = None
        self.is_running = True
        self.error = None
        self.source = source
        self.ingestion_status = "waiting"
        self.ingestion_error = None
        self.analysis_status = "waiting"
        self.analysis_error = None
        self.last_model_response_at = None
        self.audio_chunk_count = 0
        self.last_audio_chunk_at = None
        self.elevenlabs_connected = False
        self.last_elevenlabs_event_type = None
        self.last_elevenlabs_event_at = None
        self.elevenlabs_close_error = None
        self.elevenlabs_connection_attempts = 0
        self.audio_queue = queue.Queue(maxsize=128)

        self.thread = threading.Thread(
            target=self._run_async_loop,
            args=(session, profile, source),
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.audio_queue:
            self._put_audio_sentinel()
        if self.ingestion_state:
            self.ingestion_state.disconnect()
        if self.thread:
            self.thread.join(timeout=2.0)
        with self.state_lock:
            self.is_running = False
            self.ingestion_status = "disconnected"
            self.elevenlabs_connected = False

    def get_state(self):
        with self.state_lock:
            return {
                "transcript_chunks": list(self.transcript_chunks),
                "latest_command": self.latest_command,
                "is_running": self.is_running,
                "error": self.error,
                "source": self.source,
                "ingestion_status": self.ingestion_status,
                "ingestion_error": self.ingestion_error,
                "analysis_status": self.analysis_status,
                "analysis_error": self.analysis_error,
                "last_model_response_at": self.last_model_response_at,
                "audio_chunk_count": self.audio_chunk_count,
                "last_audio_chunk_at": self.last_audio_chunk_at,
                "elevenlabs_connected": self.elevenlabs_connected,
                "last_elevenlabs_event_type": self.last_elevenlabs_event_type,
                "last_elevenlabs_event_at": self.last_elevenlabs_event_at,
                "elevenlabs_close_error": self.elevenlabs_close_error,
                "elevenlabs_connection_attempts": self.elevenlabs_connection_attempts,
            }

    def submit_audio_chunk(self, chunk: bytes) -> None:
        if not chunk or self.stop_event.is_set():
            return
        audio_queue = self.audio_queue
        if audio_queue is None:
            return
        if audio_queue.full():
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                pass
        try:
            audio_queue.put_nowait(chunk)
        except queue.Full:
            return
        with self.state_lock:
            self.audio_chunk_count += 1
            self.last_audio_chunk_at = time.time()

    def _run_async_loop(
        self,
        session: dict[str, Any],
        profile: dict[str, Any],
        source: TranscriptSource,
    ):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._async_pipeline(session, profile, source))
        except Exception as exc:
            with self.state_lock:
                self.error = str(exc)
                self.is_running = False
        finally:
            self.loop.close()

    async def _async_pipeline(
        self,
        session: dict[str, Any],
        profile: dict[str, Any],
        source: TranscriptSource,
    ):
        ingestion_state = self.ingestion_state
        if ingestion_state is None:
            raise RuntimeError("Transcript ingestion state was not initialized.")

        producer = asyncio.create_task(self._produce_transcripts(source, session, ingestion_state))
        monitor = asyncio.create_task(self._publish_ingestion_state(ingestion_state))

        try:
            async for command in analyze_live_text_flow(
                ingestion_state.chunks(),
                session,
                profile,
                use_llm=True,
                analysis_interval_seconds=2.0,
                on_analysis_error=self._set_analysis_error,
                on_analysis_success=self._set_analysis_success,
            ):
                if self.stop_event.is_set():
                    break
                with self.state_lock:
                    self.latest_command = command
                    if command.type == "neutral" and self.analysis_status == "waiting":
                        self.analysis_status = "fallback"
        finally:
            producer.cancel()
            monitor.cancel()
            await asyncio.gather(producer, monitor, return_exceptions=True)
            ingestion_state.disconnect()
            self._copy_ingestion_snapshot(ingestion_state)
            with self.state_lock:
                self.is_running = False

    async def _produce_transcripts(
        self,
        source: TranscriptSource,
        session: dict[str, Any],
        ingestion_state: TranscriptIngestionState,
    ) -> None:
        if source == "elevenlabs_live":
            source = "browser_mic"
        if source == "demo_markdown":
            ingestion_state.connect()
            try:
                async for raw_chunk in iter_transcript_file(session["path"], delay_seconds=2.0):
                    if self.stop_event.is_set():
                        break
                    await ingestion_state.push(raw_chunk)
            finally:
                ingestion_state.disconnect()
            return

        while not self.stop_event.is_set():
            with self.state_lock:
                self.ingestion_status = "waiting"
                self.ingestion_error = "Waiting for browser audio before connecting to ElevenLabs."

            audio_chunks = self._browser_audio_chunks()
            first_chunk, replayable_chunks = await first_audio_chunk(
                audio_chunks,
                timeout_seconds=1.0,
            )
            if first_chunk is None:
                continue

            with self.state_lock:
                self.elevenlabs_connection_attempts += 1
                self.ingestion_error = None

            try:
                await stream_elevenlabs_audio_chunks(
                    replayable_chunks,
                    ingestion_state,
                    should_stop=self.stop_event.is_set,
                    on_event=self._set_elevenlabs_event,
                    on_close=self._set_elevenlabs_close,
                    on_error_event=self._set_elevenlabs_close,
                    manage_ingestion_lifecycle=False,
                )
            except Exception as exc:
                if self.stop_event.is_set():
                    break
                self._set_elevenlabs_close(str(exc))
                await asyncio.sleep(1.0)

    async def _publish_ingestion_state(self, ingestion_state: TranscriptIngestionState) -> None:
        while not self.stop_event.is_set():
            self._copy_ingestion_snapshot(ingestion_state)
            await asyncio.sleep(0.2)

    def _copy_ingestion_snapshot(self, ingestion_state: TranscriptIngestionState) -> None:
        snapshot = ingestion_state.snapshot()
        with self.state_lock:
            self.transcript_chunks = snapshot["rolling_window"]
            self.ingestion_status = snapshot["status"]
            self.ingestion_error = snapshot["last_error"]

    async def _browser_audio_chunks(self):
        audio_queue = self.audio_queue
        if audio_queue is None:
            raise RuntimeError("Browser audio queue was not initialized.")
        while not self.stop_event.is_set():
            try:
                chunk = await asyncio.to_thread(audio_queue.get, True, 0.2)
            except queue.Empty:
                continue
            if chunk is None:
                break
            yield chunk

    def _put_audio_sentinel(self) -> None:
        audio_queue = self.audio_queue
        if audio_queue is None:
            return
        try:
            audio_queue.put_nowait(None)
        except queue.Full:
            try:
                audio_queue.get_nowait()
            except queue.Empty:
                pass
            audio_queue.put_nowait(None)

    def _set_analysis_error(self, message: str) -> None:
        with self.state_lock:
            self.analysis_status = "fallback"
            self.analysis_error = message

    def _set_analysis_success(self) -> None:
        with self.state_lock:
            self.analysis_status = "model"
            self.analysis_error = None
            self.last_model_response_at = time.time()

    def _set_elevenlabs_event(self, message_type: str) -> None:
        with self.state_lock:
            self.last_elevenlabs_event_type = message_type
            self.last_elevenlabs_event_at = time.time()
            self.elevenlabs_close_error = None
            if message_type == "session_started":
                self.elevenlabs_connected = True

    def _set_elevenlabs_close(self, message: str) -> None:
        with self.state_lock:
            self.elevenlabs_close_error = message
            self.elevenlabs_connected = False

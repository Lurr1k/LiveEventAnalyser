from __future__ import annotations

import asyncio
import threading
from typing import Any, Literal

from backend.elevenlabs_live import stream_elevenlabs_microphone
from backend.live_analysis import analyze_live_text_flow
from backend.live_ingestion import TranscriptIngestionState, iter_transcript_file


TranscriptSource = Literal["elevenlabs_live", "demo_markdown"]


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
        self.source: TranscriptSource = "elevenlabs_live"
        self.ingestion_status = "disconnected"
        self.ingestion_error = None

    def start(
        self,
        session: dict[str, Any],
        profile: dict[str, Any],
        *,
        source: TranscriptSource = "elevenlabs_live",
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

        self.thread = threading.Thread(
            target=self._run_async_loop,
            args=(session, profile, source),
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.ingestion_state:
            self.ingestion_state.disconnect()
        if self.thread:
            self.thread.join(timeout=2.0)
        with self.state_lock:
            self.is_running = False
            self.ingestion_status = "disconnected"

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
            }

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
            ):
                if self.stop_event.is_set():
                    break
                with self.state_lock:
                    self.latest_command = command
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

        await stream_elevenlabs_microphone(
            ingestion_state,
            should_stop=self.stop_event.is_set,
        )

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

import asyncio
import threading
import time
from typing import Any

from backend.live_analysis import analyze_live_text_flow
from backend.live_ingestion import iter_transcript_file

class SessionStateManager:
    """
    Manages a background thread running the async backend pipeline
    and updating shared state for Streamlit.
    """
    def __init__(self):
        self.thread = None
        self.loop = None
        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()
        
        # Shared state
        self.transcript_chunks = []
        self.latest_command = None
        self.is_running = False
        self.error = None

    def start(self, session: dict[str, Any], profile: dict[str, Any]):
        self.stop()
        self.stop_event.clear()
        
        self.transcript_chunks = []
        self.latest_command = None
        self.is_running = True
        self.error = None

        self.thread = threading.Thread(
            target=self._run_async_loop,
            args=(session, profile),
            daemon=True
        )
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def get_state(self):
        with self.state_lock:
            return {
                "transcript_chunks": list(self.transcript_chunks),
                "latest_command": self.latest_command,
                "is_running": self.is_running,
                "error": self.error,
            }

    def _run_async_loop(self, session: dict[str, Any], profile: dict[str, Any]):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._async_pipeline(session, profile))
        except Exception as e:
            with self.state_lock:
                self.error = str(e)
                self.is_running = False
        finally:
            self.loop.close()

    async def _async_pipeline(self, session: dict[str, Any], profile: dict[str, Any]):
        # Custom generator to add chunks to state and check stop_event
        async def stream():
            async for raw_chunk in iter_transcript_file(session["path"], delay_seconds=2.0):
                if self.stop_event.is_set():
                    break
                with self.state_lock:
                    self.transcript_chunks.append(raw_chunk)
                    # Keep max chunks for UI
                    if len(self.transcript_chunks) > 50:
                        self.transcript_chunks.pop(0)
                yield raw_chunk

        # Run analysis flow
        try:
            async for command in analyze_live_text_flow(
                stream(),
                session,
                profile,
                use_llm=False,  # Use neutral fallback for now
                analysis_interval_seconds=1.0,
            ):
                if self.stop_event.is_set():
                    break
                with self.state_lock:
                    self.latest_command = command
        finally:
            with self.state_lock:
                self.is_running = False

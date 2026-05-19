from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from .live_ingestion import TranscriptIngestionState


ELEVENLABS_REALTIME_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
DEFAULT_MODEL_ID = "scribe_v2_realtime"
DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_BLOCK_SECONDS = 0.25


@dataclass(frozen=True)
class ElevenLabsRealtimeConfig:
    api_key: str | None = None
    model_id: str = DEFAULT_MODEL_ID
    language_code: str = "en"
    sample_rate: int = DEFAULT_SAMPLE_RATE
    block_seconds: float = DEFAULT_BLOCK_SECONDS
    include_timestamps: bool = True
    commit_strategy: str = "vad"
    vad_silence_threshold_secs: float = 1.0
    vad_threshold: float = 0.4
    min_speech_duration_ms: int = 100
    min_silence_duration_ms: int = 100


def convert_elevenlabs_event(event: dict[str, Any], expect_timestamps: bool = True) -> list[dict[str, str]]:
    """Convert stable ElevenLabs transcript events into app transcript chunks."""
    message_type = str(event.get("message_type") or "")
    if message_type == "partial_transcript":
        return []
    if message_type == "committed_transcript_with_timestamps":
        return _convert_timestamped_event(event)
    if message_type == "committed_transcript":
        if expect_timestamps:
            return []
        text = str(event.get("text") or "").strip()
        if not text:
            return []
        return [{"timestamp": "00:00:00", "speaker": "Speaker", "text": text}]
    if message_type.endswith("_error") or message_type == "error":
        message = event.get("message") or event.get("error") or event
        raise RuntimeError(f"ElevenLabs transcription error: {message}")
    return []


async def stream_elevenlabs_microphone(
    ingestion_state: TranscriptIngestionState,
    *,
    config: ElevenLabsRealtimeConfig | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_event: Callable[[str], None] | None = None,
    on_close: Callable[[str], None] | None = None,
    on_error_event: Callable[[str], None] | None = None,
    manage_ingestion_lifecycle: bool = True,
) -> None:
    """Capture the server microphone and push committed ElevenLabs transcripts."""
    config = config or config_from_env()
    api_key = config.api_key or os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is required for live transcription.")

    ingestion_state.connect()
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=32)
    stop_requested = should_stop or (lambda: False)

    try:
        async with _open_microphone_stream(config, audio_queue):
            await stream_elevenlabs_audio_chunks(
                _queue_audio_chunks(audio_queue, stop_requested),
                ingestion_state,
                config=config,
                api_key=api_key,
                should_stop=stop_requested,
                on_event=on_event,
                on_close=on_close,
                on_error_event=on_error_event,
            )
    except Exception as exc:
        ingestion_state.status = "disconnected"
        ingestion_state.last_error = str(exc)
        raise
    finally:
        ingestion_state.disconnect()


def config_from_env() -> ElevenLabsRealtimeConfig:
    return ElevenLabsRealtimeConfig(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        model_id=os.getenv("ELEVENLABS_MODEL_ID", DEFAULT_MODEL_ID),
        language_code=os.getenv("ELEVENLABS_LANGUAGE_CODE", "en"),
        sample_rate=_env_int("ELEVENLABS_SAMPLE_RATE", DEFAULT_SAMPLE_RATE),
    )


async def stream_elevenlabs_audio_chunks(
    audio_chunks,
    ingestion_state: TranscriptIngestionState,
    *,
    config: ElevenLabsRealtimeConfig | None = None,
    api_key: str | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_event: Callable[[str], None] | None = None,
    on_close: Callable[[str], None] | None = None,
    on_error_event: Callable[[str], None] | None = None,
    manage_ingestion_lifecycle: bool = True,
) -> None:
    """Stream caller-provided 16 kHz mono PCM chunks to ElevenLabs."""
    config = config or config_from_env()
    api_key = api_key or config.api_key or os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is required for live transcription.")

    if manage_ingestion_lifecycle:
        ingestion_state.connect()
    stop_requested = should_stop or (lambda: False)
    try:
        await _run_realtime_websocket(
            ingestion_state,
            audio_chunks,
            config,
            api_key,
            stop_requested,
            on_event,
            on_close,
            on_error_event,
        )
    except Exception as exc:
        if manage_ingestion_lifecycle:
            ingestion_state.status = "disconnected"
        ingestion_state.last_error = str(exc)
        raise
    finally:
        if manage_ingestion_lifecycle:
            ingestion_state.disconnect()


async def _run_realtime_websocket(
    ingestion_state: TranscriptIngestionState,
    audio_chunks,
    config: ElevenLabsRealtimeConfig,
    api_key: str,
    should_stop: Callable[[], bool],
    on_event: Callable[[str], None] | None = None,
    on_close: Callable[[str], None] | None = None,
    on_error_event: Callable[[str], None] | None = None,
) -> None:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError(
            "websockets is required for ElevenLabs realtime transcription."
        ) from exc

    uri = _build_realtime_uri(config)
    try:
        async with _connect_websocket(websockets, uri, api_key) as websocket:
            sender = asyncio.create_task(_send_audio(websocket, audio_chunks, config, should_stop))
            receiver = asyncio.create_task(
                _receive_transcripts(
                    websocket,
                    ingestion_state,
                    config,
                    on_event=on_event,
                    on_error_event=on_error_event,
                )
            )
            try:
                while not should_stop():
                    if receiver.done():
                        receiver.result()
                        raise RuntimeError("ElevenLabs websocket closed before recording was stopped.")
                    if sender.done():
                        sender.result()
                        raise RuntimeError("Audio stream ended before recording was stopped.")
                    await asyncio.sleep(0.2)
            finally:
                sender.cancel()
                receiver.cancel()
                await asyncio.gather(sender, receiver, return_exceptions=True)
    except Exception as exc:
        close_message = _close_message(exc)
        if close_message and on_close is not None:
            on_close(close_message)
        raise


async def _send_audio(
    websocket: Any,
    audio_chunks,
    config: ElevenLabsRealtimeConfig,
    should_stop: Callable[[], bool],
) -> None:
    async for chunk in audio_chunks:
        if should_stop():
            break
        if not chunk:
            continue
        payload = {
            "message_type": "input_audio_chunk",
            "audio_base_64": base64.b64encode(chunk).decode("ascii"),
            "sample_rate": config.sample_rate,
        }
        if config.commit_strategy == "manual":
            payload["commit"] = False
        await websocket.send(json.dumps(payload))


async def _receive_transcripts(
    websocket: Any,
    ingestion_state: TranscriptIngestionState,
    config: ElevenLabsRealtimeConfig,
    *,
    on_event: Callable[[str], None] | None = None,
    on_error_event: Callable[[str], None] | None = None,
) -> None:
    async for raw_message in websocket:
        event = json.loads(raw_message)
        message_type = str(event.get("message_type") or "unknown")
        if on_event is not None:
            on_event(message_type)
        if _is_error_event(event):
            message = _event_error_message(event)
            if on_error_event is not None:
                on_error_event(message)
            raise RuntimeError(message)
        for chunk in convert_elevenlabs_event(event, expect_timestamps=config.include_timestamps):
            await ingestion_state.push(chunk)


def _build_realtime_uri(config: ElevenLabsRealtimeConfig) -> str:
    query = {
        "model_id": config.model_id,
        "audio_format": "pcm_16000",
        "include_timestamps": str(config.include_timestamps).lower(),
        "commit_strategy": config.commit_strategy,
        "vad_silence_threshold_secs": str(config.vad_silence_threshold_secs),
        "vad_threshold": str(config.vad_threshold),
        "min_speech_duration_ms": str(config.min_speech_duration_ms),
        "min_silence_duration_ms": str(config.min_silence_duration_ms),
    }
    if config.language_code:
        query["language_code"] = config.language_code
    return f"{ELEVENLABS_REALTIME_URL}?{urlencode(query)}"


def _connect_websocket(websockets: Any, uri: str, api_key: str):
    headers = {"xi-api-key": api_key}
    try:
        return websockets.connect(uri, additional_headers=headers)
    except TypeError:
        return websockets.connect(uri, extra_headers=headers)


class _MicrophoneStream:
    def __init__(self, config: ElevenLabsRealtimeConfig, audio_queue: asyncio.Queue[bytes | None]):
        self.config = config
        self.audio_queue = audio_queue
        self.stream: Any | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    async def __aenter__(self):
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "sounddevice is required to capture the server microphone."
            ) from exc

        self.loop = asyncio.get_running_loop()
        blocksize = max(1, int(self.config.sample_rate * self.config.block_seconds))

        def callback(indata, frames, time_info, status) -> None:
            del frames, time_info
            if status:
                return
            if self.loop is None:
                return
            data = bytes(indata)
            self.loop.call_soon_threadsafe(self._put_audio, data)

        self.stream = sd.RawInputStream(
            samplerate=self.config.sample_rate,
            blocksize=blocksize,
            dtype="int16",
            channels=1,
            callback=callback,
        )
        self.stream.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
        await self.audio_queue.put(None)

    def _put_audio(self, data: bytes) -> None:
        if self.audio_queue.full():
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self.audio_queue.put_nowait(data)


def _open_microphone_stream(
    config: ElevenLabsRealtimeConfig,
    audio_queue: asyncio.Queue[bytes | None],
) -> _MicrophoneStream:
    return _MicrophoneStream(config, audio_queue)


async def _queue_audio_chunks(
    audio_queue: asyncio.Queue[bytes | None],
    should_stop: Callable[[], bool],
):
    while not should_stop():
        try:
            chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.2)
        except asyncio.TimeoutError:
            continue
        if chunk is None:
            break
        yield chunk


def _convert_timestamped_event(event: dict[str, Any]) -> list[dict[str, str]]:
    words = [word for word in event.get("words", []) if isinstance(word, dict)]
    if not words:
        text = str(event.get("text") or "").strip()
        return [{"timestamp": "00:00:00", "speaker": "Speaker", "text": text}] if text else []

    chunks: list[dict[str, str]] = []
    current_speaker: str | None = None
    current_start: float | None = None
    current_text: list[str] = []

    for word in words:
        word_text = str(word.get("text") or "")
        if not word_text:
            continue
        word_type = str(word.get("type") or "word")
        speaker = _speaker_label(word.get("speaker_id") or word.get("speaker"))

        if word_type == "spacing":
            if current_text:
                current_text.append(word_text)
            continue

        if current_speaker is None:
            current_speaker = speaker
            current_start = _word_start(word)
        elif speaker != current_speaker:
            _append_converted_chunk(chunks, current_start, current_speaker, current_text)
            current_speaker = speaker
            current_start = _word_start(word)
            current_text = []

        current_text.append(word_text)

    _append_converted_chunk(chunks, current_start, current_speaker or "Speaker", current_text)
    if chunks:
        return chunks

    text = str(event.get("text") or "").strip()
    return [{"timestamp": "00:00:00", "speaker": "Speaker", "text": text}] if text else []


def _append_converted_chunk(
    chunks: list[dict[str, str]],
    start: float | None,
    speaker: str,
    text_parts: list[str],
) -> None:
    text = "".join(text_parts).strip()
    if not text:
        return
    chunks.append(
        {
            "timestamp": _format_timestamp(start),
            "speaker": speaker,
            "text": text,
        }
    )


def _speaker_label(raw_speaker: Any) -> str:
    if raw_speaker is None or str(raw_speaker).strip() == "":
        return "Speaker"
    label = str(raw_speaker).strip()
    if label.lower().startswith("speaker"):
        return label
    return f"Speaker {label}"


def _word_start(word: dict[str, Any]) -> float | None:
    try:
        return float(word.get("start"))
    except (TypeError, ValueError):
        return None


def _format_timestamp(seconds: float | None) -> str:
    if seconds is None:
        return "00:00:00"
    total_seconds = max(0, int(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default





def _is_error_event(event: dict[str, Any]) -> bool:
    message_type = str(event.get("message_type") or "").lower()
    return message_type == "error" or "error" in message_type


def _event_error_message(event: dict[str, Any]) -> str:
    message = event.get("message") or event.get("error") or event.get("detail") or event
    return f"ElevenLabs transcription error: {message}"


def _close_message(exc: BaseException) -> str | None:
    code = getattr(exc, "code", None)
    reason = getattr(exc, "reason", None)
    if code is None and reason is None:
        return None
    if reason:
        return f"ElevenLabs websocket closed with code {code}: {reason}"
    return f"ElevenLabs websocket closed with code {code}"

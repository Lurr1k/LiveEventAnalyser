import pytest

from backend.elevenlabs_live import (
    ElevenLabsRealtimeConfig,
    _receive_transcripts,
    _send_audio,
    convert_elevenlabs_event,
    first_audio_chunk,
)
from backend.live_ingestion import TranscriptIngestionState


def test_partial_transcript_is_ignored():
    event = {"message_type": "partial_transcript", "text": "still changing"}

    assert convert_elevenlabs_event(event) == []


def test_committed_transcript_converts_to_chunk():
    event = {"message_type": "committed_transcript", "text": "This is stable."}

    assert convert_elevenlabs_event(event) == [
        {"timestamp": "00:00:00", "speaker": "Speaker", "text": "This is stable."}
    ]


def test_timestamped_transcript_groups_by_speaker():
    event = {
        "message_type": "committed_transcript_with_timestamps",
        "text": "Hello there. Good morning.",
        "words": [
            {"text": "Hello", "start": 1.2, "end": 1.4, "type": "word", "speaker_id": "1"},
            {"text": " ", "start": 1.4, "end": 1.5, "type": "spacing"},
            {"text": "there.", "start": 1.5, "end": 1.8, "type": "word", "speaker_id": "1"},
            {"text": "Good", "start": 3.0, "end": 3.2, "type": "word", "speaker_id": "2"},
            {"text": " ", "start": 3.2, "end": 3.3, "type": "spacing"},
            {"text": "morning.", "start": 3.3, "end": 3.7, "type": "word", "speaker_id": "2"},
        ],
    }

    assert convert_elevenlabs_event(event) == [
        {"timestamp": "00:00:01", "speaker": "Speaker 1", "text": "Hello there."},
        {"timestamp": "00:00:03", "speaker": "Speaker 2", "text": "Good morning."},
    ]


def test_timestamped_transcript_falls_back_without_words():
    event = {
        "message_type": "committed_transcript_with_timestamps",
        "text": "Fallback text.",
        "words": [],
    }

    assert convert_elevenlabs_event(event) == [
        {"timestamp": "00:00:00", "speaker": "Speaker", "text": "Fallback text."}
    ]


def test_error_event_raises_runtime_error():
    event = {"message_type": "scribe_auth_error", "message": "bad key"}

    with pytest.raises(RuntimeError, match="bad key"):
        convert_elevenlabs_event(event)


@pytest.mark.asyncio
async def test_ingestion_dedupes_repeated_committed_chunks():
    state = TranscriptIngestionState()
    chunk = {"timestamp": "00:00:01", "speaker": "Speaker 1", "text": "Hello there."}

    first = await state.push(chunk)
    second = await state.push(chunk)

    assert first is not None
    assert second is None
    assert state.rolling_window() == [chunk]


@pytest.mark.asyncio
async def test_send_audio_streams_browser_pcm_chunks():
    class FakeWebSocket:
        def __init__(self):
            self.messages = []

        async def send(self, message):
            self.messages.append(message)

    async def chunks():
        yield b"\x01\x02"
        yield b""
        yield b"\x03\x04"

    websocket = FakeWebSocket()

    await _send_audio(
        websocket,
        chunks(),
        ElevenLabsRealtimeConfig(sample_rate=16000),
        should_stop=lambda: False,
    )

    assert len(websocket.messages) == 2
    assert all('"message_type": "input_audio_chunk"' in message for message in websocket.messages)


@pytest.mark.asyncio
async def test_receive_transcripts_reports_event_types():
    class FakeWebSocket:
        def __aiter__(self):
            self.messages = iter(
                [
                    '{"message_type": "session_started"}',
                    '{"message_type": "partial_transcript", "text": "Hel"}',
                    '{"message_type": "committed_transcript", "text": "Hello"}',
                ]
            )
            return self

        async def __anext__(self):
            try:
                return next(self.messages)
            except StopIteration:
                raise StopAsyncIteration

    state = TranscriptIngestionState()
    events = []

    await _receive_transcripts(FakeWebSocket(), state, on_event=events.append)

    assert events == [
        "session_started",
        "partial_transcript",
        "committed_transcript",
    ]
    assert state.rolling_window() == [
        {"timestamp": "00:00:00", "speaker": "Speaker", "text": "Hello"}
    ]


@pytest.mark.asyncio
async def test_first_audio_chunk_replays_first_non_empty_chunk():
    async def chunks():
        yield b""
        yield b"\x01\x02"
        yield b"\x03\x04"

    first, replayable = await first_audio_chunk(chunks(), timeout_seconds=1.0)

    assert first == b"\x01\x02"
    replayed = []
    async for chunk in replayable:
        replayed.append(chunk)
    assert replayed == [b"\x01\x02", b"\x03\x04"]


@pytest.mark.asyncio
async def test_first_audio_chunk_times_out_without_audio():
    async def chunks():
        while True:
            yield b""

    first, replayable = await first_audio_chunk(chunks(), timeout_seconds=0.01)

    assert first is None
    assert replayable is not None

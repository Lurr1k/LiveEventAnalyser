import pytest

from backend.elevenlabs_live import convert_elevenlabs_event
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

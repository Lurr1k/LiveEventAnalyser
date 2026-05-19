import queue

from frontend.state import SessionStateManager


def test_submit_audio_chunk_updates_diagnostics():
    manager = SessionStateManager()
    manager.audio_queue = queue.Queue(maxsize=2)

    manager.submit_audio_chunk(b"\x01\x02")
    state = manager.get_state()

    assert state["audio_chunk_count"] == 1
    assert state["last_audio_chunk_at"] is not None


def test_elevenlabs_event_updates_diagnostics():
    manager = SessionStateManager()

    manager._set_elevenlabs_event("session_started")
    state = manager.get_state()

    assert state["elevenlabs_connected"] is True
    assert state["last_elevenlabs_event_type"] == "session_started"
    assert state["last_elevenlabs_event_at"] is not None


def test_elevenlabs_close_updates_diagnostics():
    manager = SessionStateManager()

    manager._set_elevenlabs_close("closed with code 1000")
    state = manager.get_state()

    assert state["elevenlabs_connected"] is False
    assert state["elevenlabs_close_error"] == "closed with code 1000"


def test_initial_state_exposes_connection_attempts():
    manager = SessionStateManager()

    assert manager.get_state()["elevenlabs_connection_attempts"] == 0

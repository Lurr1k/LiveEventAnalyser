import asyncio
import pytest
from pathlib import Path

from backend.data_loading import discover_data_paths, load_attendees, load_sessions
from backend.audience import get_audience_profile
from backend.live_ingestion import iter_transcript_file, TranscriptIngestionState
from backend.live_analysis import analyze_live_text_flow

@pytest.mark.asyncio
async def test_end_to_end_data_integration():
    """
    Test the full backend pipeline using the actual mock data files.
    This reads the real Excel and markdown files from the `data/` folder,
    generates an audience profile, and simulates a live transcript feed
    by rapidly parsing a few lines from the real markdown transcript.
    """
    # 1. Discover paths
    paths = discover_data_paths()
    assert paths["data_dir"].exists(), "Data directory not found"
    assert paths["attendees"].exists(), "Attendees Excel not found"
    assert paths["sessions"].exists(), "Sessions directory not found"

    # 2. Load data
    attendees = load_attendees(paths["attendees"])
    sessions = load_sessions(paths["sessions"])
    assert len(sessions) > 0, "No sessions loaded"
    
    # We pick the first session (no random selection)
    session = sessions[0]
    assert session["session_id"] is not None

    # 3. Generate audience profile
    profile = get_audience_profile(attendees, sessions, session["session_id"])
    assert profile["attendee_count"] > 0
    assert "top_intents" in profile

    # 4. Stream real transcript chunks rapidly
    async def fast_mock_stream():
        count = 0
        # iter_transcript_file yields raw markdown transcript lines one by one
        async for chunk in iter_transcript_file(session["path"], delay_seconds=0.001):
            yield chunk
            count += 1
            if count >= 30:  # Only process the first 30 chunks to keep the test fast
                break

    # 5. Analyze the flow (without LLM)
    commands_received = 0
    async for command in analyze_live_text_flow(
        fast_mock_stream(),
        session,
        profile,
        use_llm=False,
        analysis_interval_seconds=0.01,  # Fast interval to quickly yield commands
    ):
        assert command.type == "neutral"
        assert command.headline == "Keep listening"
        commands_received += 1
    
    assert commands_received > 0, "Expected at least one UICommand to be generated"

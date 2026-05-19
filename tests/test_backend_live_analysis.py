import asyncio
import pytest

from backend.live_analysis import (
    analyze_live_text_flow,
    analyze_with_gpt54_mini,
    RollingTranscript,
    TranscriptChunk,
    rule_based_analyze,
    UICommand,
)

@pytest.fixture
def session_context():
    return {
        "session_id": "test_session",
        "title": "Test Session",
        "room": "Test Room",
        "agenda": ["Topic 1", "Topic 2"],
        "current_agenda_item": "Topic 1",
        "next_agenda_item": "Topic 2",
    }

@pytest.fixture
def audience_profile():
    return {
        "session_id": "test_session",
        "attendee_count": 50,
        "ai_experience_distribution": {"Beginner": 10, "Intermediate": 30, "Advanced": 10},
        "academic_background_distribution": {"Computer Science": 50},
        "intent_distribution": {"Learn": 25, "Networking": 25},
        "top_intents": ["Learn", "Networking"],
        "beginner_ratio": 0.2,
    }

def test_rolling_transcript():
    """
    Test the `RollingTranscript` data structure.
    Ensures that when new transcript chunks are appended, the max_chunks
    limit is respected and old chunks are correctly evicted.
    """
    rolling = RollingTranscript(max_chunks=2)
    
    chunk1 = TranscriptChunk(timestamp="00:00:01", speaker="Alice", text="Hello")
    chunk2 = TranscriptChunk(timestamp="00:00:02", speaker="Bob", text="Hi")
    chunk3 = TranscriptChunk(timestamp="00:00:03", speaker="Alice", text="How are you?")
    
    rolling.append(chunk1)
    rolling.append(chunk2)
    assert len(rolling.chunks) == 2
    
    rolling.append(chunk3)
    # chunk1 should be evicted because max_chunks is 2
    assert len(rolling.chunks) == 2
    assert rolling.chunks[0].text == "Hi"
    assert rolling.chunks[1].text == "How are you?"

def test_rule_based_analyze(session_context, audience_profile):
    """
    Test the synchronous fallback analysis logic.
    Verifies that when `rule_based_analyze` is called, it correctly returns
    a `UICommand` in a neutral state, ensuring UI stability without an LLM.
    """
    rolling = RollingTranscript(max_chunks=5)
    rolling.append(TranscriptChunk(timestamp="00:00:01", speaker="Alice", text="Hello world!"))
    
    command = rule_based_analyze(rolling, session_context, audience_profile)
    
    assert isinstance(command, UICommand)
    assert command.type == "neutral"
    assert command.priority == "low"
    assert command.headline == "Continue"

@pytest.mark.asyncio
async def test_analyze_live_text_flow_neutral_fallback(session_context, audience_profile):
    """
    Test the end-to-end async text flow pipeline.
    This simulates an asynchronous stream of live audio transcript chunks,
    feeds it into `analyze_live_text_flow` (with LLM disabled), and verifies
    that it yields neutral fallback commands correctly over time.
    """
    # Create an async generator for mock live chunks
    async def mock_chunks():
        yield {"timestamp": "00:00:01", "speaker": "Alice", "text": "This is the first sentence."}
        # Yield a bit later to simulate time gap? Not necessary for the basic queue
        yield {"timestamp": "00:00:02", "speaker": "Bob", "text": "This is the second sentence."}

    # Run the live text flow with a very short analysis interval and use_llm=False
    commands = []
    async for command in analyze_live_text_flow(
        mock_chunks(),
        session_context,
        audience_profile,
        analysis_interval_seconds=0.1,  # Fast flush
        use_llm=False,
    ):
        commands.append(command)
        
    assert len(commands) >= 1
    assert all(cmd.type == "neutral" for cmd in commands)
    assert commands[0].headline == "Continue"


@pytest.mark.asyncio
async def test_analyze_with_gpt54_mini_reports_empty_output(session_context, audience_profile):
    class EmptyResponse:
        output_text = ""

    class FakeResponses:
        async def create(self, **kwargs):
            return EmptyResponse()

    class FakeClient:
        responses = FakeResponses()

    errors = []
    rolling = RollingTranscript(max_chunks=5)
    rolling.append(
        TranscriptChunk(
            timestamp="00:00:01",
            speaker="Alice",
            text="Explain RAG clearly for beginners.",
        )
    )

    command = await analyze_with_gpt54_mini(
        rolling,
        session_context,
        audience_profile,
        client=FakeClient(),
        on_error=errors.append,
    )

    assert command.type == "neutral"
    assert errors == ["OpenAI returned an empty output_text."]

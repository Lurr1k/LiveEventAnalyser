# Backend Work Done

This file is the recovery note for the EuroHackNL backend work completed so far.

## Current Architecture

The backend is now **LLM-led** for live analysis.

Live transcript chunks are collected into a rolling transcript window. The analyzer sends that rolling window plus session and audience context to `gpt-5.4-mini` on a fixed time slot, default `5.0` seconds. The backend does **not** try to catch jargon, topic fatigue, or FOMO with keyword lists.

If the model cannot run, the fallback is intentionally neutral only. This keeps the UI valid without pretending that backend heuristics understood the talk.

## Files

### `data_loading.py`

Step 2 implementation.

Provides:

```python
discover_data_paths(project_root=None) -> dict[str, Path]
load_attendees(path) -> pandas.DataFrame
load_sessions(path_or_dir) -> list[dict]
normalize_transcript_chunk(raw_chunk) -> dict[str, str]
```

Responsibilities:

- locate `../Data/hackathon_mock_attendees.xlsx`
- locate `../Data/sessions`
- load attendee Excel with pandas
- normalize attendee columns to snake_case
- load session markdown metadata
- normalize incoming transcript chunks into:

```python
{
    "timestamp": "00:00:00",
    "speaker": "string",
    "text": "string",
}
```

### `audience.py`

Step 3 implementation.

Provides:

```python
get_session_by_id(sessions, session_id) -> dict
filter_attendees_for_session(attendees, session)
build_audience_profile(attendees, session_id, room=None, *, session=None) -> dict
get_audience_profile(attendees, sessions, session_id) -> dict
```

Current mock attendee data has no session/room registration column, so filtering falls back to the full attendee set. If future attendee data adds `session_id`, session title, or room columns, filtering will use them.

Audience profile shape:

```python
{
    "session_id": "string",
    "attendee_count": 0,
    "ai_experience_distribution": {},
    "academic_background_distribution": {},
    "intent_distribution": {},
    "top_intents": ["string"],
    "beginner_ratio": 0.0,
}
```

### `live_ingestion.py`

Step 4 implementation.

Provides:

```python
TranscriptIngestionState
IngestedTranscriptChunk
TopicState
replay_transcript_file(path, ingestion_state, delay_seconds=0.2)
iter_transcript_file(path, delay_seconds=0.2)
iter_manual_chunks(queue)
```

`TranscriptIngestionState` owns:

- live chunk queue
- connection status: `disconnected`, `waiting`, `receiving`
- latest transcript chunk
- rolling transcript window for UI display
- non-semantic window timing/count state for UI/debug display

### `rule_analysis.py`

Fallback-only module.

Provides:

```python
UICommand
analyze_rules(transcript_chunks, session_context, audience_profile) -> UICommand
neutral_command() -> UICommand
```

Important: despite the file name, this module no longer performs semantic rules. It returns only a neutral fallback command:

```python
UICommand(
    type="neutral",
    priority="low",
    headline="Keep listening",
    detail="No model analysis is available for this time window.",
    related_topic=None,
)
```

This is deliberate. Coaching, fatigue, and FOMO are model judgments.

### `live_analysis.py`

LLM analysis pipeline.

Key functions:

```python
analyze_with_gpt54_mini(...)
analyze_live_text_flow(...)
build_llm_payload(...)
rule_based_analyze(...)
```

`analyze_live_text_flow(...)` is now time-slotted:

- consumes live transcript chunks continuously
- keeps a rolling transcript window
- sends the current window to the model every `analysis_interval_seconds`, default `5.0`
- skips slots where no new transcript arrived
- flushes one final analysis when the stream ends and there are unanalyzed chunks

Compatibility note:

- `min_analysis_interval_seconds` still exists as an alias for older callers, but new code should use `analysis_interval_seconds`.

The GPT payload contains:

- active session context
- agenda context
- audience profile
- FOMO context:
  - top attendee intents
  - full intent distribution
  - attendee count
  - current transcript window text
  - snippet requirements for model-generated notification text
- rolling transcript chunks and formatted text
- rolling transcript window metadata:
  - chunk count
  - max window size
  - oldest transcript timestamp
  - newest transcript timestamp
  - transcript duration in seconds when timestamps are parseable
- analysis context:
  - configured analysis interval
  - `fatigue_decision_owner: "model"`
  - `fomo_decision_owner: "model"`
  - `backend_keyword_detection: False`
- neutral fallback command

The model must return one structured `UICommand`.

### Step 6 Topic Fatigue Support

Topic fatigue is supported by context, not backend detection.

The backend passes these fields to the model:

```python
{
    "agenda_context": {
        "agenda": [...],
        "current_agenda_item": "...",
        "next_agenda_item": "...",
    },
    "transcript_window": {
        "text": "...",
        "chunks": [...],
        "metadata": {
            "chunk_count": 0,
            "max_window_chunks": 24,
            "oldest_timestamp": "00:00:00 | None",
            "newest_timestamp": "00:00:05 | None",
            "transcript_duration_seconds": 5,
        },
    },
}
```

The model decides whether the discussion is lingering, looping, or blocking agenda progress. The backend does not count repeated topic words.

### Step 7 FOMO Support

FOMO generation is supported by context, not backend detection.

The backend passes this block to the model:

```python
{
    "fomo_context": {
        "top_intents": [...],
        "intent_distribution": {...},
        "attendee_count": 0,
        "current_window_text": "...",
        "snippet_requirements": {
            "source": "current transcript window only",
            "style": "short notification-style summary",
            "do_not_invent_names": True,
            "intended_audience": "attendees with adjacent interests",
        },
    },
}
```

The model decides whether the current transcript contains an actionable insight worth sharing. The backend does not scan for insight phrases.

### `llm_algorithm.md`

Design note for the intended LLM-led time-slot algorithm.

## Typical Flow

```python
import asyncio
from openai import AsyncOpenAI
from audience import get_audience_profile
from data_loading import discover_data_paths, load_attendees, load_sessions
from live_analysis import analyze_live_text_flow
from live_ingestion import TranscriptIngestionState, replay_transcript_file

async def main():
    paths = discover_data_paths()
    attendees = load_attendees(paths["attendees"])
    sessions = load_sessions(paths["sessions"])

    session = sessions[0]
    profile = get_audience_profile(attendees, sessions, session["session_id"])

    state = TranscriptIngestionState(max_window_chunks=24)
    producer = asyncio.create_task(
        replay_transcript_file(session["path"], state, delay_seconds=0.2)
    )

    async for command in analyze_live_text_flow(
        state.chunks(),
        session,
        profile,
        client=AsyncOpenAI(),
        model="gpt-5.4-mini",
        analysis_interval_seconds=5.0,
    ):
        print(command)

    await producer

asyncio.run(main())
```

## Dependencies

`pyproject.toml` includes:

```toml
dependencies = [
    "openai>=2.0.0",
    "openpyxl>=3.1.0",
    "pandas>=2.2.0",
]
```

The project uses flat modules, so `pyproject.toml` also lists:

```toml
py-modules = [
    "main",
    "audience",
    "data_loading",
    "live_analysis",
    "live_ingestion",
    "rule_analysis",
]
```

## Verification To Re-Run

Syntax:

```powershell
.\.venv\Scripts\python.exe -m py_compile audience.py data_loading.py live_analysis.py live_ingestion.py rule_analysis.py
```

Smoke test without an API key should produce neutral fallback commands, not semantic coaching/fatigue/FOMO.

## Known Constraints

- Real transcription provider integration is not implemented yet.
- Current transcript input supports manual queues and markdown replay.
- Current attendee data has no session-specific registration mapping.
- GPT calls require `OPENAI_API_KEY` or an explicitly configured `AsyncOpenAI` client.
- Without model credentials, analysis returns neutral fallback only.
- There are no backend keyword lists for jargon, insight detection, fatigue detection, or FOMO detection.

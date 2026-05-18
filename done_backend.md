# Backend Work Done

This document summarizes backend work completed so far for the EuroHackNL live event assistant. It is written for session recovery and for teammates who need to understand the current backend shape without reading the full conversation.

## Scope Completed

Completed backend work from `order.md`:

- Step 2: Data discovery and file loading.
- Step 3: Session selection and audience profiling.
- Step 4: Live transcript ingestion.
- Step 5: Rule-based analysis first.
- Early Step 7 support: async GPT-5.4-mini prompt chain and structured command parsing with rule fallback.

## Files Added

### `data_loading.py`

Owns data discovery, attendee loading, session metadata loading, and transcript chunk normalization.

Main functions:

```python
discover_data_paths(project_root=None) -> dict[str, Path]
load_attendees(path) -> pandas.DataFrame
load_sessions(path_or_dir) -> list[dict]
normalize_transcript_chunk(raw_chunk) -> dict[str, str]
```

Behavior:

- Finds data under `../Data` from the repo root:
  - `../Data/hackathon_mock_attendees.xlsx`
  - `../Data/sessions`
- Loads the attendee Excel file with `pandas.read_excel`.
- Normalizes attendee column names into snake_case.
- Validates expected attendee columns:
  - `id`
  - `full_name`
  - `university_affiliation`
  - `academic_background`
  - `ai_experience_level`
  - `intent_of_attending`
  - `goal_of_the_event`
- Loads session markdown files and extracts the JSON block under `## Metadata`.
- Returns sessions in the shared shape expected by `order.md`:

```python
{
    "session_id": "string",
    "title": "string",
    "room": "string",
    "agenda": ["string"],
    "current_agenda_item": "string",
    "next_agenda_item": None,
    "metadata": {},
    "path": "string",
}
```

- Normalizes either diarized transcript strings or dict-style live transcript payloads into:

```python
{
    "timestamp": "00:00:00",
    "speaker": "string",
    "text": "string",
}
```

Important note:

- `load_attendees` is intentionally synchronous because it is startup/session-selection work over local files. If async startup is needed later, wrap it with `asyncio.to_thread`.

### `audience.py`

Owns backend step 3: selecting a session, filtering attendees, and building an audience profile.

Main functions:

```python
get_session_by_id(sessions, session_id) -> dict
filter_attendees_for_session(attendees, session)
build_audience_profile(attendees, session_id, room=None, *, session=None) -> dict
get_audience_profile(attendees, sessions, session_id) -> dict
```

Audience profile shape:

```python
{
    "session_id": "string",
    "attendee_count": 0,
    "ai_experience_distribution": {
        "Beginner": 0,
        "Intermediate": 0,
        "Advanced": 0,
    },
    "academic_background_distribution": {},
    "top_intents": ["string"],
    "beginner_ratio": 0.0,
}
```

Filtering behavior:

- If attendee data later includes one of these session columns, filtering uses it:
  - `session_id`
  - `registered_session_id`
  - `selected_session_id`
  - `current_session_id`
- If attendee data includes one of these title columns, filtering uses it:
  - `session_title`
  - `registered_session`
  - `selected_session`
  - `current_session`
- If attendee data includes one of these room columns, filtering uses it:
  - `room`
  - `session_room`
  - `registered_room`
  - `selected_room`
  - `current_room`
- The current mock Excel file has no session or room assignment columns, so filtering intentionally falls back to the full attendee set.

Verified current profile from real data:

- Attendee count: `100`
- Beginner ratio: `0.36`
- AI experience distribution includes:
  - `Beginner: 36`
  - `Intermediate: 46`
  - `Power user: 15`
  - `Never used: 3`
  - `Advanced: 0`

### `live_ingestion.py`

Owns backend step 4: live transcript ingestion state.

Main classes/functions:

```python
TranscriptIngestionState
IngestedTranscriptChunk
TopicState
replay_transcript_file(path, ingestion_state, delay_seconds=0.2)
iter_transcript_file(path, delay_seconds=0.2)
iter_manual_chunks(queue)
```

`TranscriptIngestionState` provides:

- async queue for incoming transcript chunks
- status tracking:
  - `disconnected`
  - `waiting`
  - `receiving`
- rolling transcript window
- latest transcript chunk
- topic pulse state
- UI-ready snapshot

Typical usage:

```python
state = TranscriptIngestionState(max_window_chunks=24)
await state.push("[00:01:02] Speaker 1: We use embeddings here.")

async for chunk in state.chunks():
    ...
```

Useful UI methods:

```python
state.latest_chunk()
state.rolling_window()
state.topic_state()
state.snapshot()
state.disconnect()
```

Demo connector:

```python
await replay_transcript_file(session["path"], state, delay_seconds=0.2)
```

This replays the provided transcript markdown as if it were a live stream. It stops cleanly when `state.disconnect()` is called.

### `live_analysis.py`

Started earlier as the analysis layer and now remains compatible with the new backend modules.

Main pieces:

```python
TranscriptChunk
UICommand
RollingTranscript
load_attendees(path)
load_sessions(path_or_dir)
build_audience_profile(attendees, session_id, room=None)
normalize_transcript_chunk(raw_chunk)
rule_based_analyze(rolling, session_context, audience_profile)
analyze_with_gpt54_mini(...)
analyze_live_text_flow(...)
stream_transcript_file(...)
```

Compatibility notes:

- `load_attendees`, `load_sessions`, and `normalize_transcript_chunk` delegate to `data_loading.py`.
- `build_audience_profile` delegates to `audience.py`.
- Existing code that imports these from `live_analysis.py` should still work.

Analysis behavior:

- Maintains a rolling transcript window.
- Has a deterministic fallback analyzer:
  - beginner-heavy audience plus jargon -> coaching command
  - repeated topic terms -> fatigue command
  - strong takeaway language -> FOMO command
  - otherwise neutral
- Has async GPT-5.4-mini integration through the OpenAI Responses API.
- Requires structured JSON matching the `UICommand` schema.
- Falls back to rule-based output if:
  - OpenAI package is missing
  - API credentials are missing
  - the model call times out or fails
  - the model returns invalid output

Important fix made:

- `live_analysis.py` was missing `import re`; this was restored.
- OpenAI client creation now catches missing API-key errors and returns fallback output instead of crashing.
- `analyze_with_gpt54_mini(...)` and `analyze_live_text_flow(...)` now accept `use_llm=False` for deterministic rule-only demo paths.

### `rule_analysis.py`

Owns backend step 5: deterministic analysis before LLM calls.

Main functions/classes:

```python
UICommand
analyze_rules(transcript_chunks, session_context, audience_profile) -> UICommand
neutral_command() -> UICommand
```

Rule behavior:

- Audience-aware coaching:
  - triggers when beginner ratio is at least `0.35`
  - scans recent transcript text for jargon such as `llm`, `rag`, `embedding`, `vector database`, `inference`, `valuation`, and similar terms
  - suppresses the prompt if the speaker already appears to be explaining the concept with phrases such as `means`, `stands for`, `in simple terms`, or `basically`
  - output example: `Define your terms`
- Topic fatigue:
  - checks the recent rolling transcript for repeated topic terms
  - triggers when the same topic appears across enough recent chunks
  - uses `next_agenda_item` when available
  - output examples: `Move to next topic`, `Pivot the topic`
- FOMO:
  - detects actionable takeaway language such as `key takeaway`, `the lesson`, `you should`, or `the opportunity`
  - matches the insight to known attendee intents where possible
  - output example: `Share this insight`
- Neutral:
  - returns `Keep listening` when no useful intervention is needed

The command shape remains:

```python
{
    "type": "coaching | fatigue | fomo | neutral",
    "priority": "low | medium | high",
    "headline": "3-7 word action prompt",
    "detail": "short explanation",
    "target": "speaker | moderator | attendee",
    "related_topic": "string | None",
}
```

### `llm_algorithm.md`

Human-readable design note for the async transcript-to-LLM algorithm.

Includes:

- high-level flow
- proposed GPT-5.4-mini prompt
- expected structured output
- example usage

## Files Modified

### `pyproject.toml`

Dependencies added:

```toml
dependencies = [
    "openai>=2.0.0",
    "openpyxl>=3.1.0",
    "pandas>=2.2.0",
]
```

Build metadata added because setuptools could not infer multiple top-level flat modules:

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
py-modules = [
    "main",
    "audience",
    "data_loading",
    "live_analysis",
    "live_ingestion",
    "rule_analysis",
]
```

## Dependency/Environment Notes

The project venv initially did not have `pip`. It was bootstrapped with:

```powershell
.\.venv\Scripts\python.exe -m ensurepip --upgrade
```

Then dependencies were installed with:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Network approval was required for dependency installation.

Installed packages include:

- `pandas`
- `openpyxl`
- `openai`
- their transitive dependencies

## Verification Performed

Syntax checks:

```powershell
.\.venv\Scripts\python.exe -m py_compile audience.py data_loading.py live_analysis.py live_ingestion.py rule_analysis.py
```

Data loading verified:

- Attendees load as a pandas DataFrame.
- Current shape: `(100, 7)`.
- Columns:

```python
[
    "id",
    "full_name",
    "university_affiliation",
    "academic_background",
    "ai_experience_level",
    "intent_of_attending",
    "goal_of_the_event",
]
```

Session loading verified:

- `30` session markdown files load from `../Data/sessions`.
- Example first session:
  - session id: `209e6b9e`
  - title: `Are We Still Backing the Crazy Ones - Day 1`

Transcript normalization verified:

```python
normalize_transcript_chunk("[00:01:02] Speaker 1: Hello world")
```

returns:

```python
{
    "timestamp": "00:01:02",
    "speaker": "Speaker 1",
    "text": "Hello world",
}
```

Audience profile verified:

- `get_audience_profile(...)` works with real attendee/session data.
- Because there is no per-session registration field yet, it profiles all 100 mock attendees.

Live ingestion verified:

- `replay_transcript_file(...)` feeds transcript chunks into `TranscriptIngestionState`.
- `state.chunks()` can be consumed asynchronously.
- `state.disconnect()` stops the replay cleanly.
- `state.latest_chunk()`, `state.rolling_window()`, and `state.topic_state()` return usable state.

Analyzer integration verified:

```python
analyze_live_text_flow(state.chunks(), session, profile, min_analysis_interval_seconds=0)
```

works with the new ingestion stream.

Rule-based analysis verified:

- coaching command is produced for beginner-heavy audience plus unexplained jargon
- fatigue command is produced for repeated topic terms
- FOMO command is produced for actionable takeaway language matching attendee intent
- neutral command is produced when no rule should fire

Deterministic live analysis path verified:

```python
async for command in analyze_live_text_flow(
    state.chunks(),
    session,
    profile,
    min_analysis_interval_seconds=0,
    use_llm=False,
):
    print(command)
```

No API key was configured, so GPT calls were not verified against the network. The fallback path was verified and returns `UICommand` objects without crashing.

## Current Backend Flow

Basic app-side flow should be:

```python
from data_loading import discover_data_paths, load_attendees, load_sessions
from audience import get_audience_profile
from live_ingestion import TranscriptIngestionState, replay_transcript_file
from live_analysis import analyze_live_text_flow

paths = discover_data_paths()
attendees = load_attendees(paths["attendees"])
sessions = load_sessions(paths["sessions"])

session = sessions[0]
profile = get_audience_profile(attendees, sessions, session["session_id"])

state = TranscriptIngestionState(max_window_chunks=24)

# In one async task:
await replay_transcript_file(session["path"], state, delay_seconds=0.2)

# In another async task:
async for command in analyze_live_text_flow(state.chunks(), session, profile):
    print(command)
```

For rule-only demos, call:

```python
async for command in analyze_live_text_flow(
    state.chunks(),
    session,
    profile,
    use_llm=False,
):
    print(command)
```

## Known Constraints

- The current attendee Excel file has no session/room registration mapping, so audience profiles are event-wide for now.
- `data_loading.py` and `audience.py` are synchronous by design because they are startup/session-selection work.
- `live_ingestion.py` and `live_analysis.py` are async where the live stream and model calls happen.
- Streamlit UI is not implemented yet.
- Real transcription provider integration is not implemented yet; the backend currently supports:
  - manual queue style ingestion
  - markdown transcript replay for demos
- GPT-5.4-mini call path exists but needs `OPENAI_API_KEY` or an explicit configured client to call the API.

## Suggested Next Backend Step

Step 7 or step 8 from `order.md`, depending on team priority:

- Step 7: wire the LLM prompt chain into the UI path, keeping `use_llm=False` available for demos.
- Step 8: make topic fatigue more agenda-aware and surface topic duration from `live_ingestion.TopicState`.

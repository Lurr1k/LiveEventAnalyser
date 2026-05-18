# Implementation Order: Live Event Agentic Assistant

## Goal
Build a Streamlit MVP for a real-time speaker and moderator HUD. The app consumes live transcript chunks, combines them with session audience context, sends that context to an LLM, and displays concise, actionable prompts for the presenter.

The general idea stays the same as `spec.md`: the MVP is transcript-first, Streamlit-based, and focused on audience-aware coaching, topic fatigue detection, and FOMO snippet generation.

## Team Split

### Backend / LLM Engineer
Owns the data pipeline, live transcript ingestion, session context, analysis logic, and LLM calls.

Primary responsibilities:
- Load and normalize attendee data from `hackathon_mock_attendees.xlsx`.
- Load and normalize session metadata.
- Connect the live transcription source to the analysis pipeline.
- Build the audience profile for the active session.
- Build prompt inputs from rolling transcript context and audience context.
- Implement LLM response parsing into simple UI-ready commands.
- Provide stable functions the UI can call.

### UI / Streamlit Engineer
Owns the Streamlit app shell, HUD layout, visual hierarchy, state display, and demo flow.

Primary responsibilities:
- Create the Streamlit app structure.
- Build the session selector and live transcript status controls.
- Display the recent transcript feed.
- Display the speaker action zone with max 3-7 word prompts.
- Display secondary context such as audience profile, fatigue state, and FOMO snippets.
- Add minimal custom CSS for a clean terminal-inspired HUD.
- Make the app easy to demo during judging.

## Shared Interfaces

Agree on these interfaces early so both engineers and their AI agents can work independently.

### Session Context

```python
{
    "session_id": "string",
    "title": "string",
    "room": "string",
    "agenda": ["string"],
    "current_agenda_item": "string",
    "next_agenda_item": "string | None",
}
```

### Audience Profile

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

### Transcript Chunk

```python
{
    "timestamp": "00:00:00",
    "speaker": "string",
    "text": "string",
}
```

### UI Command

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

## Implementation Order

### 1. Repository and App Skeleton

Owner: UI engineer, with backend engineer confirming expected entry points.

Tasks:
- Create a runnable Streamlit app entry point.
- Add a simple app layout with placeholder areas for:
  - Session selector
  - Transcript feed
  - Action zone
  - Audience profile
  - FOMO output
- Add a minimal local run command to the README or app comments if needed.

Done when:
- `streamlit run <app_file>.py` opens a working placeholder HUD.
- The app has stable placeholder containers the backend can later populate.

### 2. Data Discovery and File Loading

Owner: Backend engineer.

Tasks:
- Locate the attendee Excel file and session metadata.
- Implement data loading functions using `pandas` for Excel and standard JSON parsing for metadata.
- Normalize column names and metadata keys into predictable internal names.
- Add defensive handling for missing or malformed files.

Suggested functions:

```python
load_attendees(path) -> pandas.DataFrame
load_sessions(path_or_dir) -> list[dict]
normalize_transcript_chunk(raw_chunk) -> dict
```

Done when:
- Attendee data can be loaded into a dataframe.
- Session metadata can be listed.
- Incoming transcript chunks can be normalized into the shared `Transcript Chunk` shape.

### 3. Session Selection and Audience Profiling

Owner: Backend engineer for logic, UI engineer for display.

Backend tasks:
- Filter registered attendees for the selected room/session.
- Calculate audience profile fields:
  - attendee count
  - AI experience distribution
  - academic background distribution
  - top attending intents
  - beginner ratio
- Return the profile using the shared `Audience Profile` shape.

UI tasks:
- Add a session selector.
- Display selected session title, room, and audience summary.
- Keep the display compact and glanceable.

Done when:
- Selecting a session updates the audience context in the UI.
- Beginner-heavy sessions are easy to identify.

### 4. Live Transcript Ingestion

Owner: Backend engineer for ingestion state, UI engineer for connection controls and feed.

Backend tasks:
- Connect to the real-time transcript source used during the hackathon.
- Normalize each incoming transcript update into the shared `Transcript Chunk` shape.
- Maintain a rolling transcript window.
- Track elapsed topic time or chunk count for fatigue detection.
- Store the latest transcript state in Streamlit session state or a lightweight in-process queue.
- Add clear handling for disconnected, waiting, and receiving states.

UI tasks:
- Add live connection/status controls.
- Show recent transcript chunks in a muted scrolling feed as they arrive.
- Make the feed secondary to the action zone.

Done when:
- The UI can receive and display real transcript chunks.
- The latest transcript chunk is visible.
- The rolling transcript window is available to the analysis layer.

### 5. Rule-Based Analysis First

Owner: Backend engineer.

Build deterministic analysis before adding LLM calls. This gives the UI stable demo data and gives the team a fallback if LLM access is unreliable.

Tasks:
- Audience-aware coaching:
  - If beginner ratio is high and transcript contains technical jargon, emit a high-priority coaching command.
  - Example headline: `Define your terms`
- Topic fatigue:
  - If similar topic terms repeat for too many chunks or too long, emit a fatigue command.
  - Example headline: `Pivot the topic`
- FOMO:
  - If a chunk contains a strong insight and matches attendee intent data, emit a FOMO command.
  - Example headline: `Share this insight`

Done when:
- The backend can return at least one valid `UI Command` for each core feature.
- The Streamlit UI can display these commands without using an LLM.

### 6. Speaker HUD Action Zone

Owner: UI engineer.

Tasks:
- Build the main action zone as the visual focal point.
- Show only the highest-priority current command.
- Keep the headline to 3-7 words.
- Use high-contrast typography and avoid clutter.
- Add priority styling for high, medium, and low priority states.
- Show detail text only as secondary context.

Done when:
- A speaker can glance at the screen and understand the next suggested action immediately.
- The transcript feed and metadata do not compete with the action zone.

### 7. LLM Prompt Chain

Owner: Backend engineer.

Tasks:
- Choose the LLM provider available for the hackathon.
- Build a system prompt that requires concise, actionable UI commands.
- Send only:
  - rolling live transcript window
  - active session metadata
  - audience profile
  - current agenda item
  - next agenda item
- Require structured output matching the `UI Command` schema.
- Add timeout, error handling, and a fallback to the rule-based analyzer.

Prompt constraints:
- Use only transcript text and session metadata.
- Do not invent facts.
- Prefer short action prompts.
- Return neutral when no useful action is needed.

Done when:
- The backend can produce structured commands from an LLM.
- Bad or slow LLM responses do not break the demo.
- Rule-based fallback still works.

### 8. Topic Fatigue HUD

Owner: Backend engineer for detection, UI engineer for presentation.

Backend tasks:
- Track repeated topic concepts over the rolling transcript.
- Compare current topic duration against a simple threshold.
- Include `next_agenda_item` when available.

UI tasks:
- Surface fatigue prompts in the action zone when priority is high.
- Optionally show current topic and duration in a compact secondary panel.

Done when:
- Lingering on one topic produces a clear moderator prompt.
- Example output: `Pivot to Q&A` or `Move to next topic`.

### 9. FOMO Generator

Owner: Backend engineer for matching and generation, UI engineer for display.

Backend tasks:
- Detect highly actionable transcript insights.
- Match insight topics against attendee intent data for people not in the room, if the data supports that distinction.
- Generate short summary snippets for those attendees.

UI tasks:
- Display generated FOMO snippets in a secondary panel.
- Keep this separate from the main speaker action zone.

Done when:
- The app can show at least one real-time FOMO-style snippet based on transcript content and attendee intent.
- The snippet is clearly generated from the current session context.

### 10. Integration Pass

Owners: both engineers.

Tasks:
- Wire the Streamlit UI to real backend functions.
- Remove placeholder data from the main demo path.
- Verify session selection, live transcript ingestion, analysis, and HUD updates work together.
- Make sure Streamlit session state is used consistently.
- Keep module boundaries clear enough for AI agents to edit without stepping on each other.

Done when:
- One command starts the app.
- Selecting a session and receiving transcript chunks updates the HUD continuously.
- At least the audience-aware coaching path works end to end.

### 11. Demo Scenario

Owners: both engineers.

Tasks:
- Pick one best live demo session for judging.
- Ensure the live transcript path can surface:
  - beginner-sensitive jargon
  - one topic that lingers long enough to trigger fatigue
  - one actionable insight suitable for FOMO
- Add a minimal manual fallback input only if the live transcript source fails.
- Prepare a predictable live demo path.

Done when:
- The team can run a 2-3 minute demo with all three MVP features visible.
- The integration with attendee/session data is obvious to judges.

### 12. Polish and Reliability

Owners: both engineers.

Backend tasks:
- Cache loaded data.
- Cache or throttle LLM calls.
- Add clear error messages for missing data or API keys.
- Make fallback analysis reliable.

UI tasks:
- Refine spacing, colors, and typography.
- Keep the layout distraction-free.
- Ensure no text-heavy panels dominate the HUD.
- Verify the app works at common laptop screen sizes.

Done when:
- The demo works after a fresh restart.
- The app still provides useful output if the LLM is unavailable.
- The UI looks intentional and focused.

## Suggested Work Parallelization

### First Parallel Block

Backend engineer:
- Data loading
- Session metadata parsing
- Audience profiling

UI engineer:
- Streamlit skeleton
- Placeholder HUD
- Session selector shell

Integration point:
- UI calls `get_audience_profile(session_id)`.

### Second Parallel Block

Backend engineer:
- Live transcript ingestion
- Rolling transcript window
- Rule-based analysis

UI engineer:
- Transcript feed
- Live transcript status controls
- Action zone styling

Integration point:
- UI receives normalized transcript chunks and calls `analyze_current_context()`.

### Third Parallel Block

Backend engineer:
- LLM structured output
- FOMO matching
- Fallback behavior

UI engineer:
- FOMO panel
- Priority styling
- Final demo layout

Integration point:
- UI renders a list of `UI Command` objects.

## MVP Priority

Build in this order if time is tight:

1. Streamlit app opens.
2. Session and audience data load.
3. Live transcript ingestion works.
4. Audience-aware coaching appears in the action zone.
5. Topic fatigue appears.
6. FOMO snippet appears.
7. LLM improves the quality of prompts.
8. Visual polish.

The minimum successful hackathon demo is a transcript-driven Streamlit HUD that clearly uses attendee context to produce timely speaker guidance.

## Out of Scope for This MVP

- Native real-time audio ingestion.
- Audio-to-audio Realtime API flows.
- Speech rate, intonation, or monotone detection.
- Full public marketing website.
- Production authentication or registration flows.
- Complex multi-room event operations.

# Backend Implementation Order: Live Event Agentic Assistant

## Goal
Build the data pipeline, transcript ingestion, and LLM analysis logic for the real-time speaker HUD. The backend is responsible for processing data and returning structured commands to the Streamlit UI.

*(Note: For UI specific steps, see `frontendOrder.md`. For shared data contracts and state management, see `integrationOrder.md`)*

## Backend / LLM Engineer Responsibilities
Owns the data pipeline, live transcript ingestion, session context, analysis logic, and LLM calls.
- Load and normalize attendee data from `hackathon_mock_attendees.xlsx`.
- Load and normalize session metadata.
- Connect the live transcription source to the analysis pipeline.
- Build the audience profile for the active session.
- Build prompt inputs from rolling transcript context and audience context.
- Implement LLM response parsing into simple UI-ready commands.
- Provide stable functions the UI can call.

## Implementation Order

### 1. Data Discovery and File Loading
**Tasks:**
- Locate the attendee Excel file and session metadata.
- Implement data loading functions using `pandas` for Excel and standard JSON parsing for metadata.
- Normalize column names and metadata keys into predictable internal names.
- Add defensive handling for missing or malformed files.

*Suggested functions:*
```python
load_attendees(path) -> pandas.DataFrame
load_sessions(path_or_dir) -> list[dict]
normalize_transcript_chunk(raw_chunk) -> dict
```

### 2. Session Selection and Audience Profiling
**Tasks:**
- Filter registered attendees for the selected room/session.
- Calculate audience profile fields:
  - attendee count
  - AI experience distribution
  - academic background distribution
  - top attending intents
  - beginner ratio
- Return the profile using the shared `Audience Profile` shape (defined in `integrationOrder.md`).

### 3. Live Transcript Ingestion
**Tasks:**
- Connect to the real-time transcript source used during the hackathon.
- Normalize each incoming transcript update into the shared `Transcript Chunk` shape.
- Maintain a rolling transcript window in memory.
- Track elapsed topic time or chunk count for fatigue detection.
- Add clear handling for disconnected, waiting, and receiving states.

### 4. Rule-Based Analysis First
Build deterministic analysis before adding LLM calls. This gives the UI stable demo data and a fallback if LLM access is unreliable.
**Tasks:**
- **Audience-aware coaching:** If beginner ratio is high and transcript contains technical jargon, emit a high-priority coaching command (e.g., `Define your terms`).
- **Topic fatigue:** If similar topic terms repeat for too many chunks or too long, emit a fatigue command (e.g., `Pivot the topic`).
- **FOMO:** If a chunk contains a strong insight and matches attendee intent data, emit a FOMO command (e.g., `Share this insight`).

### 5. LLM Prompt Chain
**Tasks:**
- Choose the LLM provider available for the hackathon.
- Build a system prompt that requires concise, actionable UI commands.
- Send only: rolling live transcript window, active session metadata, audience profile, current agenda item, next agenda item.
- Require structured output matching the `UI Command` schema.
- Add timeout, error handling, and a fallback to the rule-based analyzer.

*Prompt constraints:*
- Use only transcript text and session metadata. Do not invent facts.
- Prefer short action prompts. Return neutral when no useful action is needed.

### 6. Topic Fatigue HUD logic
**Tasks:**
- Track repeated topic concepts over the rolling transcript.
- Compare current topic duration against a simple threshold.
- Include `next_agenda_item` when available.

### 7. FOMO Generator logic
**Tasks:**
- Detect highly actionable transcript insights.
- Match insight topics against attendee intent data for people not in the room, if the data supports that distinction.
- Generate short summary snippets for those attendees.

## Backend MVP Priority
1. Session and audience data load successfully.
2. Live transcript ingestion works and maintains history.
3. Rule-based analysis returns valid UI Commands.
4. LLM integration accurately improves the quality of the commands.

## Out of Scope for This MVP
- Native real-time audio ingestion.
- Audio-to-audio Realtime API flows.
- Speech rate, intonation, or monotone detection.
- Complex multi-room event operations.

# Frontend Integration Checklist

- Use `data_loading.discover_data_paths()` on app startup to locate the attendee Excel file and session markdown directory.

- Load backend data once and cache it:
  - `load_attendees(paths["attendees"])`
  - `load_sessions(paths["sessions"])`

- Build the session selector from `sessions`.
  - Display each option using `session["title"]`.
  - Store the selected session object in Streamlit session state.

- When a session is selected, build the audience profile:
  - `get_audience_profile(attendees, sessions, session["session_id"])`
  - Display `attendee_count`, `beginner_ratio`, `top_intents`, and `intent_distribution`.

- Create one `TranscriptIngestionState` per active session.
  - Store it in `st.session_state`.
  - Reset it when the selected session changes.

- For demo mode, use:
  - `replay_transcript_file(session["path"], ingestion_state, delay_seconds=...)`

- For real live transcription, push each incoming transcript chunk into:
  - `await ingestion_state.push(raw_chunk)`

- Render transcript feed from:
  - `ingestion_state.rolling_window()`

- Render connection/status UI from:
  - `ingestion_state.snapshot()["status"]`
  - `ingestion_state.snapshot()["latest_chunk"]`
  - `ingestion_state.snapshot()["last_error"]`

- Start backend analysis with:
  - `analyze_live_text_flow(...)`

- Pass these arguments to `analyze_live_text_flow`:
  - `ingestion_state.chunks()`
  - selected `session`
  - `audience_profile`
  - `client=AsyncOpenAI()` when API access is available
  - `analysis_interval_seconds=5.0`

- Store the latest returned `UICommand` in Streamlit session state.

- Render the action zone from the latest command:
  - `command.headline` as the main large text
  - `command.detail` as secondary text
  - `command.type` for category styling
  - `command.priority` for urgency styling
  - `command.related_topic` as optional small context

- Do not expect a `target` field. It was removed from `UICommand`.

- Expected `UICommand` shape:

```python
{
    "type": "coaching | fatigue | fomo | neutral",
    "priority": "low | medium | high",
    "headline": "3-7 word action prompt",
    "detail": "short explanation",
    "related_topic": "string | None",
}
```

- Treat `neutral` commands as low-urgency idle state.
  - Example UI text: show the headline quietly or keep the previous non-neutral command dimmed, depending on design choice.

- Use `type == "fatigue"` for topic/agenda pacing prompts.

- Use `type == "fomo"` for shareable insight snippets.

- Use `type == "coaching"` for speaker/moderator guidance.

- Do not implement frontend keyword detection for jargon, FOMO, or fatigue.
  - The backend sends rolling context to the LLM.
  - The model decides the command type.

- Add loading/processing state while waiting for the next 5-second analysis result.

- Keep transcript feed visually secondary to the action zone.

- Keep the action zone focused on one current command, not a long list.

- If no OpenAI API key/client is available, backend will return neutral fallback commands.

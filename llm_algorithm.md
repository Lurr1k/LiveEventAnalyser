# Time-Slotted Live Transcript Analysis

The intended backend algorithm is LLM-led. The backend should not try to detect jargon, fatigue, or FOMO with keyword lists. It should collect live transcript chunks into a rolling window and ask `gpt-5.4-mini` to analyze that window on a fixed cadence, for example every 5 seconds.

## Runtime Flow

1. Load attendee and session context once:
   - `load_attendees("../Data/hackathon_mock_attendees.xlsx")`
   - `load_sessions("../Data/sessions")`
   - `get_audience_profile(...)`
2. Start live transcript ingestion.
3. Normalize every incoming transcript chunk into:

```python
{"timestamp": "00:00:00", "speaker": "Speaker 1", "text": "..."}
```

4. Append normalized chunks to a bounded rolling transcript window.
5. Every analysis slot, default `5.0` seconds, send the current rolling window to `gpt-5.4-mini`.
6. Ask the model for exactly one structured UI command.
7. If no new transcript arrived since the previous slot, skip that slot.
8. If the model is unavailable, return a neutral fallback command so the HUD stays valid.

## What The Backend Does Not Do

The backend does not maintain lists of jargon words, insight phrases, or fatigue keywords. Those judgments belong to the model because they depend on session context, audience profile, phrasing, and the evolving discussion.

The only non-LLM fallback is neutral:

```python
{
    "type": "neutral",
    "priority": "low",
    "headline": "Keep listening",
    "detail": "No model analysis is available for this time window.",
    "target": "speaker",
    "related_topic": None,
}
```

## Prompt

```text
You are the live analysis engine for a real-time speaker HUD.

Analyze only the supplied rolling transcript, session metadata, agenda, and audience profile.
Do not invent facts, names, audience traits, or claims that are not present in the input.

Return exactly one UI command as JSON. The command must help a speaker or moderator act now.
Use "neutral" when no useful action is needed.

Rules:
- headline must be 3-7 words.
- detail must be one short sentence.
- priority should be high only for urgent clarity, fatigue, or strong FOMO moments.
- coaching means audience-aware clarity or engagement advice.
- fatigue means the same topic is lingering or repeating.
- fomo means a concise shareable insight for absent or adjacent-interest attendees.
- neutral means keep listening.
```

## Usage

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

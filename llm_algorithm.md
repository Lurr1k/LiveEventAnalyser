# Async Live Transcript Analysis Algorithm

This backend path implements step 7 from `order.md`: feed a rolling live transcript window plus session and audience context into `gpt-5.4-mini`, then return one structured `UI Command`.

## Flow

1. Load attendee rows from `../Data/hackathon_mock_attendees.xlsx`.
2. Load session metadata from `../Data/sessions/*.md`.
3. Build the active audience profile:
   - attendee count
   - AI experience distribution
   - academic background distribution
   - top attendee intents
   - beginner ratio
4. Normalize each live transcript update into:

```python
{"timestamp": "00:00:00", "speaker": "Speaker 1", "text": "..."}
```

5. Append each chunk to a bounded rolling transcript window.
6. Throttle analysis calls so the model is not called on every token.
7. Run deterministic rules first as a fallback signal:
   - beginner-heavy audience plus jargon -> coaching
   - repeated topic terms -> fatigue
   - strong takeaway language -> FOMO
8. Send the rolling transcript, session context, audience profile, and fallback signal to `gpt-5.4-mini`.
9. Require strict JSON matching the `UI Command` schema.
10. If the model is unavailable, slow, or returns invalid JSON, return the rule-based command.

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
from live_analysis import (
    analyze_live_text_flow,
    build_audience_profile,
    load_attendees,
    load_sessions,
    stream_transcript_file,
)

async def main():
    attendees = load_attendees("../Data/hackathon_mock_attendees.xlsx")
    session = load_sessions("../Data/sessions")[0]
    profile = build_audience_profile(attendees, session["session_id"], session["room"])

    client = AsyncOpenAI()
    transcript_source = stream_transcript_file(session["path"], delay_seconds=0.2)

    async for command in analyze_live_text_flow(
        transcript_source,
        session,
        profile,
        client=client,
        model="gpt-5.4-mini",
    ):
        print(command)

asyncio.run(main())
```

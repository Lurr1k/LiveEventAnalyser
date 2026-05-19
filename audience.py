from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


SESSION_ID_COLUMNS = (
    "session_id",
    "registered_session_id",
    "selected_session_id",
    "current_session_id",
)
SESSION_TITLE_COLUMNS = (
    "session_title",
    "registered_session",
    "selected_session",
    "current_session",
)
ROOM_COLUMNS = (
    "room",
    "session_room",
    "registered_room",
    "selected_room",
    "current_room",
)


def get_session_by_id(
    sessions: Iterable[dict[str, Any]], session_id: str
) -> dict[str, Any]:
    for session in sessions:
        if str(session.get("session_id")) == str(session_id):
            return session
    raise ValueError(f"Unknown session_id: {session_id}")


def filter_attendees_for_session(attendees: Any, session: dict[str, Any]):
    """Return attendees registered for a session when registration fields exist.

    The current mock Excel file has attendee traits but no per-session room
    assignment, so this intentionally returns the full frame/list in that case.
    """
    if _is_dataframe(attendees):
        return _filter_dataframe_attendees(attendees, session)

    rows = list(attendees)
    if not rows:
        return rows

    session_id_key = _first_existing_key(rows[0], SESSION_ID_COLUMNS)
    if session_id_key:
        session_id = str(session.get("session_id", "")).lower()
        return [
            row for row in rows if str(row.get(session_id_key, "")).lower() == session_id
        ]

    session_title_key = _first_existing_key(rows[0], SESSION_TITLE_COLUMNS)
    if session_title_key:
        title = str(session.get("title", "")).lower()
        return [
            row for row in rows if str(row.get(session_title_key, "")).lower() == title
        ]

    room_key = _first_existing_key(rows[0], ROOM_COLUMNS)
    if room_key:
        room = str(session.get("room", "")).lower()
        return [row for row in rows if str(row.get(room_key, "")).lower() == room]

    return rows


def build_audience_profile(
    attendees: Any,
    session_id: str,
    room: str | None = None,
    *,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if session is None:
        session = {"session_id": session_id, "room": room}

    filtered_attendees = filter_attendees_for_session(attendees, session)
    rows = _to_records(filtered_attendees)

    experience = _value_counts(rows, "ai_experience_level")
    backgrounds = _value_counts(rows, "academic_background")
    intents = _value_counts(rows, "intent_of_attending", "intent_of_attending_track")
    beginner_count = experience.get("Beginner", 0)
    attendee_count = len(rows)

    profile = {
        "session_id": str(session_id),
        "attendee_count": attendee_count,
        "ai_experience_distribution": _with_expected_experience_keys(experience),
        "academic_background_distribution": dict(backgrounds),
        "intent_distribution": dict(intents),
        "top_intents": [intent for intent, _ in intents.most_common(5)],
        "beginner_ratio": beginner_count / attendee_count if attendee_count else 0.0,
    }

    if session.get("title"):
        profile["session_title"] = session["title"]
    if session.get("room"):
        profile["room"] = session["room"]

    return profile


def get_audience_profile(
    attendees: Any,
    sessions: Iterable[dict[str, Any]],
    session_id: str,
) -> dict[str, Any]:
    session = get_session_by_id(sessions, session_id)
    return build_audience_profile(
        attendees,
        str(session["session_id"]),
        str(session.get("room") or ""),
        session=session,
    )


def _filter_dataframe_attendees(attendees: Any, session: dict[str, Any]):
    columns = set(attendees.columns)

    session_id_key = _first_existing_name(columns, SESSION_ID_COLUMNS)
    if session_id_key:
        session_id = str(session.get("session_id", "")).lower()
        return attendees[
            attendees[session_id_key].astype(str).str.lower() == session_id
        ]

    session_title_key = _first_existing_name(columns, SESSION_TITLE_COLUMNS)
    if session_title_key:
        title = str(session.get("title", "")).lower()
        return attendees[
            attendees[session_title_key].astype(str).str.lower() == title
        ]

    room_key = _first_existing_name(columns, ROOM_COLUMNS)
    if room_key:
        room = str(session.get("room", "")).lower()
        return attendees[attendees[room_key].astype(str).str.lower() == room]

    return attendees


def _to_records(attendees: Any) -> list[dict[str, Any]]:
    if _is_dataframe(attendees):
        return attendees.to_dict(orient="records")
    return list(attendees)


def _value_counts(rows: list[dict[str, Any]], *keys: str) -> Counter[str]:
    values = Counter()
    for row in rows:
        value = None
        for key in keys:
            value = row.get(key)
            if value:
                break
        values[str(value or "Unknown")] += 1
    return values


def _with_expected_experience_keys(counts: Counter[str]) -> dict[str, int]:
    distribution = {
        "Beginner": counts.get("Beginner", 0),
        "Intermediate": counts.get("Intermediate", 0),
        "Advanced": counts.get("Advanced", 0),
    }
    for level, count in counts.items():
        distribution.setdefault(level, count)
    return distribution


def _first_existing_key(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    return next((key for key in keys if key in row), None)


def _first_existing_name(names: set[str], keys: tuple[str, ...]) -> str | None:
    return next((key for key in keys if key in names), None)


def _is_dataframe(value: Any) -> bool:
    return hasattr(value, "to_dict") and hasattr(value, "columns")

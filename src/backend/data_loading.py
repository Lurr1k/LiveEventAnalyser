from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


EXPECTED_ATTENDEE_COLUMNS = {
    "id",
    "full_name",
    "university_affiliation",
    "academic_background",
    "ai_experience_level",
    "intent_of_attending",
    "goal_of_the_event",
}


class DataLoadingError(RuntimeError):
    """Raised when demo data is missing or cannot be normalized."""


def discover_data_paths(project_root: str | Path | None = None) -> dict[str, Path]:
    root = Path(project_root) if project_root else Path(__file__).resolve().parent.parent
    data_dir = root / "Data"
    return {
        "data_dir": data_dir,
        "attendees": data_dir / "hackathon_mock_attendees.xlsx",
        "sessions": data_dir / "sessions",
    }


def load_attendees(path: str | Path):
    """Load and normalize the attendee Excel file into a pandas DataFrame."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise DataLoadingError(
            "pandas is required to load attendee Excel data. "
            "Install project dependencies before running the app."
        ) from exc

    attendee_path = Path(path)
    if not attendee_path.exists():
        raise DataLoadingError(f"Attendee file not found: {attendee_path}")
    if attendee_path.suffix.lower() not in {".xlsx", ".xls"}:
        raise DataLoadingError(f"Expected an Excel attendee file, got: {attendee_path}")

    try:
        frame = pd.read_excel(attendee_path)
    except Exception as exc:
        raise DataLoadingError(f"Could not read attendee Excel file: {attendee_path}") from exc

    frame = frame.rename(columns={column: _normalize_key(str(column)) for column in frame.columns})
    frame = frame.fillna("")

    missing = sorted(EXPECTED_ATTENDEE_COLUMNS - set(frame.columns))
    if missing:
        raise DataLoadingError(
            f"Attendee file is missing expected columns: {', '.join(missing)}"
        )

    for column in frame.columns:
        if frame[column].dtype == "object":
            frame[column] = frame[column].astype(str).str.strip()

    return frame


def load_sessions(path_or_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(path_or_dir)
    if not path.exists():
        raise DataLoadingError(f"Session path not found: {path}")

    files = [path] if path.is_file() else sorted(path.glob("*.md"))
    if not files:
        raise DataLoadingError(f"No session markdown files found in: {path}")

    sessions: list[dict[str, Any]] = []
    for file_path in files:
        try:
            text = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DataLoadingError(f"Could not read session file: {file_path}") from exc

        metadata = _extract_metadata(text, file_path)
        normalized_metadata = {
            _normalize_key(str(key)): value for key, value in metadata.items()
        }
        title = str(metadata.get("title") or _title_from_filename(file_path))
        tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []

        sessions.append(
            {
                "session_id": file_path.stem.split("__")[-1],
                "title": title,
                "room": str(metadata.get("event_name") or "START Summit Stage"),
                "agenda": [str(tag) for tag in tags],
                "current_agenda_item": str(metadata.get("summary") or title),
                "next_agenda_item": None,
                "metadata": normalized_metadata,
                "path": str(file_path),
            }
        )

    return sessions


def normalize_transcript_chunk(raw_chunk: dict[str, Any] | str) -> dict[str, str]:
    if isinstance(raw_chunk, str):
        match = re.match(r"\[(?P<time>[^\]]+)\]\s*(?P<speaker>[^:]+):\s*(?P<text>.*)", raw_chunk)
        if match:
            return {
                "timestamp": match.group("time").strip(),
                "speaker": match.group("speaker").strip(),
                "text": match.group("text").strip(),
            }
        return {"timestamp": "00:00:00", "speaker": "Speaker", "text": raw_chunk.strip()}

    timestamp = raw_chunk.get("timestamp") or raw_chunk.get("time") or "00:00:00"
    speaker = raw_chunk.get("speaker") or raw_chunk.get("speaker_name") or "Speaker"
    text = raw_chunk.get("text") or raw_chunk.get("transcript") or raw_chunk.get("content") or ""
    return {
        "timestamp": str(timestamp).strip(),
        "speaker": str(speaker).strip() or "Speaker",
        "text": str(text).strip(),
    }


def _extract_metadata(markdown: str, file_path: Path) -> dict[str, Any]:
    match = re.search(r"## Metadata\s+```json\s*(.*?)\s*```", markdown, re.DOTALL)
    if not match:
        return {}

    try:
        metadata = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise DataLoadingError(f"Malformed metadata JSON in session file: {file_path}") from exc

    if not isinstance(metadata, dict):
        raise DataLoadingError(f"Metadata JSON must be an object in: {file_path}")
    return metadata


def _normalize_key(value: str) -> str:
    key = value.lower().strip()
    key = re.sub(r"\([^)]*\)", "", key)
    key = re.sub(r"[^a-z0-9]+", "_", key)
    return key.strip("_")


def _title_from_filename(file_path: Path) -> str:
    stem = file_path.stem.split("__")[0]
    return stem.replace("-", " ").title()

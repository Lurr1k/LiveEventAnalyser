import sys
from pathlib import Path
import streamlit as st

# Ensure backend imports work
sys.path.append(str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
except ImportError:
    pass

from backend.data_loading import discover_data_paths, load_attendees, load_sessions
from backend.audience import get_audience_profile
from frontend.state import SessionStateManager
from frontend.components import (
    render_analysis_status,
    render_browser_microphone,
    render_sidebar,
    render_transcript,
    render_transcription_diagnostics,
    render_action_zone,
)

def init_app_state():
    if "paths" not in st.session_state:
        st.session_state.paths = discover_data_paths()
    if "attendees" not in st.session_state:
        st.session_state.attendees = load_attendees(st.session_state.paths["attendees"])
    if "sessions" not in st.session_state:
        st.session_state.sessions = load_sessions(st.session_state.paths["sessions"])
    if "state_manager" not in st.session_state:
        st.session_state.state_manager = SessionStateManager()
        
def main():
    st.set_page_config(
        page_title="Live Event Analyser HUD",
        page_icon="🎙️",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    init_app_state()
    
    sessions = st.session_state.sessions
    attendees = st.session_state.attendees
    manager = st.session_state.state_manager
    
    # Get current backend state
    backend_state = manager.get_state()
    is_running = backend_state["is_running"]
    
    # Render Sidebar and get interactions
    selected_id = sessions[0]["session_id"] if sessions else None
    
    # We only compute profile for the selected session
    profile = None
    if selected_id:
        # Default selected profile on initial load
        if "selected_id" in st.session_state:
            selected_id = st.session_state.selected_id
        profile = get_audience_profile(attendees, sessions, selected_id)
        
    new_selected_id, transcript_source, action = render_sidebar(
        sessions,
        attendees,
        profile,
        is_running,
    )
    
    if new_selected_id != selected_id:
        st.session_state.selected_id = new_selected_id
        st.rerun()
        
    if action == "start":
        session = next(s for s in sessions if s["session_id"] == new_selected_id)
        # Recompute profile just in case
        profile = get_audience_profile(attendees, sessions, new_selected_id)
        manager.start(session, profile, source=transcript_source)
        st.rerun()
    elif action == "stop":
        manager.stop()
        st.rerun()
        
    # Main Layout
    if backend_state["error"]:
        st.error(f"Backend Error: {backend_state['error']}")

    render_browser_microphone(
        manager,
        enabled=is_running and backend_state.get("source") in {"browser_mic", "elevenlabs_live"},
    )
    render_live_hud(manager)

def render_live_hud(manager):
    if hasattr(st, "fragment"):
        @st.fragment(run_every="1s")
        def live_hud_fragment():
            _render_live_hud_body(manager)

        live_hud_fragment()
        return

    _render_live_hud_body(manager)


def _render_live_hud_body(manager):
    state = manager.get_state()
    render_analysis_status(state)
    render_transcription_diagnostics(state)
    render_action_zone(state["latest_command"])
    render_transcript(
        state["transcript_chunks"],
        status=state.get("ingestion_status", "disconnected"),
        error=state.get("ingestion_error"),
    )


if __name__ == "__main__":
    main()

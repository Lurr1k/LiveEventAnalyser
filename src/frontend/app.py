import sys
from pathlib import Path
import time
import streamlit as st

# Ensure backend imports work
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.data_loading import discover_data_paths, load_attendees, load_sessions
from backend.audience import get_audience_profile
from frontend.state import SessionStateManager
from frontend.components import render_sidebar, render_transcript, render_action_zone

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
        
    new_selected_id, action = render_sidebar(sessions, attendees, profile, is_running)
    
    if new_selected_id != selected_id:
        st.session_state.selected_id = new_selected_id
        st.rerun()
        
    if action == "start":
        session = next(s for s in sessions if s["session_id"] == new_selected_id)
        # Recompute profile just in case
        profile = get_audience_profile(attendees, sessions, new_selected_id)
        manager.start(session, profile)
        st.rerun()
    elif action == "stop":
        manager.stop()
        st.rerun()
        
    # Main Layout
    if backend_state["error"]:
        st.error(f"Backend Error: {backend_state['error']}")
        
    render_action_zone(backend_state["latest_command"])
    render_transcript(backend_state["transcript_chunks"])
    
    # Auto-refresh loop if the backend is running
    if is_running:
        time.sleep(1) # Refresh every second
        st.rerun()

if __name__ == "__main__":
    main()

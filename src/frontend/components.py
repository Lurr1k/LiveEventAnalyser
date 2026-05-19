import streamlit as st

def render_sidebar(sessions, attendees, profile, is_running):
    """Render the sidebar with session selection and audience profile."""
    with st.sidebar:
        st.title("Event Controls")
        
        # Session Selection
        session_options = {s["session_id"]: s for s in sessions}
        session_names = {s["session_id"]: s["title"] for s in sessions}
        
        selected_id = st.selectbox(
            "Select Session",
            options=list(session_options.keys()),
            format_func=lambda x: session_names[x],
            disabled=is_running
        )
        
        if is_running:
            if st.button("Stop Session", use_container_width=True):
                return selected_id, "stop"
        else:
            if st.button("Start Session", type="primary", use_container_width=True):
                return selected_id, "start"
                
        st.divider()
        
        # Audience Profile
        if profile:
            st.subheader("Audience Profile")
            st.metric("Total Attendees", profile["attendee_count"])
            
            beginner_ratio = profile.get("beginner_ratio", 0)
            st.write(f"Beginner Ratio: {beginner_ratio:.0%}")
            st.progress(beginner_ratio)
            
            st.write("**Top Intents:**")
            for intent in profile.get("top_intents", []):
                st.caption(f"- {intent}")
                
    return selected_id, "none"

def render_transcript(chunks):
    """Render the rolling transcript feed at the top."""
    st.subheader("Live Transcript Feed")
    
    # Use a container with a fixed height and scrollbar for the transcript
    feed_container = st.container(height=300)
    
    with feed_container:
        if not chunks:
            st.info("Waiting for transcript...")
        else:
            # Render chunks in reverse order (newest at top) to avoid scrolling issues
            total = len(chunks)
            for i, chunk in enumerate(reversed(chunks)):
                # Calculate fading opacity (1.0 for newest, down to 0.3 for oldest)
                alpha = 1.0 - (0.7 * (i / max(1, total - 1)))
                
                # Basic parsing to bold the speaker name
                formatted_chunk = chunk
                if "]" in chunk and ":" in chunk:
                    try:
                        time_part, rest = chunk.split("]", 1)
                        speaker, text = rest.split(":", 1)
                        formatted_chunk = f"**{time_part}]{speaker}:** {text}"
                    except ValueError:
                        pass
                
                # Apply opacity using HTML span
                st.markdown(f'<span style="opacity: {alpha:.2f}; display: block; margin-bottom: 0.5rem;">{formatted_chunk}</span>', unsafe_allow_html=True)

def render_action_zone(command):
    """Render the action zone at the bottom, prioritizing LLM commands."""
    st.divider()
    st.subheader("Action Zone")
    
    if not command:
        st.info("Waiting for analysis...")
        return
        
    # Pick colors based on priority
    # Using Streamlit info/warning/error/success boxes as a vanilla starting point
    if command.priority == "high":
        box = st.error
    elif command.priority == "medium":
        box = st.warning
    else:
        # For neutral or low priority coaching
        if command.type == "neutral":
            box = st.info
        else:
            box = st.success
            
    icon = "💡" if command.type != "neutral" else "ℹ️"
    
    body = f"### {command.headline}\n\n{command.detail}"
    if command.related_topic:
        body += f"\n\n*Related Topic:* {command.related_topic}"
        
    box(body, icon=icon)

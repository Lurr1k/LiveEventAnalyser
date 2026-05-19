from html import escape

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

        source = st.selectbox(
            "Transcript Source",
            options=["elevenlabs_live", "demo_markdown"],
            format_func=lambda value: {
                "elevenlabs_live": "ElevenLabs live mic",
                "demo_markdown": "Demo markdown replay",
            }[value],
            disabled=is_running,
        )
        
        if is_running:
            if st.button("Stop Session", use_container_width=True):
                return selected_id, source, "stop"
        else:
            if st.button("Start Session", type="primary", use_container_width=True):
                return selected_id, source, "start"
                
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
                
    return selected_id, source, "none"

def render_transcript(chunks, *, status="disconnected", error=None):
    """Render the rolling transcript feed at the bottom."""
    st.subheader("Live Transcript")
    st.caption(f"Transcription status: {status}")
    if error:
        st.warning(error)
    
    if not chunks:
        st.info("Waiting for transcript...")
        return

    html_lines = []
    total = len(chunks)
    for i, chunk in enumerate(chunks):
        # Base fading on distance from the bottom (newest is always 1.0, older chunks fade out)
        distance_from_bottom = total - 1 - i
        alpha = max(0.2, 1.0 - (distance_from_bottom / 15.0) * 0.8)
        
        timestamp = escape(str(chunk.get("timestamp", "00:00:00")))
        speaker = escape(str(chunk.get("speaker", "Speaker")))
        text = escape(str(chunk.get("text", "")))
        formatted_chunk = f"<strong>[{timestamp}] {speaker}:</strong> {text}"
        html_lines.append(f'<div style="opacity: {alpha:.2f}; margin-bottom: 0.5rem; line-height: 1.5;">{formatted_chunk}</div>')

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
    /* Hide scrollbar for Chrome, Safari and Opera */
    ::-webkit-scrollbar {{
        display: none;
    }}
    body {{
        margin: 0;
        padding: 0 10px 10px 0;
        background-color: #0E1117;
        color: rgb(250, 250, 250);
        font-family: "Source Sans Pro", sans-serif;
        font-size: 16px;
        /* Hide scrollbar for IE, Edge and Firefox */
        -ms-overflow-style: none;  
        scrollbar-width: none;  
    }}
    </style>
    </head>
    <body>
        {''.join(html_lines)}
    <script>
        window.scrollTo(0, document.body.scrollHeight);
    </script>
    </body>
    </html>
    """
    
    import streamlit.components.v1 as components
    components.html(html_content, height=300, scrolling=True)

def render_action_zone(command):
    """Render the action zone, centered with large font and priority colors."""
    if not command:
        st.markdown(
            '<div style="text-align: center; padding: 3rem; color: #888;"><h3>Waiting for analysis...</h3></div>', 
            unsafe_allow_html=True
        )
        return
        
    # Pick colors based on priority to mimic Streamlit's native alerts
    if command.priority == "high":
        bg_color = "rgba(255, 75, 75, 0.15)"
        border_color = "rgb(255, 75, 75)"
    elif command.priority == "medium":
        bg_color = "rgba(255, 193, 7, 0.15)"
        border_color = "rgb(255, 193, 7)"
    else:
        # For neutral or low priority coaching
        if command.type == "neutral":
            bg_color = "rgba(43, 123, 255, 0.15)"
            border_color = "rgb(43, 123, 255)"
        else:
            bg_color = "rgba(9, 171, 59, 0.15)"
            border_color = "rgb(9, 171, 59)"
            
    html = f"""
    <div style="background-color: {bg_color}; border: 2px solid {border_color}; border-radius: 1rem; padding: 3rem 2rem; text-align: center; margin: 1rem 0 3rem 0; box-shadow: 0 4px 20px rgba(0,0,0,0.2);">
        <h1 style="margin-top: 0; margin-bottom: 1rem; font-size: 3.5rem; line-height: 1.2;">{command.headline}</h1>
        <p style="font-size: 1.5rem; color: #E0E0E0; margin-bottom: 0;">{command.detail}</p>
        {f'<p style="font-size: 1rem; color: #999; margin-top: 1rem;"><em>Related Topic: {command.related_topic}</em></p>' if command.related_topic else ''}
    </div>
    """
    
    st.markdown(html, unsafe_allow_html=True)

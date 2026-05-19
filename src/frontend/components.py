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
    
    if not chunks:
        st.info("Waiting for transcript...")
        return

    html_lines = []
    total = len(chunks)
    for i, chunk in enumerate(chunks):
        # Calculate fading opacity (0.3 for oldest, 1.0 for newest)
        alpha = 0.3 + (0.7 * (i / max(1, total - 1))) if total > 1 else 1.0
        
        formatted_chunk = chunk
        if "]" in chunk and ":" in chunk:
            try:
                time_part, rest = chunk.split("]", 1)
                speaker, text = rest.split(":", 1)
                formatted_chunk = f"<strong>{time_part}]{speaker}:</strong> {text}"
            except ValueError:
                pass
        
        html_lines.append(f'<div style="opacity: {alpha:.2f}; margin-bottom: 0.5rem; line-height: 1.5;">{formatted_chunk}</div>')

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
    body {{
        margin: 0;
        padding: 0 10px 10px 0;
        background-color: #0E1117;
        color: rgb(250, 250, 250);
        font-family: "Source Sans Pro", sans-serif;
        font-size: 16px;
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
            
    body = f"### {command.headline}\n\n{command.detail}"
    if command.related_topic:
        body += f"\n\n*Related Topic:* {command.related_topic}"
        
    box(body, icon=None)

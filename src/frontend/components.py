from html import escape

import streamlit as st

def render_sidebar(sessions, attendees, profile, is_running):
    """Render the sidebar with session selection and audience profile."""
    with st.sidebar:
        st.title("Event Controls")
        
        source = st.selectbox(
            "Transcript Source",
            options=["browser_mic", "demo_markdown"],
            index=1,
            format_func=lambda value: {
                "browser_mic": "Browser mic",
                "demo_markdown": "Demo replay",
            }[value],
            disabled=is_running,
        )
        
        # Session Selection
        session_options = {s["session_id"]: s for s in sessions}
        session_names = {s["session_id"]: s["title"] for s in sessions}
        
        selected_id = st.selectbox(
            "Select Session",
            options=list(session_options.keys()),
            format_func=lambda x: session_names[x],
            disabled=is_running or source == "browser_mic"
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


def render_browser_microphone(manager, *, enabled: bool):
    """Render browser microphone capture for the live ElevenLabs source."""
    if not enabled:
        return

    st.caption("Browser microphone capture")
    try:
        import av
        from streamlit_webrtc import WebRtcMode, webrtc_streamer
        from streamlit_webrtc.webrtc import SignallingTimeoutError
    except ImportError:
        st.error("Browser mic capture requires streamlit-webrtc and av.")
        return

    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)

    def audio_frame_callback(frame):
        for resampled in resampler.resample(frame):
            manager.submit_audio_chunk(resampled.to_ndarray().tobytes())
        return frame

    retry = st.session_state.get("browser_mic_retry", 0)
    try:
        context = webrtc_streamer(
            key=f"browser-mic-elevenlabs-{retry}",
            mode=WebRtcMode.SENDONLY,
            audio_frame_callback=audio_frame_callback,
            media_stream_constraints={"video": False, "audio": True},
            rtc_configuration={"iceServers": []},
            async_processing=True,
        )
    except SignallingTimeoutError:
        st.warning(
            "Browser microphone setup timed out before WebRTC finished signalling. "
            "This can happen on the first attempt; retry the mic component."
        )
        if st.button("Retry microphone", use_container_width=True):
            st.session_state.browser_mic_retry = retry + 1
            st.rerun()
        return

    playing = bool(getattr(getattr(context, "state", None), "playing", False))
    st.caption(f"WebRTC: {'recording' if playing else 'waiting for browser mic'}")


def render_analysis_status(state):
    status = state.get("analysis_status", "idle")
    if status == "model":
        st.caption("Analysis: model")
    elif status == "fallback":
        st.warning(f"Analysis fallback: {state.get('analysis_error') or 'No model output.'}")
    elif state.get("is_running"):
        st.caption("Analysis: waiting for transcript window")


def render_transcription_diagnostics(state):
    if not state.get("is_running"):
        return

    audio_count = state.get("audio_chunk_count", 0)
    last_audio = _relative_time(state.get("last_audio_chunk_at"))
    last_event = state.get("last_elevenlabs_event_type") or "none"
    last_event_at = _relative_time(state.get("last_elevenlabs_event_at"))
    elevenlabs_status = "connected" if state.get("elevenlabs_connected") else "waiting"
    close_error = state.get("elevenlabs_close_error")
    attempts = state.get("elevenlabs_connection_attempts", 0)

    st.caption(
        " | ".join(
            [
                f"Browser audio chunks: {audio_count}",
                f"last audio: {last_audio}",
                f"ElevenLabs: {elevenlabs_status}",
                f"attempts: {attempts}",
                f"last event: {last_event} ({last_event_at})",
            ]
        )
    )
    if close_error:
        st.warning(close_error)

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
            
    headline = escape(str(command.headline))
    detail = escape(str(command.detail))
    related_topic = escape(str(command.related_topic)) if command.related_topic else ""

    html = f"""
    <div style="background-color: {bg_color}; border: 2px solid {border_color}; border-radius: 1rem; padding: 3rem 2rem; text-align: center; margin: 1rem 0 3rem 0; box-shadow: 0 4px 20px rgba(0,0,0,0.2);">
        <h1 style="margin-top: 0; margin-bottom: 1rem; font-size: 3.5rem; line-height: 1.2;">{headline}</h1>
        <p style="font-size: 1.5rem; color: #E0E0E0; margin-bottom: 0;">{detail}</p>
        {f'<p style="font-size: 1rem; color: #999; margin-top: 1rem;"><em>Related Topic: {related_topic}</em></p>' if related_topic else ''}
    </div>
    """
    
    st.markdown(html, unsafe_allow_html=True)


def _relative_time(timestamp):
    if not timestamp:
        return "never"
    try:
        import time

        elapsed = max(0.0, time.time() - float(timestamp))
    except (TypeError, ValueError):
        return "unknown"
    if elapsed < 1:
        return "now"
    return f"{elapsed:.0f}s ago"

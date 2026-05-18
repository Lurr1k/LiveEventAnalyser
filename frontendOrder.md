# Frontend Implementation Order: Live Event Agentic Assistant

## Goal
Build the UI/UX for the "Live Event Agentic Assistant" using Streamlit. The interface needs to act as a distraction-free, terminal-inspired heads-up display (HUD) for speakers and moderators. 

## Approach & Recommendation: Where to Start?
**Recommendation: Start with the Main Dashboard HUD Skeleton first, then bolt on the Session Selection ("Splash") later.** 

*Why?* The core value of this hackathon project is the real-time Speaker HUD (the action zone). If you start by perfecting a splash screen or event creation form, you risk running out of time for the most critical piece. 
1. Build the skeleton of the HUD with placeholder/dummy data.
2. Ensure the layout (Action Zone, Transcript Feed, FOMO snippets) looks great and is easily readable from a distance.
3. Once the HUD layout is solid, build the "Session Selector" (Splash Screen) which will simply act as a gateway to populate the HUD with the correct session context.

---

## Implementation Phases

### Phase 1: App Skeleton & The "Ugly" Layout
**Goal:** Get the Streamlit app running and define the visual grid. Do not worry about styling yet.
*   **Initialize:** Set up `main.py` with `import streamlit as st`.
*   **Page Config:** Set `st.set_page_config(layout="wide")` to maximize screen real estate.
*   **Grid Structure:** Use `st.columns()` to rough out the main areas:
    *   **Sidebar/Top Bar:** For the eventual Session Selection and status indicators.
    *   **Left/Main Column (70%):** The Speaker Action Zone (Big text) and the recent transcript feed.
    *   **Right Column (30%):** Secondary context (Audience Profile, Topic Fatigue stats, FOMO snippets).
*   **Placeholder Data:** Hardcode some fake strings into these zones just to see where they render.

### Phase 2: The Core Speaker HUD (Visual Polish)
**Goal:** Make the Action Zone look like a premium, distraction-free HUD.
*   **The Action Zone:** This is the most important part of the app. Use custom HTML/CSS via `st.markdown("<style>...</style>", unsafe_allow_html=True)` to create a massive, high-contrast text area.
    *   Example: A dark, terminal-like background with bright, bold text.
    *   Implement priority colors (e.g., Red for high-priority "Define Terms", Yellow for "Pivot Topic", Muted Green for "Neutral").
*   **The Transcript Feed:** Create a container that displays the last ~5 chunks of text. Style it to be muted/grayed out so it doesn't distract from the Action Zone.
*   **Responsiveness Check:** Ensure the text remains readable if the browser window is resized.

### Phase 3: The Session Selector (The "Splash" State)
**Goal:** Build the interface to select which event/session is currently active.
*   **State Management:** Use `st.session_state` to track if a session has been selected.
*   **The UI:** If no session is selected (or in a sidebar), show a clean dropdown or set of buttons to pick a session (e.g., "AI in Business Panel").
*   **Audience Profile Display:** Once a session is selected, render the audience metrics (Beginner Ratio, Top Intents) in the secondary context column using Streamlit metrics or simple charts (`st.progress` or `st.metric`).

### Phase 4: Dynamic Integration (Wiring to Backend)
**Goal:** Connect the UI components to the data structures defined by the backend engineer.
*   **Transcript Ingestion:** Set up an auto-refreshing loop (using `st_autorefresh` or Streamlit's native rerun capabilities) to poll for new transcript chunks.
*   **State Updates:** Write the logic that updates the Action Zone and Transcript Feed when new data arrives from the backend's `UI Command` output.
*   **FOMO & Fatigue Panels:** Wire up the secondary column to display real-time generated FOMO snippets and fatigue warnings based on backend triggers.

### Phase 5: Demo Mode & Final Polish
**Goal:** Ensure the app never crashes during the hackathon demo and looks flawless.
*   **Empty States:** What does the HUD look like when the speaker first walks on stage and nobody has spoken? Ensure there's a clean "Waiting for audio..." state.
*   **Smooth Transitions:** Ensure that when the Action Zone text changes, the UI doesn't jump around erratically. Fix container heights if necessary.
*   **Demo Controls:** (Optional but highly recommended) Add a hidden "Debug" expander that allows you to manually trigger specific UI commands (Coaching, Fatigue, FOMO) just in case the backend or LLM fails during judging.

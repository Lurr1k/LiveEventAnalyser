# Project Specification: Live Event Agentic Assistant

## 1. Project Overview
The "Live Event Agentic Assistant" is a real-time, AI-driven heads-up display (HUD) for speakers and panel moderators. By analyzing a continuous feed of live audio transcripts and cross-referencing them with dynamic audience demographic and intent data, the system provides hyper-contextual, instantaneous feedback to presenters. 

The core focus of this MVP is **transcript analysis**—using the text of what is being said to generate actionable suggestions regarding content relevance, pacing, and audience engagement, thereby elevating the value of the in-person event experience.

## 2. Core Features & Hackathon "Lane" Alignment

### 2.1 Audience-Aware Coaching (Lane 02: Connect Better)
* **Mechanism:** The system cross-references the registered attendees in a specific session room against their dataset (`AI Experience Level` and `Academic Background`).
* **Action:** If a room is predominantly "Beginner", and the real-time transcript detects deep technical jargon being discussed without context, the assistant flashes a high-priority prompt to the speaker: **"High beginner presence: define your terms."**
* **Data Pipeline:** Ingest Excel dataset -> Profile audience for the current session -> Feed context + transcript chunks to the LLM.

### 2.2 The Topic Fatigue HUD (Lane 03: Have More Fun)
* **Mechanism:** A transcript-based pulse check. The system measures the textual density and duration a single topic has been discussed based on the transcript timestamps.
* **Action:** If the transcript shows the panel has lingered on the same conceptual block for too long, the system prompts the moderator: **"Topic fatiguing. Pivot to: [Next Agenda Item] or Ask the Audience."**

### 2.3 The FOMO Generator (Lane 01: Learn More)
* **Mechanism:** Capitalizing on the "Intent of Attending" data field. 
* **Action:** If the LLM detects a highly actionable insight in the transcript, it checks the attendee database for users currently not in the room whose intents match the topic (e.g., "AI for Business").
* **Output:** Generates a real-time summary snippet for those attendees: *"Alex Schmitt is dropping insights on VC pattern recognition right now—key takeaway: Seek truth seekers."*

## 3. Technical Architecture (Streamlit Python Stack)

The architecture prioritizes rapid development, data science tooling integration, and a unified Python ecosystem, ensuring the team can iterate quickly during the hackathon.

### 3.1 Core Dashboard (Streamlit MVP)
* **Framework:** The entire core application and speaker HUD will be built using **Streamlit**. This allows for seamless integration of the UI, backend logic, and data processing within a single Python codebase.
* **Data Handling:** Leveraging `pandas` to load, hold, and filter the `hackathon_mock_attendees.xlsx` data and JSON session metadata in memory for rapid lookups.
* **Transcript Ingestion:** A simulated live feed that pushes chunks of the provided mock transcripts into the Streamlit session state, triggering the LLM analysis loop.

### 3.2 AI & Logic Layer
* **Text-Based LLM Integration:** The system will utilize standard, fast text-based LLM API calls (e.g., OpenAI or Anthropic). Chunks of the rolling transcript, combined with the audience profile matrix, are sent to the LLM.
* **System Prompting:** The LLM is strictly prompted to output concise, actionable UI commands based *only* on the text content and session metadata (e.g., "Elaborate on concept X", "Move to next topic").

### 3.3 Public Website / Future Landing Page
* While the core speaker software runs on Streamlit, the public-facing landing page and promotional event website can be built later utilizing a standard web stack (e.g., React/Next.js) to handle marketing and attendee registration flows.

## 4. UI/UX: The Speaker HUD
* **Design Philosophy:** Even within Streamlit, the UI will be styled to reflect a distraction-free, terminal-inspired aesthetic. It must be exceptionally clean to minimize cognitive load for the speaker.
* **Layout:**
    * **Context Feed:** A muted, scrolling feed of the recent transcript text.
    * **Action Zone:** The focal point of the app. Huge, high-contrast typography displaying max 3-7 words at a time (e.g., **"Consider elaborating on that"**).

## 5. Out of Scope / Future Enhancements
*To maintain strict focus during the hackathon, the following concepts are logged as future ideas and will not be implemented in the MVP:*
* **Realtime API (Audio-to-Audio):** Native voice integrations are too complex for the current timeline; the app relies strictly on text transcripts.
* **Acoustic Analysis:** Detecting speech rate (words-per-minute), intonation, or monotone delivery is out of scope. All suggestions will be derived purely from the semantic meaning of the transcribed text.

## 6. Execution Plan (Hackathon Phases)

1.  **Data & Environment Prep:**
    * Initialize the Streamlit app.
    * Build the `pandas` pipelines to parse the Excel and JSON metadata.
2.  **Transcript Simulation & Prompting:**
    * Create a loop in Streamlit that "plays back" the provided transcripts chunk-by-chunk.
    * Build the prompt chain feeding the text and audience data to the LLM.
3.  **UI Polish:**
    * Refine the Streamlit layout using columns and custom CSS/markdown styling to achieve the minimalist, high-visibility speaker HUD.
4.  **Final Review:**
    * Ensure the app clearly demonstrates the integration of the provided datasets (`hackathon_mock_attendees.xlsx` and session files) for the judges.

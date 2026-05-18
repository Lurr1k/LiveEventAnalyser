# Project Specification: Live Event Agentic Assistant

## 1. Project Overview
The "Live Event Agentic Assistant" is a real-time, AI-driven heads-up display (HUD) for speakers and panel moderators. By continuously ingesting live audio transcripts and cross-referencing them with dynamic audience data (`hackathon_mock_attendees.xlsx`), the system provides hyper-contextual, instantaneous feedback to presenters. 

The goal is to elevate the scarcity and value of in-real-life (IRL) events by ensuring the content perfectly matches the room's knowledge level, pacing, and intent, while actively combating audience fatigue.

## 2. Core Features & Hackathon "Lane" Alignment

### 2.1 Audience-Aware Coaching (Lane 02: Connect Better)
* **Mechanism:** The system cross-references the registered attendees in a specific session room against their `AI Experience Level` and `Academic Background`.
* **Action:** If a room is 80% "Beginner", and the real-time transcript detects deep technical jargon (e.g., "RAG implementations with cosine similarity"), the assistant flashes a high-priority prompt to the speaker: **"High beginner presence: define your terms."**
* **Data Pipeline:** Ingest Excel dataset -> Cluster audience metrics for the current session -> LLM prompt injection for live context.

### 2.2 The Gamified Speaker HUD (Lane 03: Have More Fun)
* **Mechanism:** A live pulse-check system. As the transcript rolls in, the system measures the duration a single topic has been discussed. 
* **Action:** If the panel has lingered on "Information Asymmetry" for more than 7 minutes without a change in speaker or topic, the system prompts the moderator: **"Topic fatiguing. Pivot to: [Next Agenda Item] or Poll Audience."**
* **Vibe Check:** Integrating a simple audience-facing web interface where they can tap "Confused" or "Mind Blown" emojis. The HUD synthesizes these inputs into actionable directives for the speaker.

### 2.3 The FOMO Generator (Lane 01: Learn More)
* **Mechanism:** Capitalizing on the "Intent of Attending" data field. 
* **Action:** If the LLM detects a highly actionable insight being spoken on stage (e.g., about "Early Stage VC Vibes"), it searches the attendee database for users currently not in the room who listed their intent as "AI for Business" or "Job / internship".
* **Output:** Generates a real-time push notification or personalized summary snippet for those attendees: *"Alex Schmitt is dropping insights on VC pattern recognition right now—key takeaway: Seek truth seekers."*

## 3. Technical Architecture

To maintain the ultra-low latency required for live speaker feedback, the architecture leans on high-performance data handling and optimized stream processing.

### 3.1 Backend & Audio Processing
* **Audio Ingestion:** A low-latency C++ based audio processing node (e.g., leveraging `whisper.cpp` for bare-metal performance) to capture and transcribe the live microphone feeds.
* **Stream Orchestration:** A robust Python backend (FastAPI + WebSockets) managing the state of the session, handling the chunked transcripts, and pushing updates to the frontend.
* **Data Engine:** The Python backend utilizes `pandas` to load and hold the `hackathon_mock_attendees.xlsx` data in memory, allowing for sub-millisecond lookups of audience demographics and intents.

### 3.2 AI & Logic Layer
* **Real-Time LLM Integration:** Streaming the transcribed chunks to an LLM optimized for speed (e.g., GPT-4o real-time or Claude 3 Haiku). 
* **System Prompting:** The LLM is given a strict system prompt containing the session's JSON metadata (speakers, tags, summary) and the current audience profile. It is instructed to output *only* short, command-style JSON payloads.

### 3.3 Frontend UI / The Speaker HUD
* **Design Philosophy:** Distraction-free, terminal-inspired aesthetic. The UI must feel like a highly customized, minimalist developer environment (akin to a clean Neovim workspace) rather than a cluttered web dashboard.
* **Layout:**
    * **Top 20%:** A muted, scrolling feed of the last 3 sentences transcribed (for speaker context/confidence).
    * **Bottom 80%:** The active directive zone. Huge typography, displaying max 3-7 words at a time.
* **Color Coding:** * *White/Grey:* Neutral information (e.g., "5 minutes remaining").
    * *Yellow:* Formatting/Pacing suggestions (e.g., "Speak a little slower").
    * *Red/Flashing:* Critical audience disconnect (e.g., "Explain: Vector DBs").

## 4. Execution Plan (Hackathon Phases)

1.  **Data & Environment Prep (Hours 1-2):**
    * Parse the provided Excel and JSON metadata.
    * Set up the WebSocket server and the simulated audio stream (using the provided mp3s to simulate live input).
2.  **LLM Pipeline (Hours 3-6):**
    * Build the prompt chain that feeds the transcript chunks and audience data to the LLM.
    * Tune the LLM to output valid UI commands.
3.  **Frontend Build (Hours 7-10):**
    * Develop the minimalist HUD. Connect it to the WebSocket to receive the live directives.
4.  **Integration & Polish (Hours 11+):**
    * Stress-test the latency. Ensure the UI text is readable from a distance. Prepare the final pitch highlighting the use of all provided datasets.

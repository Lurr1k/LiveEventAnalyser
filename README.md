# Live Event Agentic Assistant 🎙️🚀

Welcome to the **Live Event Agentic Assistant** (also known as *Live Event Analyser*), a real-time, AI-driven heads-up display (HUD) designed for speakers and panel moderators. 

By analyzing a continuous feed of live audio transcripts and cross-referencing them with dynamic audience demographic and intent data, the system provides hyper-contextual, instantaneous feedback to presenters to elevate the in-person event experience.

---

## 💡 The Core Vision
The main objective of this MVP is **transcript analysis**—using the text of what is currently being said on stage to generate actionable, real-time suggestions regarding content relevance, pacing, and audience engagement.

### Real-Time Directive Examples:
* ⏱️ **Topic Stagnation & Pacing:** If speakers dwell on a single topic for too long or begin repeating themselves, the system—aware of the event schedule—suggests moving on to the next agenda item.
* 🧠 **Conceptual Friction & Clarity:** If speakers dive into complex, jargon-heavy topics, the system suggests explaining specific terms or provides immediate prerequisite bullet points.
* 🎮 **Engagement & Gamification:** If the transcript indicates the discussion is becoming dry, the assistant prompts the speaker with targeted questions to throw to the room to revive engagement.

---

## 🌟 Core Features & Hackathon Focus
Our features are strategically aligned to maximize attendee value and engagement:

### 1. Audience-Aware Coaching 👥 *(Lane: Connect Better)*
* **How it works:** Cross-references the registered attendees in the room against their profiles (e.g., `AI Experience Level` and `Academic Background`).
* **The Action:** If a room is predominantly beginners and the real-time transcript detects deep technical jargon being discussed without context, the assistant flashes a high-priority prompt to the speaker: `"High beginner presence: define your terms."`

### 2. The Topic Fatigue HUD 📈 *(Lane: Have More Fun)*
* **How it works:** Performs a transcript-based pulse check, measuring the density and duration a single topic has been discussed based on rolling timestamps.
* **The Action:** If the panel lingers on the same conceptual block for too long, the system prompts the moderator: `"Topic fatiguing. Pivot to: [Next Agenda Item] or Ask the Audience."`

### 3. The FOMO Generator 🔔 *(Lane: Learn More)*
* **How it works:** Monitors attendee "Intent of Attending" data fields.
* **The Action:** When the LLM detects a highly actionable insight in the transcript, it checks the database for registered attendees who are *not* currently in the room but have a matching intent.
* **The Output:** Generates a real-time summary snippet for them: *"Alex Schmitt is dropping insights on VC pattern recognition right now—key takeaway: Seek truth seekers."*

---

## 🛠️ Technical Architecture
The project prioritizes rapid development, powerful data science tooling, and a unified Python ecosystem:

* **Core Dashboard (Streamlit MVP):** The entire speaker HUD and core application are built using **Streamlit**. This integrates the user interface, backend logic, and data processing within a single Python codebase.
* **Data Handling:** Leverages `pandas` to load, hold, and filter mock attendee Excel files and JSON session metadata in memory for rapid lookups.
* **Transcript Ingestion:** ElevenLabs realtime speech-to-text is the primary live source. Committed transcript segments are normalized and fed into the rolling analysis loop; mock markdown replay remains available as a demo fallback.
* **AI & Logic Layer:** Utilizes fast, text-based LLM API calls. Chunks of the rolling transcript combined with the audience profile matrix are analyzed to output concise, actionable UI directives.

### Live Transcription Setup
Set `ELEVENLABS_API_KEY` before starting the Streamlit app, then choose **Browser mic** in the sidebar. Streamlit asks the browser for microphone permission, forwards 16 kHz mono PCM audio to the backend, streams it to ElevenLabs realtime STT, and sends only committed transcript segments to the model for on-stage analysis.

---

## 🚫 Out of Scope for MVP
To maintain a strict and high-quality focus during early development, the following enhancements are logged for future phases:
* **Realtime Audio API:** All processing is done via text-based transcripts; native audio-to-audio integrations are out of scope.
* **Acoustic Analysis:** Detection of speech rate, intonation, or monotone delivery is not supported. Suggestions are derived purely from the semantic meaning of the transcript text.

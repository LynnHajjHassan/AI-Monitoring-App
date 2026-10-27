# COMP 4990 — AI-Powered Video Monitoring and Understanding System
## Project scope and functional requirements
**Team:** Marco Lee-Shi, Lynn Hajj Hassan
**Status:** Proposed; incorporates October 27 camera-priority decisions; requires team and supervisor review  


## 1. Project objective
Build a web application that displays **live camera video** and accepts **uploaded video**, allowing a user to ask natural-language questions and request AI-generated descriptions and summaries of the visual content. The first release prioritizes **on-demand video understanding**; automatic event detection and alerts are subsequent enhancements.

This refines the earlier COMP 4990 video client/server concept. The earlier notes emphasized video playback, requesting clips, and adding AI object/event detection in stages. The new scope retains those engineering foundations but prioritizes a live source and an AI question-answering experience. Confirm with the course supervisor that this change in AI emphasis is acceptable.

## 2. Users and main workflows
**Primary user:** A person monitoring a camera feed or reviewing a recording for informational purposes.

**Workflow A — Live video (highest priority):**
1. Open the web dashboard.
2. Select/start a supported live camera (browser webcam initially; existing ESP32 also required for final MVP), granting browser permission if requested.
3. View a live video preview.
4. Ask a question such as “What can you see now?” or “What happened in the last 20–30 seconds?”
5. The system samples or records the relevant recent visual data, runs AI inference, and returns a clearly labeled answer.
6. The user can inspect the associated time window or frames used for the answer.

**Workflow B — Uploaded recording:**
1. Upload a supported short video (MP4 first).
2. Play the video in the dashboard.
3. Ask a question or request a summary.
4. View the response and identify the clip/time range analyzed.

**Workflow C — Optional monitoring rules:**
1. Enable a supported detector (e.g., person detection).
2. Optionally specify a region or simple condition.
3. Review a saved detection event or alert. These are unverified signals, not emergency judgments.

## 3. Functional requirements
Priority: **MUST** = required for the planned MVP, **SHOULD** = high-value target after MVP works, **COULD** = stretch goal.

| ID | Priority | Requirement | Acceptance test |
|---|---|---|---|
| FR-01 | MUST | Display a live video feed from **at least one camera source**. Start with the laptop/browser webcam as a reliable development baseline. | User grants permission and sees video; Start and Stop controls work. |
| FR-02 | MUST | Support recent live-video context for AI requests, initially a bounded **20–30-second window**. | A question about the selected window supplies actual recent frames/short footage to the AI and labels the time window. |
| FR-03 | MUST | Allow the user to type questions about the available video context. | User submits a prompt, receives an answer or clear error, and can submit another prompt. |
| FR-04 | MUST | Generate a short visual description/summary on request. | User clicks Summarize; the system returns an answer grounded in sampled frames or a short clip. |
| FR-05 | MUST | Upload and play a short MP4 recording, then analyze it with the same AI interface. | User uploads a test MP4, plays it, and asks an AI question about it. |
| FR-06 | MUST | Explain the scope of every analysis result. | UI displays the source and analyzed time window; it distinguishes observations from uncertainty. |
| FR-07 | MUST | Show loading, connection, camera-permission, and inference-error states. | Missing/denied camera, model failure, and unsupported video produce understandable feedback without crashing. |
| FR-08 | MUST | Provide a basic backend API to receive analysis requests and return results. | Frontend and backend exchange a documented request/response payload in an integration test. |
| FR-09 | MUST | Integrate the existing **ESP32-CAM as a second supported live camera source** for the final MVP, alongside a browser/device webcam. | The dashboard can display the ESP32 stream and request AI analysis of recent ESP32 frames when the camera is network-reachable; the team demonstrates this on a suitable local network. |
| FR-10 | SHOULD | Save limited analysis history with source, prompt, response, and timestamp. | User can review previous queries in the same session or a stored history view. |
| FR-11 | SHOULD | Provide a way to review/save the short analyzed clip or frames. | User can open or play back the relevant video segment. |
| FR-12 | SHOULD | Run basic pretrained object/person detection on one video source and display results. | Sample frames show labeled detections, with limitations recorded. Helps preserve original proposal's detection component. |
| FR-13 | COULD | Draw a simple rectangular restricted zone and define a person-entry rule. | Entering person creates an event for review in a controlled test. |
| FR-14 | COULD | Create automatic in-app event alerts and event history. | Event appears with time and associated visual evidence; user can review it. |
| FR-15 | COULD | Support a **remote phone as a wireless camera source**, multiple concurrent cameras, or semantic video search. | Demonstrable only after the webcam and ESP32 workflows are stable. |
| FR-16 | EXPERIMENTAL | Evaluate specialized weapon-like object or violence recognition. | Document false positives/negatives on consented test data; never treat as confirmed danger or automatically dispatch emergency services. |

### Scope decisions
- **Live video is a MUST**, not merely an optional add-on.
- **AI responses are on demand**, not continuous VLM analysis of every frame.
- **The first complete vertical slice:** live webcam → recent frames → AI question → response displayed in the web dashboard.
- **Uploaded video is also in the MVP**, so the AI pipeline is testable when physical cameras are unavailable.
- **One active live camera at a time** is sufficient for the MVP; no simultaneous feeds are required.
- **Restricted zones and automatic alerts are not MVP dependencies.**
- **ESP32 is a required final supported camera source**, but not a blocker for the first webcam-to-AI vertical slice. **Phone camera is optional**, especially remote phone-to-laptop transmission.
- No custom LLM/VLM training is required. Pretrained inference, with local or hosted execution determined by feasibility testing, is sufficient for the proposed implementation.

## 4. Recommended enhancements, in order
1. **Evidence-aware answers (high-value):** show which time window/frames were analyzed. Add a “View analyzed segment” link where feasible. This improves trust and debugging.
2. **Basic object/person detection:** improves technical breadth and preserves original proposal alignment; can run on selected frames instead of all frames continuously.
3. **Saved clips and query history:** allows useful review and richer demonstrations.
4. **Restricted-zone rules + event markers:** implement as a coherent package rather than drawing a zone with no monitoring behavior.
5. **Automatic alerts:** add only after one event rule is reliably detected.
6. **Specialized safety detection:** research/stretch only, because false negatives and false positives may be consequential.

## 5. Non-functional requirements
| ID | Requirement | Measurement/validation |
|---|---|---|
| NFR-01 | Keep analysis memory bounded. | Configure a rolling buffer by elapsed seconds and sample rate; confirm memory does not grow without limit. |
| NFR-02 | Keep camera capture permission explicit. | Webcam/phone use browser permission flows; provide Stop Camera. |
| NFR-03 | Privacy-conscious handling of footage. | Only process consented test footage; no public camera exposure by default; configurable retention/deletion if recordings are stored. |
| NFR-04 | Explain AI uncertainty and coverage. | Do not claim events are absent when sampled frames are insufficient; show which time interval was inspected. |
| NFR-05 | Demonstrable without a dedicated cloud GPU. | Prototype works on a development machine; note that hosted VLM use is optional and may have cost/privacy implications. |
| NFR-06 | Maintainable teamwork. | Shared GitHub repository; documented setup; issues, pull requests, and clear API contract. |
| NFR-07 | Measure performance, not assume it. | Benchmark Q&A response time, memory usage, and camera/processing reliability on real project hardware. |
| NFR-08 | Robust format handling. | Validate uploads, enforce reasonable file-size/duration limits, and show friendly errors. |

## 6. Candidate technology stack (not yet final)
- **UI:** React + TypeScript, with live camera preview, video player, and Q&A panel.
- **Backend:** Existing Flask prototype as a reference; choose Flask or FastAPI after reviewing API needs.
- **Video:** Browser MediaDevices for a webcam on the device running the UI, ESP32 HTTP/MJPEG adapter, OpenCV and/or FFmpeg for sampling and clips. A remote phone-to-backend stream would require a separate transport; sending occasional snapshots is simpler but not equivalent to streaming smooth video.
- **AI:** Pretrained small vision-language model for sampled video frames/short clips; evaluate on M4 Pro (24 GB unified memory). A hosted model API is an optional fallback, not a prerequisite.
- **Data:** Initially files and small local storage; SQLite if persisting events/history.
- **Deployment:** Local demonstration first. A shared Linux host is optional after end-to-end integration.

A remote phone camera streaming **to a backend on a different device** requires networking/transport beyond merely opening the phone camera in its own browser; that is why the second live source requires a feasibility test. Camera APIs also require permission and a secure browser context (HTTPS or localhost).

## 7. Acceptance scenario for the MVP
1. Start the application with documented commands.
2. Open the dashboard and start a live camera.
3. See ongoing preview and an indicator that the camera is active.
4. Wait at least 20 seconds, then ask “What happened recently?”
5. The application analyzes recent visual content and displays an answer, with analyzed time window and clear uncertainty when needed.
6. Upload a short MP4 and play it.
7. Request a summary of that recording and receive an answer.
8. Demonstrate recovery from a denied camera permission or failed AI request.
9. Record and report at least a small evaluation set: correct/incorrect video answers, response latency, and a basic stream-reliability test.

**Required additional acceptance demonstration:** connect the existing ESP32 on a reachable local network, display its stream in the dashboard, and ask the AI about recent captured frames. **Optional demonstration:** remote phone camera, person detection, and saved clips.

## 8. Explicitly out of scope for MVP
- Continuous high-confidence weapon/violence identification or emergency dispatch.
- Production-grade public surveillance or biometric identification.
- Fine-tuning or training a large multimodal model from scratch.
- Simultaneous processing of multiple cameras.
- Full semantic search across many hours of archived footage.
- User accounts, complex permission systems, or paid cloud deployment unless demanded by course requirements.

## 9. Risks and feasibility gates
1. **VLM quality:** run the same 3–5 short test videos and prompts through a local candidate model; score answer correctness and omissions.
2. **Live pipeline:** demonstrate a stable live feed and a bounded recent-frame buffer early.
3. **ESP32 integration:** recover the Arduino sketch, validate the current camera URL and Flask proxy, and demonstrate ESP32-to-AI analysis on a reachable network. Do not assume its LAN address is remotely reachable. A phone remains optional, not a replacement for ESP32.
4. **Latency:** benchmark inference on the M4 Pro before promising real-time responsiveness.
5. **Professor/course fit:** confirm that on-demand video understanding plus basic detection fulfills the course's original video/AI goals.

## 10. Open decisions for Lynn and Marco
- [ ] Confirm official submission/demo dates and weekly time available.
- [ ] Ask the supervisor whether VLM video Q&A is an acceptable central AI feature and whether conventional object detection is required.
- [x] Camera order: laptop/browser webcam for initial integration, ESP32 as a required second source, remote phone camera optional.
- [ ] Choose analysis mode for initial live Q&A: sampled frames over 20–30 seconds vs short encoded clips; test both if needed.
- [ ] Choose local-only VLM vs optional hosted API after model comparison and privacy/cost review.
- [ ] Decide whether to keep Flask or move to FastAPI, based on existing demo and API contracts.
- [ ] Approve the MUST/SHOULD/COULD scope together before scheduling implementation.

## 11. Decision log (October 27, 2026)
- **Agreed direction:** live-first hybrid AI video understanding application with uploaded-video Q&A.
- **Camera sequence:** browser laptop camera first for development; ESP32-CAM is a required additional supported input; remotely streaming a phone camera is a later enhancement.
- **User-facing quality features:** display evidence/time window for answers, retain limited question/summary history, expose model uncertainty, provide camera Start/Stop controls.
- **Scope caution:** do not schedule restricted zones or automatic alerts until the live-video question-and-answer path and ESP32 integration are demonstrated.
- **Still open:** model choice, hosting/API policy, exact submission date, and professor approval of the revised AI emphasis.

## 12. Next planning artifacts
1. `docs/architecture.md` — components, data flows, camera transport, buffer/inference design, storage, deployment.
2. `docs/api-contract.md` — frontend/backend and backend/AI request and response schemas.
3. `docs/task-distribution.md` — responsibility matrix with balanced estimates and dependencies.
4. GitHub Issues / GitHub Project — actual task tracking; linked to these documents.

**Suggested repository location for this file:** `docs/requirements.md` in the existing `AI-Monitoring-App` repository. Review and approve before committing.

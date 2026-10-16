# BusinessLabs Capstone Project: AI Tech Consultant

An enterprise AI consulting platform that automates software consulting workflows across three unified modules:
1. **Task 1: Knowledge Brain (Python RAG Engine)** — Ingests 2,000+ pages of Brilliant Directories documentation, generates grounded answers with strict citations, and manages two-tier escalations.
2. **Task 2: Inbox Agent (TypeScript Service)** — Categorizes client support inquiries, queries the Knowledge Brain, generates grounded drafts, and enforces a strict 20-consecutive-approval autonomy threshold.
3. **Task 3: Meeting to Scope (Python Agent Workflow)** — Analyzes client discovery transcripts, checks native BD capabilities vs custom development, produces bottom-up task hour estimates, detects scope drift across follow-up meetings, and enforces human approval gates before delivery.
4. **Unified Frontend Dashboard** — A responsive web interface connecting all three backend services into an interactive consulting cockpit.

---

## Architecture Overview

```
[ Client Meeting Transcripts ]                 [ Customer Emails ]
            │                                           │
            ▼                                           ▼
   ┌──────────────────┐                       ┌──────────────────┐
   │  Task 3: Scope   │                       │  Task 2: Inbox   │
   │  Agent Workflow  │                       │  Triage Agent    │
   └────────┬─────────┘                       └────────┬─────────┘
            │                                          │
            └─────────────► ┌──────────────────┐ ◄─────┘
                            │ Task 1: Knowledge│
                            │ Brain RAG Engine │
                            └─────────▲────────┘
                                      │
                         ┌────────────┴───────────┐
                         │ Unified Web Dashboard  │
                         │ http://127.0.0.1:3000  │
                         └────────────────────────┘
```

---

## Prerequisites & Setup

- **Prerequisites**: Python 3.10+, Node.js 18+
- **Configuration**: Copy `.env.example` to `.env` (defaults to safe offline deterministic mode, `MOCK_LLM=true`)

### Single-Command Startup & Active Endpoints

Start all three services and the web dashboard concurrently with a single command:

```powershell
# Windows PowerShell (Starts ports 8000, 3000, 8001)
& "knowledge-brain/.venv/Scripts/python" run_all.py

# Health verification probe across all services
& "knowledge-brain/.venv/Scripts/python" run_all.py --verify
```

### Service Directory
| Module | URL | Description |
|---|---|---|
| **Unified Web Dashboard** | `http://127.0.0.1:3000` | Complete interactive GUI for all 3 tasks |
| **Task 1: Knowledge Brain** | `http://127.0.0.1:8000` | Swagger interactive docs at `/docs` |
| **Task 2: Inbox Agent API** | `http://127.0.0.1:3000/api/v1/inbox` | Health endpoint at `/health` |
| **Task 3: Meeting to Scope** | `http://127.0.0.1:8001` | Swagger interactive docs at `/docs` |

---

## Automated Test Suites (146 Passing Tests)

```bash
# Task 1 (46 passing tests)
cd knowledge-brain && .venv/Scripts/pytest -v

# Task 2 (60 passing tests, 0 TypeScript errors)
cd task2-inbox-agent && npm test

# Task 3 (40 passing tests)
cd task3-meeting-scope && ..\knowledge-brain\.venv\Scripts\pytest -v
```

---

## 10-Minute Demonstration Walkthrough

When presenting or recording the candidate demonstration:
1. **Startup (1 min)**: Run `python run_all.py`. Open `http://127.0.0.1:3000` and show all 3 health dots green.
2. **Knowledge Brain (2 mins)**: Ask *"How to connect a live custom domain?"* Show grounded answer, documentation link, and attached screenshots. Then click *"HIPAA compliance"* to demonstrate honest uncertainty and Tier 2 human escalation.
3. **Inbox Agent (2 mins)**: Ingest a customer email. Show AI draft citing Task 1. Explain the 20-approval streak requirement and demonstrate the quality-drop withdrawal safeguard.
4. **Meeting to Scope (3 mins)**: Click *"Load Scenario A"*, run initial scoping, and show bottom-up hours math.
5. **Security Gate Proof (1 min)**: Click *"Attempt Delivery Without Approval"*. Show backend blocking delivery with **HTTP 403 Forbidden**. Click *"Approve Proposal"* to unlock delivery.
6. **Follow-up Change Detection (1 min)**: Click *"Load Scenario C"*. Show the Change Detection Report: reviews removed (-4.0h), multi-currency modified (+3.5h), Zapier webhook added (+5.0h), and Scope v2.0 requiring renewed approval.

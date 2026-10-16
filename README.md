# BusinessLabs AI Tech Consultant Capstone

An enterprise AI consulting platform that automates software discovery, documentation retrieval, customer inquiry triage, and implementation scoping for Brilliant Directories (BD).

---

## Three Core Tasks

1. **Task 1: Knowledge Brain (Python RAG Engine)** — Crawls and indexes official Brilliant Directories documentation into ChromaDB (`all-MiniLM-L6-v2`). Synthesizes answers grounded strictly in retrieved context with Claude 3.5 Sonnet, attaches verified citations and screenshots, and routes unsupported queries to a two-tier human expert escalation queue.
2. **Task 2: Inbox Agent (TypeScript Service)** — Classifies customer support inquiries into 7 distinct categories using Claude 3 Haiku, retrieves verified context from Task 1, and drafts contextual replies. Governed by an `AutonomyEngine` that permits auto-sending only after **20 consecutive unedited approvals** per category and revokes autonomy if quality declines.
3. **Task 3: Meeting to Scope (Python Multi-Agent Workflow)** — Translates discovery transcripts into structured implementation scopes, checks native platform settings via Task 1, computes bottom-up task hours, and produces client proposals. Features a `DiffEngine` that tracks scope changes across follow-up meetings and enforces non-negotiable **HTTP 403 delivery security gates**.

---

## Technology Stack

- **Backends**: Python 3.11, FastAPI, Pydantic v2, ChromaDB, SentenceTransformers, TypeScript 5, Node.js 18+, Express.
- **AI Models**: Anthropic Claude 3.5 Sonnet (reasoning & scoping), Claude 3 Haiku (high-speed inquiry classification).
- **Frontend & Storage**: Vanilla CSS/JS cyber-glass single-page dashboard; atomic file-backed JSON persistence (`scope_store.json`, `inbox_store.json`, `escalations.json`).
- **Testing Frameworks**: `pytest`, `pytest-asyncio`, `jest`, `ts-jest`, `supertest`.

---

## Prerequisites & Environment Setup

- **Prerequisites**: Python 3.10+ and Node.js 18+ installed locally.
- **Environment Configuration**: Copy `.env.example` to `.env` in the project root:
  ```powershell
  cp .env.example .env
  ```
  *Default safe mode (`MOCK_LLM=true`) allows complete offline execution without third-party API keys. To enable live Claude inference, set `MOCK_LLM=false` and provide your `ANTHROPIC_API_KEY`.*

---

## Running the Project (Single Command)

Launch all three backend services and the unified web dashboard concurrently with a single command:

```powershell
# Windows PowerShell (Starts ports 8000, 3000, and 8001)
& "knowledge-brain/.venv/Scripts/python" run_all.py

# Health verification probe across all running services
& "knowledge-brain/.venv/Scripts/python" run_all.py --verify
```

### Verified Active Endpoints
| Service | Local URL | Primary Endpoints |
|---|---|---|
| **Unified Web Dashboard** | `http://127.0.0.1:3000` | Complete interactive GUI for all 3 tasks |
| **Task 1: Knowledge Brain** | `http://127.0.0.1:8000` | `POST /api/v1/query`, `POST /api/v1/capability-check`, `GET /docs` |
| **Task 2: Inbox Agent** | `http://127.0.0.1:3000` | `POST /api/v1/inbox/emails`, `POST /api/v1/inbox/drafts/:id/review` |
| **Task 3: Meeting to Scope** | `http://127.0.0.1:8001` | `POST /api/v1/meetings/initial`, `POST /api/v1/meetings/followup`, `POST /api/v1/projects/:id/deliver` |

---

## Running Tests (146 Passing Tests)

Run all unit, integration, and scenario tests across the three tasks:

```powershell
# Task 1: Knowledge Brain (46 passed)
cd knowledge-brain; .venv\Scripts\pytest -v; cd ..

# Task 2: Inbox Agent (60 passed, 0 TypeScript errors)
cd task2-inbox-agent; npm test; cd ..

# Task 3: Meeting to Scope (40 passed)
cd task3-meeting-scope; ..\knowledge-brain\.venv\Scripts\pytest -v; cd ..
```

---

## Human-Approval & Safety Features

1. **Anti-Hallucination Grounding**: Every technical citation is validated against retrieved ChromaDB chunks. Unverified claims or low-confidence questions (<0.70) trigger honest abstention and create human escalation tasks.
2. **20-Approval Autonomy Threshold**: Email auto-sending requires 20 consecutive unedited human approvals in that specific category. Edits or rejections reset the streak to 0, and rolling edit rates >25% revoke autonomy.
3. **Hard Delivery Security Gate**: Delivering an unapproved draft or superseded proposal (`v1.0` when `v2.0` exists) triggers **HTTP 403 Forbidden** (`PermissionError`). Proposals require explicit human sign-off before simulated dispatch.

---

## Documentation References

- **[DESIGN.md](file:///c:/Business%20Labs%20AI%20Tech%20Consultant%20assignment/DESIGN.md)** — Detailed 4-page system architecture, multi-agent pipeline, model trade-offs, and failure mode mitigations.
- **[EVALS.md](file:///c:/Business%20Labs%20AI%20Tech%20Consultant%20assignment/EVALS.md)** — Benchmark report containing 20 test cases per task, 55 synthetic email evaluations, and model comparison matrices.
- **[AI_LOG.md](file:///c:/Business%20Labs%20AI%20Tech%20Consultant%20assignment/AI_LOG.md)** — Development log featuring 5 engineering prompts and the technical rationale for rejecting monolithic LLM scoping.

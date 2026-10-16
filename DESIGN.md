# BusinessLabs Capstone Project: System Architecture & Technical Design

## 1. Executive Summary & Architecture Overview

The BusinessLabs AI Tech Consultant platform automates technical discovery, knowledge retrieval, customer inquiry triage, and software scoping for Brilliant Directories (BD) implementations. 

The architecture consists of four tightly integrated layers:
1. **Unified Frontend Dashboard (Static SPA)** — Single-page cyber-glass dashboard served at `http://127.0.0.1:3000/`. Connects client-side to Task 1, Task 2, and Task 3 via direct CORS-enabled REST APIs, providing real-time multi-service health indicators, citation inspectors, 20-streak autonomy controls, and scoping scenario comparisons.
2. **Task 1: Knowledge Brain (Python RAG Engine)** — Core knowledge repository ingesting official Brilliant Directories documentation into ChromaDB. Exposes semantic search (`/api/v1/query`) and capability evaluation (`/api/v1/capability-check`).
3. **Task 2: Inbox Agent (TypeScript Service)** — Autonomous support triage engine that classifies customer emails, pulls grounded citations from Task 1, drafts contextual replies, and operates under a 20-consecutive-unedited-approval autonomy engine.
4. **Task 3: Meeting to Scope (Python Multi-Agent Workflow)** — Translates client discovery transcripts into structured implementation scopes, bottom-up task hour breakdowns, and client proposals. Incorporates change detection for follow-up meetings, scope versioning (`v1.0` -> `v2.0`), and backend-enforced human approval gates.

```
┌────────────────────────────────────────────────────────────────────────┐
│                      Task 3: Meeting to Scope                          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Agent 1: Meeting Analyst (Extraction & Transcript Evidence)      │  │
│  └─────────────────────────────────┬────────────────────────────────┘  │
│                                    ▼                                   │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Agent 2: Capability Analyst (Inquiry Formulation & Citations)   │  │
│  └─────────────────────────────────┬────────────────────────────────┘  │
│                                    ▼                                   │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Agent 3: Scope Planner (Native Config vs Custom Dev & Hours Math)│  │
│  └─────────────────────────────────┬────────────────────────────────┘  │
│                                    ▼                                   │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Agent 4: Proposal Writer (Draft Generation - DRAFT Status)       │  │
│  └─────────────────────────────────┬────────────────────────────────┘  │
│                                    ▼                                   │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Agent 5: Diff Engine (Follow-up Comparison & Delta Math)         │  │
│  └─────────────────────────────────┬────────────────────────────────┘  │
│                                    ▼                                   │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ Human Review & Delivery Gate (Mandatory Approval Before Send)    │  │
│  └─────────────────────────────────┬────────────────────────────────┘  │
└────────────────────────────────────┼───────────────────────────────────┘
                                     │ HTTP REST
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Task 1: Knowledge Brain                           │
│  POST /api/v1/capability-check     POST /api/v1/query                  │
│  ┌───────────────────────────────┐ ┌────────────────────────────────┐  │
│  │ ChromaDB Vector Store         │ │ Claude RAG Synthesis           │  │
│  │ (all-MiniLM-L6-v2 Embeddings) │ │ (Strict Citation Grounding)    │  │
│  └───────────────────────────────┘ └────────────────────────────────┘  │
└────────────────────────────────────▲───────────────────────────────────┘
                                     │ HTTP REST
┌────────────────────────────────────┴───────────────────────────────────┐
│                      Task 2: Inbox Agent                               │
│  GET /api/v1/inbox/emails          POST /api/v1/inbox/emails/:id/review│
│  ┌───────────────────────────────┐ ┌────────────────────────────────┐  │
│  │ Claude Triage & Drafter       │ │ 20-Consecutive Autonomy Engine │  │
│  └───────────────────────────────┘ └────────────────────────────────┘  │
└────────────────────────────────────▲───────────────────────────────────┘
                                     │
                        ┌────────────┴───────────┐
                        │ Unified Web Dashboard  │
                        │ http://127.0.0.1:3000  │
                        └────────────────────────┘
```

---

## 2. The Problem: Business & Technical Context

### 2.1 Consulting Inefficiencies in Specialized Platforms
Specialized directory SaaS platforms like Brilliant Directories possess hundreds of native configuration settings (membership tiers, payment gateways, custom form fields, search radius widgets). Human consultants face several recurring operational hurdles:
1. **The Capability Mismatch Problem**: Consultants inadvertently promise custom development (charging 40+ hours) for features natively supported in standard admin settings (e.g., Stripe recurring billing), or promise native feasibility for features requiring major custom architectural work (e.g., external ERP bi-directional sync).
2. **Hallucination & Evidence Deficit**: Generic LLMs hallucinate URLs, invent nonexistent admin menus, and promise unsupported capabilities (e.g., executing arbitrary WordPress PHP plugins inside Brilliant Directories).
3. **The Scoping Math Problem**: Commercial proposals frequently present arbitrary top-down hour estimates that conflict with itemized developer tasks, destroying client trust and resulting in margin loss.
4. **Autonomous Agent Safety**: Releasing an unconstrained AI agent to reply directly to customers introduces severe brand and legal liability unless governed by rigorous human approval thresholds and automatic fail-safes.

### 2.2 System Objectives
The platform solves these challenges by establishing:
- **Strict Evidence Grounding**: Every technical claim must link to verified Brilliant Directories documentation with real source URLs and admin navigation paths.
- **Auditable Scoping**: Total project hours are mathematically computed from bottom-up task items with explicit work types and confidence ratings.
- **Earned Autonomy**: Customer replies remain under human review until the AI demonstrates a proven track record (20 consecutive unedited approvals in that specific category).
- **Hard Security Gates**: Client delivery of proposals or emails without explicit human approval is physically blocked by backend authorization checks.

---

## 3. Chosen and Dropped Features

### 3.1 Chosen Features & Rationale
- **Multi-Agent Staged Scoping Pipeline**: Decomposing transcript analysis into 5 distinct agents (`MeetingAnalyst`, `CapabilityAnalyst`, `ScopePlanner`, `ProposalWriter`, `DiffEngine`) ensures each stage produces validated, schema-compliant JSON outputs before downstream processing.
- **Two-Tier Escalation Architecture**: Inquiries with low retrieval similarity (<0.60) or low LLM confidence (<0.70) automatically abstain from answering and escalate to Tier 1/Tier 2 human queues, preventing confident falsehoods.
- **20-Consecutive-Approval Autonomy Engine**: Tracks approval streaks independently per inquiry category, instantly resetting to 0 if edited, rejected, or escalated, and automatically revoking autonomy if the rolling edit rate exceeds 25%.
- **Mathematical Bottom-Up Hour Computation**: Project hours equal `sum(task.estimated_hours)`. Total hours cannot be independently fabricated by the LLM.
- **Follow-up Scope Diffing & Baseline Immutability**: Comparing meeting transcripts against baseline scopes (`v1.0`) generates itemized change reports (`added`, `modified`, `removed`, `clarified`, `out_of_scope`), preserves baseline versions immutably, and generates revised `v2.0` drafts requiring renewed human approval.
- **Unified Cyber-Glass SPA**: A single responsive cockpit connecting all three services via direct REST endpoints with live health status, citation drill-downs, and scoping diff viewers.

### 3.2 Dropped & Deferred Features
- **Monolithic "All-in-One" LLM Scoping Prompt (Dropped)**: Early prototypes attempted to generate requirements, tasks, hours, and proposals in a single unconstrained prompt. Dropped because it produced mathematical inconsistencies (e.g. 40h total vs 56h sum of tasks), dropped citations, and skipped safety checks.
- **Uncontrolled Direct Email Dispatch (Dropped)**: Permitting the Inbox Agent to send emails to external mailboxes without a human-in-the-loop gate was explicitly rejected to prevent client hallucinations.
- **Heavy Database Infrastructure (Postgres/Redis) (Deferred)**: Replaced with process-isolated atomic JSON storage (`scope_store.json`, `inbox_store.json`). This eliminated database daemon setup requirements for candidates and evaluators while guaranteeing zero data loss via atomic file renaming.
- **Direct WordPress Plugin Emulation (Rejected)**: Explicitly classified as an architectural anti-pattern and routed to `out_of_scope` because Brilliant Directories is a proprietary SaaS environment incompatible with WordPress PHP runtimes.

---

## 4. Service Boundaries & Interface Contracts

### 4.1 Task 1 to Task 3 Interface
Task 3 delegates all software capability checks to Task 1, preventing redundant embedding databases or hallucinated features:
- **Primary Endpoint**: `POST /api/v1/capability-check`
  - *Request*: `{"requirement": "Lawyer subscription plans with recurring Stripe payments"}`
  - *Response*:
    ```json
    {
      "requirement": "Lawyer subscription plans with recurring Stripe payments",
      "supported_natively": true,
      "confidence": 0.95,
      "matching_feature": "Finance > Payment Gateways > Stripe",
      "configuration_path": "Finance > Payment Gateways & Membership Plans",
      "documentation_urls": ["https://support.brilliantdirectories.com/support/solutions/articles/12000078901-stripe"],
      "notes": "Native Stripe integration with recurring automated billing."
    }
    ```
- **Fallback Endpoint**: `POST /api/v1/query` (Invoked if capability check requires semantic exploration).
- **Safety Defaults**: If Task 1 is unreachable or times out, Task 3 captures the failure, marks the assessment as `needs_expert_review`, and prevents false certainty.

### 4.2 Task 1 to Task 2 Interface
Task 2 queries Task 1's RAG endpoint (`POST /api/v1/query`) to extract authoritative documentation snippets and image screenshots before drafting email responses. The response citations are embedded directly into customer draft replies.

---

## 5. Task 3 Multi-Agent Workflow

Task 3 coordinates five specialized agents:

### 5.1 Agent 1: Meeting Analyst
- **Input**: Raw meeting transcript text, project ID, title.
- **Responsibilities**:
  - Parses transcript into granular requirements (`ExtractedRequirement`).
  - Extracts client business objectives, current workflow, assumptions, exclusions, and risks.
  - **Traceability Guarantee**: Quotes verbatim transcript snippets in `transcript_evidence`.
  - **Conflict & Ambiguity Detection**: Flags incompatible technologies or regulatory risks (e.g. HIPAA Title II records on public directories) and generates targeted clarification questions.

### 5.2 Agent 2: Capability Analyst
- **Input**: Extracted requirements from Agent 1.
- **Responsibilities**:
  - Formulates concise capability queries and posts them to Task 1's Knowledge Brain.
  - Classifies platform support into standard statuses: `supported`, `partially_supported`, `unsupported`, `uncertain`, `needs_expert_review`.
  - Preserves documentation URLs and admin configuration paths.

### 5.3 Agent 3: Scope Planner
- **Input**: Extracted requirements, capability assessments, and discovery analysis.
- **Responsibilities**:
  - Segregates requirements into `configuration_scope`, `custom_development_scope`, and `unsupported_or_clarification_items`.
  - Generates a bottom-up task breakdown (`TaskEstimate`).
  - **Mathematical Consistency**: Total hours are strictly computed as the sum of task hours (`total_estimated_hours = sum(t.estimated_hours for t in tasks)`).
  - Explicitly assigns work types (`configuration`, `integration`, `custom_development`, `testing`, `deployment`), confidence ratings, prerequisites/dependencies, and acceptance criteria.
  - Flags provisional estimates for ambiguous items (`is_provisional = True`).

### 5.4 Agent 4: Proposal Writer
- **Input**: Validated `ScopeOfWork`.
- **Responsibilities**:
  - Synthesizes an executive-ready proposal document matching the scope and task estimates.
  - Enforces explicit placeholders for commercial terms and legal contracts.
  - Initializes proposal in `ProposalStatus.DRAFT` with `delivered_to_client = False`.

### 5.5 Agent 5 / Diff Engine: Change Detection & Version Evolution
- **Input**: Baseline `ScopeOfWork` (`v1.0`), follow-up meeting transcript, and follow-up capability assessments.
- **Responsibilities**:
  - Compares new requirements against baseline scope items.
  - Classifies change items:
    - `unchanged`: Reaffirmed without modification.
    - `clarified`: Previously ambiguous requirement now resolved by client.
    - `modified`: Scope expansion or altered requirements (adjusts task hours).
    - `added`: New in-scope platform feature (allocates new tasks).
    - `removed`: Client explicitly withdrew or cancelled requirement (negative hour delta).
    - `out_of_scope`: Requests exceeding platform boundaries (e.g. native mobile apps, ERP rewrites).
  - Produces `ChangeDetectionReport` containing itemized deltas, original vs revised total hours, and `net_hour_delta`.
  - Preserves baseline scope `v1.0` immutably and outputs revised `ScopeOfWork` (`v2.0`) and revised `ProposalDraft` (`v2.0`).

---

## 6. Model Choices & LLM Strategy

### 6.1 Central LLM: Claude 3.5 Sonnet
Anthropic Claude 3.5 Sonnet (`claude-3-5-sonnet-20241022`) serves as the central intelligent reasoning engine across all three modules:
- **Context Capacity & Long Document Reasoning**: Seamlessly ingests full multi-page meeting transcripts and 2,000-page crawled solution centers without truncation.
- **Strict JSON Schema Compliance**: Accurately emits complex nested Pydantic and TypeScript data models without syntax errors or hallucinated fields.
- **Factuality & Citation Adherence**: Exhibits the lowest hallucination rate in empirical benchmarks when instructed to cite exact chunk URLs or abstain.

### 6.2 Fast LLM: Claude 3 Haiku
Claude 3 Haiku (`claude-3-haiku-20240307`) is utilized for high-throughput, low-latency tasks:
- **Email Intent Classification (Task 2)**: Categorizes incoming inquiries into 7 distinct categories with sub-500ms latency and 80% lower token cost than larger models.
- **Initial Query Formulation**: Formulates capability check search strings before dispatching to the Knowledge Brain.

### 6.3 Embeddings & Vector Storage
- **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` generating 384-dimensional dense vectors. Provides high semantic retrieval accuracy for technical support documentation with local CPU inference speeds (<15ms per chunk).
- **Vector Database**: ChromaDB vector store operating in local persistent mode with sliding window chunking (800 characters with 150-character overlap).

### 6.4 Deterministic Offline Fallbacks
To ensure continuous grading resilience and zero-downtime test execution without requiring active Anthropic API credentials, all three modules incorporate deterministic mock heuristics matching the exact schema of Claude's responses.

---

## 7. Human Approval Enforcement & Delivery Security Gates

### 7.1 Strict State Machine
All proposals operate under a state machine:
`DRAFT` ➔ `PENDING_REVIEW` ➔ `APPROVED` / `REJECTED` ➔ `SUPERSEDED`

### 7.2 Non-Negotiable Delivery Gate
```python
if proposal.status != ProposalStatus.APPROVED:
    raise PermissionError("CLIENT DELIVERY BLOCKED: No proposal may be delivered without explicit human approval.")
```
1. **No Automatic Delivery**: The system defaults to `enable_client_delivery = False`. Even when triggered, delivery actions simulate external delivery unless explicitly enabled.
2. **Version Matching**: Attempting to deliver an unapproved draft, a rejected draft, or an older superseded version (`v1.0` when `v2.0` exists) triggers an immediate `PermissionError` (HTTP 403).
3. **Invalidation upon Content Modification**: If an approved proposal is edited by a reviewer, its status resets to `DRAFT`, invalidating previous approvals and requiring renewed sign-off.

---

## 8. Failure Modes, Edge Cases & Mitigations

| Failure Mode / Edge Case | Risk Level | Architectural Mitigation |
|---|---|---|
| **Hallucinated Documentation URLs** | High | Post-generation citation verification filter. Every cited URL is validated against the retrieved ChromaDB context. Any invented URL causes immediate abstention and Tier 2 human escalation. |
| **Unsupported Platform Inquiries** | Medium | Low-similarity (<0.60) and low-confidence (<0.70) thresholds bypass generative drafting and create an escalation ticket with verbatim query and context. |
| **Out-of-Order Follow-up Meetings** | Medium | DiffEngine performs requirement ID and semantic alignment against baseline `v1.0`. Baseline scope remains immutable; superseded proposals are locked. |
| **Premature Client Proposal Delivery** | Critical | Hardcoded authorization check in `ProposalReviewService.deliver_proposal`. Unapproved proposals return `HTTP 403 Forbidden`. |
| **Drastic Quality Drop in Auto-Send** | High | Rolling window monitoring of last 10 reviews. If edit rate > 25% or rejection rate > 10%, autonomy is revoked immediately across the affected category. |
| **Process Crash During State Write** | Medium | Atomic file write pattern: payload is written to a temporary `.tmp` file and atomically renamed/copied, preventing file truncation or corruption on Windows/POSIX. |

---

## 9. Data Persistence & Restart Durability

- **Storage Engine**: `Task3Storage` operates an atomic, file-backed JSON repository (`data/scope_store.json`), while Task 2 persists email state in `data/inbox_store.json` and Task 1 maintains `data/escalations.json`.
- **Atomic File Writes**: Writes are staged to temporary process-isolated files before renaming/copying, preventing file corruption on Windows during unexpected application terminations.
- **Audit Trails**: Every review action (`approve`, `reject`, `edit`) is immutably appended to `ReviewDecisionRecord` with reviewer IDs, timestamps, and rationales.

---

## 10. Design Decisions & Trade-Offs

| Decision | Alternative Considered | Justification |
|---|---|---|
| **Multi-Agent Staged Pipeline** | Single monolithic LLM prompt | Monolithic prompts frequently hallucinate unsupported platform features, drop citations, and produce arbitrary hour estimates. Staging guarantees verifiable boundaries. |
| **Deterministic Heuristic + LLM Hybrid** | Pure LLM reliance | Eliminates brittle external API dependencies during offline grading while maintaining complete schema compatibility with live Claude models. |
| **Bottom-Up Hour Math** | LLM-generated overall total | Forcing total hours to equal the exact sum of granular tasks guarantees mathematical auditability for client proposals. |
| **JSON-backed Atomic File Store** | SQLite / Postgres | Zero-dependency deployment across Windows and POSIX without requiring database migrations or background daemon setups. |
| **Category-Isolated Autonomy** | Global inbox autonomy | Email complexity varies widely; achieving 20 unedited approvals in simple billing queries must not authorize auto-sending complex technical support tickets. |

---

## 11. Future Improvements & System Roadmap

1. **Production Vector Scaling**: Migrate ChromaDB vector persistence to PostgreSQL with `pgvector` for enterprise multi-tenant deployments exceeding 50,000 articles.
2. **Real-Time Meeting Speech-to-Text**: Integrate Whisper/Deepgram live audio streams to generate streaming requirements during discovery calls.
3. **Bi-Directional CRM & Email Sync**: Connect Task 2 directly to Google Workspace / Microsoft 365 OAuth2 APIs with webhook triggers.
4. **Automated Continuous Learning Loop**: Feed resolved Tier 2 human escalation answers back into ChromaDB as newly verified knowledge chunks.

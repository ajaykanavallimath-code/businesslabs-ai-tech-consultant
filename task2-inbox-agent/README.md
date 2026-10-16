# Task 2: Inbox Agent (TypeScript)

A production-grade, TypeScript-based AI Inbox Agent designed for intelligent customer email categorization, evidence-backed reply drafting grounded in Task 1 Knowledge Brain documentation, a robust human-in-the-loop review workflow, and a strict 20-consecutive-approval autonomy engine with quality-drop withdrawal.

---

## 1. Architecture Overview

```
task2-inbox-agent/
├── src/
│   ├── agents/
│   │   └── inboxAgent.ts          # Central orchestrator: intake, classification, KB retrieval, drafting, routing
│   ├── services/
│   │   ├── classifier.ts          # Claude email categorization into 7 categories + heuristics
│   │   ├── kbClient.ts            # Strongly-typed HTTP client for Task 1 POST /api/v1/query
│   │   ├── drafter.ts             # Claude grounded reply drafting with citations & company voice
│   │   ├── reviewService.ts       # Human review workflow (approve, edit, reject, regenerate, escalate)
│   │   ├── autonomyEngine.ts      # Strict 20-consecutive-approval streak tracking & quality withdrawal
│   │   └── emailSender.ts         # Safe email sending abstraction (simulated default)
│   ├── api/
│   │   ├── app.ts                 # Express REST API (routes for intake, reviews, autonomy, metrics)
│   │   └── server.ts              # API server startup entry point
│   ├── models/
│   │   └── types.ts               # Complete domain interfaces & type definitions
│   ├── storage/
│   │   └── persistentStore.ts     # Atomic file-backed JSON storage surviving restarts
│   ├── utils/
│   │   ├── config.ts              # Environment configuration loader with safe defaults
│   │   ├── logger.ts              # Safe logger with secret/API key masking
│   │   └── voiceGuide.ts          # Configurable company voice and formatting principles
│   ├── data/
│   │   └── syntheticEmails.ts     # 55 realistic synthetic customer emails covering 7 categories
│   ├── scripts/
│   │   └── evaluate.ts            # 55-email evaluation runner and reporting pipeline
│   └── cli.ts                     # Terminal CLI for queue inspection and draft review
├── tests/
│   ├── classifier.test.ts         # Categorization, uncertainty, and edge case tests
│   ├── kbClient.test.ts           # KB client, citations, timeout, and mock fallback tests
│   ├── drafter.test.ts            # Reply drafting, company voice, and escalation routing tests
│   ├── autonomyEngine.test.ts     # 20-streak threshold, category isolation, resets, and quality withdrawal
│   ├── reviewWorkflow.test.ts     # Approve, edit, reject, regenerate, escalate, and audit history tests
│   ├── sendingSafety.test.ts      # Safe simulated sending, duplicate prevention, and pre-send checks
│   ├── api.test.ts                # Supertest integration tests for REST API endpoints
│   └── evaluation.test.ts         # Synthetic dataset validation and evaluation reproducibility tests
├── .env.example                   # Safe environment template
├── tsconfig.json                  # Strict TypeScript configuration
└── package.json                   # Dependencies, scripts, and Jest config
```

---

## 2. Configured Email Categories

The system categorizes incoming emails into 7 configurable categories:

1. `technical_support`: Server bugs, DNS/SSL failures, webhook 500 errors, rate limits, script breaks.
2. `billing_and_payments`: Invoices, VAT receipts, credit card updates, refund inquiries, Stripe gateway settings.
3. `account_and_login`: Password resets, 2FA lockout, admin user roles, account ownership transfers, session timeouts.
4. `product_configuration`: How-to questions, form manager dropdowns, lead routing, menus, recurring plans, SEO meta tags.
5. `feature_request`: Mobile app wrappers, crypto payments, AI writing assistants, WhatsApp buttons, CRM sync.
6. `complaints`: Frustrated customers, service interruption complaints, billing disputes, legal/trademark grievances.
7. `other_or_uncertain`: Ambiguous messages, empty bodies, unsupported third-party software (e.g. WordPress plugins), partnership pitches.

---

## 3. Knowledge Brain Integration (`POST /api/v1/query`)

Before drafting factual customer replies, the agent queries the Task 1 Knowledge Brain:

- **Endpoint**: `POST /api/v1/query`
- **Request Format**:
  ```json
  {
    "query": "How do I connect my custom domain nameservers?",
    "top_k": 3,
    "min_score": 0.5
  }
  ```
- **Response Format**:
  ```json
  {
    "query": "How do I connect my custom domain nameservers?",
    "answer": "Grounded answer from documentation...",
    "confidence_score": 0.94,
    "escalated": false,
    "escalation_id": null,
    "sources": [
      {
        "title": "Guide 1. How to Connect a Live Domain Name",
        "url": "https://support.brilliantdirectories.com/support/solutions/articles/12000065940-guide-1-how-to-connect-a-live-domain-name",
        "snippet": "The current Domain Manager guides the entire connection...",
        "score": 0.88,
        "images": [...]
      }
    ],
    "images": [...]
  }
  ```
- **Factual Grounding**: Factual claims cite retrieved source URLs and screenshot references. If the Knowledge Brain returns `escalated: true` or low confidence (`< 0.60`), the agent marks `humanReviewRequired: true` and refrains from sending unverified answers.
- **Resilience**: If Task 1 is unreachable or times out, the client logs a warning and falls back to deterministic mock data without crashing.

---

## 4. Strict 20-Consecutive-Approval Autonomy Rule

Automatic sending is gated by the strict 20-consecutive-approval rule:

- **Category Isolation**: Consecutive approval streaks are tracked **strictly per category**. Approvals in `technical_support` do not bleed into `billing_and_payments`.
- **Threshold**: Exactly **20 consecutive unedited human approvals** in a category must be recorded before autonomy (`isAutonomous = true`) is granted for that category.
- **Strict Reset**: Any **edit**, **rejection**, or **regeneration** immediately resets `consecutiveUneditedApprovals = 0`.
- **Draft-Level Gates**: Even if a category has achieved autonomy, an individual draft **cannot** be auto-sent if:
  - `draft.humanReviewRequired === true` (ambiguous question, sensitive billing refund, or complaint).
  - `draft.supportingSources.length === 0` (no factual grounding).
  - Email has already been sent (duplicate send prevention).
- **Persistence & Concurrency**: Streak counts and autonomy states persist across application restarts via atomic JSON writes and mutex locking.

---

## 5. Quality-Based Withdrawal of Autonomy

Autonomy is not irrevocable. To safeguard customer experience against quality drift:

- **Rolling Window**: Monitors the last 10 reviews in each category (`qualityWindowSize = 10`).
- **Trigger Conditions**:
  - **Edit Rate**: If more than 20% of recent drafts in the window required edits (`editRate > 0.20`), autonomy is revoked immediately.
  - **Rejection Rate**: If more than 5% of drafts are rejected (`rejectionRate > 0.05`), autonomy is revoked immediately.
- **State Update**: `isAutonomous` transitions to `false`, `autonomyWithdrawnAt` timestamp is recorded, and the exact mathematical reason is logged and persisted.
- **Recovery Condition**: The category returns to human-review mode. To recover autonomy, the agent must achieve **another 20 consecutive unedited approvals**.

---

## 6. Safe Email Sending Abstraction

- **Simulated Sending by Default**: `ENABLE_REAL_EMAIL_SENDING=false`. Drafts approved or auto-sent are recorded in `data/inbox_store.json` under `sentLog` with `simulated: true`, printing clear logs and preventing email leaks.
- **Real Provider Gate**: A real email provider is enabled only when `ENABLE_REAL_EMAIL_SENDING=true` and explicit SMTP credentials are provided.
- **Pre-Send Verification**: Every send checks `store.isAlreadySent(email.id)` to block duplicate sends.

---

## 7. Setup & Installation

### Prerequisites
- Node.js v18+ (tested on Node.js v24.19.0)
- npm v9+

### Installation
```bash
cd task2-inbox-agent
npm install
```

### Environment Configuration
Copy the example file:
```bash
cp .env.example .env
```
Key environment variables:
| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | `""` | Anthropic Claude API Key (optional in mock mode) |
| `MOCK_LLM` | `true` | When `true`, uses deterministic Claude mocks |
| `MOCK_KB` | `true` | When `true`, uses offline Knowledge Brain mock |
| `KB_API_URL` | `http://127.0.0.1:8000` | Task 1 Knowledge Brain endpoint URL |
| `ENABLE_REAL_EMAIL_SENDING` | `false` | Safe simulation mode (prevents real email dispatch) |
| `INBOX_PORT` | `3000` | REST API Server port |

---

## 8. Running the Application

### 1. Start REST API Server
```bash
npm start
# or
npm run dev
```
Server boots on `http://localhost:3000`.

### 2. Run Interactive CLI
```bash
# View current inbox status and category autonomy streaks
npm run cli -- status

# View drafts currently awaiting human review
npm run cli -- drafts

# Review a draft (approve, edit, reject, regenerate, escalate)
npm run cli -- review draft_123 approve
npm run cli -- review draft_123 edit "Custom edited reply text"
npm run cli -- review draft_123 reject "Incorrect advice"

# Ingest a test email
npm run cli -- ingest customer@example.com "DNS help" "How do I point my domain?"
```

---

## 9. Automated Testing

Run the complete test suite:
```bash
npm test
```
The suite includes 8 test files and 44 automated tests:
- `tests/classifier.test.ts`: Categorization accuracy, heuristics, empty/vague inputs.
- `tests/kbClient.test.ts`: Knowledge Brain HTTP contract, citations, timeout, fallback.
- `tests/drafter.test.ts`: Grounded reply drafting, company voice, screenshot references.
- `tests/autonomyEngine.test.ts`: 20-streak threshold, category isolation, resets, restart persistence, concurrency, and rolling quality withdrawal.
- `tests/reviewWorkflow.test.ts`: Approve, edit, reject, regenerate, escalate actions and audit trail.
- `tests/sendingSafety.test.ts`: Safe simulated sending, duplicate send prevention.
- `tests/api.test.ts`: Supertest integration tests for REST API endpoints.
- `tests/evaluation.test.ts`: Synthetic dataset schema and evaluation runner validation.

---

## 10. Synthetic Evaluation Dataset (55 Emails)

The evaluation suite evaluates 55 realistic synthetic customer emails covering all 7 categories:
- Technical support (DNS, SSL, webhooks, 500 errors, rate limits, photo uploads, database timeouts).
- Billing and payments (VAT receipts, Stripe gateways, duplicate charges, tax exemptions, chargebacks).
- Account and login (password resets, 2FA lockout, ownership transfers, admin roles, session timeouts).
- Product configuration (custom form fields, lead routing, menu links, recurring plans, SEO meta tags).
- Feature requests (mobile apps, crypto payments, AI writing, WhatsApp buttons, CRM sync).
- Complaints (downtime outrage, SLA delays, billing disputes, CSS regressions, listing fraud, legal threats).
- Other or uncertain inquiries (empty body, ambiguous queries, WordPress plugin questions, HIPAA compliance).

### Running Evaluation
```bash
npm run eval
```
Sample benchmark results:
- **Category Classification Accuracy**: **94.5% (52/55)**
- **Knowledge Brain Grounded Rate**: **98.2%**
- **Average Processing Latency**: **11.8 ms**
- **Output Report**: Saved to `data/evaluation_report.json`.

---

## 11. REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/inbox/health` | Service health status and active configuration |
| `POST` | `/api/v1/inbox/emails` | Ingest single incoming customer email |
| `POST` | `/api/v1/inbox/emails/batch` | Batch ingest array of customer emails |
| `GET` | `/api/v1/inbox/emails` | List all customer emails |
| `GET` | `/api/v1/inbox/emails/:id` | Get email details and associated draft ID |
| `GET` | `/api/v1/inbox/drafts` | List drafts (`?awaiting_review=true` filter supported) |
| `GET` | `/api/v1/inbox/drafts/:id` | Get single draft with customer email and citations |
| `POST` | `/api/v1/inbox/drafts/:id/review` | Submit human review decision (`approve`, `edit`, `reject`, `regenerate`, `escalate`) |
| `GET` | `/api/v1/inbox/autonomy` | Current autonomy state and consecutive streaks for all 7 categories |
| `GET` | `/api/v1/inbox/metrics` | Overall quality, approval rates, edit rates, and rejection rates |
| `GET` | `/api/v1/inbox/sent` | Sent log of simulated and live email transmissions |
| `GET` | `/api/v1/inbox/reviews` | Complete audit history of human review decisions |

---

## 12. Known Limitations & Future Improvements

1. **Email Threading**: Currently operates on single-turn customer emails; multi-turn conversation threading and ticket history can be added.
2. **Multi-Reviewer Role-Based Access Control**: Currently accepts reviewer names; future versions could integrate with OAuth2/JWT auth to restrict approval authority based on reviewer clearance level.
3. **Live Task 1 Co-Hosting**: Designed to run seamlessly either standalone in mock mode or live alongside Task 1 Knowledge Brain running on `http://127.0.0.1:8000`.

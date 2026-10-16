# AI Development Log: Prompts & Decision Records

This log documents five high-value prompts used during the development of the BusinessLabs AI Tech Consultant platform, along with one explicitly rejected AI-generated implementation and rationale.

---

## Five Useful Engineering Prompts

### 1. Task 1: Strict Anti-Hallucination & Evidence Grounding Prompt
> *"You are the Brilliant Directories Technical Consultant RAG Engine. Generate a solution to the user inquiry grounded strictly in the retrieved ChromaDB chunks. You must include exact source URLs and image references provided in chunk metadata. If the retrieved chunks do not contain sufficient evidence to answer the inquiry definitively, you must abstain and flag the inquiry for Tier 2 human-expert escalation. Never fabricate external documentation URLs or assume unsupported platform capabilities."*
- **Outcome**: Successfully eliminated invented documentation URLs and enforced deterministic escalation when evidence was missing.

### 2. Task 2: Autonomy Engine State Machine & Streak Tracking Prompt
> *"Design a TypeScript service managing the 20-consecutive-unedited-approval autonomy rule. It must track approvals on an isolated per-category basis, reset the streak to 0 immediately if a human reviewer edits, rejects, or escalates a draft, and withdraw autonomy if the rolling window edit rate exceeds 25%. Ensure state persists across restarts and that concurrent reviews are serialized via an in-memory lock."*
- **Outcome**: Produced the thread-safe `AutonomyEngine` and persisted audit logs in `task2-inbox-agent/src/services/autonomyEngine.ts`.

### 3. Task 3: Granular Meeting Requirement Extraction Prompt
> *"Analyze this client meeting transcript. Extract every requirement as a granular object with a stable ID, title, description, and verbatim supporting quote from the transcript. Distinguish explicit facts from unconfirmed interpretations, assumptions, and conflicts. Do not invent pricing, timelines, or product capabilities. If a requirement is contradictory or incomplete, formulate a targeted clarification question."*
- **Outcome**: Formed the core prompt of `MeetingAnalyst` in `task3-meeting-scope/src/agents/analyst.py`.

### 4. Task 3: Bottom-Up Task Breakdown & Mathematical Consistency Prompt
> *"Generate an implementation task breakdown from the extracted requirements and capability assessments. Every task must link to requirement IDs, work type (configuration, integration, custom_dev, testing, deployment), and estimated hours >= 0. Total project hours must be mathematically computed strictly as the sum of task hours rather than an independently estimated figure. Mark tasks linked to ambiguous requirements as provisional."*
- **Outcome**: Established the bottom-up hour estimation engine in `ScopePlanner` (`planner.py`).

### 5. Task 3: Change Detection & Version Evolution Prompt
> *"Compare this follow-up transcript against baseline Scope v1.0. Classify each change item into unchanged, clarified, modified, added, removed, or out_of_scope. Calculate individual hour deltas and net project delta. Output a ChangeDetectionReport, preserve baseline v1.0 immutably, and output revised Scope v2.0 in draft status requiring renewed human approval."*
- **Outcome**: Implemented the change classification and version preservation engine in `DiffEngine` (`diff_engine.py`).

---

## One Rejected AI Suggestion & Engineering Rationale

### The Rejected Suggestion: Monolithic "All-in-One" LLM Scope & Hours Generator
During early Task 3 prototyping, an LLM suggested generating the entire scope, task breakdown, hour estimates, and proposal draft in a single unconstrained prompt:
```
Prompt: "Here is a meeting transcript. Write a complete scope of work, break it into tasks with hours, and write a client proposal."
```

### Why It Was Rejected
1. **Mathematical Inconsistency**: The monolithic generation produced a proposal claiming a "40-hour total implementation", while the itemized tasks summed to 56 hours.
2. **Hallucinated Capabilities**: The unconstrained model assumed Brilliant Directories natively supported "HIPAA-compliant medical record storage" and "native iOS Swift wrappers", which are completely unsupported by the platform.
3. **Loss of Traceability**: The single prompt dropped verbatim transcript evidence, making it impossible for a human consultant to verify where a requirement originated.
4. **Bypassed Approval Gates**: Generating a proposal directly from raw transcript text skipped capability checks and human review, violating the core safety requirement: *No proposal may be delivered to a client without explicit human approval.*

### Adopted Solution
We rejected the monolithic approach in favor of a 5-stage pipeline (`MeetingAnalyst` ➔ `CapabilityAnalyst` ➔ `ScopePlanner` ➔ `ProposalWriter` ➔ `DiffEngine`) with Knowledge Brain grounding, bottom-up hour sums, and hard backend delivery gates.

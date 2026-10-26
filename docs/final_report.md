# AegisFlow — Final Report

**Project:** AegisFlow: A Governed Hierarchical Multi-Agent System for Document-Based Task Automation with Human-in-the-Loop Approval  
**Course:** SIP10 Final Project — “Building a Simple Governed Agentic AI System”  
**Version:** 0.1.0  
**Date:** 26 October 2026  
**Prepared by:** SIP10 project author  
**Environment:** Windows, Python 3.13.7, project `.venv`  
**Recorded test result:** **76 passed, 0 failed** (`pytest tests\ -q`)

---

## Abstract

AegisFlow is a working prototype of a governed, hierarchical multi-agent document assistant built with LangGraph, LangChain, Streamlit, Pydantic, and SQLite. A user submits a natural-language request with PDF, TXT, or DOCX files. A Planner creates a validated plan; a deterministic Orchestrator routes work through analysis, drafting, and assurance teams; specialist LLM workers extract claims, verify them against the source, and write a cited deliverable; deterministic checks and an independent reviewer assess the result; and the workflow stops at a human approval gate. No output can be finalized or exported as approved without a human decision bound to the exact output version and SHA-256 content hash.

The prototype is designed around a distinction between **generation** and **authority**. Language models generate and transform text. Deterministic code owns routing, permissions, retry limits, approval validation, and export checks. The human owns final approval.

Mock mode is implemented and verified with 76 automated tests, including 13 end-to-end scenarios and three headless Streamlit UI flows. A project-scoped `aegisflow-ui` skill documents the tokenized, responsive interface. Real-provider adapters for OpenRouter, Gemini, and OpenAI are implemented, but **no live provider call was made** in this build because real mode was not enabled and no external call was authorized. Real mode is therefore reported as implemented but unverified, not as a demonstrated capability.

---

## 1. Introduction

### 1.1 Problem

Document work is repetitive but consequential. A meeting brief, project summary, or action list may influence decisions, yet it is often produced by a single model call over a file. That pattern hides three risks:

1. **Fabrication.** The model can add plausible facts that are absent from the source.
2. **Prompt injection.** A document may contain instructions that attempt to change model behaviour, reveal secrets, or bypass review.
3. **Unaccountable automation.** A reader may not know which text was approved, by whom, or whether it changed afterward.

Prompt engineering alone does not solve these problems because a prompt is advisory. A system that needs dependable controls must enforce them in code and give a human explicit authority over the final artefact.

### 1.2 Goal

Build a prototype that:

- performs a real document task end to end;
- demonstrates a hierarchical multi-agent workflow on LangGraph;
- treats uploaded content as untrusted data;
- produces traceable, non-fabricated output;
- requires human approval before finalization;
- records routing, agent, policy, and human activity;
- applies NIST AI RMF concepts honestly;
- is tested and documented rather than merely proposed.

### 1.3 Contributions

The project contributes:

1. A **hybrid hierarchy** in which LLM workers provide language capability while rule-based leads and deterministic gates own permissions, routing, and approval.
2. A **hash-bound human approval** protocol that survives resume, version changes, and content tampering.
3. A **mock model that is a real LangChain `BaseChatModel`**, so tests exercise the production invoke → parse → validate → retry path without network access.
4. A **selective routing** scheme that runs only the agents a validated plan requires.
5. A **complete evidence package**: 8 governance rules, 9 risks, 13 end-to-end scenarios, 6 skills, a NIST worksheet, and an honest verification matrix.

### 1.4 Scope

In scope: a single-user local web application; PDF/TXT/DOCX extraction; document-grounded summaries, outlines, reports, meeting briefs, and action items; human approve/reject/revision; Markdown/TXT export; audit and workload metrics.

Out of scope: multi-user authentication, OCR, external actions, web research, email/calendar integration, PDF/DOCX export, queues, containers, and production deployment.

---

## 2. Requirements and alignment

### 2.1 Course requirements

The assignment images specify:

- **Image 1:** an agentic system, the PLAN → ORCHESTRATE → EXECUTE → CHECK → HUMAN APPROVAL → OUTPUT pipeline, NIST AI RMF, agents plus skills, at least 3 agents, and at least 5 governance rules.
- **Image 2:** twelve deliverables: working prototype, project description, 3+ agents, 3+ `SKILL.md` files, orchestration workflow, system diagram, NIST worksheet, 5+ risks, 5+ test cases, 5+ governance rules, human approval explanation, and a presentation of at most 15 minutes.
- **Image 3:** USER → PLANNER → ORCHESTRATOR → three SKILL/AGENT boxes → REVIEWER → HUMAN APPROVAL → FINAL OUTPUT.

### 2.2 Delivered counts

| Item | Required | Delivered |
|---|---:|---:|
| Agents/roles | 3 | **6** |
| `SKILL.md` packages | 3 | **6** |
| Governance rules | 5 | **8** |
| Risks | 5 | **9** |
| Test cases | 5 | **13 E2E + 60 unit/integration + 3 UI = 76** |
| NIST functions | 4 | **4** |
| UI pages | not specified | **5** |
| UI design system skills | not specified | **1** (`aegisflow-ui`) |
| SQLite application tables | not specified | **9** |

A detailed requirement-to-evidence mapping is in [requirements_traceability.md](requirements_traceability.md).

### 2.3 Alignment verdict

The prototype aligns with all three images and exceeds the stated minimums. The one interpretive decision is **selective routing**: a summary task does not invoke all three executors because that would waste calls and increase failure surface. The required three-executor chain is demonstrated by a report or meeting-brief task, and TC-13 verifies that routing follows the plan rather than a fixed pipeline. The Workflow page always shows the full four-level hierarchy and routing log, so the required sequence remains visible even when a task legitimately skips an executor.

---

## 3. Design

### 3.1 Design principles

1. **Authority is not generated.** Models can propose; deterministic code and humans decide.
2. **Ground every claim.** A claim needs a source reference or an explicit `UNVERIFIED` label.
3. **Treat documents as data.** Uploaded text never changes permissions or tools.
4. **Minimize external exposure.** Mock mode is the default; real mode requires explicit authorization.
5. **Bound autonomy.** Every loop has a limit and an escalation path.
6. **Make activity visible.** Routing, agents, errors, policy findings, and decisions are recorded.
7. **Label simulation.** Mock output is never presented as real analysis.

### 3.2 System context

```text
User
  │ request + files
  ▼
Streamlit UI ──────────────► SQLite app database (9 tables)
  │ start / resume                 ▲
  ▼                                │
WorkflowService ──► LangGraph root graph
                         │
                         ├── mock ScriptedChatModel (no network)
                         └── real OpenRouter / Gemini / OpenAI (explicitly gated)
                         │
                         ▼
                 SQLite checkpoint database
```

The two SQLite files have different jobs:

- `aegisflow.sqlite` stores tasks, files, subtasks, executions, versions, reviews, evidence, audit, and workload metrics.
- `checkpoints.sqlite` stores LangGraph checkpoints keyed by `thread_id = task_id`.

### 3.3 Hierarchy

| Level | Component | Model calls? | Responsibility |
|---|---|---|---|
| 1 | Root Orchestrator | No | Validate, route, enforce limits, open the human gate, finalize, escalate |
| 2 | Planner | **Yes, always first** | Produce a validated plan from a fixed executor/skill catalog |
| 2 | Team leads | No | Enforce prerequisites, choose the next worker, classify team status |
| 3 | Document Analyst | Yes | Extract sentence-level claims with file and location |
| 3 | Evidence Verifier | Yes | Mark claims supported, unsupported, conflicting, or unverified |
| 3 | Report Writer | Yes | Format only supplied claims into required sections |
| 3 | Independent Reviewer | Yes | Pass, needs revision, or fail with reasons |
| 4 | Policy Checker | No | Deterministic draft checks |
| 4 | Approval and export gates | No | Hash-bound human control and re-verification |

Work is delegated downward, results report upward, and unresolved problems escalate to the human. The leads are deterministic on purpose: if a language model could choose whether approval is required, approval would not be a control.

### 3.4 Graph topology

```text
START
  │
validate_request
  ├── invalid ──► blocked
  ▼
planner
  ├── missing information ──► blocked
  ├── failure ──► escalate
  ▼
orchestrator ◄──────────────────────┐
  ├── analysis_team ─────────────────┤
  ├── drafting_team ─────────────────┤
  ├── assurance_team ────────────────┘
  ├── human_review ──► interrupt()
  │       ├── approve + valid record ──► finalize ──► END
  │       ├── reject ──► rejected ──► END
  │       └── revision ──► bounded loop
  ├── blocked ──► END
  └── escalate ──► END
```

### 3.5 State design

The parent state is a `TypedDict` with append-only fields (`agent_results`, `errors`, `routing_log`, `audit_events`) using reducers, plus ordinary fields for plan, claims, evidence, draft, version, policy report, review result, approval, revision counters, and status.

Team subgraphs use a plain `TeamState` without reducers. A wrapper node slices the parent state on input and returns only team output keys on output. This was a deliberate engineering response to a verified problem: passing inherited append-only lists into a subgraph that shares reducers duplicated records. The wrapper keeps reducers at one graph level and is documented in [architecture.md](architecture.md) §6.2.

Secrets, API keys, raw prompts, and the full document corpus are not stored in checkpoints. The graph holds the extracted text needed by workers plus IDs and hashes. Raw uploaded text is not written to the audit log.

### 3.6 Persistence

The application database has nine tables:

1. `tasks`
2. `task_files`
3. `subtasks`
4. `agent_executions`
5. `output_versions`
6. `human_reviews`
7. `evidence_refs`
8. `audit_log`
9. `workload_metrics`

Foreign keys cascade from tasks. SQLite uses WAL journaling, foreign keys, `synchronous=NORMAL`, and an application-level lock. Deleting a task removes its rows, uploaded files, and checkpoint thread.

### 3.7 Agents and skills

| Agent | Skill | Key constraint |
|---|---|---|
| Planner | `task-planning` | Plan only from the executor/skill whitelist; report missing information |
| Document Analyst | `document-extraction` | Every claim carries filename + location; skip instruction-like text |
| Evidence Verifier | `evidence-verification` | Use supplied passages only; never verify from model memory |
| Report Writer | `report-writing` | Required sections; no external-action claims; no invented facts |
| Reviewer | `quality-review` | Independent; never rewrites or self-approves |
| Policy Checker | `untrusted-content-handling` (shared) | Deterministic; no model |

Six `SKILL.md` files are validated at load time. Each has frontmatter (`name`, `description`, `owner_agent`, `inputs`, `outputs`) and body sections for purpose, procedure, output format, constraints, failure conditions, and escalation. The skill used is recorded in `agent_executions`.

### 3.8 Selective routing

| Request signal | Plan | Executors invoked |
|---|---|---|
| “summary”, “summarize” | Analyst only | Document Analyst |
| “outline” | Analyst → Writer | Document Analyst, Report Writer |
| “brief”, “meeting”, “report”, action items, default | Analyst → Verifier → Writer | All three |
| No readable file | No executable subtasks | None; task blocked |

The orchestrator accepts only this destination whitelist: `analysis_team`, `drafting_team`, `assurance_team`, `human_review`, `blocked`, `escalate`. Every choice is validated and written to the routing log and audit trail with a reason and rule ID.

---

## 4. Governance, NIST, and human approval

### 4.1 Governance rules

| ID | Rule | Primary enforcement |
|---|---|---|
| GR-01 | Human approval before finalization/export | Interrupt, persisted decision, hash checks in finalize and export |
| GR-02 | No fabrication | Source-bound claims, verifier, required sections, policy checks, reviewer |
| GR-03 | Uploaded content is untrusted data | Delimiters, injection scan, empty tool allowlist, policy scan |
| GR-04 | Protect PII and secrets | Redaction, mock default, external-LLM authorization gate |
| GR-05 | Least privilege | State slicing, fixed whitelist, no action tools |
| GR-06 | Auditable activity | Audit log, execution rows, routing log, immutable versions |
| GR-07 | Bounded autonomy | Retries, team/lead limits, revision budget, recursion limit |
| GR-08 | Transparency | SIMULATED labels in UI, draft, version, and export |

Each rule has an owner, enforcement point, evidence, failure behavior, residual risk, and tests in [governance_rules.md](governance_rules.md).

### 4.2 NIST AI RMF

- **GOVERN:** eight rules with named owners, a third-party provider gate, approval accountability, and documented policies.
- **MAP:** intended use, single-user context, non-goals, data sources, affected parties, and nine risks.
- **MEASURE:** groundedness, citation coverage, approval outcome, revisions, retries, elapsed time, and 76 tests. No benchmark numbers are invented.
- **MANAGE:** block/escalate paths, bounded retries, incident procedure, deletion, residual-risk acceptance, and open actions.

The worksheet is candid about gaps: live-provider behavior, stakeholder consultation, formal impact assessment, drift monitoring, backup/restore, and fairness evaluation are not complete.

### 4.3 Human approval protocol

An approval binds:

- task id;
- output version id;
- SHA-256 content hash;
- reviewer name;
- an actor string beginning with `human:`;
- timestamp.

The UI must call `record_decision(...)` **before** resuming the graph. The graph does not trust the resume payload; it re-reads the persisted review for the exact version. On approval it calls `assert_finalizable`, which verifies:

1. the task exists and is `approved` or `completed`;
2. the approved version is still current;
3. the stored content matches its hash;
4. the latest review for that version is `approve`;
5. the review's hash equals the content hash.

Export runs the same check. A new output version invalidates the previous approval. Rejection is terminal. Human-requested revision is bounded by `max_revisions` and returns to review with a new version.

### 4.4 Threat model

| Threat | Control | Residual |
|---|---|---|
| Agent records an approval | Actor prefix check; agents never import approval code | A future code change could bypass; tests guard it |
| Forged resume payload | Graph re-reads persisted review | None found in tests |
| Replay of an old approval | Duplicate and stale-version checks | — |
| Content edited after approval | Hash recomputation at finalize/export | Local DB rewrite can forge both content and hash |
| Local SQLite tampering | Detective hash/audit checks | Not tamper-evident against a local administrator |
| Impersonated reviewer | Reviewer name is free text | No authentication in v1 |
| UI crash after decision | Decision is durable before resume | Operator retries resume |

The hash is an integrity check, **not** a digital signature. This is stated in the approval design, risk register, NIST worksheet, and final report.

---

## 5. Implementation

### 5.1 Technology

| Component | Version |
|---|---|
| Python | 3.13.7 |
| langgraph | 1.2.16 |
| langgraph-checkpoint-sqlite | 3.1.2 |
| langchain-core | 1.6.12 |
| langchain-openai | 1.7.2 |
| langchain-google-genai | 4.4.2 |
| streamlit | 1.66.1 |
| pydantic | 2.12.5 |
| pymupdf | 2.0 |
| python-docx | 1.2.0 |
| python-dotenv | 1.2.4 |
| PyYAML | 6.0.3 |
| pytest | 9.1.1 |

All versions were verified in the project virtual environment. No FastAPI, Redis, Docker, queue, or CrewAI dependency exists.

### 5.2 Mock mode

`ScriptedChatModel` subclasses `langchain_core`'s `BaseChatModel`. Its `_generate` method calls a deterministic builder supplied by the agent. The same invoke → text → JSON parse → Pydantic validation → retry path runs in tests as in real mode, with zero network calls. Mock results carry `simulated=true` and are labeled throughout the UI and exports.

This design avoids a common weakness in student prototypes: a “mock pipeline” that bypasses the real framework. AegisFlow's tests exercise the actual compiled graph and the actual LangChain model interface.

### 5.3 Real mode

Adapters:

- OpenRouter: `ChatOpenAI(base_url="https://openrouter.ai/api/v1")`
- OpenAI: `ChatOpenAI`
- Gemini: `ChatGoogleGenerativeAI`

All use temperature 0 and a 60-second timeout, with application-level retries. Provider text is stripped of Markdown fences, reduced to the outermost JSON object, and validated against the agent schema. Malformed output is classified separately from transient failure.

Real mode requires **all four** conditions:

1. `AEGISFLOW_MODE=real`
2. `AEGISFLOW_ALLOW_EXTERNAL_LLM=true`
3. a provider key
4. one non-empty model id

If any is missing, startup falls back to mock and records the reason. No live call was made in this build.

### 5.4 Document handling

Supported: `.pdf`, `.txt`, `.docx`, maximum 10 MB per file (configurable).

Each file records a status: `ok`, `empty`, `encrypted`, `corrupted`, `unsupported`, or `too_large`, with a message. Readable files proceed; all-unreadable input blocks the task. Extracted text is wrapped in delimiters and scanned for instruction-like patterns. OCR is not implemented.

### 5.5 UI

Five pages, aligned to the supplied mockup:

- **Dashboard:** metric cards, a recent-tasks table, a workload card, and a decision card that points to the current approval gate.
- **New task:** bordered request form with format, manual-time estimate, uploads, and acknowledgement, plus a “What happens next” card that explains planning, selective execution, review, and approval.
- **Workflow:** two-column view with the four-level agent hierarchy on the left and the routing log on the right; plan, policy/review status, draft preview, subtasks, executions, and audit sit under “Task details and audit”.
- **Review:** two-column view with the read-only draft and agent checks on the left, and evidence plus the version-bound decision form on the right; the exact version and hash appear in the page header and again under “Version fingerprint and technical checks”.
- **History:** columnar task table with a status filter and per-row actions; approved rows expose Markdown/TXT downloads, rejected/blocked/failed rows expose a confirmation-gated delete, and audit detail sits under “Task details and audit”.

Navigation uses a dark navy sidebar built from five Streamlit buttons that set the canonical `st.session_state["page"]`; the page key remains the single source of truth for programmatic navigation.

The interface is backed by the project-scoped `aegisflow-ui` skill (`.opencode/skills/aegisflow-ui/`): `SKILL.md`, six references, three verification scripts, a theme template, base CSS, and a `design_preview.py` preview page. Tokens live in `aegisflow/ui/styles.css`; the app shell, cards, form controls, and decision radio live in `app.css`; tables, hierarchy, routing, evidence, next-steps, and history rows live in `mockup.css`. Status is never color-only: badges pair an icon with text, green is reserved for recorded human approval, agent progress uses blue/teal, SIMULATED is amber, approval actions name the version (“Approve version N”), rejection requires a separate terminal confirmation, and deletion uses an explicit `st.dialog`. Responsive rules stack the two-column layouts and metric grid below 900px and collapse the hierarchy and history table at phone widths.

Technical material is deliberately collapsed or moved off the primary path: raw task IDs and thread details are not shown, runtime configuration is not duplicated in the sidebar, routing and audit tables sit under “Task details and audit”, and the content hash and technical checks sit under “Version fingerprint and technical checks”. This keeps the approval task visible without hiding governance evidence.

UI verification: `check_theme.py` passes 16/16, `check_contrast.py` passes 40/40 in both light and dark themes, and the headless `AppTest` suite exercises all five pages plus approval, rejection, and revision flows. Playwright with Chromium is installed in the local `.venv` for verification only; `check_responsive.py` now passes at 360, 768, 1280, and 1536 px and writes full-page screenshots to `ui_checks/`. A full accessibility (axe) audit and a pixel-diff comparison against the mockup PDF were still not run.

### 5.6 Exports

Markdown and TXT exports contain:

- task id;
- version number;
- content hash;
- reviewer;
- approval timestamp;
- simulated status;
- the approved content.

`export_markdown` and `export_txt` call `assert_finalizable` before producing content. A stale, rejected, or tampered version cannot be exported as approved.

---

## 6. Evaluation

### 6.1 Test strategy

| Level | Scope | Count |
|---|---|---:|
| Unit | Models, database, approvals, extraction, skills, policy checks, metrics, settings fallback | 60 |
| End-to-end | Real compiled graph, real SQLite, real approval state machine, mock LLM; TC-01–TC-13 | 13 |
| UI | Streamlit `AppTest`: all five pages, decision refusal, approval, rejection confirmation, revision, finalization | 3 |
| **Total** | | **76** |

Additional recorded smoke checks:

- Manual mock run reached `awaiting_human_review`; approval and resume reached `completed`.
- Streamlit server health endpoint returned `ok`.
- All 76 tests passed.
- Theme checks 16/16 PASS; contrast checks 40/40 PASS.
- Playwright responsive check at 360/768/1280/1536: **PASS** with full-page screenshots in `ui_checks/`.
- Browser spot-check of Review and History at 1280 and 360: **PASS** (`ui_checks/review_*.png`, `history_*.png`); the 360 px sidebar collapses and still reaches every page.
- `ruff check .` clean; coverage **76%** (statement + branch); CI matrix runs lint, tests with a 75% gate, and theme/contrast on Windows and Ubuntu.

### 6.2 End-to-end scenarios

| ID | Scenario | Result |
|---|---|---|
| TC-01 | Happy path: report, approval, finalize, Markdown/TXT metadata | **PASS** |
| TC-02 | Agent cannot approve; unpersisted resume escalates | **PASS** |
| TC-03 | New version invalidates prior approval | **PASS** |
| TC-04 | Rejection is terminal and blocks export | **PASS** |
| TC-05 | Revision is bounded and cannot bypass persistence | **PASS** |
| TC-06 | Prompt injection is inert; clean content survives | **PASS** |
| TC-07 | SIMULATED labels flow through review and export | **PASS** |
| TC-08 | No readable input blocks without fabrication | **PASS** |
| TC-09 | Corrupt/encrypted files are reported; readable files proceed | **PASS** |
| TC-10 | Tampering after approval blocks finalize and export | **PASS** |
| TC-11 | Repeated assurance failure escalates at the limit | **PASS** |
| TC-12 | Audit coverage; PII/secrets redacted | **PASS** |
| TC-13 | Summary uses analyst only; routes stay whitelisted | **PASS** |

### 6.3 Recorded result

```text
$ .\.venv\Scripts\python.exe -m pytest tests\ -q
...................................................................                      [100%]
76 passed in 6.79s
```

Duration varies by machine. The recorded result is the actual run, not an estimate.

### 6.4 What the evaluation proves

- The full graph runs in mock mode and stops at the human gate.
- Approval is required, persisted, hash-bound, and re-verified.
- Stale, missing, duplicate, agent-authored, and tampered approvals fail.
- Rejection and escalation cannot silently complete.
- Injection text does not reach the draft; clean facts survive.
- Selective routing is real, not a claim.
- Audit records are produced and redacted.
- The Streamlit UI component tree renders headlessly across all five mockup-aligned pages, completes an approval flow, refuses an unacknowledged decision, requires a terminal confirmation for rejection, and creates a new version through the revision flow (`AppTest`; CSS/accessibility not fully covered).
- The tokenized UI passes theme and contrast checks in light and dark themes; Playwright confirms no horizontal overflow and a usable layout at 360/768/1280/1536 px.

### 6.5 What it does not prove

| Area | Status | Reason |
|---|---|---|
| Live OpenRouter/OpenAI/Gemini calls | **Not executed** | Real mode not enabled; no call authorized |
| Real-model output quality/latency | **Not measured** | Same |
| Browser CSS/accessibility | **Partially checked** | `AppTest` is headless; Playwright responsive PASS at four widths with screenshots, but no axe audit or visual diff |
| Multi-user/concurrency | **Not tested** | Single-user design |
| OCR | **Not implemented** | Out of scope |
| Disk-full/SQLite corruption | **Not tested** | Out of scope |
| Fairness/bias | **Not evaluated** | No people-decisions or demographic data |
| Statistical quality benchmark | **Not performed** | No labelled corpus; no invented numbers |

---

## 7. Verification status

### 7.1 Implemented and verified

- Mock-mode end-to-end workflow
- Planner-first validated planning
- Rule-based team leads and LangGraph subgraphs
- Selective routing and whitelist enforcement
- Document extraction for PDF/TXT/DOCX
- Injection delimiting and scanning
- Claim extraction, evidence verification, grounded drafting
- Deterministic policy checks and independent review
- Hash-bound human approval, rejection, and bounded revision
- Finalize and export re-verification
- SQLite persistence, audit, and cascade deletion
- Log/feedback redaction
- SIMULATED labeling
- Streamlit pages, approval flow, and rejection confirmation (headless)
- Tokenized UI design system, theme/contrast checks, and four-width DOM probe
- Markdown/TXT approved exports

### 7.2 Implemented but not verified

- Live OpenRouter adapter
- Live Gemini adapter
- Live OpenAI adapter
- Real-model structured-output reliability and latency
- Real-model groundedness and citation quality
- Full browser-level layout and screenshots (Playwright responsive PASS at four widths), plus a full accessibility audit (not run)

### 7.3 Not implemented

- Authentication, roles, or multi-user operation
- OCR for scanned PDFs
- PDF/DOCX export
- External actions (email, shell, browser, calendar, finance)
- Cryptographic signatures or an external approval service
- Automated backup/restore
- Fairness/bias evaluation
- Load/performance testing at scale

These omissions are intentional scope decisions, not undisclosed gaps.

---

## 8. Discussion

### 8.1 Why deterministic leads?

A fully LLM-driven supervisor is more flexible but less governable. If a model chooses the next step, it can also be persuaded by document text to skip assurance or approve its own work. Deterministic leads trade semantic flexibility for predictable permissions, bounded cost, and testability. The design keeps language capability where it is needed — extraction, verification, writing, and review — and keeps authority in code and humans.

### 8.2 Why mock mode is more than a stub

A stub pipeline can pass tests while the real framework path remains broken. AegisFlow's mock is a genuine LangChain chat model, so the graph, message handling, parsing, validation, retries, and persistence are exercised. The limitation is output quality, not orchestration fidelity. This distinction is stated explicitly so the demo is not mistaken for real AI analysis.

### 8.3 The approval trade-off

A hash-bound approval is stronger than a boolean `approved` flag, but it is not a signature. It detects accidental or direct content changes at finalize/export time. It does not stop a local administrator who rewrites content, hash, and review rows together. For a single-user local prototype, this is a reasonable and disclosed trade-off. A production system would need authentication, signed records, and an external trust anchor.

### 8.4 Automation bias

The approval gate only works if the reviewer actually reads the output. The UI mitigates this by showing claims, evidence, policy findings, reviewer reasons, revision history, and the exact hash, and by requiring an explicit acknowledgement. It cannot eliminate rubber-stamping. A user study and reviewer training are future work.

### 8.5 PII in the review pane

Redacting the draft would make a meaningful review impossible: the reviewer must see the content that will be shared. The design therefore redacts logs, audit details, execution references, feedback, and error messages, while showing source-derived content in the review pane with a warning. This is a deliberate, disclosed trade-off, not an oversight.

---

## 9. Limitations

1. **Real-provider mode is unverified.** Adapters are implemented; no live call was made.
2. **No OCR.** Image-only PDFs cannot be processed.
3. **Single user, no authentication.** Reviewer identity is self-asserted.
4. **Local database is trusted.** Hash binding is integrity detection, not non-repudiation.
5. **Regex detection is incomplete.** Injection and PII scanners can miss novel patterns.
6. **Draft is not automatically redacted.** Reviewers must handle source PII appropriately.
7. **No external actions.** The system cannot send, publish, or execute anything.
8. **No fairness/bias evaluation.** Not intended for decisions about people.
9. **Browser-level UI testing is partial.** `AppTest` does not render CSS. Playwright now checks horizontal overflow and captures screenshots at 360/768/1280/1536, but no axe accessibility audit or pixel-diff against the mockup was performed.
10. **No statistical benchmark.** No claim of real-model quality is made.
11. **Lead iteration limits are fixed in code.** Team run limits and revision budgets are configurable; lead loops are fixed for safety.
12. **No backup/restore procedure.** Operators should copy both SQLite files before experimentation.

---

## 10. Future work

1. **Real-provider verification.** Configure a key, run TC-01/06/12 in real mode, record latency, error rates, malformed-output frequency, and a small quality evaluation.
2. **Signed approvals.** Replace the actor convention with authenticated identities and signed approval records.
3. **Browser-level UI testing.** Add Playwright/Selenium and an accessibility audit.
4. **Adversarial corpus.** Add encoded, multi-turn, delimiter-breaking, and multilingual injection fixtures.
5. **Better PII detection.** Replace regex-only detection with a reviewed detector and document residual misses.
6. **OCR.** Add a text-layer fallback for scanned PDFs, with explicit confidence and provenance.
7. **Backup/restore.** Add a tested procedure for both SQLite files.
8. **Provider failover.** Add a circuit breaker or multi-provider fallback if real mode becomes a requirement.
9. **Reviewer study.** Measure review time, trust calibration, and automation bias with real users.
10. **Optional PDF/DOCX export.** Implement only if it can be tested and approved like the current formats.

---

## 11. Conclusion

AegisFlow demonstrates that a hierarchical multi-agent document system can be useful without being unaccountable. The Planner establishes intent, the Orchestrator controls flow, specialist workers do the language work, deterministic checks and an independent reviewer challenge the result, and a human approves the exact version that will be exported.

The prototype is complete for the course scope: it runs in mock mode, it is tested with 76 passing tests, it enforces a hash-bound approval gate, it documents eight governance rules and nine risks, it includes a project-scoped UI design system, and it maps every course deliverable to evidence. It is equally important that the report does not overclaim: real-provider mode was not executed, and that limitation is visible in the README, UI, tests, NIST worksheet, and this report.

The central lesson is simple: **generation can be probabilistic; authority should not be.**

---

## Appendix A — Reproduction commands

```powershell
cd C:\xampp\htdocs\AegisFlow

# Install pinned dependencies
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Run the full test suite
.\.venv\Scripts\python.exe -m pytest tests\ -q

# Start the app (mock mode by default)
.\.venv\Scripts\python.exe -m streamlit run app.py

# Health check
Invoke-WebRequest http://localhost:8501/_stcore/health
```

Real mode: create `.env` from `.env.example`, add **one** key and **one** model id, set `AEGISFLOW_MODE=real` and `AEGISFLOW_ALLOW_EXTERNAL_LLM=true`, then re-run. Do not reuse the example file for keys.

---

## Appendix B — Project map

```text
AegisFlow/
├── app.py                         Streamlit entry point
├── config.py                      Frozen settings and safe fallback
├── requirements.txt               Pinned, verified dependencies
├── .env.example                   Placeholders only; no real secrets
├── .opencode/skills/aegisflow-ui/  UI design system, references, checks, preview
├── aegisflow/
│   ├── models.py                  Pydantic domain models and transitions
│   ├── state.py                   Graph state and reducers
│   ├── database.py                9-table SQLite schema and persistence
│   ├── approvals.py               Hash-bound approval state machine
│   ├── document_processing.py     Safe extraction and injection scan
│   ├── redaction.py               Best-effort secret/PII redaction
│   ├── validation.py              Request, plan, and routing validation
│   ├── skills_loader.py           SKILL.md loader
│   ├── metrics.py                 Groundedness, citations, time reduction
│   ├── governance/
│   │   ├── rules.py               GR-01..GR-08
│   │   └── policy_checks.py       Deterministic draft checks
│   ├── agents/                    Planner, analyst, verifier, writer, reviewer
│   ├── graph/                     Root graph, orchestrator, teams, leads
│   ├── services/                  LLM, workflow, export
│   └── ui/                        Five pages, tokenized components, responsive hierarchy
├── skills/                        6 SKILL.md packages
├── sample_data/                   Clean, injection, corrupt, encrypted fixtures
├── tests/                         76 tests
├── docs/                          Design, governance, risk, NIST, testing, report
└── slides/                        Self-contained HTML deck
```

---

## Appendix C — Evidence index

| Claim | Evidence |
|---|---|
| 76 tests passed | `docs/testing.md` §6; `tests/` |
| Approval enforcement | `docs/human_approval.md`; TC-01–TC-05, TC-10; UI approval and rejection tests |
| Selective routing | TC-13; `docs/workflow.md` §4 |
| Governance rules | `docs/governance_rules.md`; `test_governance.py` |
| Risks | `docs/risk_assessment.md` |
| NIST functions | `docs/nist_ai_rmf_worksheet.md` |
| Requirements | `docs/requirements_traceability.md` |
| Real-mode gap | README §7; `docs/testing.md` §7.2; this report §7.2 |
| UI behavior | `tests/test_ui_smoke.py`; server health check |
| UI design system | `.opencode/skills/aegisflow-ui/`; `check_theme.py` 16/16; `check_contrast.py` 40/40; `check_responsive.py` PASS at 360/768/1280/1536 |
| Presentation | `docs/presentation_script.md`; `docs/slides.md`; `slides/aegisflow_deck.html` |

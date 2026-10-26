# SIP10 Requirements Traceability

**Project:** AegisFlow v0.1.0  
**Course:** SIP10 Final Project — “Building a Simple Governed Agentic AI System”  
**Date:** 26 October 2026  
**Purpose:** map each requirement from the three assignment images to a concrete implementation, document, and verification artefact.

> **Verification key**
>
> - **Verified** — exercised by an automated test, a recorded manual run, or direct inspection of a working UI.
> - **Documented** — a complete written artefact exists; no runtime claim is implied.
> - **Implemented, unverified** — code exists but the stated environment (for example, a live provider) was not executed.
> - **Not implemented** — explicitly out of scope.

---

## 1. Summary scorecard

| Assignment area | Required minimum | AegisFlow | Status |
|---|---:|---:|---|
| Working agentic prototype | 1 | Streamlit + LangGraph application | **Verified in mock mode** |
| AI agents/roles | 3 | 6 | **Exceeds** |
| `SKILL.md` packages | 3 | 6 | **Exceeds** |
| Governance rules | 5 | 8 | **Exceeds** |
| Identified risks | 5 | 9 | **Exceeds** |
| Test cases | 5 | 13 E2E + 51 unit/integration + 3 UI = **67** | **Exceeds** |
| NIST AI RMF worksheet | 4 functions | GOVERN, MAP, MEASURE, MANAGE | **Complete** |
| Human approval explanation | where + why | Design doc + enforced gate + UI | **Verified** |
| Presentation | ≤ 15 minutes | Script + 16-slide deck | **Complete** |

The implementation deliberately exceeds the minimum counts while keeping every extra control traceable to a requirement, risk, or test.

---

## 2. Image 1 — concepts and minimum components

| ID | Requirement from Image 1 | Implementation | Evidence | Status |
|---|---|---|---|---|
| IMG1-01 | Build an agentic system that performs a specific task or solves a problem | Document-to-deliverable workflow: upload PDF/TXT/DOCX, plan, analyze, draft, assure, approve, export | `app.py`, `aegisflow/`, TC-01 | **Verified** |
| IMG1-02 | Demonstrate PLAN → ORCHESTRATE → EXECUTE → CHECK → HUMAN APPROVAL → OUTPUT | Root graph phases and state machine | `docs/workflow.md` §1–2; TC-01; Workflow hierarchy and routing log | **Verified** |
| IMG1-03 | Apply NIST AI RMF GOVERN/MAP/MEASURE/MANAGE | Four-function worksheet with evidence, owners, statuses, open actions | `docs/nist_ai_rmf_worksheet.md` | **Documented** |
| IMG1-04 | Agents and skills must work together | Six validated `SKILL.md` packages loaded into prompts; skill recorded per execution | `skills/`, `aegisflow/skills_loader.py`, `test_skills_loader.py` | **Verified** |
| IMG1-05 | Orchestrator controls which agent or skill runs next | Deterministic root Orchestrator with whitelist, plan inspection, logged reasons | `aegisflow/graph/orchestrator.py`; TC-13 | **Verified** |
| IMG1-06 | At least 3 agents/roles | Planner, Document Analyst, Evidence Verifier, Report Writer, Independent Reviewer, Policy Checker | `aegisflow/agents/`; `docs/architecture.md` §5.1 | **Exceeds** |
| IMG1-07 | At least 5 governance rules | GR-01 to GR-08 | `aegisflow/governance/rules.py`; `docs/governance_rules.md`; `test_governance.py` | **Exceeds** |
| IMG1-08 | Follow the basic workflow | Literal mapping in §4 below | `docs/workflow.md`; TC-01 | **Verified** |
| IMG1-09 | Cover the example governance concerns | GR-04 (privacy), GR-02 (false information), verifier/policy/reviewer (check output), GR-01 (approval), GR-06 (records) | `docs/governance_rules.md` §1 and §2 | **Verified** |
| IMG1-10 | 15-minute presentation | Timed 16-slide script and self-contained deck | `docs/presentation_script.md`, `docs/slides.md`, `slides/aegisflow_deck.html` | **Complete** |

### 2.1 Governance example mapping

| Image 1 example concern | AegisFlow rule | Concrete control | Test evidence |
|---|---|---|---|
| Protect personal information | **GR-04** | Redact logs/audit/feedback; external-LLM authorization gate; PII warning | TC-12 |
| Do not intentionally create false information | **GR-02** | Source reference or `UNVERIFIED`; deterministic section/citation checks | TC-01, TC-06, TC-08, TC-11 |
| Check important AI-generated information | Verifier + Policy Checker + Reviewer | Independent verification, deterministic checks, separate review | TC-01, TC-11 |
| Require human approval for high-risk actions | **GR-01** | `interrupt()` gate, hash-bound persisted approval, finalize/export re-check | TC-01–TC-04, TC-10, UI test |
| Keep a record of important AI activities | **GR-06** | Nine-table SQLite audit and execution trail | TC-12 |

---

## 3. Image 2 — twelve required deliverables

| # | Deliverable | Required minimum | AegisFlow artefact | Verification | Status |
|---:|---|---|---|---|---|
| 1 | Working agentic AI prototype | Runs end to end | `app.py`, `aegisflow/`, `requirements.txt` | Manual smoke; 67 tests; server health `ok` | **Verified in mock mode** |
| 2 | Project description | Clear problem/scope | `README.md`; `docs/final_report.md` | Document review | **Complete** |
| 3 | AI agents/roles | 3 | `aegisflow/agents/`: Planner, Analyst, Verifier, Writer, Reviewer; deterministic Policy Checker | TC-01, TC-13; architecture table | **6 implemented** |
| 4 | `SKILL.md` files | 3 | `skills/task-planning`, `document-extraction`, `evidence-verification`, `report-writing`, `quality-review`, `untrusted-content-handling` | `test_skills_loader.py` (5 tests) | **6 implemented and verified** |
| 5 | Orchestration workflow | Diagram + explanation | `docs/workflow.md`; `aegisflow/graph/` | TC-01, TC-05, TC-11, TC-13 | **Complete and verified** |
| 6 | System diagram | At least one | Mermaid context, container, and graph diagrams in `docs/architecture.md`; workflow sequence in `docs/workflow.md` | Document review | **Complete** |
| 7 | NIST AI RMF worksheet | All four functions | `docs/nist_ai_rmf_worksheet.md` | Document review; statuses separate verified/unverified | **Complete** |
| 8 | Risk assessment | 5 risks | `docs/risk_assessment.md` — R-01 to R-09 with L×I scores, controls, residual risk, owner | Document review; tests mapped per risk | **9 risks** |
| 9 | Testing | 5 cases | `docs/testing.md`; 13 E2E (TC-01–TC-13), 51 unit/integration, 3 UI = **67** | Recorded `67 passed` | **Exceeds** |
| 10 | AI governance rules | 5 | `docs/governance_rules.md`; `aegisflow/governance/rules.py` — GR-01 to GR-08 | `test_governance.py`; E2E rule assertions | **8 rules** |
| 11 | Human approval — where and why | Explanation + implementation | `docs/human_approval.md`; `aegisflow/approvals.py`; `aegisflow/ui/review_page.py` | TC-01–TC-05, TC-10; AppTest UI flow | **Verified** |
| 12 | Final presentation | ≤ 15 minutes | `docs/presentation_script.md`; `docs/slides.md`; `slides/aegisflow_deck.html` | Timing plan 15:00; deck opens locally | **Complete** |

Additional project-scoped deliverable: `.opencode/skills/aegisflow-ui/` contains the UI design system (`SKILL.md`, six references, three verification scripts, theme template, base CSS) and `design_preview.py`. Theme checks pass 16/16, contrast checks pass 40/40, and the Playwright (Chromium) check loads the live mock-mode app at 360/768/1280/1536, finds no horizontal overflow, and writes screenshots to `ui_checks/`. Playwright is installed in the local `.venv` for verification only and is not listed in `requirements.txt`.

---

## 4. Image 3 — basic workflow, step by step

```text
USER
  ↓
PLANNER
  ↓
ORCHESTRATOR
  ↓
SKILL / AGENT   SKILL / AGENT   SKILL / AGENT
  ↓
REVIEWER
  ↓
HUMAN APPROVAL
  ↓
FINAL OUTPUT
```

| Image step | AegisFlow component | File | Evidence |
|---|---|---|---|
| **USER** | Streamlit New Task form: request, format, manual estimate, uploads, acknowledgement | `aegisflow/ui/task_creation.py` | UI test; manual smoke |
| **PLANNER** | Planner Agent, always first; validated plan with task type, subtasks, skills, dependencies, missing information | `aegisflow/agents/planner.py` | TC-01, TC-08, TC-13; plan unit tests |
| **ORCHESTRATOR** | Root deterministic router: whitelist, reasons, retries, revision loops, escalation | `aegisflow/graph/orchestrator.py` | TC-05, TC-11, TC-13 |
| **SKILL / AGENT 1** | Document Analyst + `document-extraction` | `aegisflow/agents/document_analyst.py` | TC-01, TC-06 |
| **SKILL / AGENT 2** | Evidence Verifier + `evidence-verification` | `aegisflow/agents/evidence_verifier.py` | TC-01, TC-11 |
| **SKILL / AGENT 3** | Report Writer + `report-writing` | `aegisflow/agents/report_writer.py` | TC-01, TC-11 |
| **REVIEWER** | Assurance Lead → deterministic Policy Checker → Independent Reviewer + `quality-review` | `aegisflow/graph/assurance_team.py`, `aegisflow/agents/reviewer.py` | TC-01, TC-11; UI test |
| **HUMAN APPROVAL** | `interrupt()` gate, hash-bound persisted decision, actor restriction, finalize re-check | `aegisflow/graph/root.py`, `aegisflow/approvals.py`, `aegisflow/ui/review_page.py` | TC-01–TC-05, TC-10; UI test |
| **FINAL OUTPUT** | `finalize` + approved Markdown/TXT export with metadata and re-verification | `aegisflow/graph/root.py`, `aegisflow/services/export_service.py` | TC-01, TC-04, TC-10 |

### 4.1 Literal workflow compliance note

The assignment shows three `SKILL/AGENT` boxes. AegisFlow maps them to **Document Analyst**, **Evidence Verifier**, and **Report Writer**. The **Policy Checker** is an additional deterministic control inside the **Reviewer** step, not a replacement for the Independent Reviewer. The team leads add hierarchy above the workers but do not remove or reorder any required step.

Selective routing means a **summary** task may use only the Analyst and then assurance. For a demonstration that shows all three executor boxes, submit a **report** or **meeting brief** request. This behavior is intentional and tested by TC-13; it is also documented in the README and user guide.

---

## 5. Acceptance criteria trace

The master prompt contains 15 acceptance criteria. Their status:

| # | Criterion | Status | Evidence |
|---:|---|---|---|
| 1 | App starts with documented commands | **Verified** | Streamlit server health `ok`; README quick start |
| 2 | User can submit a task and upload supported files | **Verified** | UI test; manual smoke; extraction tests |
| 3 | Planner always runs first and produces a validated plan | **Verified** | Graph topology; plan tests; TC-01 |
| 4 | Orchestrator selects only relevant agents, delegates through leads, logs reasons | **Verified** | TC-13; routing log assertions |
| 5 | Skills load from `SKILL.md` and are recorded per execution | **Verified** | `test_skills_loader.py`; agent execution rows |
| 6 | Distinct Reviewer checks output before human review | **Verified** | Assurance team; TC-01 |
| 7 | Missing information and failures handled without false success | **Verified** | TC-08, TC-09, TC-11 |
| 8 | User can approve, reject, and request revisions | **Verified** | E2E and AppTest UI flow |
| 9 | Approval enforced in backend, bound to version hash, re-checked at finalization | **Verified** | TC-01–TC-04, TC-10 |
| 10 | History, decisions, audit persist in SQLite | **Verified** | DB tests; TC-12 |
| 11 | Finalized output can be exported | **Verified** | TC-01 Markdown/TXT assertions |
| 12 | Mock mode works without credentials | **Verified** | Full suite runs without keys |
| 13 | Tests cover routing, hierarchy, workflow, governance, approval | **Verified** | 67 tests |
| 14 | All 12 SIP10 deliverables exist and are consistent | **Complete** | This document |
| 15 | No feature falsely described as implemented or tested | **Maintained** | Verification matrix below |

---

## 6. Verification matrix

### Implemented and verified

| Capability | Evidence |
|---|---|
| Mock-mode full graph to human review | TC-01, manual smoke |
| Hash-bound approval, finalize, export | TC-01–TC-04, TC-10, UI test |
| Rejection terminal; revision bounded | TC-04, TC-05 |
| Injection treated as data | TC-06 |
| SIMULATED labels in payload and exports | TC-07 |
| Missing/unreadable input blocks or reports safely | TC-08, TC-09 |
| Tamper detection after approval | TC-10 |
| Bounded assurance failure → escalation | TC-11 |
| Audit coverage and redaction | TC-12 |
| Selective routing and whitelist | TC-13 |
| Streamlit page rendering, approval, and rejection confirmation | `test_ui_smoke.py` |
| Tokenized UI theme and contrast | `aegisflow-ui` scripts: 16/16 and 40/40 PASS |
| Responsive width containment | Playwright (Chromium) at 360/768/1280/1536 — **PASS**, screenshots in `ui_checks/` |
| Six skills load and validate | `test_skills_loader.py` |
| Governance policy checks | `test_governance.py` |
| SQLite lifecycle, versions, cascade delete | `test_database.py` |
| Metrics math | `test_metrics.py` |

### Implemented but not verified

| Capability | Why not verified | What would verify it |
|---|---|---|
| Live OpenRouter provider | Real mode not enabled / no call made | Set real mode + authorization + one model; run TC-01, TC-06, TC-12; record latency and errors |
| Live Gemini provider | Same | Same with `AEGISFLOW_PROVIDER=gemini` |
| Live OpenAI provider | Same | Same with `AEGISFLOW_PROVIDER=openai` |
| Real-model output quality | Same | Labelled evaluation set; groundedness and citation review |
| Browser CSS/accessibility | `AppTest` is headless; Playwright checks overflow and captures screenshots only | axe accessibility audit + pixel-diff against the mockup |
| Multi-user concurrency | Single-user design | Load/concurrency test with auth |
| Disk-full/SQLite corruption recovery | Out of scope | Fault-injection and restore test |
| OCR for scanned PDFs | Not implemented | Add OCR pipeline and fixtures |

### Not implemented

- Multi-user authentication, roles, or remote deployment
- OCR for image-only PDFs
- PDF/DOCX export (Markdown/TXT are required and verified)
- External actions: email, shell, browser, calendar, finance
- Cryptographic signatures or an external approval service
- Automated backup/restore
- Fairness/bias evaluation

These are not failures hidden by the build; they are stated in the README, user guide, risk assessment, NIST worksheet, and final report.

---

## 7. Evidence index

| Evidence | Location |
|---|---|
| Recorded test result and matrix | `docs/testing.md` |
| Architecture and Mermaid diagrams | `docs/architecture.md` |
| Workflow and state machine | `docs/workflow.md` |
| Governance rules and rule-to-risk map | `docs/governance_rules.md` |
| Human approval design and threat model | `docs/human_approval.md` |
| NIST AI RMF worksheet | `docs/nist_ai_rmf_worksheet.md` |
| Risk register | `docs/risk_assessment.md` |
| User instructions | `docs/user_guide.md` |
| Presentation script and timing | `docs/presentation_script.md` |
| Slide source | `docs/slides.md` |
| HTML deck | `slides/aegisflow_deck.html` |
| Test code | `tests/` |
| Skill packages | `skills/*/SKILL.md` |
| Sample documents | `sample_data/` |

---

## 8. Traceability conclusion

AegisFlow meets all twelve deliverables and all visible Image 1/Image 3 requirements, with the required minimums exceeded. The central claims are backed by executed tests in mock mode. The real-provider path is implemented but **not executed**, and no presentation material or report describes it as verified.

The remaining gaps are engineering scope decisions for a single-user, local, academic prototype — not hidden assumptions.

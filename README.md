# AegisFlow

[![CI](https://github.com/JessAndreySundiang/AegisFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/JessAndreySundiang/AegisFlow/actions/workflows/ci.yml)

A governed, hierarchical multi-agent document-task prototype built with **LangGraph**, **LangChain**, **Streamlit**, and **SQLite**.

AegisFlow turns uploaded PDF/TXT/DOCX files into a reviewed deliverable through a visible chain of specialist agents. It is designed around one rule: **no output is finalized, exported as final, or marked complete without a human approval bound to the exact output version and content hash.**

> **Status: working prototype, mock mode verified.** All 92 automated tests pass. Real LLM mode is implemented but **not verified** because real mode was not enabled and no live provider call was made. See [Verification status](#verification-status).
>
> **Repository:** <https://github.com/JessAndreySundiang/AegisFlow>

---

## 1. What problem does it solve?

Document work is often delegated to a single model call: upload a file, get a summary, hope it is accurate. That pattern hides three risks:

1. **Fabrication** — the model can add facts that are not in the source.
2. **Untrusted input** — a document can contain instructions that try to change the model's behaviour.
3. **Unaccountable automation** — nobody can prove who approved what, or which exact text was approved.

AegisFlow addresses these with a hierarchical agent graph, deterministic governance checks, an explicit human approval gate, and a complete SQLite audit trail.

### Core capabilities

| Capability | Implementation |
|---|---|
| Hierarchical multi-agent workflow | Root orchestrator → rule-based team leads → LLM workers |
| Planner always first | Planner selects a minimal plan from a fixed executor whitelist |
| Selective routing | Summary tasks skip the verifier and writer; reports use all three executors |
| Untrusted-document handling | Delimited `<untrusted_document>` blocks + injection scanning |
| Grounded output | Every claim carries a source reference or an explicit `UNVERIFIED` label |
| Deterministic policy checks | Required sections, citations, secrets, PII, injection leftovers, external-action claims |
| Human-in-the-loop | LangGraph `interrupt()` + hash-bound approval + `Command(resume=...)` |
| Bounded autonomy | Retry, revision, delegation-depth, and recursion limits with escalation |
| Auditability | 9 SQLite tables, append-only audit log, per-agent execution records |
| Approved exports | Markdown and TXT with approval metadata, re-verified at export time |
| Safe mock mode | A real `BaseChatModel` subclass produces deterministic output with zero network calls |
| Responsive, tokenized UI | Project-scoped `aegisflow-ui` skill: light/dark tokens, 44px targets, icon+text statuses, responsive hierarchy |

### Explicit non-goals

- No CrewAI, FastAPI, Redis, Docker, queues, or external action tools.
- No web research, email, calendar, shell, or financial operations.
- No multi-user authentication in v1; this is a single-user local prototype.
- No OCR for scanned PDFs.
- No claim that mock output is real AI analysis.

---

## 2. Quick start (Windows, project `.venv`)

```powershell
cd C:\xampp\htdocs\AegisFlow

# 1. Activate or create the project environment
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Optional: copy the environment template (mock mode works without a key)
Copy-Item .env.example .env

# 3. Run the app
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open <http://localhost:8501>.

### Run the tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -q
```

Expected result at the time of writing: **92 passed**.

### Quality checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest --cov=aegisflow --cov-report=term-missing
```

Lint is clean, and the suite sits at **78% coverage** (statement + branch) with a CI gate of 75%. `.github/workflows/ci.yml` runs lint, tests with coverage, and the theme/contrast checks on Windows and Ubuntu for every push.

### Try it without uploading anything

Use the files in `sample_data/`:

- `project_notes.txt` — clean notes with an email address (demonstrates the PII warning).
- `injection_notes.txt` — contains an embedded prompt-injection attempt (demonstrates GR-03).
- `corrupted.pdf`, `encrypted.pdf`, `empty.txt` — demonstrate safe unreadable-file handling.
- `supplier_brief.docx`, `board_brief.pdf` — additional extraction samples.

Recommended first task: request *“Please prepare a meeting report from these notes”* and upload `project_notes.txt`. The workflow stops at the human approval gate. Review the version and hash, approve, then download the Markdown/TXT export from **History**.

---

## 3. Modes and configuration

AegisFlow defaults to **mock mode**. No key is required and no document text leaves the machine.

| Mode | Requirements | Network |
|---|---|---|
| `mock` (default) | none | none |
| `real` | `AEGISFLOW_MODE=real`, `AEGISFLOW_ALLOW_EXTERNAL_LLM=true`, provider key, and `AEGISFLOW_MODEL` | sends extracted text to the provider |

Real mode fails safe: if authorization, key, or model is missing, startup falls back to mock and records a warning.

```dotenv
AEGISFLOW_MODE=mock
AEGISFLOW_PROVIDER=openrouter

# Real mode only (all four conditions are required)
AEGISFLOW_MODE=real
AEGISFLOW_ALLOW_EXTERNAL_LLM=true
AEGISFLOW_MODEL=your-model-id
OPENROUTER_API_KEY=...

# Optional Gemini / OpenAI
GOOGLE_API_KEY=...
OPENAI_API_KEY=...
```

`Settings.describe()` and the UI sidebar never print secret values.

---

## 4. How a task runs

```text
validate_request
      │
   planner                 ← always first; fixed executor whitelist
      │
 orchestrator              ← deterministic routing + audit
      ├── analysis_team    ← Document Analyst → Evidence Verifier
      ├── drafting_team    ← Report Writer
      └── assurance_team   ← Policy Checker → Independent Reviewer
      │
 human_review              ← LangGraph interrupt(); approval is hash-bound
      ├── approve  → finalize → completed → export
      ├── reject   → rejected (terminal)
      └── revise   → bounded loop back to drafting or analysis
```

- **Summary requests** use only the Document Analyst, then go straight to assurance.
- **Report / meeting-brief requests** use the analyst, verifier, and writer.
- The orchestrator can route only to a fixed whitelist; every choice is logged with a reason.
- A failed or blocked task escalates instead of looping.

See [docs/workflow.md](docs/workflow.md) for the full state machine.

---

## 5. Governance at a glance

| Rule | Control | Verified by |
|---|---|---|
| GR-01 | Human approval precedes finalization; approval is hash-bound | TC-01, TC-02, TC-03, TC-04, TC-10 |
| GR-02 | No fabrication; source reference or `UNVERIFIED` label | TC-01, TC-06, TC-08, TC-11 |
| GR-03 | Uploaded content is untrusted data | TC-06 |
| GR-04 | Redact secrets/PII from logs; gate external LLM use | TC-12 |
| GR-05 | Least privilege; no external-action tools | TC-13 + architecture review |
| GR-06 | Auditable routing, agent, and human activity | TC-12 |
| GR-07 | Bounded autonomy with retries, revisions, escalation | TC-05, TC-11 |
| GR-08 | Simulated output is labeled everywhere | TC-07 |

Full rule definitions and enforcement points: [docs/governance_rules.md](docs/governance_rules.md).

---

## 6. Project layout

```text
AegisFlow/
├── app.py                     # Streamlit entry point
├── config.py                  # Settings, env validation, mock fallback
├── requirements.txt
├── .env.example
├── .opencode/skills/aegisflow-ui/ # UI design system, refs, checks, preview
├── aegisflow/
│   ├── models.py              # Pydantic models, enums, task transitions
│   ├── state.py               # AegisState / TeamState and reducers
│   ├── database.py            # 9-table SQLite schema and persistence
│   ├── approvals.py           # Hash-bound approval state machine
│   ├── document_processing.py # PDF/TXT/DOCX extraction, injection scan
│   ├── redaction.py           # Secret/PII redaction
│   ├── validation.py          # Request/plan/routing validation
│   ├── skills_loader.py       # SKILL.md loader
│   ├── metrics.py             # Groundedness, citation, time-reduction metrics
│   ├── governance/
│   │   ├── rules.py           # GR-01..GR-08 definitions
│   │   └── policy_checks.py   # Deterministic draft checks
│   ├── agents/                # Planner, analyst, verifier, writer, reviewer
│   ├── graph/                 # Root graph, orchestrator, teams, leads
│   ├── services/              # LLM, workflow, export services
│   └── ui/                    # Streamlit pages and shared components
├── skills/                    # 6 SKILL.md instruction packages
├── sample_data/               # Clean, injection, corrupt, encrypted fixtures
├── tests/                     # 92 unit, integration, E2E, UI tests
├── docs/                      # Design, governance, risk, testing, NIST, report
└── slides/                    # Self-contained HTML presentation
```

---

## 7. Verification status

| Area | Status | Evidence |
|---|---|---|
| Mock-mode full pipeline | **Implemented and verified** | TC-01 to TC-13; 92 passing tests |
| Engineering baseline | **Implemented** | `ruff check` clean; 78% coverage with a 75% gate; CI matrix (Windows + Ubuntu) runs lint, tests, theme and contrast |
| Human approval / hash binding | **Implemented and verified** | E2E + approval unit tests; UI approval and rejection flows |
| Approval race and DB backstop | **Implemented and verified** | Checks and write in one transaction; unique `(version_id, decision)` index; concurrent-approval test |
| Upload extraction guards | **Implemented and verified** | 10 MB cap, 200-page PDF cap, DOCX entry/size/ratio limits, signature checks |
| Injection handling | **Implemented and verified** | TC-06 |
| Audit and redaction | **Implemented and verified** | TC-12 |
| Streamlit UI | **Implemented and verified headlessly** | `AppTest` approval and rejection flows; server health `ok`; Playwright responsive check PASS at 360/768/1280/1536 |
| UI design system | **Implemented and verified** | `aegisflow-ui` skill; theme 16/16 PASS; contrast 40/40 PASS; responsive check PASS with screenshots |
| Accessibility | **Verified** | axe-core 0 WCAG 2.1 A/AA violations on five pages in light and dark; skip link, live focus, reduced-motion, 44 px targets |
| Summary voice | **Implemented and verified** | Substance-first summaries, page-aware source line, attention block only when warranted, banned meta-phrases tested |
| Real OpenRouter / Gemini / OpenAI | **Implemented, not executed** | Real mode was not enabled; no live call recorded; see limitation below |
| OCR for scanned PDFs | **Not implemented** | Documented limitation |
| Multi-user auth / remote deployment | **Not implemented** | Single-user local prototype |

> **Real-mode caveat:** the provider adapters (`ChatOpenAI` with an OpenRouter base URL, direct OpenAI, and `ChatGoogleGenerativeAI`) are constructed from verified installed packages, and the JSON parse/retry path is shared with mock mode. However, no live provider call was made. Do not present real-mode behaviour as verified until a key is configured and a live run is recorded.

Other known limitations:

- A local user who can edit SQLite can bypass application controls. Hash binding detects stale content at finalize/export time but is not a cryptographic signature.
- PII is redacted from logs, not from the source-derived draft shown to the reviewer.
- Regex-based secret/PII detection can miss unusual identifiers.
- The UI is a single-user local app with no login.
- Playwright and Chromium are development-only tools (`requirements-dev.txt`). The page sweep passes at 360/768/1280/1536 px, and axe-core reports **0 WCAG 2.1 A/AA violations** on all five pages in light and dark mode (screenshots in `ui_checks/`, CI artifact `ui-evidence`). No pixel-diff against the mockup PDF was run.

---

## 8. Deliverables

| # | Deliverable | File |
|---|---|---|
| 1 | Working prototype | `app.py`, `aegisflow/` |
| 2 | Project overview | `README.md` |
| 3 | Architecture | [docs/architecture.md](docs/architecture.md) |
| 4 | Workflow and state machine | [docs/workflow.md](docs/workflow.md) |
| 5 | Governance rules | [docs/governance_rules.md](docs/governance_rules.md) |
| 6 | Human approval design | [docs/human_approval.md](docs/human_approval.md) |
| 7 | NIST AI RMF worksheet | [docs/nist_ai_rmf_worksheet.md](docs/nist_ai_rmf_worksheet.md) |
| 8 | Risk assessment | [docs/risk_assessment.md](docs/risk_assessment.md) |
| 9 | Test plan and results | [docs/testing.md](docs/testing.md) |
| 10 | User guide | [docs/user_guide.md](docs/user_guide.md) |
| 11 | Presentation script | [docs/presentation_script.md](docs/presentation_script.md) |
| 12 | Slide deck | [slides/aegisflow_deck.html](slides/aegisflow_deck.html) + [docs/slides.md](docs/slides.md) |
| 13 | Final report | [docs/final_report.md](docs/final_report.md) |
| 14 | Requirements traceability | [docs/requirements_traceability.md](docs/requirements_traceability.md) |
| 15 | UI design system skill | [.opencode/skills/aegisflow-ui/](.opencode/skills/aegisflow-ui/) + [design_preview.py](.opencode/skills/aegisflow-ui/design_preview.py) |
| 16 | UI design guide | [docs/ui_design.md](docs/ui_design.md) |

---

## 9. Resume and export guarantees

1. The UI writes the human decision to SQLite **before** resuming the graph.
2. The graph independently re-checks that a persisted decision exists for the exact version.
3. `finalize` re-verifies the approval record and the stored content hash.
4. Export re-runs the same verification, so a tampered or stale version cannot be downloaded as approved.
5. Any new output version invalidates the previous approval.

Details and failure messages: [docs/human_approval.md](docs/human_approval.md).

---

## 10. License and academic use

This is an academic SIP10 final-project prototype. It is not production software. Do not use it to process regulated, confidential, or sensitive personal data without an independent security review.

Released under the [MIT License](LICENSE). Security reports: see [SECURITY.md](SECURITY.md).

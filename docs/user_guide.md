# AegisFlow User Guide

**Version:** 0.1.0  
**Audience:** the single local user who submits a document task and acts as the human reviewer  
**Platform used for verification:** Windows, Python 3.13.7, project `.venv`  
**Status:** mock mode is implemented and verified; real-provider mode is implemented but not verified.

---

## 1. What this guide covers

This guide explains how to install, configure, run, and use AegisFlow. It also explains what to do when a task blocks or escalates, where data is stored, and which limitations are intentional.

AegisFlow is an academic prototype. It is **not** production software and is not approved for regulated, confidential, or sensitive personal data.

---

## 2. Before you start

### 2.1 Required

- Windows 10/11, macOS, or Linux
- Python **3.11 or newer** (the verified build used Python 3.13.7)
- About 500 MB of free disk space for the virtual environment and local data
- A modern browser for the Streamlit UI

### 2.2 Optional, only for real-provider mode

- An OpenRouter, Google Gemini, or OpenAI API key
- The exact model id supported by that provider
- Explicit authorization to send extracted document text to that provider

Mock mode needs **no key and no network access**.

---

## 3. Installation

### 3.1 Open a terminal in the project folder

```powershell
cd C:\xampp\htdocs\AegisFlow
```

### 3.2 Use the existing project environment

The project already contains `.venv`. Install or refresh the pinned dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3.3 Create the environment from scratch (optional)

Use this only if `.venv` is missing or broken:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3.4 Verify the key imports

```powershell
.\.venv\Scripts\python.exe -c "import streamlit, fitz, docx, langgraph; print('imports ok')"
```

Expected output:

```text
imports ok
```

> PyMuPDF may print a deprecation warning if you import `fitz`. AegisFlow uses the supported `pymupdf` API; the warning does not affect operation.

---

## 4. Configuration

### 4.1 Mock mode (default and recommended for the demo)

Mock mode is deterministic, runs locally, and makes **zero** network calls. Do nothing, or create a `.env` file with:

```dotenv
AEGISFLOW_MODE=mock
```

### 4.2 Create `.env` from the template

```powershell
Copy-Item .env.example .env
```

`.env` is ignored by `.gitignore`. Never put real keys in `.env.example`, and never commit `.env`.

### 4.3 Real-provider mode

Real mode requires **all four** conditions:

1. `AEGISFLOW_MODE=real`
2. `AEGISFLOW_ALLOW_EXTERNAL_LLM=true`
3. a key for the selected provider
4. a non-empty `AEGISFLOW_MODEL` holding at least one model id

```dotenv
AEGISFLOW_MODE=real
AEGISFLOW_PROVIDER=gemini
AEGISFLOW_ALLOW_EXTERNAL_LLM=true
AEGISFLOW_MODEL=gemini:gemini-3.5-flash,openrouter:openai/gpt-4o

GOOGLE_API_KEY=your-key-here
# or
OPENROUTER_API_KEY=your-key-here
# or
OPENAI_API_KEY=your-key-here
```

`AEGISFLOW_MODEL` is a comma separated list in failover order: the first entry is the primary, and the next one is tried when a model is missing, rate limited, or otherwise fails. Gemini is the default provider, so a bare model id is sent to it. Write `provider:model` to name a provider per entry.

A slash only counts as a provider prefix when it names the configured provider. Writing `openai/gpt-4o` while the provider is `gemini` is rejected at startup with both readings spelled out, because the same string also reads as an OpenRouter model id; real mode falls back to mock rather than guessing.

Provider values: `openrouter`, `gemini`, or `openai`.

If any condition is missing, `config.py` falls back to mock mode, records a startup warning, and displays the fallback reason in the UI. It never silently sends documents externally.

> **Real mode has not been executed in this build.** The adapters import correctly, but no live call was made because real mode was not enabled. See section 12.

### 4.4 Optional limits

| Variable | Default | Meaning |
|---|---:|---|
| `AEGISFLOW_MAX_FILE_MB` | `10` | Maximum size per uploaded file |
| `AEGISFLOW_MAX_RETRIES` | `2` | Retries after the first agent attempt |
| `AEGISFLOW_MAX_REVISIONS` | `2` | Human/assurance revision budget |
| `AEGISFLOW_MAX_DELEGATION_DEPTH` | `3` | Maximum hierarchy depth |
| `AEGISFLOW_RECURSION_LIMIT` | `80` | LangGraph recursion guard |
| `AEGISFLOW_DATA_DIR` | `data` | Storage directory, relative to the project root |

Invalid values fail fast at startup with a clear error.

---

## 5. Run the application

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Streamlit prints a local URL, normally:

```text
http://localhost:8501
```

Open it in a browser.

To use a different port:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8600
```

To stop the server, press `Ctrl+C` in the terminal.

### 5.1 Run the tests before a demo

```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -q
```

The last recorded result is **92 passed**. Test duration varies by machine.

---

## 6. Interface tour

AegisFlow has five pages, available from the dark left sidebar.

| Page | Purpose |
|---|---|
| **Dashboard** | Metric cards, recent tasks, workload, and a decision card for the current approval gate |
| **New task** | Upload documents, describe the deliverable, and see “What happens next” before starting |
| **Workflow** | Follow the four-level agent hierarchy and routing log; plan, subtasks, executions, and audit are under **Task details and audit** |
| **Review** | Read the draft and agent checks on the left; review evidence and record a decision on the right; the hash is under **Version fingerprint and technical checks** |
| **History** | Filter tasks by status, download approved Markdown/TXT, save a time estimate, or delete failed work under **Task details and audit** |

The main banner shows the active mode. In mock mode an amber banner reads **SIMULATED OUTPUT** and states that the data is not real AI analysis; in real mode it names the provider. The sidebar holds navigation and the mock/real mode indicator, without duplicating runtime settings.

---

## 7. Guided first run

This walkthrough produces a reviewed meeting brief from the supplied sample file. It takes about two minutes.

### Step 1 — Start a task

1. Open **New Task**.
2. Keep the request: `Please prepare a meeting brief from the uploaded notes.`
3. Choose output format `markdown`.
4. Set your manual estimate, for example `45` minutes. This is used only for the time-reduction metric.
5. Upload `sample_data/project_notes.txt`.
6. Tick the simulated-output acknowledgement.
7. Click **Run AegisFlow**.

### Step 2 — Watch the governed workflow

The graph validates the request, runs the Planner, routes the analysis, drafting, and assurance teams, and then stops at the human gate. The UI moves to **Review**.

A completed report task normally executes:

- Document Analyst
- Evidence Verifier
- Report Writer
- deterministic Policy Checker
- Independent Reviewer

### Step 3 — Review the exact output

On **Review**, check:

- **Version** and **Simulated = YES**
- the draft text in the read-only pane
- claim statuses and evidence excerpts under **Evidence**
- policy findings and reviewer reasons under **Reviewer and policy checks**
- previous human decisions, if any

The draft is read-only. Open **Version fingerprint and technical checks** to see the content hash. The hash is the binding value: if the content changes, the approval no longer applies.

### Step 4 — Record a decision

In the **Your decision** panel on the right:
1. Verify the reviewer name (defaults to "Local Reviewer", expandable under **Reviewer details**).
2. Select **Approve version {N}** (or **Reject version {N} (terminal)** / **Request a bounded revision of version {N}**).
3. Tick the acknowledgement checkbox: **I reviewed version {N} and the content hash shown above.**
4. If rejecting, tick the explicit terminal confirmation checkbox.
5. If requesting a revision, supply non-empty feedback and select the revision target (`drafting` or `analysis`).
6. Click the version-named confirmation button (e.g. **Approve version 1**).

The UI writes the decision to SQLite **before** resuming the graph. The graph then re-verifies the approval and hash and transitions the task to `completed`.

### Step 5 — Export

Open **History** and use the status filter if needed. Approved tasks show **Export .md** or **Export .txt** in the row. The download re-checks the approval record. The export includes the version, content hash, reviewer, approval timestamp, and simulated status.

### Step 6 — Record a workload metric (optional)

In **History**, open **Task details and audit**, choose the task, and save the approval outcome and your own 1–5 quality rating. The time-reduction figure compares the measured elapsed time with your manual estimate. It is a scheduling metric, **not** a quality score.

---

## 8. Task types and selective routing

The Planner chooses a minimal plan from a fixed whitelist. The orchestrator then runs only the teams that plan requires.

| Request pattern | Typical route |
|---|---|
| “summary”, “summarize” | Document Analyst → assurance → human review. Verifier and writer are skipped. |
| “outline” | Document Analyst → Report Writer → assurance → human review |
| “brief”, “meeting”, “report”, action items, or the default | Document Analyst → Evidence Verifier → Report Writer → assurance → human review |
| No readable document | Blocked with missing-information reasons; no content is invented |

For a course demonstration that must show all three executor roles, use a **report** or **meeting brief** request rather than a one-line summary.

---

## 9. Decisions, revisions, and failure states

### 9.1 Decisions

| Decision | What happens | Can the output be exported? |
|---|---|---|
| **Approve version {N}** | Approval is recorded, hash re-checked, task becomes `completed` | Yes |
| **Reject version {N} (terminal)** | Task becomes `rejected` (requires explicit confirmation) | No |
| **Request a bounded revision of version {N}** | The selected target is re-run, a new version is created, and the graph returns to review | Only after the new version is approved |

A revision requires feedback. The budget defaults to two revisions. When it is exhausted, the UI refuses another revision and the graph escalates.

### 9.2 Revision target

- **drafting** — rewrite the deliverable from existing verified claims.
- **analysis** — re-extract and re-verify claims, then rewrite.

Every revision creates a new output version and invalidates the previous approval.

### 9.3 Terminal and stopped states

| Status | Meaning | Next action |
|---|---|---|
| `completed` | Approved and finalized | Export from History |
| `rejected` | Human rejected the output | Start a new task |
| `blocked` | Missing input or an unusable plan | Read the reason and audit trail; add a readable document |
| `failed` | Retry, revision, or worker limit reached | Inspect **Task details and audit**; start a new task or investigate |
| `awaiting_human_review` | Waiting for a decision | Use Review |

No failure path silently marks a task complete.

Deletion is intentionally limited. **Rejected, blocked, and failed** tasks can be deleted from **History** after an explicit confirmation dialog. **Approved and completed** tasks have no delete action in the UI: their version, hash, decision, and audit records remain available as evidence. Remove the local database only as a deliberate reset (section 10).

---

## 10. Data, privacy, and reset

### 10.1 Where data lives

| Path | Contents |
|---|---|
| `data/aegisflow.sqlite` | Tasks, files, versions, reviews, evidence, audit, metrics |
| `data/checkpoints.sqlite` | LangGraph checkpoints, keyed by task id |
| `data/uploads/<task-id>/` | Stored copies of uploaded files |

Mock mode never sends document content off the machine.

### 10.2 Delete one task

Use **History → Delete task**. Deletion removes the task rows, uploaded files, and the checkpoint thread. Confirm the checkbox first.

### 10.3 Reset all data

Stop the Streamlit server first, then remove the two database files and the uploads folder:

```powershell
Remove-Item data\aegisflow.sqlite, data\checkpoints.sqlite -ErrorAction SilentlyContinue
Remove-Item data\uploads -Recurse -Force -ErrorAction SilentlyContinue
```

The app recreates the schema on the next start.

### 10.4 Privacy behavior

- Audit details, agent execution references, file messages, escalation reasons, and review feedback are passed through best-effort redaction.
- The review pane intentionally shows source-derived text so the reviewer can judge it. That text may contain personal data.
- The review pane and exports carry a warning/label, but the system cannot control downstream sharing.
- Regex redaction can miss unusual identifiers.

Do not process regulated or confidential data with this prototype.

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `streamlit` is not recognized | Wrong Python environment | Use `.\.venv\Scripts\python.exe -m streamlit run app.py` |
| Import error for `pymupdf`, `docx`, or `langgraph` | Dependencies not installed in `.venv` | Re-run the pip install command |
| UI shows **SIMULATED OUTPUT** after setting real mode | One of the four real-mode conditions is missing | Check the fallback banner and the model/key configuration in `.env`; the sidebar only reports the active mode |
| Real mode fails on first call | Wrong model id, invalid key, rate limit, or provider outage | Confirm the exact model id and key; check the audit/agent error; return to mock for the demo |
| “The request must contain at least 8 characters” | Request too short | Write a complete deliverable request |
| Task is blocked with no readable content | Encrypted, corrupted, empty, or scanned PDF | Supply a text-based PDF, TXT, or DOCX |
| A PDF has no text | Likely a scanned image; OCR is not implemented | Use a text-based source |
| “This version is stale” | A newer version exists | Refresh and review the current version |
| “Output content hash mismatch” | Stored content changed | Do not export; investigate the database/audit trail |
| Export blocked | No valid current approval | Approve the current version first |
| “Maximum revision cycles reached” | Revision budget exhausted | Approve or reject |
| Database is locked | Another process or a stale Streamlit instance | Stop all app instances; retry; back up `data/` before deleting lock/WAL files |
| `AppTest` or UI test fails after changing environment variables | Cached Streamlit resources | Clear the cache in the test or restart the test process |
| Browser page is stale after a decision | Streamlit rerun timing | Refresh the page; the database record is authoritative |

### 11.1 Health check

```powershell
Invoke-WebRequest http://localhost:8501/_stcore/health
```

Expected body: `ok`.

---

## 12. Known limitations

1. **Real-provider mode is not verified.** No live OpenRouter, Gemini, or OpenAI call was made in this build.
2. **No OCR.** Scanned PDFs without a text layer are unusable.
3. **Single user, no authentication.** Reviewer identity is self-asserted.
4. **Local SQLite is trusted.** A local administrator can edit the database and checkpoints. Hash binding is an integrity check, not a signature.
5. **Regex detection is best-effort.** Prompt-injection and PII scanners can miss novel patterns.
6. **The review pane is not redacted.** It must show source-derived content for a meaningful review; handle it accordingly.
7. **No external actions.** AegisFlow never sends email, runs shell commands, browses the web, or moves money.
8. **No fairness or bias evaluation.** The system is not intended for decisions about people.
9. **Visual fidelity is not pixel-diffed.** The UI is covered by a Playwright page sweep (five pages at 360/768/1280/1536) and an axe-core WCAG 2.1 A/AA audit that reports 0 violations in light and dark mode, but no pixel comparison against the mockup PDF is run.

Detailed controls and residual risks: [governance_rules.md](governance_rules.md), [risk_assessment.md](risk_assessment.md), [testing.md](testing.md).

---

## 13. Command reference

```powershell
# Install
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Run
.\.venv\Scripts\python.exe -m streamlit run app.py

# Test
.\.venv\Scripts\python.exe -m pytest tests\ -q

# Collect test names
.\.venv\Scripts\python.exe -m pytest tests\ --collect-only -q

# Check the server
Invoke-WebRequest http://localhost:8501/_stcore/health

# Reset local data (stop the app first)
Remove-Item data\aegisflow.sqlite, data\checkpoints.sqlite -ErrorAction SilentlyContinue
Remove-Item data\uploads -Recurse -Force -ErrorAction SilentlyContinue
```

---

## 14. Getting help

Start with the audit trail on the **Workflow** page. It records routing decisions, agent failures, policy findings, approvals, and escalations with rule IDs. For design rationale, read:

- [README.md](../README.md)
- [architecture.md](architecture.md)
- [workflow.md](workflow.md)
- [human_approval.md](human_approval.md)
- [testing.md](testing.md)

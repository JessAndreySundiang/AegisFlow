# Test Plan and Results

**System:** AegisFlow v0.1.0
**Date:** 26 October 2026
**Environment:** Windows, Python 3.13.7, project `.venv`, pytest 9.1.1
**Result:** **67 passed, 0 failed** (`pytest tests\ -q`)

---

## 1. Objective

Verify that AegisFlow:

1. runs the full LangGraph workflow in mock mode without network access;
2. never finalizes or exports without a valid, hash-bound human approval;
3. treats uploaded content as untrusted data;
4. preserves a complete, redacted audit trail;
5. enforces bounded retries, revisions, and escalation;
6. routes selectively rather than calling every agent;
7. renders the five Streamlit pages and completes approval and rejection-confirmation flows through the UI test harness.

---

## 2. How to run

```powershell
# Full suite
.\.venv\Scripts\python.exe -m pytest tests\ -q

# Verbose
.\.venv\Scripts\python.exe -m pytest tests\ -v

# A single group
.\.venv\Scripts\python.exe -m pytest tests\test_e2e.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_ui_smoke.py -q

# List tests without running
.\.venv\Scripts\python.exe -m pytest tests\ --collect-only -q
```

Tests use `tmp_path`; they do not write to the project `data/` directory. The UI test redirects `AEGISFLOW_DATA_DIR` to a temporary directory and clears Streamlit's resource cache.

---

## 3. Test levels

| Level | Files | What is exercised |
|---|---|---|
| Unit | `test_models.py`, `test_database.py`, `test_approvals.py`, `test_document_processing.py`, `test_skills_loader.py`, `test_governance.py`, `test_metrics.py` | Schemas, transitions, hashing, persistence, extraction, skills, policy checks, metrics |
| Integration / E2E | `test_e2e.py` (TC-01 to TC-13) | Real compiled LangGraph, real SQLite, real approval state machine, mock LLM |
| UI | `test_ui_smoke.py` | Streamlit `AppTest`: all five pages, review form, approval, rejection confirmation, finalization |
| Manual smoke | recorded during build | Full pipeline to `awaiting_human_review`, approve/resume to `completed`, exports |
| Server smoke | recorded during build | `streamlit run app.py` → health endpoint returned `ok` |

The mock LLM is not a stub pipeline: it is a real LangChain `BaseChatModel` subclass, so the same invoke → parse → validate → retry path runs in tests.

---

## 4. Test-case matrix (TC-01 to TC-13)

| ID | Objective | Test | Rules / risks | Result |
|---|---|---|---|---|
| TC-01 | Full pipeline reaches human review; approve/finalize; Markdown and TXT exports contain approval metadata | `test_e2e.py::test_tc01_happy_path_approval_finalize_and_export` | GR-01, GR-02, GR-08 / R-01, R-04 | **PASS** |
| TC-02 | Agent cannot record approval; resuming approve without a persisted decision escalates | `test_e2e.py::test_tc02_agent_cannot_approve_and_unpersisted_resume_escalates` | GR-01 / R-04 | **PASS** |
| TC-03 | A new output version invalidates the prior approval; resuming the old version escalates | `test_e2e.py::test_tc03_edit_invalidates_prior_approval` | GR-01 / R-04, R-08 | **PASS** |
| TC-04 | Rejection is terminal and blocks both exports | `test_e2e.py::test_tc04_reject_is_terminal_and_blocks_export` | GR-01 / R-04 | **PASS** |
| TC-05 | Human revision creates a new version, is bounded by `max_revisions`, and cannot be bypassed by an unpersisted resume | `test_e2e.py::test_tc05_revision_loop_is_bounded` | GR-07, GR-01 / R-05 | **PASS** |
| TC-06 | Prompt injection is inert; clean content is still extracted; no injection survives into the draft | `test_e2e.py::test_tc06_prompt_injection_is_treated_as_data` | GR-03, GR-02 / R-02 | **PASS** |
| TC-07 | SIMULATED labels appear in payload, version, Markdown, and TXT | `test_e2e.py::test_tc07_simulated_labels_flow_through_review_and_export` | GR-08 / R-01 | **PASS** |
| TC-08 | No readable input blocks the task without fabricating content | `test_e2e.py::test_tc08_no_readable_input_blocks_without_fabrication` | GR-02 / R-01, R-07 | **PASS** |
| TC-09 | Corrupted and encrypted files are reported; readable files still drive the run | `test_e2e.py::test_tc09_mixed_unreadable_files_are_reported` | GR-02 / R-07 | **PASS** |
| TC-10 | Content tampering after approval blocks finalization and export | `test_e2e.py::test_tc10_tamper_after_approval_blocks_finalization` | GR-01 / R-04, R-08 | **PASS** |
| TC-11 | Repeated assurance failure escalates at the revision limit instead of looping | `test_e2e.py::test_tc11_assurance_failure_escalates_at_limit` | GR-07 / R-05 | **PASS** |
| TC-12 | Audit trail covers routing/agents/policy/decisions; feedback PII and secrets are redacted | `test_e2e.py::test_tc12_audit_trail_and_redaction` | GR-04, GR-06 / R-03 | **PASS** |
| TC-13 | Summary requests use only the analyst; orchestrator destinations stay in the whitelist | `test_e2e.py::test_tc13_selective_routing_summary_uses_analyst_only` | GR-05, GR-06 / R-09 | **PASS** |

### UI test

| Objective | Test | Result |
|---|---|---|
| All five pages render; the review form refuses an unacknowledged submission; a real approval through Streamlit finalizes the task and records `actor=human:streamlit` | `test_ui_smoke.py::test_ui_renders_pages_and_approval_flow_finalizes` | **PASS** |
| Rejecting a version requires a separate terminal confirmation; without it the task stays awaiting review and no decision is stored | `test_ui_smoke.py::test_ui_rejection_requires_terminal_confirmation` | **PASS** |
| Requesting a revision requires non-empty feedback, creates a new version, and leaves the prior version unapproved | `test_ui_smoke.py::test_ui_revision_requires_feedback_and_creates_new_version` | **PASS** |

---

## 5. Unit test inventory

| File | Tests | Coverage focus |
|---|---:|---|
| `test_models.py` | 7 | Plan id/dependency validation, blocked-plan rule, claim text, stable hash, status values |
| `test_database.py` | 7 | Task lifecycle, invalid transitions, version numbering/hash, cascade delete, audit redaction, workload, counts |
| `test_approvals.py` | 8 | Approve/finalize, agent refusal, duplicate, stale version, hash mismatch, content tamper, reject terminal, revision feedback/limit |
| `test_document_processing.py` | 12 | Extensions, TXT/PDF/DOCX extraction, empty, corrupted, encrypted, unsupported, size limit, injection scan, delimiters, safe filenames, deletion |
| `test_skills_loader.py` | 5 | Six skills load, agent mapping, catalog/unknown, malformed frontmatter/body |
| `test_governance.py` | 9 | Eight unique rules, good draft, missing reference/section, injection, secret, external action, simulated warning, invented email |
| `test_metrics.py` | 3 | Groundedness, citation coverage, time reduction (including negative) |
| `test_e2e.py` | 13 | TC-01 to TC-13 |
| `test_ui_smoke.py` | 3 | Streamlit pages + approval flow + rejection confirmation + revision flow |
| **Total** | **67** | |

---

## 6. Recorded result

```text
$ .\.venv\Scripts\python.exe -m pytest tests\ -q
...................................................................                      [100%]
67 passed in 12.13s
```

A separate Streamlit server smoke test was run:

```text
$ .\.venv\Scripts\python.exe -m streamlit run app.py --server.headless true --server.port 8599
$ Invoke-WebRequest http://localhost:8599/_stcore/health
ok
```

UI design-system checks were run separately:

```text
$ python .opencode/skills/aegisflow-ui/scripts/check_theme.py
RESULT PASS (16/16)

$ python .opencode/skills/aegisflow-ui/scripts/check_contrast.py
RESULT PASS (40/40)

$ .\.venv\Scripts\python.exe .opencode/skills/aegisflow-ui/scripts/check_responsive.py
PASS width=360 scrollWidth=360 bodyWidth=360 innerWidth=360
PASS width=768 scrollWidth=768 bodyWidth=768 innerWidth=768
PASS width=1280 scrollWidth=1280 bodyWidth=1280 innerWidth=1280
PASS width=1536 scrollWidth=1536 bodyWidth=1536 innerWidth=1536
RESULT PASS
```

Playwright and Chromium were installed in the local `.venv` for verification only; neither is listed in `requirements.txt`. The script loads the live mock-mode app at each width and writes full-page screenshots to `ui_checks/width_*.png`. It checks horizontal overflow, not accessibility or visual fidelity to the mockup.

---

## 7. What the tests actually prove

### Proven

- The compiled LangGraph runs end to end in mock mode and reaches `awaiting_human_review`.
- `record_decision` + `workflow.resume` finalizes only with a matching approval.
- Missing, stale, duplicate, agent-authored, or tampered approvals are refused.
- A new version invalidates prior approval.
- Rejection is terminal and blocks export.
- Injection fixtures do not reach the draft; clean facts survive.
- Audit detail redacts email/API-key patterns, and source PII is absent from logs.
- Revision and assurance loops escalate at their limits.
- Summary routing skips verifier and writer; orchestrator routes stay whitelisted.
- All five Streamlit pages render under `AppTest`; approval finalizes the task, and rejection requires a separate terminal confirmation.
- The UI uses icon+text status badges, 44px approval targets, version-named approval actions, and a responsive hierarchy. Green is reserved for human-approved output; SIMULATED is amber.
- Theme tokens pass 16/16 checks and contrast passes 40/40 checks.

### Not proven

| Area | Why | Status |
|---|---|---|
| Live OpenRouter/OpenAI/Gemini calls | Real mode not enabled | **Not executed** |
| Real-model output quality/latency | Same | **Not measured** |
| Browser rendering/accessibility | `AppTest` is headless; Playwright responsive check PASS at four widths with screenshots; no axe audit | **Partially checked** |
| OCR of scanned PDFs | Not implemented | **Not applicable** |
| Multi-user/concurrent access | Single-user design | **Not tested** |
| Files > 10 MB | Rejected by design; boundary unit test exists | **Partially tested** |
| Disk full / SQLite corruption | Out of scope | **Not tested** |
| Adversarial injection beyond the fixture | Limited corpus | **Partially tested** |
| Fairness/bias | No people-decisions, no demographic data | **Not evaluated** |
| Load/performance | Prototype scale | **Not measured** |

---

## 8. Test design notes

- **Deterministic mock:** no network, no sleeps beyond retry backoff, stable output.
- **Isolation:** each test gets a fresh `tmp_path`, database, and checkpointer.
- **Real components:** tests use the real graph, real SQLite schema, real approval logic, and real extraction where relevant.
- **Fault injection:** TC-11 monkeypatches the policy checker to force bounded assurance failure. `MockLLMService.scripted_failures` additionally supports transient/malformed/empty/exception injection for future resilience tests.
- **PII fixtures:** `project_notes.txt` contains an email; TC-12 uses a review feedback string containing an email and an OpenRouter-style key.
- **Unreadable fixtures:** `corrupted.pdf`, `encrypted.pdf`, and `empty.txt` are committed to `sample_data/`.

---

## 9. Known test limitations and future work

1. Add a real-provider test that is skipped unless all four real-mode conditions are present, and record latency/error rates when run.
2. Add a browser-level accessibility audit (axe) and visual regression checks; Playwright responsive checks already pass at 360/768/1280/1536.
3. Add a larger injection corpus, including encoded and delimiter-breaking payloads.
4. Add concurrency/load tests only if the deployment model changes.
5. Add backup/restore tests for both SQLite files.
6. Add property-based tests for hash/version invariants.
7. Measure groundedness and citation coverage on a labelled document set rather than a single fixture.

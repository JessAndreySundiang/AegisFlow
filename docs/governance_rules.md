# AegisFlow Governance Rules (GR-01 to GR-08)

These eight rules are the normative controls for the prototype. Each rule has a single owner, a concrete enforcement point in code, and test evidence. Rules are intentionally **deterministic** wherever a model could otherwise be persuaded to bypass them.

**Verification key**

- **Verified** — exercised by an automated test and/or a recorded manual run.
- **Partially verified** — code exists and is exercised, but a stated part (e.g. live provider) was not run.
- **Not verified** — no execution evidence.

---

## 1. Rule summary

| ID | Rule | Primary risk | Status |
|---|---|---|---|
| GR-01 | Human approval precedes finalization | Unauthorized completion | Verified |
| GR-02 | No fabrication; source or `UNVERIFIED` label | Hallucinated content | Verified |
| GR-03 | Uploaded content is untrusted data | Prompt injection | Verified |
| GR-04 | Protect personal information and secrets | Privacy leakage | Verified (redaction), partial (real provider) |
| GR-05 | Least privilege | Excess capability | Verified by architecture/test coverage |
| GR-06 | Auditable activity | Unaccountable automation | Verified |
| GR-07 | Bounded autonomy | Runaway loops/cost | Verified |
| GR-08 | Transparency | Simulated output mistaken for real | Verified |

---

## GR-01 — Human approval precedes finalization

**Purpose.** No output may be finalized, exported as final, or marked completed without a human approval bound to the exact output version and content hash.

**Enforcement points.**

- `graph/root.py::human_review_node` calls `interrupt(payload)`.
- `approvals.record_decision` accepts only `actor.startswith("human:")` and checks task status, version currency, content hash, duplicate decisions, and transition validity.
- `graph/root.py::finalize_node` calls `assert_finalizable` again.
- `services/export_service.py` calls `assert_finalizable` on every export.
- A new output version makes the prior approval stale.

**Evidence.** `human_reviews` row + `audit_log` (`human_decision`, `finalized`), version hash in export metadata.

**Tests.** TC-01 (approve/finalize/export), TC-02 (agent cannot approve; unpersisted resume escalates), TC-03 (edit invalidates), TC-04 (reject terminal), TC-10 (tamper blocked), plus `tests/test_approvals.py` (8 tests) and the UI approval test.

**Failure behavior.** Refuse the decision or escalate; never finalize.

**Residual risk.** A local user with SQLite edit rights can bypass application controls. Hash binding detects stale content at finalize/export but is not a cryptographic signature.

---

## GR-02 — No fabrication; source or unverified label

**Purpose.** Every claim carries a source reference or an explicit `UNVERIFIED` label. Missing evidence is stated as a gap, never filled from model memory.

**Enforcement points.**

- Planner must report `missing_information` when no readable document exists.
- Document Analyst must attach filename + location to every claim.
- Evidence Verifier marks supported/unsupported/conflicting/unverified using supplied passages only.
- Report Writer must include Summary, Key Findings, Sources, and Limitations/Unverified sections.
- Policy Checker rejects claim lines without `[S#]`/`[UNVERIFIED]`, missing sections, and external-action claims.
- Reviewer checks claim-status consistency.

**Evidence.** `claims` in graph state, `evidence_refs` table, policy findings, draft labels.

**Tests.** TC-01 (grounded draft), TC-06 (clean content preserved after injection), TC-08 (no readable input blocks instead of inventing), TC-11 (policy failure escalates), `tests/test_governance.py` (9 tests), `tests/test_metrics.py` (groundedness/citation coverage).

**Failure behavior.** High-severity finding → bounded revision; exhausted → escalate. Missing input → block.

**Residual risk.** The verifier uses exact normalized substring matching in mock mode. Real-mode semantic verification is unverified. A model could still phrase a claim that is technically cited but misleading; the human reviewer is the final control.

---

## GR-03 — Uploaded content is untrusted data

**Purpose.** Document text is delimited data, never instructions. Instruction-like content must not change permissions, reveal secrets, or bypass approval.

**Enforcement points.**

- `build_untrusted_block` wraps extracted text in `<untrusted_document filename='...'> ... </untrusted_document>`.
- `scan_injection` detects ignore/override/reveal/act-as/external-action patterns at ingestion and over draft/claims.
- The analyst skips sentences that match injection patterns.
- The writer is instructed never to emit the delimiter or follow document instructions.
- Policy Checker rejects surviving injection text or leaked delimiters.
- No external-action tools exist to be hijacked.

**Evidence.** Injection findings in agent uncertainty, policy findings, audit details.

**Tests.** TC-06 (injection fixture is inert; real deadline survives; no attacker email), `test_injection_leftover_fails`, `test_injection_scan`, `test_untrusted_block_delimits`.

**Failure behavior.** A claim containing instruction-like content fails validation; the agent retries or the task escalates.

**Residual risk.** Regex detection cannot cover every prompt-injection phrasing. Defense-in-depth relies on delimiting, immutable permissions, empty tool allowlist, and the human gate.

---

## GR-04 — Protect personal information and secrets

**Purpose.** Redact secrets and PII from logs/audit records. Send documents to an external provider only when the user has configured and authorized it.

**Enforcement points.**

- `redaction.sanitize_detail` is applied to audit details, agent execution refs, file messages, and escalation reasons.
- Patterns cover OpenRouter/OpenAI/Google keys, bearer tokens, labeled secrets, emails, PH mobile numbers, and card-like sequences.
- `Settings.validate` falls back to mock unless `AEGISFLOW_ALLOW_EXTERNAL_LLM=true` **and** a provider key **and** a model are present.
- The UI displays an explicit real-mode warning.
- The review pane warns that source-derived content may contain PII.

**Evidence.** Redacted `audit_log` details, startup warnings, `Settings.describe()` without secret values.

**Tests.** TC-12 (feedback containing an email/key is redacted in stored review feedback; source PII absent from audit), `test_audit_redacts_secrets_and_pii`, `test_secret_fails`, `test_new_email_fails`.

**Failure behavior.** Secret-like values in a draft are high-severity policy findings. Missing external authorization falls back to mock, never silently sends data.

**Residual risk.** Regex detection is best-effort. The draft shown to the reviewer intentionally contains source content and may contain PII. Real-provider data handling is unverified.

---

## GR-05 — Least privilege

**Purpose.** Each agent receives only the state it needs and has no shell, email, calendar, financial, or external-action tools.

**Enforcement points.**

- `_team_input` slices parent state; workers do not receive secrets or the full task history.
- The executor whitelist and agent/skill mapping are fixed in `validation.py`.
- No tool bindings exist in the prototype; all “actions” are text generation.
- Routing is restricted to a fixed whitelist.
- Review/approval writes are separated into `approvals.py` and actor-gated.

**Evidence.** Architecture review, whitelist constants, state key lists.

**Tests.** TC-13 (summary route never calls verifier/writer; all orchestrator destinations are in the whitelist), `test_eight_unique_rules`, `test_agent_actor_cannot_approve`.

**Failure behavior.** Unknown agents/skills or routing choices are rejected; invalid routing escalates.

**Residual risk.** The prototype has no per-user roles. “Least privilege” is at the agent/state level, not multi-user authorization.

---

## GR-06 — Auditable activity

**Purpose.** Record routing decisions, agent executions, errors, escalations, output versions, and human decisions in an append-only audit trail.

**Enforcement points.**

- `audit_log` writes from validation, planner, agents, leads, orchestrator, approvals, finalize, block, escalate, reject.
- `agent_executions` records one row per completed/failed call.
- `routing_log` is stored in graph state and written to audit.
- `human_reviews` stores every decision with version, hash, reviewer, and actor.
- Output versions are immutable rows with content hashes.

**Evidence.** `audit_log`, `agent_executions`, `routing_log`, `output_versions`, `human_reviews`.

**Tests.** TC-12 (expected event types and all six agents/checks present), `test_task_lifecycle`, `test_audit_redacts_secrets_and_pii`.

**Failure behavior.** Audit write failures raise and abort the operation rather than proceeding silently.

**Residual risk.** Append-only is an application convention; a local user with SQLite access can edit or delete rows. No external tamper-evident log.

---

## GR-07 — Bounded autonomy

**Purpose.** Retry, revision, delegation-depth, and recursion limits are enforced. The system escalates instead of looping or guessing indefinitely.

**Enforcement points.**

- `call_agent`: `max_retries + 1` attempts with error classification.
- Team leads: analysis 8 iterations, drafting/assurance 6.
- Orchestrator: each team at most 4 runs.
- Revision budget: `max_revisions` (default 2) for both assurance and human revisions.
- LangGraph `recursion_limit` (default 80).
- Escalation paths set `status=failed` and an explicit reason.

**Evidence.** `retry_counts`, `agent_executions.retries`, `escalation_reason`, audit events.

**Tests.** TC-05 (revision budget and anti-bypass), TC-11 (assurance failure escalates after one bounded revision), `test_revision_requires_feedback_and_reaches_limit`.

**Failure behavior.** Escalate with a reason; never continue indefinitely.

**Residual risk.** Lead iteration limits are fixed in code rather than configurable. `AEGISFLOW_LLM_TIMEOUT` (default 60 s) bounds each call and the whole candidate across retries, so a slow provider fails over instead of being retried repeatedly; a call that ignores the SDK's own timeout can still hang, because no separate watchdog thread interrupts it.

---

## GR-08 — Transparency

**Purpose.** Simulated output is labeled in the UI and exports; uncertainty and reviewer findings are shown; mock results are never presented as real.

**Enforcement points.**

- `Settings.simulated` controls the mode.
- Mock draft header: `**SIMULATED OUTPUT** — deterministic mock content; not real AI analysis.`
- UI banner on Dashboard, Workflow, and Review: amber **SIMULATED OUTPUT** notice.
- Export metadata: `simulated: true` / `Simulated: yes`.
- Review page repeats the simulated warning and shows policy/reviewer findings.
- Startup warnings surface fallback reasons.

**Evidence.** Draft headers, UI banner, export metadata, `output_versions.simulated`.

**Tests.** TC-07 (labels in payload, version, Markdown, TXT), `test_missing_simulated_label_is_warning_not_failure`, UI smoke test (banner present).

**Failure behavior.** Missing label is a warning, not a silent pass; the human sees it in policy findings.

**Residual risk.** A user could copy the draft without its label. The system cannot control downstream sharing.

---

## 2. Rule-to-risk-to-test map

| Rule | Risks addressed | Primary tests |
|---|---|---|
| GR-01 | R-04, R-08 | TC-01, TC-02, TC-03, TC-04, TC-10 |
| GR-02 | R-01, R-07 | TC-01, TC-06, TC-08, TC-11 |
| GR-03 | R-02, R-09 | TC-06 |
| GR-04 | R-03 | TC-12 |
| GR-05 | R-09 | TC-13 + architecture review |
| GR-06 | R-04, R-08 | TC-12 |
| GR-07 | R-05, R-06 | TC-05, TC-11 |
| GR-08 | R-01, R-04 | TC-07 |

Risk definitions are in [risk_assessment.md](risk_assessment.md).

---

## 3. Operating procedure when a rule fires

1. **Stop the task.** Do not resume or export.
2. **Read the audit trail.** Identify the event type, actor, and rule id.
3. **Classify.**
   - Missing input → ask the user for readable documents.
   - Policy/review failure → inspect findings; revise if budget remains.
   - Approval mismatch/tamper → do not approve; investigate the version.
   - Injection → confirm the document is untrusted; do not “fix” by editing permissions.
4. **Record the outcome.** Revisions and rejections are human decisions and must go through the UI.
5. **Escalate to the project owner** if a control failed or a limit was reached unexpectedly.

---

## 4. Change control

Any change to a governance control requires:

- an updated rule definition in `aegisflow/governance/rules.py`
- an updated or new test in `tests/`
- a note in [testing.md](testing.md) and [risk_assessment.md](risk_assessment.md)
- a documented residual-risk decision

Rules are not “advisory prompts”. If a control cannot be enforced in code or by a deterministic check, it must be described as a limitation, not a rule.

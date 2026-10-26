# NIST AI Risk Management Framework Worksheet

**System:** AegisFlow v0.1.0 — governed hierarchical document-task agent
**Framework reference:** NIST AI Risk Management Framework (AI RMF 1.0), functions GOVERN / MAP / MEASURE / MANAGE
**Assessment date:** 26 October 2026
**Assessor:** SIP10 project author
**Status legend:** ✅ implemented & verified · 🟡 implemented, not verified · ⚪ planned / partial · ➖ not applicable to this prototype

> This is a **course-prototype worksheet**, not a certification or a formal NIST assessment. Statuses reflect what was actually executed. Real-provider behaviour is unverified because no live provider call was authorized.

---

## 1. System description

| Item | Description |
|---|---|
| Purpose | Convert uploaded documents into a cited, reviewed deliverable under human control |
| Intended users | A single local user acting as requester and reviewer |
| Deployment | Local Windows machine, Streamlit UI, SQLite, Python 3.13 project virtual environment |
| Inputs | Natural-language request; PDF, TXT, or DOCX files up to 10 MB |
| Outputs | Markdown/TXT draft; approved Markdown/TXT export with approval metadata |
| Model use | Mock deterministic model by default; optional OpenRouter/OpenAI/Gemini in real mode |
| Autonomy | Bounded; no external actions; human approval required before finalization |
| Out of scope | Multi-user auth, regulated data, OCR, web access, email/calendar/finance tools |
| Success criteria | Traceable claims, deterministic policy pass, independent review pass, human approval, reproducible audit |

### Assumptions

- The user supplies readable documents and reviews output competently.
- The local machine and SQLite files are trusted.
- Extracted text is the only document content used; no OCR.
- The mock model is a test/demo mechanism, not a claim of AI capability.

### Risk tolerance

Low tolerance for unauthorized finalization, fabricated claims, and secret leakage. Moderate tolerance for latency and manual review effort. The prototype is not authorized for regulated or confidential data.

---

## 2. GOVERN

| Category | Intended outcome | AegisFlow implementation / evidence | Status | Gap / action |
|---|---|---|---|---|
| GOVERN 1 — Accountability | Clear owners for risk decisions | GR-01 to GR-08 each name an owner; approval bound to reviewer + actor; audit trail | ✅ | Add a named system owner outside the student author for any real deployment |
| GOVERN 2 — Culture | Safety and transparency are normal operating practice | SIMULATED banner, visible limitations, explicit non-goals, no “AI decides” claims | ✅ | Add reviewer training material before real use |
| GOVERN 3 — Risk management process | Risks are identified, assessed, and tracked | `risk_assessment.md` R-01..R-09 with likelihood/impact/mitigation/residual | ✅ | Re-review after any provider/model change |
| GOVERN 4 — Third-party risk | External providers are governed | Three-part authorization gate; provider/model recorded; fallback to mock; no key in logs | 🟡 | Real provider data-retention and subprocessors not reviewed (real mode not enabled) |
| GOVERN 5 — Stakeholder engagement | Affected parties are considered | Human reviewer is the primary stakeholder; PII warning in review pane | ⚪ | No external stakeholder consultation; add for production |
| GOVERN 6 — Policies | Written policies exist | Governance rules, approval design, user guide, testing doc | ✅ | Policies are project-level, not organizational |

---

## 3. MAP

| Category | Intended outcome | AegisFlow implementation / evidence | Status | Gap / action |
|---|---|---|---|---|
| MAP 1 — Context | Intended use and context are documented | README scope, architecture context, user guide | ✅ | — |
| MAP 2 — Categorization | System and risks are classified | Document-task prototype; risks categorized by type; no high-stakes decisions | ✅ | Add a formal impact tier if deployed beyond coursework |
| MAP 3 — Capabilities | Capabilities and limits are known | Capability table; non-goals; verified/unverified status; agent/skill map | ✅ | Real-mode capability unverified |
| MAP 4 — Risks | Risks are identified | R-01..R-09 with sources and affected rules | ✅ | Add adversarial testing beyond the current injection fixture |
| MAP 5 — Impacts | Impacts on users/affected parties are considered | Fabrication, privacy, over-automation, and local tampering analyzed | ⚪ | No formal user study or impact assessment on third parties |

---

## 4. MEASURE

| Category | Intended outcome | AegisFlow implementation / evidence | Status | Gap / action |
|---|---|---|---|---|
| MEASURE 1 — Metrics | Appropriate metrics are selected | Groundedness, citation coverage, revisions, approval outcome, time reduction, retries | ✅ | Metrics are defined; no statistical benchmark across a corpus |
| MEASURE 2 — Evaluation | System is evaluated against criteria | 67 automated tests, incl. 13 E2E and 3 UI flows; manual mock smoke run; theme 16/16 and contrast 40/40 PASS | ✅ | Real-provider quality and latency not measured |
| MEASURE 3 — Tracking | Risks are monitored over time | Audit log, agent executions, workload metrics, dashboard counts | ✅ | No automated drift monitoring; local-only |
| MEASURE 4 — Feedback | Feedback is collected and used | Reviewer feedback on revisions; quality rating; approval outcome | 🟡 | No structured post-deployment feedback loop |

### Measurement definitions

| Metric | Definition | Caveat |
|---|---|---|
| Groundedness | Supported claims with a source reference ÷ all claims | Mock verifier uses exact substring matching |
| Citation coverage | Detected claim lines with `[S#]`/`[UNVERIFIED]` ÷ all claim lines | Heuristic line detection |
| Time reduction | (manual minutes − elapsed) ÷ manual minutes | **Not a quality measure**; negative means slower |
| Revisions requested | Count of human `request_revision` decisions | Does not include automatic assurance revisions |
| Approval outcome | approved / rejected / revision_requested | Human judgement, not model quality |

No invented benchmark numbers are reported.

---

## 5. MANAGE

| Category | Intended outcome | AegisFlow implementation / evidence | Status | Gap / action |
|---|---|---|---|---|
| MANAGE 1 — Prioritization | Risks are prioritized | Risk scores; R-01/R-02/R-03/R-04 are high and mapped to GR-01..GR-04 | ✅ | Re-score after real-mode testing |
| MANAGE 2 — Response | Controls reduce prioritized risks | Delimiting, injection scan, policy checks, hash-bound approval, redaction, limits | ✅ | Regex injection/PII detection is incomplete by nature |
| MANAGE 3 — Recovery | Failures are contained and recoverable | Block/escalate paths, checkpoint persistence, crash-recovery note, no silent completion | 🟡 | No automated restore/backup procedure for SQLite |
| MANAGE 4 — Communication | Risks and incidents are communicated | UI reasons, audit trail, risk register, final report | ✅ | No external incident-notification process |

---

## 6. Trustworthy AI characteristics

| Characteristic | How AegisFlow addresses it | Status | Honest gap |
|---|---|---|---|
| Valid and reliable | Source-bound claims, verifier, policy checks, independent review, tests | 🟡 | Real-model accuracy unverified; mock is deterministic, not intelligent |
| Safe | No external actions, bounded loops, human gate, escalation | ✅ | Local-only prototype |
| Secure and resilient | Untrusted-input delimiting, actor-gated approvals, hash checks, redaction, fail-safe mode | 🟡 | Local DB tampering and regex gaps; no auth |
| Accountable and transparent | Audit trail, version hashes, reviewer identity, rule IDs, simulated labels | ✅ | Reviewer identity is self-asserted |
| Explainable and interpretable | Routing reasons, claim sources, policy findings, reviewer reasons, no hidden scoring | ✅ | Model reasoning in real mode is not exposed |
| Privacy-enhanced | Mock default, external gate, log redaction, PII warning | 🟡 | Draft intentionally contains source PII; real-provider handling unverified |
| Fair with harmful bias managed | No demographic decisions; no ranking/scoring of people | ➖/⚪ | Bias was not evaluated; the system is not designed for people-decisions |

---

## 7. Open actions

| # | Action | Priority | Owner | Target |
|---|---|---|---|---|
| A-01 | Configure a real provider key and run TC-01/06/12 in real mode; record latency, errors, and output quality | High | Project author | Before claiming real-mode support |
| A-02 | Add broader prompt-injection fixtures (encoded, multi-turn, delimiter-breaking) | High | Project author | Next iteration |
| A-03 | Add a backup/restore procedure for `aegisflow.sqlite` and `checkpoints.sqlite` | Medium | Project author | Before any non-demo use |
| A-04 | Add authentication/roles if the app is ever shared | High (if shared) | Project owner | Before multi-user deployment |
| A-05 | Evaluate bias/fairness only if the use case expands to people-related decisions | Low | Project owner | If scope changes |
| A-06 | Replace regex PII detection with a reviewed detector; document residual misses | Medium | Project author | Next iteration |
| A-07 | Add a formal user study for reviewer workload and trust calibration | Medium | Project author | Research extension |

---

## 8. Assessment conclusion

For a **single-user, local, mock-mode academic prototype**, AegisFlow has credible controls for the four highest-priority risks: unauthorized finalization, fabrication, prompt injection, and log leakage. The controls are implemented in code and exercised by automated tests.

The assessment does **not** support claims of production readiness, real-provider reliability, regulatory compliance, multi-user security, or fairness. Those remain open actions and documented limitations.

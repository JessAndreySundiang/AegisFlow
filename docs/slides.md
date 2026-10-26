---
marp: true
theme: default
paginate: true
size: 16:9
header: "AegisFlow · SIP10 Final Project"
footer: "Working prototype · mock mode verified · 90 tests passing"
style: |
  :root {
    --ink: #0f172a;
    --muted: #64748b;
    --line: #cbd5e1;
    --paper: #f8fafc;
    --teal: #0f766e;
    --teal-soft: #ccfbf1;
    --amber: #b45309;
    --red: #b91c1c;
  }
  section {
    font-family: "Segoe UI", Arial, sans-serif;
    color: var(--ink);
    background: var(--paper);
    padding: 42px 56px;
    font-size: 25px;
    line-height: 1.35;
  }
  section.lead {
    background: linear-gradient(135deg, #0f172a 0%, #134e4a 100%);
    color: white;
    justify-content: center;
  }
  section.lead h1 { font-size: 64px; line-height: 1.02; margin: 0 0 14px; letter-spacing: -2px; }
  section.lead h2 { font-size: 28px; font-weight: 400; color: #99f6e4; margin: 0 0 30px; }
  section.lead p, section.lead footer { color: #cbd5e1; }
  section.lead footer { font-size: 14px; }
  h1 { font-size: 44px; letter-spacing: -1px; margin: 0 0 8px; }
  h2 { font-size: 30px; color: var(--teal); margin: 0 0 18px; }
  h3 { font-size: 23px; margin: 0 0 8px; }
  p, li { font-size: 23px; }
  strong { color: #0f172a; }
  table { font-size: 19px; width: 100%; border-collapse: collapse; }
  th { background: #e2e8f0; text-align: left; }
  th, td { border-bottom: 1px solid var(--line); padding: 7px 9px; }
  blockquote { border-left: 5px solid var(--teal); margin: 16px 0; padding: 12px 20px; background: white; }
  code { background: #e2e8f0; border-radius: 4px; padding: 2px 5px; font-size: 0.85em; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 26px; }
  .three { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 18px; }
  .card { background: white; border: 1px solid var(--line); border-radius: 14px; padding: 18px; }
  .card h3 { color: var(--teal); }
  .card p { font-size: 20px; color: #334155; }
  .risk { border-left: 6px solid var(--red); }
  .ok { border-left: 6px solid var(--teal); }
  .warn { border-left: 6px solid var(--amber); }
  .small { font-size: 16px; color: var(--muted); }
  .pill { display: inline-block; background: var(--teal-soft); color: #115e59; border-radius: 999px; padding: 2px 11px; font-size: 16px; font-weight: 600; }
  .flow { font-size: 19px; background: white; border: 1px solid var(--line); border-radius: 12px; padding: 17px; text-align: center; line-height: 1.7; }
  .big { font-size: 32px; font-weight: 700; color: var(--teal); }
  section::after { color: var(--muted); font-size: 14px; }
---

<!-- _class: lead -->
<!-- _paginate: false -->

# AegisFlow

## A governed hierarchical multi-agent system for document tasks — with human-in-the-loop approval

**SIP10 Final Project** · 26 October 2026  
Working prototype · mock mode verified · **90 tests passing**

<!--
SPEAKER NOTES
Open with the one-line rule: AI does the work; the human keeps final authority.
State immediately that the demo runs in mock mode. Do not imply real AI analysis.
-->

---

# One model call hides three risks

<div class="three">
<div class="card risk">
<h3>Fabrication</h3>
<p>Adds a budget, deadline, or name that was never in the source.</p>
</div>
<div class="card risk">
<h3>Prompt injection</h3>
<p>A document tells the model to ignore instructions or reveal secrets.</p>
</div>
<div class="card risk">
<h3>Unaccountable automation</h3>
<p>Nobody can prove what was approved, by whom, or whether it changed.</p>
</div>
</div>

> AegisFlow treats these as **governance** problems, not prompt-engineering problems.

<!--
SPEAKER NOTES
Give one concrete example for each. Then transition: a prompt is advisory; a control must be enforced in code.
-->

---

# Course alignment, exceeded

<div class="cols">
<div>

### Required
- 3 agents/roles
- 3 SKILL.md files
- 5 governance rules
- 5 risks
- 5 tests
- Human approval
- NIST AI RMF

</div>
<div>

### Delivered
- **6** agents/roles
- **6** SKILL.md packages
- **8** governance rules
- **9** risks
- **90** tests (13 E2E + 74 unit/integration + 3 UI)
- Hash-bound approval
- GOVERN / MAP / MEASURE / MANAGE

</div>
</div>

<p class="pill">12/12 SIP10 deliverables mapped to evidence</p>

<!--
SPEAKER NOTES
Do not read every item. Point out that the counts exceed minimums and every extra control is tied to a test.
-->

---

# Architecture: a real hierarchy

<div class="flow">
USER → PLANNER → <strong>ORCHESTRATOR</strong><br>
┬─ Analysis Lead (rules) → Analyst → Verifier<br>
├─ Drafting Lead (rules) → Writer<br>
└─ Assurance Lead (rules) → Policy Checker → Reviewer<br>
→ <strong>HUMAN APPROVAL</strong> → FINALIZE → EXPORT
</div>

<div class="cols" style="margin-top:18px">
<div class="card ok">
<h3>LLM workers</h3>
<p>Extract, verify, write, and review language.</p>
</div>
<div class="card ok">
<h3>Deterministic authority</h3>
<p>Route, retry, limit, gate, approve, and export. Not arguable by a model.</p>
</div>
</div>

<!--
SPEAKER NOTES
Work is delegated downward, results report upward, problems escalate to the human.
Team leads make zero model calls. This is a hybrid hierarchy by design.
-->

---

# Workflow: stop before authority

<div class="flow">
validate_request → planner → orchestrator<br>
→ analysis / drafting / assurance → <strong>human_review</strong><br>
approve → finalize · reject → terminal · revise → bounded loop
</div>

<div class="cols" style="margin-top:20px">
<div>

### Persist first
The UI writes the decision to SQLite **before** `Command(resume=...)`.

</div>
<div>

### Then re-verify
The graph re-reads the approval for the **exact version and hash**.

</div>
</div>

<p class="small">A forged resume payload cannot finalize a task.</p>

<!--
SPEAKER NOTES
Slow down here. Persist-first, resume-second is the core defense.
Approval is not a boolean flag; it is bound to version id + SHA-256.
-->

---

# Six agents, six skills

| Agent | Type | Skill |
|---|---|---|
| Planner | LLM | task-planning |
| Document Analyst | LLM | document-extraction |
| Evidence Verifier | LLM | evidence-verification |
| Report Writer | LLM | report-writing |
| Independent Reviewer | LLM | quality-review |
| Policy Checker | deterministic | untrusted-content-handling |

<p class="small">Every execution records the agent, level, skill, status, retries, error class, and simulated flag.</p>

<!--
SPEAKER NOTES
The Policy Checker is not another opinion. It checks required sections, citations, secrets, injection leftovers, and external-action claims.
The Reviewer never rewrites the draft.
-->

---

# Untrusted in. Grounded out.

<div class="cols">
<div class="card warn">
<h3>Uploaded text is data</h3>
<ul>
<li>Delimited as <code>&lt;untrusted_document&gt;</code></li>
<li>Scanned for instruction patterns</li>
<li>Instruction-like sentences skipped</li>
<li>Zero action tools to hijack</li>
<li>Human gate remains</li>
</ul>
</div>
<div class="card ok">
<h3>Every claim is traceable</h3>
<ul>
<li>Filename + location</li>
<li>Supported / unsupported / conflicting / unverified</li>
<li>Required Sources and Limitations</li>
<li>Policy check + independent review</li>
<li>Human sees the evidence</li>
</ul>
</div>
</div>

> TC-06: injection text does not reach the draft; a clean deadline from the same file survives.

<!--
SPEAKER NOTES
Call it defense-in-depth, not a guarantee. Regex detection is incomplete; the empty tool allowlist and human gate are backstops.
-->

---

# Selective routing, not a fixed pipeline

<div class="three">
<div class="card">
<h3>Summary</h3>
<p><strong>Analyst</strong><br>→ assurance<br><span class="small">verifier and writer skipped</span></p>
</div>
<div class="card">
<h3>Outline</h3>
<p><strong>Analyst → Writer</strong><br>→ assurance<br><span class="small">verifier skipped</span></p>
</div>
<div class="card">
<h3>Report / brief</h3>
<p><strong>Analyst → Verifier → Writer</strong><br>→ assurance<br><span class="small">all three executors</span></p>
</div>
</div>

- Routing is driven by the validated plan, not a model improvising at runtime.
- Every destination is checked against a fixed whitelist.
- TC-13 proves a summary creates no verifier/writer execution rows.

<!--
SPEAKER NOTES
For the course demo, use a report request so all three executor boxes are visible.
Selective routing is better engineering and is tested, not hidden.
-->

---

# Eight governance rules, enforced in code

| Rule | Control |
|---|---|
| **GR-01** | Human approval before finalization |
| **GR-02** | Source reference or `UNVERIFIED` |
| **GR-03** | Uploaded content is data |
| **GR-04** | Redact secrets/PII; gate external LLM |
| **GR-05** | Least privilege; no action tools |
| **GR-06** | Audit routing, agents, decisions |
| **GR-07** | Bounded retries, revisions, recursion |
| **GR-08** | Label simulated output |

<p class="small">Each rule has an owner, enforcement point, evidence, failure behavior, residual risk, and tests.</p>

<!--
SPEAKER NOTES
These are not advisory prompts. If a control cannot be enforced in code or a deterministic check, it is documented as a limitation instead.
-->

---

# NIST AI RMF: claims and gaps

<div class="cols">
<div class="card ok">
<h3>GOVERN / MAP</h3>
<p>Owners, policies, third-party provider gate; purpose, limits, affected parties, nine risks.</p>
</div>
<div class="card ok">
<h3>MEASURE / MANAGE</h3>
<p>Audit, tests, groundedness, citation coverage; block/escalate, limits, recovery, residual risk.</p>
</div>
</div>

<div class="card warn" style="margin-top:18px">
<h3>Stated gaps</h3>
<p>Live provider behavior unverified · regex detection incomplete · single-user local prototype · no fairness evaluation · no formal impact study</p>
</div>

<!--
SPEAKER NOTES
Do not claim certification. This is a course worksheet that distinguishes verified controls from open actions.
-->

---

# Approval is bound to the exact output

<div class="flow">
draft v1 + SHA-256<br>
→ human reads draft, claims, evidence, findings<br>
→ decision persisted in SQLite (<code>actor = human:*</code>)<br>
→ graph resume → re-read approval → re-check hash<br>
→ finalize → export re-check → approved Markdown / TXT
</div>

<div class="cols" style="margin-top:18px">
<div>

### New version?
Prior approval becomes **stale**.

</div>
<div>

### Content changed?
Finalize and export **refuse**.

</div>
</div>

<p class="small">Integrity detection, not a cryptographic signature. Local DB tampering is disclosed as residual risk.</p>

<!--
SPEAKER NOTES
Only human:* actors may write decisions. Agents never import the approval module.
The hash is not non-repudiation; be explicit about that.
-->

---

# Live demo: 4 minutes

<div class="cols">
<div>

### Path
1. New Task → report request + `project_notes.txt`
2. Workflow → agent hierarchy + routing log
3. Workflow → Task details and audit
4. Review → version, hash, evidence, decision
5. Approve version N → acknowledgment → finalize
6. History → status filter + Markdown/TXT export
7. Optional: injection fixture

</div>
<div>

### What to watch
- Amber SIMULATED OUTPUT banner
- Dark sidebar and page header
- Planner runs first
- Routing reasons + whitelist
- Green reserved for human approval
- Hash on the Review page
- Decision recorded before resume
- Tokenized badges + 44px targets
- Export re-verification

</div>
</div>

> Fallback: if the UI fails, say so and use recorded screenshots and the test evidence. Never fake a live result.

<!--
SPEAKER NOTES
Keep the demo capped at four minutes. If it is slow, narrate the audit trail instead of clicking ahead.
The UI is backed by the project-scoped aegisflow-ui skill; technical tables and the hash sit in collapsed sections.
-->

---

# Tests: 90 passed

<div class="three">
<div class="card ok">
<h3>51</h3>
<p>Unit + integration<br><span class="small">models, DB, approvals, extraction, skills, governance, metrics</span></p>
</div>
<div class="card ok">
<h3>13</h3>
<p>End-to-end<br><span class="small">TC-01 to TC-13 on the real graph and SQLite</span></p>
</div>
<div class="card ok">
<h3>3</h3>
<p>Streamlit UI<br><span class="small">all pages + approval, rejection, revision flows</span></p>
</div>
</div>

```text
$ .\.venv\Scripts\python.exe -m pytest tests\ -q
90 passed in 19.21s
```

<p class="small">Proven: approval, tamper detection, injection, routing, escalation, audit redaction.<br>
Not proven: live provider quality/latency, browser CSS/accessibility, OCR, multi-user load.</p>

<!--
SPEAKER NOTES
Offer the command. Distinguish what the tests prove from what they do not.
-->

---

# Honest limits

<div class="cols">
<div class="card warn">
<h3>Not verified</h3>
<ul>
<li>Live OpenRouter / Gemini / OpenAI calls</li>
<li>Real-model quality and latency</li>
<li>Browser-level accessibility</li>
</ul>
</div>
<div class="card risk">
<h3>Residual risk</h3>
<ul>
<li>Local SQLite can be rewritten</li>
<li>Hash is integrity, not signature</li>
<li>Regex detection is incomplete</li>
<li>Single user, no auth, no OCR</li>
</ul>
</div>
</div>

> Confidence comes from naming limits, not hiding them.

<!--
SPEAKER NOTES
If asked whether real GPT/Gemini was tested: no. The adapters are implemented; no live call was made.
-->

---

# Generation is probabilistic. Authority is not.

<div class="big">
Planner → Orchestrator → 3 executors → Reviewer → Human → Output
</div>

- 6 agents · 6 skills · 8 governance rules · 9 risks
- Approval bound to the exact version and SHA-256 hash
- 90 automated tests · mock mode verified
- Real-provider mode implemented but **not verified**

### Thank you — questions?

<!--
SPEAKER NOTES
Close on the central lesson. Then invite questions. Keep the Q&A backup slide ready.
-->

---

# Q&A backup

| Likely question | Short answer |
|---|---|
| Really LangGraph? | Root `StateGraph`, three team subgraphs, `interrupt()` / `Command(resume=...)`, SQLite checkpointer, whitelist routing |
| How stop injection? | Delimit, scan, no tools, policy check, human gate; defense-in-depth, not a guarantee |
| Why not always run all agents? | Plan-driven routing cuts cost/latency/failure surface; TC-13 proves selective execution |
| What is not done? | Live provider run, browser-level UI test, OCR, auth/multi-user, backup/restore |
| Is the hash a signature? | No — integrity detection only; local tampering remains a disclosed risk |

<!--
SPEAKER NOTES
Use only when asked. Do not read this slide unprompted.
-->

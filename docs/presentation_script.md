# AegisFlow Presentation Script

**Delivery limit:** 15 minutes maximum (Q&A after, if permitted)  
**Deck:** [`slides/aegisflow_deck.html`](../slides/aegisflow_deck.html) · Marp source: [`slides.md`](slides.md)  
**Mode for the live demo:** mock mode (deterministic, local, no network)  
**Status to state on stage:** 92 automated tests pass; real-provider mode is implemented but **not verified**.

> **Speaker rule:** never describe mock output as real AI analysis. The UI labels it SIMULATED for a reason. If the demo fails, use the fallback in section 10 and say so plainly.

---

## Timing plan (15:00)

| Section | Slides | Time | Cumulative |
|---|---|---:|---:|
| Problem, goal, requirements | 1–3 | 2:00 | 2:00 |
| Hierarchy and workflow | 4–5 | 2:00 | 4:00 |
| Agents, skills, selective routing | 6–8 | 2:00 | 6:00 |
| Governance, NIST, human approval | 9–11 | 2:00 | 8:00 |
| Live demo | 12 | 4:00 | 12:00 |
| Tests and results | 13 | 1:30 | 13:30 |
| Risks and limitations | 14 | 1:00 | 14:30 |
| Conclusion and Q&A transition | 15–16 | 0:30 | 15:00 |

If the demo runs long, shorten slides 9–11 to the one-line rule summaries and keep tests/limitations intact.

---

## Slide 1 — Title (0:00–0:20)

**On screen**

> **AegisFlow**  
> A Governed Hierarchical Multi-Agent System for Document Tasks with Human-in-the-Loop Approval  
> SIP10 Final Project · 26 October 2026

**Say**

> “Good morning. AegisFlow is a working LangGraph prototype that turns uploaded documents into a cited, reviewed deliverable. Its defining rule is simple: AI does the work, but a human keeps the authority to approve the final output.”

**Cue:** point to the subtitle “working prototype · mock mode verified”.

---

## Slide 2 — The problem (0:20–1:10)

**On screen:** three risk cards — Fabrication, Prompt injection, Unaccountable automation.

**Say**

> “Most document assistants are one model call: upload a file, get a summary, hope. That hides three problems.
>
> First, fabrication. The model can add a budget or a deadline that was never in the source.
>
> Second, prompt injection. A document can contain text that tells the model to ignore its instructions, reveal secrets, or skip approval.
>
> Third, accountability. Nobody can prove which exact text was approved, by whom, or whether it changed afterward.
>
> AegisFlow treats these as governance problems, not just prompt-engineering problems.”

**Cue:** the next slide answers each risk with a control.

---

## Slide 3 — Goal and requirements (1:10–2:00)

**On screen:** the course pipeline and the 12-deliverable checklist with counts.

> PLAN → ORCHESTRATE → EXECUTE → CHECK → HUMAN APPROVAL → OUTPUT

**Say**

> “The course asks for a pipeline, a hierarchy, at least three agents and three skills, five governance rules, five risks, five tests, a NIST worksheet, and a human approval point.
>
> AegisFlow implements all twelve deliverables: six agents and six SKILL.md packages, eight governance rules, nine risks, six end-to-end scenarios plus seven more, and 92 automated tests in total.
>
> The basic workflow maps literally: Planner first, Orchestrator next, three executor roles, Reviewer, human approval, final output. The added team leads make the hierarchy real without changing that required chain.”

**Cue:** do not read every row. Point to “6 agents / 6 skills / 8 rules / 9 risks / 92 tests”.

---

## Slide 4 — Architecture and hierarchy (2:00–3:00)

**On screen:** layered diagram.

- Level 1: Root Orchestrator + Planner
- Level 2: rule-based Analysis / Drafting / Assurance leads
- Level 3: Analyst, Verifier, Writer, Reviewer
- Level 4: Policy Checker, approval gate, export gate
- Storage: SQLite app DB + checkpoint DB
- Models: mock `ScriptedChatModel` or real provider adapter

**Say**

> “Work is delegated downward, results report upward, and unresolved problems escalate to the human.
>
> At the top, the Planner always runs first and produces a validated plan. The root Orchestrator routes deterministically over that plan. It does not ask a model what to do next.
>
> The three team leads are rule-based supervisors. They enforce prerequisites, choose the next worker, and return completed, blocked, or escalated. That is deliberate: permissions and routing should not be arguable by a language model.
>
> The workers are LLM-backed. The Policy Checker and the approval/export gates are deterministic. This is a hybrid hierarchy: language capability at the bottom, authority at the top.”

**Cue:** emphasize that the leads make **no extra model calls**.

---

## Slide 5 — Workflow and state machine (3:00–4:00)

**On screen:** state diagram.

```text
validate → planner → orchestrator
                         ├── analysis_team
                         ├── drafting_team
                         └── assurance_team
                                  ↓
                            human_review (interrupt)
                         ┌────────┼─────────┐
                      approve   reject    revise
                         ↓        ↓          ↓
                     finalize  rejected   bounded loop
```

**Say**

> “The graph validates the request, plans, and then routes selectively. Assurance always runs before the human gate.
>
> At `human_review`, LangGraph calls `interrupt()` and stops. The UI records the decision in SQLite first, then resumes with `Command(resume=...)`. The graph independently re-reads the persisted decision for the exact version. A forged resume payload does not finalize anything.
>
> Approval moves to `finalize`, which re-checks the version and hash. Rejection is terminal. Revision creates a new version and returns to review, within a budget of two.
>
> Every route is written to the routing log and audit trail with a reason and the relevant rule ID.”

**Cue:** say “persist first, resume second” slowly; this is the core defense.

---

## Slide 6 — Agents and skills (4:00–4:45)

**On screen:** six-row table.

| Agent | Type | Skill |
|---|---|---|
| Planner | LLM | task-planning |
| Document Analyst | LLM | document-extraction |
| Evidence Verifier | LLM | evidence-verification |
| Report Writer | LLM | report-writing |
| Independent Reviewer | LLM | quality-review |
| Policy Checker | deterministic | shared untrusted-content-handling |

**Say**

> “Each LLM worker has a narrow contract and a matching SKILL.md. The loader validates frontmatter and injects the body into the system prompt. Each execution records which skill was used.
>
> The Document Analyst extracts sentence-level claims with a filename and location. The Verifier checks those claims against the supplied passages only. The Writer formats only supplied claims into required sections. The Reviewer checks completeness, traceability, and policy consistency.
>
> The Policy Checker is not another opinion. It runs deterministic checks: required sections, citation or UNVERIFIED labels, leftover injection text, secret patterns, invented emails, and external-action claims.
>
> The Reviewer never rewrites the draft. The human is the final authority.”

**Cue:** contrast “LLM judgement” with “deterministic checks”.

---

## Slide 7 — Untrusted documents and grounding (4:45–5:30)

**On screen:** two columns.

- **Untrusted input:** delimit → scan → skip instructions → empty tool allowlist → human gate
- **Grounded output:** claim → source reference → verifier status → policy check → reviewer → human

**Say**

> “Uploaded text is wrapped in `<untrusted_document>` delimiters and described as data. The scanner flags ignore/override/reveal/act-as/external-action patterns. The analyst drops instruction-like sentences. The writer is told never to follow document instructions, and the policy checker rejects surviving delimiters or instruction text.
>
> Critically, the workers have no tools. There is no email, shell, browser, or financial action to hijack.
>
> For grounding: every claim needs a source reference or an explicit UNVERIFIED label. Gaps are stated as gaps. If no readable document is supplied, the task blocks instead of inventing content.
>
> Our injection test uses a real fixture: the attack text does not reach the draft, while a clean deadline from the same file does. That proves the content was processed as data, not obeyed.”

**Cue:** mention this is defense-in-depth, not a guarantee. Regex detection has limits.

---

## Slide 8 — Selective routing (5:30–6:15)

**On screen:** three route cards.

- Summary → Analyst → assurance
- Outline → Analyst → Writer → assurance
- Report / meeting brief → Analyst → Verifier → Writer → assurance

**Say**

> “The Orchestrator runs only what the plan requires. A summary does not need the verifier or the writer. An outline skips the verifier. A report runs all three executors.
>
> This is not cosmetic: selective routing reduces cost, latency, and unnecessary failure surface. The route is driven by validated subtasks, not by a model improvising at runtime.
>
> TC-13 checks that a summary creates no verifier or writer execution rows, and that every routing destination is in the whitelist. For the course demo, we use a report request so all three executor roles are visible.”

**Cue:** pause here for the governance section; this is the transition from “how it works” to “how it is controlled”.

---

## Slide 9 — Governance rules (6:15–6:55)

**On screen:** eight compact rule cards.

| Rule | Control |
|---|---|
| GR-01 | Human approval before finalization |
| GR-02 | Source reference or UNVERIFIED |
| GR-03 | Uploaded content is data |
| GR-04 | Redact secrets/PII; gate external LLM |
| GR-05 | Least privilege; no action tools |
| GR-06 | Audit routing, agents, decisions |
| GR-07 | Bounded retries, revisions, recursion |
| GR-08 | Label simulated output |

**Say**

> “These are the eight rules. They are not advisory prompts; each one has a deterministic enforcement point and a test.
>
> GR-01 is the approval gate. GR-02 is grounding. GR-03 is untrusted input. GR-04 covers redaction and the external-provider gate. GR-05 is least privilege: no action tools, and agents receive only sliced state. GR-06 is the audit trail. GR-07 bounds autonomy. GR-08 keeps mock output honest.
>
> The course asked for five. Eight let us cover the example concerns one-for-one: personal information, false information, checking AI output, human approval, and records.”

**Cue:** point to the rule-to-risk-to-test table in the docs if asked.

---

## Slide 10 — NIST AI RMF (6:55–7:15)

**On screen:** four columns.

- **GOVERN:** owners, policies, third-party gate
- **MAP:** purpose, limits, nine risks
- **MEASURE:** tests, audit, groundedness, citation coverage, time
- **MANAGE:** block/escalate, limits, incident procedure, residual risk

**Say**

> “The worksheet is organized by the four NIST functions. GOVERN defines ownership and the external-provider gate. MAP states intended use, exclusions, and the risk register. MEASURE uses the audit trail and metrics, without inventing benchmark numbers. MANAGE defines response, escalation, recovery, and residual risk.
>
> The honest gaps are recorded: real-provider behavior is unverified, regex detection is incomplete, and the prototype is single-user.”

**Cue:** do not claim NIST certification. This is a course worksheet.

---

## Slide 11 — Human approval deep dive (7:15–8:00)

**On screen:** approval flow.

```text
draft v1 + SHA-256
      ↓
human reads draft, claims, evidence, findings
      ↓
decision persisted in SQLite (actor = human:*)
      ↓
graph resume → re-read approval → re-check hash
      ↓
finalize → export re-check → approved Markdown/TXT
```

**Say**

> “This is the control the whole project is built around. An approval binds to a task, a version id, and a SHA-256 content hash. A new version invalidates the old approval.
>
> Only code paths with an actor beginning `human:` may write a decision. Agents never call the approval function. Finalize and export both re-verify the current version, the stored content, and the approval record.
>
> If someone edits the stored content after approval, finalize and export refuse it. This is integrity detection, not a cryptographic signature; a local administrator could still rewrite the database. We disclose that limitation rather than hide it.”

**Cue:** this is the best place to mention “automation bias” — the UI shows evidence and findings, not just an Approve button.

---

## Slide 12 — Live demo (8:00–12:00)

**Before the talk**

1. Start the app in mock mode:
   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
   ```
2. Confirm the amber **SIMULATED OUTPUT** banner is visible on Dashboard, Workflow, or Review.
3. Have `sample_data/project_notes.txt` and `sample_data/injection_notes.txt` ready.
4. Optionally pre-run one completed task as a backup.

### Demo path (4 minutes)

| Time | Action | What to point out |
|---:|---|---|
| 0:00 | New Task → request “Please prepare a meeting report from these notes.” → upload `project_notes.txt` → Run | Planner-first flow, acknowledgement, local mock mode, “What happens next” |
| 0:35 | Workflow → Agent hierarchy | Four levels: orchestrator, leads, workers, policy/reviewer; agent progress uses blue/teal |
| 0:55 | Workflow → Routing log | Every destination and reason; whitelist |
| 1:10 | Workflow → Task details and audit | Plan type, policy PASS, review PASS, claims/evidence counts, executions |
| 1:35 | Review | Version, hash, simulated warning, read-only draft, claim statuses, policy findings |
| 2:10 | Approve and finalize (reviewer “Demo Reviewer”) | Version-named button, acknowledgement, hash-bound decision, finalize |
| 2:30 | History → Markdown export | Status filter, export metadata: version, hash, reviewer, simulated |
| 3:00 | Optional: new task with `injection_notes.txt` | Injection ignored as instruction; clean content still present; no attacker action |
| 3:40 | Return to Workflow → Task details and audit | Human decision + finalization events |

**Say while it runs**

> “Notice the dark sidebar and the page header: status badges pair an icon with text, and the amber SIMULATED banner stays visible. The Workflow page shows the hierarchy and routing log side by side, so you can see which team acted and why.
>
> The Review page shows the exact version and hash. If I changed the draft and created a new version, that hash-bound approval would become stale. The approval button names the version, and I must acknowledge the version and hash before it will submit.
>
> Technical detail is still available under collapsed sections. The interface is quiet by default, but the governance evidence is one click away.
>
> The export is not just a download button. It re-checks the approval record before producing the file.”

**If the UI is slow:** narrate the audit trail while waiting. Do not click ahead or claim a result that has not appeared.

---

## Slide 13 — Test evidence (12:00–13:30)

**On screen:** test breakdown.

| Level | Tests |
|---|---:|
| Unit / integration | 76 |
| End-to-end scenarios TC-01–TC-13 | 13 |
| Streamlit UI flows (approval, rejection, revision) | 3 |
| **Total** | **92 passed** |

**Say**

> “The recorded run is 92 passed, zero failed, in about 10 seconds. The suite uses the real compiled LangGraph, real SQLite, real approval logic, and a real LangChain chat-model subclass for deterministic mock output. It is not a stub pipeline.
>
> The tests prove the happy path, rejection, new-version invalidation, tamper detection, injection handling, missing input, mixed unreadable files, bounded escalation, audit redaction, selective routing, and a real approval through Streamlit’s test harness.
>
> What they do not prove: live provider quality or latency, browser CSS/accessibility, OCR, multi-user concurrency, or disk-failure recovery. Those are listed as not tested, not hand-waved.”

**Cue:** if pressed on “92 tests” ask them to run the command; show `docs/testing.md`.

---

## Slide 14 — Risks and limitations (13:30–14:30)

**On screen:** four honest limitations.

1. Real mode implemented, **not executed** (real mode not enabled; no live call authorized).
2. Local SQLite is trusted; hash is integrity, not a signature.
3. Regex detection and redaction are best-effort.
4. Single user, no auth, no OCR, no external actions.

**Say**

> “The limitations are part of the design story.
>
> Real-provider mode is implemented for OpenRouter, Gemini, and OpenAI, but I did not make a live call, so I do not claim it is verified.
>
> The local database is trusted. Hash binding catches stale or altered content, but a local administrator who rewrites content, hash, and review rows can forge history. A production system needs authentication, signatures, and an external approval service.
>
> Prompt-injection and PII detection are regex-based, so they are incomplete. The empty tool allowlist and the human gate are the backstops.
>
> The prototype is single-user, has no OCR, and never performs an external action.”

**Cue:** confidence comes from naming limits, not hiding them.

---

## Slide 15 — Conclusion (14:30–15:00)

**On screen**

> **Generation is probabilistic. Authority is not.**
>
> Planner → Orchestrator → 3 executors → Reviewer → Human → Output  
> 92 automated tests · 8 governance rules · 9 risks · 6 skills · human approval bound to the exact version and hash

**Say**

> “AegisFlow shows that a multi-agent system can be useful without being unaccountable. The hierarchy does the work, deterministic controls bound the autonomy, and the human keeps the final authority.
>
> The prototype is complete for the course scope: it runs, it is tested, it is documented, and it is honest about what was not verified. Thank you. I’m happy to take questions.”

---

## Slide 16 — Q&A / defense backup

**On screen:** four short answers.

| Likely question | Short answer |
|---|---|
| “Is this really LangGraph?” | Root `StateGraph`, three team subgraphs, `interrupt()`/`Command(resume=...)`, SQLite checkpointer, whitelist routing |
| “How do you stop prompt injection?” | Delimit, scan, no tools, policy check, human gate; documented as defense-in-depth |
| “Why not always run all agents?” | Plan-driven routing reduces cost/latency/failure surface; TC-13 proves selective execution |
| “What is not done?” | Live provider run, browser-level UI test, OCR, auth/multi-user, backup/restore |

**Say only if asked.** Do not read this slide unprompted.

---

## 10. Demo fallback plan

If the app or environment fails:

1. **Say it plainly:** “The live app is not cooperating, so I’ll use the recorded evidence and walk through the same flow.”
2. Show the saved screenshots or the completed task in History if the server is still usable.
3. Show `docs/testing.md` and the passing test command output.
4. Walk the architecture diagram and the approval sequence.
5. Offer to run the demo after the session.

Do **not** simulate a live click or claim a result you did not see. A transparent fallback is stronger than a fabricated demo.

---

## 11. Q&A preparation (outside the 15 minutes)

### Architecture

**Q: Why team leads if the Orchestrator already routes?**  
A: The Orchestrator controls cross-team flow. Leads enforce intra-team prerequisites, ordering, retries, and completion. They are deterministic, so they add hierarchy without model cost or permission ambiguity.

**Q: Why not let an LLM orchestrator decide?**  
A: Routing is the permission boundary. A deterministic whitelist is testable, auditable, and cannot be talked around by document text. An LLM could be added only for ambiguity resolution with whitelist validation, but it is not needed for this scope.

**Q: What was the hardest bug?**  
A: LangGraph subgraph state reducers. Passing parent append-only state into a subgraph duplicated `agent_results`, `routing_log`, and errors. The fix is a wrapper that slices input and returns only team output keys. It is documented in `docs/architecture.md`.

### Governance

**Q: Is the hash a digital signature?**  
A: No. It detects stale or altered content. It does not establish identity or non-repudiation. A local administrator can rewrite the database. We state this in the risk register and approval threat model.

**Q: How do you prevent an agent from approving?**  
A: `record_decision` rejects any actor that does not start with `human:`. The graph also re-reads the persisted review instead of trusting the resume payload. Agents never import the approval module.

**Q: What about automation bias?**  
A: The review page shows the draft, claims, evidence, policy findings, reviewer reasons, and decision history. Approval requires an explicit acknowledgement of the version and hash. This reduces, but does not eliminate, rubber-stamping. A user study is future work.

### Testing and claims

**Q: Did you test real GPT/Gemini?**  
A: No. Real mode was not enabled and no live provider call was authorized in this build. The adapters are implemented, but real mode is unverified. That is why every document labels it that way.

**Q: Can I see the test result?**  
A: Yes:
```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -q
```
The recorded result is 92 passed.

**Q: Is the mock output meaningful?**  
A: It is deterministic scripted output for testing orchestration, not a claim of analysis quality. The UI says SIMULATED on every page and every export.

### Product

**Q: Why no PDF/DOCX export?**  
A: Markdown and TXT are the required formats and are fully verified. PDF/DOCX export is a stretch goal and was not implemented, rather than half-implemented.

**Q: Why SQLite?**  
A: Zero infrastructure, inspectable, reproducible, and adequate for a single-user prototype. It is not suitable for concurrent or multi-user deployment.

**Q: What would you build next?**  
A: Real-provider verification with recorded latency/error data, a browser-level UI test, authentication and signed approvals, backup/restore, OCR, and a larger adversarial injection corpus.

---

## 12. Final delivery checklist

- [ ] Server running in mock mode; SIMULATED banner visible
- [ ] `sample_data/project_notes.txt` ready
- [ ] `sample_data/injection_notes.txt` ready
- [ ] One completed backup task exists, or screenshots are available
- [ ] Deck opens in a browser and arrow keys work
- [ ] Test command and recorded result are easy to show
- [ ] Real-mode caveat is stated before any question about providers
- [ ] Timer visible; demo capped at 4 minutes
- [ ] No secret values, `.env` contents, or raw API keys on screen

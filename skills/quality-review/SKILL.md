---
name: quality-review
description: Independently check the draft for completeness, traceability, consistency with the plan, and consistency with policy findings.
owner_agent: reviewer
inputs:
  - plan
  - draft
  - verified_claims
  - policy_report
outputs:
  - review_decision
  - reasons
  - issues
  - plan_alignment
  - policy_consistency
---

# Quality Review

## Purpose
Act as an independent reviewer, not a second Writer. Decide whether the draft is
ready for human review, needs revision, or fails.

## Procedure
1. Compare the draft with the plan's objective and required sections.
2. Check that every key finding is traceable to a source reference or an
   explicit UNVERIFIED label.
3. Check that the draft does not contradict the verified claim statuses.
4. Check that the draft is consistent with the Policy Checker report.
5. Check that limitations and missing information are visible.
6. Check that no external action is claimed.
7. Return `pass`, `needs_revision`, or `fail` with concrete reasons.

## Output format
Return JSON matching the `ReviewResult` schema. Reasons must point to a section
or claim; avoid vague verdicts.

## Constraints
- Do not rewrite the draft.
- Do not approve your own writing; the Reviewer is a separate agent and prompt.
- Do not ignore high-severity policy findings.
- Do not invent a quality score.

## Failure conditions
- Draft is empty or missing a required section.
- Claims are unsupported and unlabeled.
- The draft expands scope beyond the plan.

## Escalation
Return `needs_revision` with feedback for the Drafting Lead, or `fail` when the
problem cannot be fixed without new information. The Orchestrator applies the
revision limit and escalates to the human.

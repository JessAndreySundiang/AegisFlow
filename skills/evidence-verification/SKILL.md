---
name: evidence-verification
description: Check each extracted claim against its source passage and label it supported, unsupported, conflicting, or unverified.
owner_agent: evidence_verifier
inputs:
  - claims
  - source_passages
outputs:
  - verified_claims
  - notes
  - uncertainty
---

# Evidence Verification

## Purpose
Prevent unsupported statements from reaching the draft. Verification uses only
the supplied source passages. Model memory is not evidence.

## Procedure
1. For each claim, locate the cited file and location.
2. Compare the claim with the exact passage.
3. Mark `supported` only when the passage entails the claim.
4. Mark `conflicting` when documents disagree or the passage contradicts the claim.
5. Mark `unsupported` when the passage does not support the claim.
6. Mark `unverified` when the passage is missing or unreadable.
7. Add a short rationale quoting or pointing to the passage.

## Output format
Return JSON matching the `VerificationResult` schema.

## Constraints
- Do not verify from memory.
- Do not use external search unless a search tool is explicitly configured and enabled.
- Do not silently repair a claim; report the status.
- Never claim a search happened when it did not.

## Failure conditions
- No source passage for a claim.
- Citation points to a nonexistent file or location.
- Claims conflict and cannot be reconciled.

## Escalation
Return the unresolved claims with `unverified` or `conflicting`; the Assurance
Lead and human reviewer will see them.

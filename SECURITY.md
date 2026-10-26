# Security policy

AegisFlow is a local, single-user research prototype. It is not a hosted
service and has no authentication by design; do not expose it to untrusted
networks.

## Supported versions

| Version | Supported |
|---|---|
| 0.6.x (current `main`) | Yes |
| Older commits | No |

## Reporting a vulnerability

Email **sundiang.jessandrey@student.auf.edu.ph** with:

- the affected file or screen and the version/commit,
- reproduction steps and the observed result,
- the impact you believe it has.

Please do not open a public issue for a suspected vulnerability before it is
acknowledged. Expect an initial reply within seven days.

## In scope

- Approval bypass, stale/duplicate approval acceptance, or export without a
  valid hash-bound approval.
- Prompt-injection content reaching the final draft or exports.
- Secret or PII leakage into logs, the audit trail, the UI, or exported files.
- Path traversal or unsafe file handling in upload/extraction.
- Deletion of approved or completed tasks.

## Not in scope (documented limitations)

- A local administrator editing `data/*.sqlite` or checkpoints. Hash binding is
  an integrity check, not a cryptographic signature.
- Missing authentication and multi-user isolation, which are explicit non-goals
  for v1.
- Real-provider output quality; mock mode is simulated output and is labelled as
  such.
- Best-effort regex detection of novel PII or injection patterns.

## Secret hygiene

Credentials live only in a local `.env` file that is git-ignored. If you believe
a key was committed, rotate it at the provider and report it here.

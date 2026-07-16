# Acceptable Use Policy

**Visibility:** Customer under NDA
**Document type:** Business draft — **mandatory legal review before any external or platform-facing
use.**
**Status:** First draft, internal only.
**Owner:** Governance/compliance owner (name to be assigned)
**Review cadence:** Before external distribution; whenever the destination platform's policies
change; whenever autonomy tiers or gate behavior change.

## Purpose

State what this platform is permitted and not permitted to be used for, consistent with the actual
technical controls that exist.

## Intended Audience

Operators, internal staff, and — once legally reviewed — any external party granted access.

## Scope

Covers use of the content-generation and publishing pipeline and its outputs. Does not cover use of
any downstream platform's own acceptable-use terms, which apply independently.

## Permitted Use

- Operating the pipeline through its defined stages (recommendation, candidate selection, gated live
  generation, quality review, and — once explicitly authorized — gated publishing).
- Using generated content for the managed persona's intended purpose within the destination
  platform's own content and synthetic-media policies.

## Prohibited Use

- Bypassing or attempting to bypass the reconciliation gate, approval binding checks, the
  dry-run default, or the publish freeze.
- Manually editing artifact files to simulate an approval or reconciliation decision that did not
  actually occur through the defined pipeline.
- Treating a reconciliation decision as if it authorized live generation or publishing — by design,
  it authorizes handoff preparation only, and no other authority.
- Using the platform to generate or publish content that misrepresents the managed persona as a
  real, identifiable individual without appropriate disclosure — noting that this platform's own
  documentation currently has an open, unresolved question about whether its identity reference
  material depicts a real person (see the Data Privacy document and the dedicated identity/likeness
  rights record, both Legal-draft or Legal-review visibility); this question must be resolved before
  any public claim about the persona's nature is made.
- Using the platform outside its currently authorized autonomy tier — e.g., attempting a live
  provider call without a valid approval, or a publish action while the freeze is active.

## Responsibilities

- **Operators:** follow the Operator Runbook (Internal visibility) exactly; do not manually
  construct or edit artifacts to work around a fail-closed gate.
- **Governance/compliance owner:** maintains this policy; escalates any observed attempt to
  circumvent a control as a governance incident.

## Controls

Enforcement is primarily technical: the gates described in the System Architecture document
(Customer-under-NDA visibility) reject prohibited actions at the code level. This policy documents
intended use boundaries; it does not add new technical enforcement by itself.

## Procedures

Any suspected violation is treated as an incident per the Incident Response plan (Internal
visibility), not resolved informally.

## Audit Evidence

Enforcement mechanisms cited here were verified against `origin/main` at commit `94da3c3d`.

## Exceptions

- This policy does not restate or supersede any destination platform's own acceptable-use or
  synthetic-media disclosure policy.
- No specific prohibited-content taxonomy is included in this draft.

## Version and Review Cadence

- **Version:** 0.3 — removed a specific historical rejection precedent and an identity-resolution
  mechanism name that were only supported by uncommitted local-workspace content.

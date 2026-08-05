# Lena Autonomous Content-Generation Platform — Commercial Documentation Suite

**Status:** First-draft business documentation. Not legally reviewed. Not yet approved for external
distribution. Every factual claim in this suite was verified directly against `origin/main` at
commit `94da3c3d` (2026-07-16) — nothing rests on uncommitted or local-only workspace content.

This directory contains first drafts of the commercial, governance, and operational documentation
for the Lena autonomous content-operations platform. The product is a **governed autonomous
content-operations platform for AI-powered digital creators and brands** — not a prompt generator,
image generator, social bot, or publishing bot; those are components it orchestrates, not the
product itself.

## Document Inventory

| # | Document | Visibility | Intended Audience | Owner | Review Cadence |
|---|---|---|---|---|---|
| 1 | [Commercial Product Overview](01_commercial_product_overview.md) | Public | Prospects, sales, partners | Product/commercial owner | Quarterly / on architecture change |
| 2 | [System Architecture and Authority Model](02_system_architecture_and_authority_model.md) | Customer under NDA | Technical buyers, integrators | Engineering lead | On every merge touching cited files |
| 3 | [AI Governance and Human Oversight Policy](03_ai_governance_and_human_oversight_policy.md) | Public | Buyers, regulators, trust & safety | Governance/compliance owner | On autonomy/freeze change |
| 4 | [Security Whitepaper](04_security_whitepaper.md) | Security-review confidential | Security reviewers, procurement | Security lead | Annually / on control change |
| 5 | [Data Privacy and Processing Overview](05_data_privacy_and_processing_overview.md) | Legal draft | Privacy officers, legal, users | Legal/privacy owner | Before external use / on new data flow |
| 6 | [Acceptable Use Policy](06_acceptable_use_policy.md) | Customer under NDA | End users, operators, partners | Governance/compliance owner | Before external use |
| 7 | [Service Description and Support Policy](07_service_description_and_support_policy.md) | Customer under NDA | Customers, support staff | Commercial/product owner | Before commercial launch |
| 8 | [Operator Runbook](08_operator_runbook.md) | Internal | Internal operators | Engineering lead / operator | Monthly / on script change |
| 9 | [Autonomy Levels and Promotion Criteria](09_autonomy_levels_and_promotion_criteria.md) | Internal | Engineering, governance reviewers | Engineering lead | On ladder policy change |
| 10 | [Artifact, Approval, and Audit-Provenance Specification](10_artifact_approval_and_audit_provenance_specification.md) | Internal | Engineers, auditors | Engineering lead / audit owner | On schema change |
| 11 | [Incident Response and Emergency Kill-Switch Plan](11_incident_response_and_emergency_kill_switch_plan.md) | Internal | Operators, on-call, incident commander | Incident commander | After any incident / quarterly |
| 12 | [Customer Implementation and Onboarding Guide](12_customer_implementation_and_onboarding_guide.md) | Customer under NDA | New customers, implementation engineers | Implementation engineering lead | On multi-tenant work start |
| — | [Lena Identity, Likeness, and Reference Media Rights Record](lena_identity_likeness_and_reference_media_rights_record.md) | **Legal draft — commercialization blocker** | Legal counsel only | Approving legal reviewer (unassigned) | Blocking until resolved |
| — | [Future Windows Operator Console — cmux-Inspired Requirements](backlog_future_windows_operator_console.md) | Internal | Internal engineering | Engineering lead | On prioritization only |

## Reading Paths

- **New commercial prospect (Public only):** 1 → 3
- **Security/procurement reviewer:** 4 → 5 → 10 → 3
- **New operator:** 9 → 8 → 11 → 10
- **Integration engineer (under NDA):** 2 → 12 → 10
- **Legal reviewer:** the identity/likeness record → 5 → 3 → 6
- **Internal engineering onboarding:** 2 → 9 → 8 → 10

## Grounding and Evidence Policy

Every control, procedure, and claim in these documents is grounded in one of:
1. Code in `origin/main` (file path cited inline where the document's visibility level allows),
2. A JSON policy/state artifact in `origin/main`, or
3. A test file that exercises the claimed behavior.

Where a claim cannot currently be substantiated by repository evidence, the document says so
explicitly rather than asserting it. **Documents classified `Public` do not cite internal file
paths, exact failure codes, operational tool names, or historical operational detail** — that
material is reserved for `Customer under NDA`, `Internal`, or `Security-review confidential`
documents.

## Commercial-Claim Discipline

This suite does not claim, anywhere: SOC 2 or ISO certification; GDPR/CCPA compliance; completed
penetration testing; guaranteed uptime; production readiness; customer adoption; a provider
partnership; unrestricted commercial rights; legal ownership of all generated outputs; or fully
autonomous publishing. Where a capability is not yet delivered, the documents use language such as
"designed to," "currently implemented," "planned," "subject to legal review," or "not yet enabled."

## What Changed From the Prior Draft of This Suite

A prior draft of this suite was found, during the fact-check pass that produced this version, to
have been grounded in part on **uncommitted, quarantined local-workspace content** that does not
exist anywhere in the shared `origin/main` repository — specifically a `pipeline/agents/lena/`
slice-documentation folder, a two-phase caption/live-publish approval schema, a real-publish
precedent with platform-reported identifiers, an identity-resolution mechanism referred to as "Rule
Zero," a clean-export re-verification chain, and a numeric autonomy-readiness score. All such content
has been removed from this version. Every remaining factual claim was independently re-verified
against `origin/main` at commit `94da3c3d`.

## Outstanding Before External Use

- The identity/likeness question in [the dedicated rights record](lena_identity_likeness_and_reference_media_rights_record.md)
  is a **commercialization blocker** until resolved.
- Legal review is required on every document marked `Legal draft` before any external or regulatory
  use, and on every `Public` or `Customer under NDA` document before it leaves internal use.
- A dedicated security review (dependency audit, secret scanning, infrastructure review) has not been
  performed; see the Security Whitepaper's Exceptions section.
- An internal repository documentation inconsistency (which generation provider is canonical) is
  flagged in the Security Whitepaper and System Architecture documents and should be resolved by
  engineering.

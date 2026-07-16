# Customer Implementation and Onboarding Guide

**Visibility:** Customer under NDA
**Document type:** Internal technical draft. No legal review required.
**Status:** First draft, internal only. Describes onboarding a **second creator persona into the
current single-tenant codebase**, not a self-service commercial onboarding flow — that flow does not
exist yet.
**Owner:** Implementation engineering lead (name to be assigned)
**Review cadence:** Revisit fully once multi-tenant architecture work begins.

## Purpose

Describe, honestly, what "onboarding a new customer" means today (standing up a second creator
namespace by hand inside the existing repository) versus what a true multi-tenant onboarding flow
would require to build.

## Intended Audience

New customers' technical stakeholders (once a real multi-tenant product exists), and internal
implementation engineers today.

## Scope

Covers the per-creator namespace pattern the codebase already uses, what would need to be duplicated
to add a second persona, and what would need to be built for real multi-tenant isolation. Does not
cover pricing/commercial terms.

## Current Reality: Single-Tenant, Per-Creator-Namespace Codebase

The codebase already separates creator-specific policy, identity, and pipeline state into
creator-named paths — for example:
- `pipeline/identity/lena_identity.py`, `pipeline/identity/lena_visual_reference_authority_v1.json`
  — Lena's identity/continuity rules and reference authority.
- `pipeline/influencer_nodes/lena/autonomy_ladder_v1.json` — Lena's autonomy policy.
- `pipeline/prompt_banks/lena/` — Lena's wardrobe catalog and scene bank.
- `tools/lena_creative_director_v1_2_8.py`, `tools/lena_influencer_node_v1_3.py` — Lena's strategy/
  content-pillar logic.

This is a reasonable **foundation** for a multi-tenant architecture — the naming convention already
assumes a creator identifier prefixes policy and state — but it is not itself tenant isolation. There
is no code today that prevents one creator's pipeline run from reading another's policy file, no
account/permission model, and no shared infrastructure (queue, publish freeze, autonomy ladder) that
is partitioned per tenant. The publish freeze, for instance, is a single global flag today, not a
per-creator flag.

## What Onboarding a Second Persona Requires Today (Manual)

1. Duplicate the creator-named path pattern above under a new creator identifier.
2. Build or adapt an identity reference authority file for the new persona, resolving the
   identity/likeness question described in
   [Data Privacy and Processing Overview](05_data_privacy_and_processing_overview.md) for that
   specific persona's reference material.
3. Build a wardrobe/scene/prompt catalog for the new persona — this is a substantial content-design
   effort, not a configuration toggle (the Lena catalog itself required multiple rounds of live-proof
   testing and catalog rejection before reaching its current state; expect the same for any new
   persona).
4. Stand up a new autonomy ladder policy file for the persona, defaulting to the same fail-closed,
   frozen-publish posture as Lena's.
5. Confirm no shared global state (the publish freeze flag, any shared queue or credential) is
   accidentally shared between personas before running any live generation for the new persona.

## What Real Multi-Tenant Onboarding Would Require to Build (Not Yet Started)

- A tenant/account model with its own permissions and credential scoping.
- Per-tenant publish-freeze and autonomy-ladder state, not a single global flag.
- Isolation guarantees (a defect or incident in one tenant's pipeline must not be able to affect
  another tenant's approvals, queues, or publish state).
- A self-service or supported onboarding flow, rather than the manual duplication process above.

## Responsibilities

- **Implementation engineer:** follows the manual process above for any second persona today; flags
  any point where tenant isolation is assumed but not actually enforced.
- **Product/engineering leadership:** owns the decision to invest in the real multi-tenant
  architecture, informed by how much manual-onboarding pain the single-tenant pattern causes in
  practice.

## Controls

None specific to multi-tenancy exist today — see "What Real Multi-Tenant Onboarding Would Require"
above for the gap list.

## Procedures

See "What Onboarding a Second Persona Requires Today" above.

## Audit Evidence

- The Lena-specific path pattern across `pipeline/identity/`, `pipeline/influencer_nodes/lena/`,
  `pipeline/prompt_banks/lena/` — all confirmed present in `origin/main` at commit `94da3c3d`.
- `pipeline/change_notes/lena_niche_reset_20260621.md` — real evidence of how much content-design
  iteration a single persona's catalog required, as a scoping input for estimating a second
  persona's onboarding effort.

## Exceptions

- This document does not describe a working multi-tenant product. Any customer-facing onboarding
  material must wait until the "What Real Multi-Tenant Onboarding Would Require" gap list is
  substantially closed.

## Version and Review Cadence

- **Version:** 0.3 — removed a reference to a `pipeline/agents/lena/` slice-documentation folder that
  does not exist in `origin/main`; all remaining path citations reconfirmed present.

# Incident Response and Emergency Kill-Switch Plan

**Visibility:** Internal
**Document type:** Business/operational draft — requires review by qualified counsel for any
customer-notification obligations before external use.
**Status:** First draft, internal only.
**Owner:** Incident commander / accountable operator (names to be assigned)
**Review cadence:** After any incident; otherwise quarterly.

## Purpose

Name the real kill switches that exist today, at what layer each operates, and the response
procedure when a control is suspected to have failed.

## Intended Audience

Operators, on-call, incident commander.

## Scope

Covers halting generation and halting publishing. Does not cover the day-to-day operator sequence
(Operator Runbook, Internal visibility). Every control below was independently verified against
`origin/main` at commit `94da3c3d`; controls from a prior draft that could not be so verified have
been removed rather than restated.

## Real Kill Switches, By Layer

| Layer | Kill switch | Effect | Confirmed present |
|---|---|---|---|
| Global publish authority | `publish_freeze.active: true` in `pipeline/influencer_nodes/lena/autonomy_ladder_v1.json` | Blocks the listed publish surfaces by default | Yes |
| Per-level autonomy | `enabled: false` on any ladder level | Disables an entire autonomy level (posting is disabled at Level 3 today) | Yes |
| Live provider execution | Absence of `--live` flag / absence of a valid approval artifact | Executor defaults to dry-run | Yes |
| Autonomy-tier enforcement at the call site | `autonomy_ladder.assert_allowed(...)` called directly inside a real, merged publish-preparation tool | Fails closed with a typed error if the requested tier is not enabled — confirmed by reading both the call site and the enforcement module | Yes |
| A specific legacy execution surface | Legacy OpenArt/Seedance routing scripts refuse to run without an explicit `--allow-legacy-openart-seedance` override flag | Prevents an old, superseded surface from being invoked accidentally | Yes, per `tools/LEGACY_PROVIDER_SURFACES.md` |

## Incident Response Procedure

1. **Identify the layer.** Use the table above to find the narrowest control that stops the specific
   behavior in question.
2. **Engage the kill switch at that layer.** If uncertain, escalate to the global publish freeze and
   the executor's dry-run default as the safe baseline, then narrow down.
3. **Preserve evidence before remediating.** Do not delete or overwrite an approval, reconciliation-
   decision, or QA artifact related to a suspected incident — copy it aside if it must be excluded
   from further processing.
4. **Quarantine, don't discard, suspect workspace state.** If uncommitted or unreviewed local changes
   are implicated, move them aside rather than deleting them — they may represent legitimate
   in-progress work.
5. **Root-cause before re-enabling.** Do not flip a disabled level or lift the publish freeze again
   until the specific failure mode is understood and, where it was a code defect, fixed and covered
   by a new or updated test.
6. **Record the incident and the exact scope of any freeze exception used**, if one is granted during
   remediation, as a one-action exception, not a policy change, and confirm the freeze is fully back
   in force for everything else immediately afterward.

## Responsibilities

- **Operator/on-call:** executes the narrowest available containment first; escalates to the
  accountable operator for anything touching the publish freeze.
- **Accountable operator:** sole authority to grant any publish-freeze exception during incident
  response, and to decide when a disabled autonomy level may be re-enabled.
- **Engineering:** ensures every kill switch named above remains independently testable.

## Controls

See the kill-switch table above. Every listed control is fail-closed by default, not fail-open.

## Procedures

See "Incident Response Procedure" above.

## Audit Evidence

`pipeline/influencer_nodes/lena/autonomy_ladder_v1.json`, `pipeline/influencer_nodes/lena/autonomy_ladder.py`,
`tools/LEGACY_PROVIDER_SURFACES.md` — all confirmed present in `origin/main` at commit `94da3c3d`.

## Exceptions

- No formal severity classification or notification-obligation matrix exists yet; if this platform
  ever processes real personal data (see the open identity/likeness question in the Data Privacy
  document, Legal-draft visibility), a breach-notification procedure must be added with counsel
  input.
- No historical incident, workspace-quarantine event, or content-rejection precedent is asserted in
  this document — a prior draft referenced such events sourced from uncommitted local-workspace
  content that could not be confirmed against `origin/main`, and they have been removed.

## Version and Review Cadence

- **Version:** 0.3 — removed all kill-switch claims that referenced environment variables or
  historical events not found anywhere in `origin/main`; kept only controls independently verified
  by direct source inspection.

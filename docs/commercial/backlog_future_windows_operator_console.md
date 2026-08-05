# Future Windows Operator Console — cmux-Inspired Requirements

**Visibility:** Internal
**Owner:** Engineering lead (name to be assigned)
**Review cadence:** Revisit only when Windows-native internal operator tooling is actually
prioritized; not on any fixed schedule until then.

**Status: planned internal tooling — not implemented, not scheduled, not part of the commercial
product.** This is a backlog note, not a design document, not a commitment, and not functionality
that belongs inside anything delivered to a customer.

## Why this note exists

`manaflow-ai/cmux` was evaluated (read-only) as a possible cockpit for coordinating Codex, Claude
Code, Git worktrees, PR review, CI, and documentation work on the Lena platform. Decision: **rejected
for adoption now.** No Mac will be purchased or repurposed for it, it will not be integrated or
forked, and its Windows roadmap will not be tracked further — the one Windows attempt in its
ecosystem is an unmerged, self-described "unofficial community build" built on a different stack
(Electron) than the real app (native Swift/AppKit on `libghostty`), with no maintainer commitment to
ship it. The tool itself is out of scope. Its **workflow concepts** are worth keeping for whenever a
Windows-native internal operator console is actually built.

## What this is not

- Not a design for Lena's commercial product. Nothing here is customer-facing.
- Not the "operator console" already referenced in
  [Customer Implementation and Onboarding Guide](12_customer_implementation_and_onboarding_guide.md)
  as future multi-tenant product work — that is a different, later, product-facing concern. This
  note is about **internal developer/operator tooling** for coordinating agents and worktrees on
  this machine, not about anything shipped to a customer.
- Not scheduled. No priority, owner, or timeline is assigned by this note.

## Reusable concepts, retained for later

If a Windows-native internal operator console is ever built, these are the concepts worth
carrying forward from the cmux evaluation:

1. **One visible workspace per agent and Git worktree** — a 1:1 visual mapping so it's always
   obvious which agent is working in which worktree.
2. **Branch, commit, PR, and check state shown beside each workspace** — surfaced inline, not
   requiring a separate `gh` lookup per worktree.
3. **Attention notifications when an agent needs input** — distinct from generic OS notifications;
   should carry actual context, not just "an agent is waiting."
4. **Lane ownership and conflict warnings** — visible signal when two agents/worktrees are about to
   touch the same files, matching the "do not overlap with these files" convention already used
   informally between Codex and Claude sessions on this project.
5. **Consolidated pending-action view** — one place to see every open approval, PR, or decision
   waiting on the human operator, across all active lanes.
6. **Scriptable workspace creation** — a CLI/API to spin up a new worktree+agent pairing without
   manual setup, for repeatable lane creation.
7. **Session restoration** — reopening the console restores workspace layout and context rather
   than starting cold.
8. **Explicit distinction between developer-agent status and Lena runtime authority** — this is the
   most important concept to carry forward, and the one cmux itself does not need to model: a
   console showing "Claude is running in worktree X" must never be visually or structurally confused
   with "generation is approved" or "publishing is authorized." Those remain governed by the
   artifacts and gates described in
   [System Architecture and Authority Model](02_system_architecture_and_authority_model.md), not by
   anything the console displays. An operator console is an observability layer over agent/worktree
   activity — it must never become a second, informal authority surface.
9. **No authenticated-browser or secret sharing across workspaces by default** — each
   workspace/lane's credentials and authenticated sessions stay scoped to that workspace unless
   explicitly and narrowly shared.
10. **Audit history of assignments, decisions, and resulting commits** — a durable record of which
    agent was assigned which lane, what it decided, and what commit resulted, independent of and
    complementary to the artifact-level audit trail in
    [Artifact, Approval, and Audit-Provenance Specification](10_artifact_approval_and_audit_provenance_specification.md).

## Explicit non-decisions

- No implementation work is authorized by this note.
- No platform, language, or framework choice is made here.
- No relationship to the commercial multi-tenant operator console (a separate, later, product-facing
  concern) is implied — if that product console is ever built, it may or may not reuse any of these
  concepts; that is a future decision, not this one.

## Version

- **Version:** 0.1 — created following the cmux evaluation and rejection decision, 2026-07-16.
- **Review cadence:** Revisit only when Windows-native internal operator tooling is actually
  prioritized; not on any fixed schedule until then.

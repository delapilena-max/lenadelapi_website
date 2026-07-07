# 90_content_packet

**Role:** Own the real publish-packet artifact built from an actual,
QA-passed Lena render -- the human-facing document an operator reviews and
approves before anything is queued or published.
**Status:** Sixth filesystem-native slice. Documentation/design only -- no
code exists yet.
**Real owners (authoritative code):** none. This slice currently has no code
owner -- see `CURRENT_STATE.md` for the one real precedent that exists as a
hand-built document, not a tool output.

## Who this agent is

This folder describes the *target* shape of a real content-packet builder --
a tool that takes a render that has already passed QA (`70_visual_qa/`) and
turns it into the operator-facing publish packet, the same kind of document
that was hand-built once for `2026-07-07-03-photo`
(`pipeline/publish_packets/lena/2026-07-07/
LENA_PUBLISH_PACKET_2026-07-07-03-photo.md`). It is downstream of
`70_visual_qa/` (needs a real QA verdict to exist first) and upstream of a
future `95_publish_gate/` (which needs a real packet artifact to gate --
see RULES.md).

## What it does (target scope, once built)

- Reads a real render's workorder metadata, the rendered image path, and its
  QA verdict (checklist + `production_scoring`, schema v2).
- Assembles a publish-packet Markdown document: image reference, QA summary,
  several caption options grounded in the actual scene, a soft CTA, an
  optional Story-poll idea, an optional pinned-comment idea, per-platform
  notes, and an explicit, unchecked operator approval checklist.
- Optionally assembles a queue-ready JSON in the shape `pipeline/
  posting_manager.py` already expects, but only as a draft an operator still
  has to approve -- never pre-approved.

## What it explicitly does not do

- **Does not generate images.** It only reads a render that already exists.
- **Does not call Kling**, does not touch the executor
  (`pipeline/kling_apilena_api_executor.py`) in any way.
- **Does not publish** and does not upload to R2.
- **Does not edit `.env`** and does not read/print credentials.
- **Does not approve posts.** It never sets `approved_for_live_publish: true`
  on any queue item it writes -- that flag is exclusively an operator
  decision, made outside this slice.
- **Does not replace `70_visual_qa/`.** It reads QA verdicts; it never scores
  or judges an image itself.
- **Does not replace a future `95_publish_gate/`.** This slice produces the
  packet; a separate, not-yet-built gate slice would be the place a formal
  approval decision gets recorded as its own artifact. This slice comes
  *before* that gate, not instead of it -- see RULES.md.
- **Does not perform QA itself** -- if a slot has no QA file, or the QA file's
  `overall` isn't `pass`, this slice has nothing safe to build a packet from.

## Files in this folder

- `AGENT.md` -- this file.
- `RULES.md` -- what this agent must never do, hard-fail conditions, and
  human-approval boundaries.
- `INPUTS.md` -- the exact real artifacts a packet builder should read.
- `OUTPUTS.md` -- the intended packet Markdown format, the optional queue-JSON
  shape, and an explicit statement that no builder code exists yet.
- `CURRENT_STATE.md` -- current status and the one real hand-built precedent.

## How a new Claude/Codex session should use this folder

1. Read this file first for orientation.
2. Read `RULES.md` before assuming a packet can be built for any given slot --
   check the QA-pass precondition first.
3. Read `CURRENT_STATE.md` to confirm no code exists yet -- do not assume a
   `lena_content_packet_builder.py`-style script is real just because this
   folder documents its target shape.
4. Read the one real precedent directly --
   `pipeline/publish_packets/lena/2026-07-07/
   LENA_PUBLISH_PACKET_2026-07-07-03-photo.md` -- before proposing any
   packet-builder code; it is the only ground truth for what a real packet
   looks like.
5. Do not propose or write packet-builder code without separate, explicit
   approval, per `RULES.md`'s human-approval list.

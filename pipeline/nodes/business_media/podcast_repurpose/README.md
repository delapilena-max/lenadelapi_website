# podcast_repurpose

**Node type:** Business media node (Revenue Lane) — first of its kind in `content_bot`.
**Status:** Docs only. No code, no clients, no pilot run yet.
**Full context:** `pipeline/change_notes/business_media_node_pivot_plan.md`.

## What this node does

Turns a business's existing raw media (podcast episodes, YouTube videos, Zoom/webinar
recordings, raw iPhone clips, testimonials) plus basic business context (product/
service info, website copy) into a month of short-form social content: clip ideas,
hooks, captions, titles, thumbnail/cover text, a posting calendar, CTA variants — all
bundled into one content packet, with an explicit approval packet before anything is
considered delivered.

## Why this node exists

`content_bot` was Lena-only until 2026-07-07. Lena is now framed as the R&D/demo/
stress-test node (generation frozen pending a Kling API question, not abandoned). This
node is the **first revenue-lane node**: a business-facing offer sellable this week,
independent of Lena's Kling blocker.

## External offer (one line)

> "I turn your existing videos, podcasts, calls, and business knowledge into a month of
> short-form social content."

## Files in this folder

- `README.md` — this file.
- `INPUTS.md` — what the node accepts.
- `OUTPUTS.md` — what the node produces.
- `WORKFLOW.md` — the MVP (manual, human-run) workflow.
- `OFFER.md` — the external sellable offer, proposed package, and pricing hypothesis.
- `PITCH_SCRIPT.md` — draft outbound messages for the first warm-outreach conversations.
- `CURRENT_STATE.md` — status and next actions.

## What this is NOT (yet)

- Not automated. Every step in `WORKFLOW.md` is run by hand for the MVP.
- Not a video-editing service — the deliverable is the plan (clip selection, hooks,
  captions, calendar), not cut footage, unless a later phase adds editing.
- Not built with the full Lena-style numbered agent-slice pattern
  (`40_identity_continuity/` .. `80_repair/`) — deliberately lightweight until real
  code and real failure modes exist to justify that structure.
- Not connected to Blotato or any posting automation — explicitly deferred.

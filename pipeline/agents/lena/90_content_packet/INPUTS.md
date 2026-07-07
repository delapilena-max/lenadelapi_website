# Inputs -- 90_content_packet

No code exists yet (see `CURRENT_STATE.md`). This documents what a real
packet-builder should read, grounded in the actual artifacts that existed
for the one real hand-built packet
(`pipeline/publish_packets/lena/2026-07-07/
LENA_PUBLISH_PACKET_2026-07-07-03-photo.md`), traced end to end against real
files on disk.

## Required inputs

| Input | Path | Role |
|---|---|---|
| Daily workorder | `pipeline/kling_workorders/<date>/<slot_id>.json` | Source of scene/wardrobe/environment/caption context: `caption`, `metadata.wardrobe_outfit_id`/`wardrobe_outfit_name`, `metadata.environment_id`/`environment_name`, `metadata.activity`, `metadata.pose`, `metadata.reference_binding_mode`. |
| Rendered image path | `slot.expected_assets.seed_image_path` or `.final_photo_path` inside the workorder | The actual image file the packet is built for. Existence-checked; the pixels themselves must have already been viewed and QA'd by a human/Claude -- this slice does not view or judge the image itself. |
| QA verdict (required, gating) | `pipeline/asset_review/lena/<date>/<slot_id>_qa.json` | Schema v2: `overall` (must be `"pass"` -- see RULES.md Rule zero), `checklist` (identity/face/skin/wardrobe/etc.), `production_scoring` (`hook_strength`, `styling_sexy_platform_safe`, both variety fields), `publish_ready`, `publish_ready_reason`, `reviewed_at_utc` (check against the render's own timestamp -- stale-QA-file risk). |

## Optional inputs

| Input | Path | Role |
|---|---|---|
| Kling result manifest | `pipeline/kling_debug/apilena_api/<date>/<slot_id>/result_manifest.json` | Provenance only -- the Kling task id, used the same way the real precedent cited `task 903349357289414713` in its §1 "Provenance" line. Not required for the packet to be useful, but strengthens traceability. |
| Prompt receipt | `pipeline/kling_debug/apilena_api/<date>/<slot_id>/prompt_receipt.json` | Not used in the one real precedent, but could inform packet notes if a reviewer wants to cite exactly what was submitted (compact prompt/negative-prompt survival). |

## What this folder does NOT read

- **No wardrobe/scene/prompt-construction source content** -- that's
  `pipeline/prompting/lena_prompt_brain.py`, owned by `50_prompt_builder/`.
  This slice reads the *outcome* (workorder metadata), not how it was
  decided.
- **No identity-resolution logic** -- that's `pipeline/identity/
  lena_identity.py`, owned by `40_identity_continuity/`.
- **No execution/submission logic** -- that's `pipeline/
  kling_apilena_api_executor.py`, owned by `60_executor/`. This slice never
  calls it and never reads its live credentials or submission internals
  beyond the already-written debug artifacts above.
- **Nothing from `tools/strategy/lena_build_content_packet_dryrun_v1.py`** --
  that tool's recipe/hook/wardrobe/environment catalogs and its own
  self-built prompt schema are a separate, disconnected, pre-render ideation
  system. See `AGENT.md` and `RULES.md` for why this slice never reads its
  output as an input.
- **No queue or publish-receipt files as an input** -- those are downstream
  *outputs* of this slice's packet (once a human approves and queues it),
  not something this slice reads to build the packet in the first place.

# Outputs -- 70_visual_qa

## What this ownership actually produces today

**`pipeline/qa/lena_photo_qa.py`:**
- Writes `pipeline/asset_review/lena/<date>/<slot_id>_qa.json` via
  `save_qa_template()` -- but **only if that path doesn't already exist**
  (`force=False` by default). It never silently overwrites a real, previously
  filled-in verdict.
- The written scaffold's shape: `schema_version`, `slot_id`, `date`,
  `media_type`, `wardrobe_outfit_id`, `environment_id`, `reviewed_by` (null until
  filled in), `reviewed_at_utc` (null until filled in), `checklist` (all 10 fields
  `unreviewed`), `overall` (`unreviewed`), `failure_reasons` (empty), and
  `created_at_utc`.
- `validate_qa_result(qa) -> (bool, List[str])` -- does not write anything; checks
  a filled-in result for internal consistency (the false-green guard, RULES.md).
  Returns errors as strings, does not raise.

**`tools/lena_review_proof_render_v1.py`:**
- Writes nothing except indirectly triggering the scaffold write above (only when
  no QA file exists yet).
- Prints a JSON review bundle to stdout per slot: `slot_id`, `date`,
  `slot_metadata`, `artifacts` (image/payload/receipt/manifest paths + existence
  booleans + `qa_result_path` + `qa_overall_status`), and
  `negative_prompt_budget`.

**Actual QA verdicts** (the real output that matters) are produced by a human or
Claude directly editing/writing
`pipeline/asset_review/lena/<date>/<slot_id>_qa.json` after viewing the real
rendered image -- not by any code in this ownership. The code's job is to scaffold
the file and assemble what's needed to fill it in correctly; the verdict itself is
never automated.

## Who consumes these outputs today

- QA verdict files under `pipeline/asset_review/lena/<date>/` are read back by
  `tools/lena_review_proof_render_v1.py` on the next invocation for that slot (to
  report `qa_overall_status`), and by whoever is deciding whether a render is
  usable -- currently a human/Claude reading the json directly, not a downstream
  automated consumer.
- **Correction (2026-07-10):** `tools/lena_review_proof_render_v1.py` is not
  the only consumer. `tools/lena_build_publish_packet_v1.py` also imports
  `pipeline.qa.lena_photo_qa` directly (`load_qa_result()`,
  `validate_qa_result()`) and is a real, working hard gate -- its
  `_resolve_qa()` ("Rule zero -- no QA pass, no packet",
  `90_content_packet/RULES.md`) refuses to build a publish packet, with zero
  file writes, unless a QA file exists, validates cleanly, and has
  `overall == "pass"`. It is Kling-shaped in its slot/image resolution
  (`pipeline/kling_workorders/`, `pipeline/kling_debug/apilena_api/`) --
  it does not yet resolve Higgsfield artifacts, but its QA-gating logic
  itself is provider-agnostic. `tools/lena_higgsfield_qa_bridge_v1.py`
  (2026-07-10) is the Higgsfield-side counterpart to
  `lena_review_proof_render_v1.py` -- it resolves a real Higgsfield
  `result_manifest.json` + saved image into the same QA scaffold/schema,
  but does not itself gate publish/queue; that wiring is a separate,
  not-yet-approved step.
- No repair/auto-fix step currently consumes QA verdicts programmatically. The
  original doctrine framing ("QA feeding a repair step") is aspirational, not
  built.

## Gap against the original doctrine target

- No automated vision-model judge exists. Every checklist field is filled in by a
  human or Claude looking at the image, not inferred by code. This is a documented
  gap, not a hidden capability -- do not claim automated QA exists.
- No CLI mechanism to force-replace a stale QA verdict (see RULES.md and
  AGENT.md) -- replacing one is currently a manual file write, not a flag on
  `tools/lena_review_proof_render_v1.py`.
- No cross-slot aggregation or trend report over multiple QA files exists yet
  (e.g. "N consecutive fails on this slot") -- each verdict json currently only
  tracks its own render (`consecutive_same_slot_wardrobe_misses` has been added by
  hand into individual QA jsons as a note field when relevant, not computed by
  code).

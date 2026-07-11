# Lena Agentic Pivot — Changelog

Append-only. Add a new dated entry per change batch; never rewrite or delete prior entries.

---

## 2026-07-05 — Batch 1: Containment (executor drift + preflight metadata-trust)

### Why
A read-only investigation traced the live photo executor call chain and found the real
executor (`pipeline/kling_apilena_api_executor.py`, verified via the actual `import` in
`pipeline/lena_production_job.py`) had drifted from the safety fixes documented in the
2026-07-03 handoff:
- a manual reference-image override (`KLING_LENA_ELEMENT_IMAGE_URLS_JSON` /
  `KLING_LENA_ELEMENT_IMAGE_URLS`) could silently outrank the live Kling element lookup,
  with no expiry or freshness check
- the submit payload sent `image_list` alongside `element_list`, violating the
  element_list-only photo contract
- `tools/lena_preflight.py` only checked self-reported metadata stamps on the queue item,
  never the actual submitted payload, so a contract-violating photo would still pass
- two docs (`tools/LEGACY_PROVIDER_SURFACES.md`,
  `pipeline/config/lena_live_path_manifest_v1.json`) named `pipeline/kling_ui_executor.py`
  as canonical, but that file has zero callers anywhere in the repo

### What changed
- `pipeline/kling_apilena_api_executor.py`
  - `_manual_live_image_urls()` now raises `RuntimeError` if either
    `KLING_LENA_ELEMENT_IMAGE_URLS_JSON` or `KLING_LENA_ELEMENT_IMAGE_URLS` is set,
    instead of returning those URLs for use. Live execution and the no-spend dry-run
    path both fail closed through this.
  - `_submit_photo()`'s payload no longer includes `image_list`. `element_list` only.
  - `payload_no_image_list` in the saved debug/result metadata flipped from a hardcoded
    `False` to `True` to match actual behavior.
- `tools/lena_preflight.py`
  - Added `APILENA_DEBUG_ROOT` and a payload-truth check for photo items: reads the
    executor's own saved `submit_payload.json` and hard-fails if `image_list` is
    non-empty, and hard-fails if `live_apilena_lookup_response.json` is missing
    alongside it (a proxy for "the live element lookup was bypassed"). If no
    `submit_payload.json` exists at all, preflight now warns that the metadata claims
    are unverified rather than silently trusting them.
- `tools/LEGACY_PROVIDER_SURFACES.md`
  - Corrected the canonical executor entry to `pipeline/kling_apilena_api_executor.py`.
  - Added a "Doc-only / uncalled surfaces" section flagging `kling_ui_executor.py`
    (untracked, no callers) and `kling_direct_executor.py` (absent from disk and git
    history entirely).
- `pipeline/config/lena_live_path_manifest_v1.json`
  - Corrected the `production_chain` entry to `pipeline/kling_apilena_api_executor.py`
    and bumped `last_curated_utc`.

### Explicitly not done in this batch
- No prompt tuning. Wardrobe-continuity/negative-prompt transport into the real
  executor's prompt builder is still outstanding (batch 3 in the containment plan).
- No broader agentic restructuring (Strategy/Creative Director/QA/Repair agents).
- `.env` was not touched. No live generation was run. Nothing was published or committed.
- `pipeline/kling_ui_executor.py` was flagged, not deleted.

---

## 2026-07-05 — Batch 2: Identity/source-of-truth hardening

### Why
Element-id cleaning and photo-identity resolution were independently duplicated in
three files (`pipeline/kling_apilena_api_executor.py`, `tools/lena_preflight.py`,
`pipeline/lena_production_job.py`), plus a fourth, unrelated implementation in the
uncalled `pipeline/kling_ui_executor.py`. Nothing forced these to agree with each
other, which is the structural reason stale/forbidden element ids were reachable at
all. This batch consolidates all of it into one owned module.

### What changed
- New: `pipeline/identity/__init__.py`, `pipeline/identity/lena_identity.py`
  - Single owner for: `clean_element_id()`, `resolve_expected_photo_element()` /
    `require_expected_photo_element()`, `expected_photo_element_name()`,
    `forbidden_photo_element_ids()`, `assert_no_manual_reference_override()`.
  - Also centralizes the allowed photo reference-mode contract as named constants:
    `ALLOWED_PHOTO_IDENTITY_BINDINGS`, `REQUIRED_REFERENCE_BINDING_MODE`,
    `REQUIRED_REFERENCE_SOURCE_POLICY`, `REQUIRED_REFERENCE_SOURCE_ELEMENT_ID_SOURCE`,
    `REQUIRED_SEED_SOURCE`.
- `pipeline/kling_apilena_api_executor.py`
  - Removed local `_clean_element_id()`; `LIVE_LENA_UI_ID`/`LIVE_LENA_NAME` and all
    call sites now derive from `lena_identity`.
  - `_manual_live_image_urls()` now delegates its fail-closed check to
    `lena_identity.assert_no_manual_reference_override()` instead of a local copy of
    the Batch 1 guard.
- `tools/lena_preflight.py`
  - Removed local `_clean_element_id()`, `_resolve_expected_photo_element()`,
    `_forbidden_photo_element_ids()`. All photo-identity checks and the allowed
    reference-mode literal sets/strings now reference `lena_identity` constants
    instead of inline duplicates.
- `pipeline/lena_production_job.py`
  - Removed local `_clean_element_id()`. `_kling_backend_name()` now delegates its
    fail-closed check to `lena_identity.require_expected_photo_element()`.
- `pipeline/kling_ui_executor.py`
  - Added a note above `_pick_live_lena_element()` marking its identity logic as
    superseded by `pipeline/identity/lena_identity.py`. Not deleted.

### Validation
- `python -m py_compile` clean on all six touched/added files.
- `python -c "import pipeline.kling_apilena_api_executor"` and
  `import pipeline.lena_production_job` both succeed with the new cross-module import.
- `python tools/lena_preflight.py` runs end-to-end against the real queue/contract
  files with the new wiring (expected result: fails on empty queue for today's date,
  unrelated to this batch — no import or identity-check regressions).

### Explicitly not done in this batch
- No prompt tuning, no wardrobe logic changes (Batch 3).
- `pipeline/kling_ui_executor.py` was not deleted, only annotated.
- `.env` was not touched. No live generation was run. Nothing was published or committed.
- The `/v1/images/omni-image` vs `/v1/images/generations` endpoint question (flagged
  in the containment memo) is still unresolved -- out of scope for identity hardening.

---

## 2026-07-05 — Batch 3: Prompt-builder / executor reconciliation

### Why
`_build_compact_prompt`/`_build_compact_negative_prompt` in the real live executor were
rebuilding a short, generic, from-scratch prompt (900/700-char cap) from raw slot
metadata fields, instead of using the prompt the brain had already built. Inspecting a
real slot from `pipeline/kling_workorders/2026-07-04/daily_workorders.json` showed
`slot["image_prompt"]` (10,364 chars) and `slot["negative_prompt"]` (3,792 chars) were
already fully correct -- built by `pipeline/prompting/lena_prompt_brain.py` at
workorder-prep time, containing the exact wardrobe continuity/outerwear-underlayer
locks, the no-invented-freckles skin policy, and catalog-specific negative terms. The
executor was silently discarding all of it and writing a weaker parallel version
(including the "natural freckles" contradiction flagged in the containment memo).

### What changed
- `pipeline/kling_apilena_api_executor.py`
  - `_build_compact_prompt(slot)` now sources from `slot["image_prompt"]` (the
    prompt-brain's own output) instead of rebuilding from raw metadata. It splits the
    source into sentences and keeps them under `PROMPT_MAX_CHARS` (2499, matching the
    existing budget convention already used in
    `tools/strategy/lena_build_content_packet_dryrun_v1.py`) using a priority-tiered
    keeper: the specific wardrobe-override sentence first, then identity/eye-color,
    then the no-invented-freckles skin policy, then wardrobe/outerwear-continuity
    locks, then public-scene-lock/hands/body-shape, then descriptive filler last.
    Final assembly restores original sentence order. Raises (caught by `_submit_photo`
    as a normal per-slot failure) if `image_prompt` is missing, instead of silently
    falling back to a weaker generic prompt.
  - `_build_compact_negative_prompt(slot)` now transports the full
    `slot["negative_prompt"]`, deduped, trimmed to `NEGATIVE_PROMPT_MAX_CHARS` (2499)
    only if it doesn't fit -- no longer a fixed generic term list plus 4-substring
    scanning.
  - Added `_build_prompt_receipt(...)`, saved as `prompt_receipt.json` next to
    `submit_payload.json` in the debug dir: records source/compact char counts, which
    safety keyword groups survived, explicit booleans for wardrobe-continuity/
    outerwear-underlayer/no-freckle-policy/public-scene-lock/hands, and full
    negative-prompt-preservation status.
  - The "natural freckles" contradiction is gone as a side effect of using the real
    slot prompt instead of the old hand-written one.

### Endpoint question, resolved
- `/v1/images/omni-image` does not appear anywhere as a real, working endpoint --
  not in `tools/generation/kling_lena_element_endpoint_research_v1.py` (the repo's own
  dedicated endpoint-research report), not in any config, not in any debug artifact.
- The research report explicitly confirms `POST https://api.klingai.com/v1/images/generations`
  as the working submit endpoint (with a matching poll endpoint), based on multiple
  prior successful requests.
- A real successful run from **2026-07-04** exists at
  `pipeline/kling_debug/apilena_api/2026-07-04/2026-07-04-01-photo/result_manifest.json`
  (`task_status: "succeed"`, image downloaded) using exactly this endpoint -- proof it
  already works, not a guess.
- That same artifact also shows `"payload_no_image_list": false` from yesterday's real
  run -- direct historical confirmation that the `image_list` contract violation fixed
  in Batch 1 actually fired in production, not just in theory.
- **No code change made for the endpoint.** The current executor default is already
  correct; changing it to a nonexistent `/v1/images/omni-image` path would have broken
  a proven-working path based on a documentation phantom.

### Validation
- `python -m py_compile pipeline/kling_apilena_api_executor.py` clean.
- Functional test (no network calls) against all 3 real photo slots in
  `pipeline/kling_workorders/2026-07-04/daily_workorders.json`: for every slot,
  `wardrobe_selection_sentence_present`, `wardrobe_continuity_present`, and
  `skin_no_freckle_policy_present` are all `True` in the resulting `prompt_receipt`.
  `outerwear_underlayer_language_present` is `True` only for the one slot whose outfit
  actually has outerwear/underlayer language to preserve (wc_p079) and correctly
  `False` for the other two (non-outerwear outfits) -- confirms the receipt reflects
  reality rather than always reporting success.
- An earlier version of the priority ordering let the broad "identity" keyword group
  crowd out the freckle-policy and specific wardrobe-override sentences under the 2499
  budget; caught by this same functional test before reporting, then fixed by adding a
  dedicated top-priority `wardrobe_selection` group and re-verified.

### Explicitly not done / disclosed limitation
- Negative-prompt full preservation is **not guaranteed**: real slots carry 150-172
  unique deduped terms (~3,800 source chars), and only ~127 fit under the 2499-char
  budget. Transport is now full-source, deduped, and priority-ordered (first-listed
  terms survive first) rather than substring-scanned -- but the budget is a real,
  disclosed constraint, not a design shortcut. Whether Kling's actual `negativePrompt`
  field accepts more than 2499 chars is unverified and should be checked before relying
  on this for content that leans on later-listed negative terms.
- No visual QA step added (Batch 4+). No broader agentic restructuring.
- `.env` was not touched. No live generation was run. Nothing was published or committed.

---

## 2026-07-05 — Batch 4: Proof-readiness + structured visual QA foundation

### Why
The reconciled executor (Batch 3) is materially healthier but unproven end-to-end, and
there was still no structured place to record a QA verdict on a rendered image --
verdicts have historically been prose in handoff `.md` files. This batch adds the
schema and the review scaffolding needed before a single controlled proof render can be
responsibly reviewed and judged, without running that render yet.

### What changed
- New: `pipeline/qa/__init__.py`, `pipeline/qa/lena_photo_qa.py`
  - Defines the 10-item Lena photo QA checklist: identity fidelity, face realism/
    anti-generic drift, skin realism/no invented marks, wardrobe class fidelity,
    public-scene clothing continuity, outerwear-underlayer correctness, body-shape
    continuity, hands/anatomy sanity, environment realism/scene coherence, and a
    caption-scene-coherence placeholder. Each item takes `pass` / `fail` /
    `not_applicable` / `unreviewed`; there's a top-level `overall` and
    `failure_reasons`.
  - `build_qa_template()` / `save_qa_template()` produce an all-`"unreviewed"`
    scaffold at `pipeline/asset_review/lena/<date>/<slot_id>_qa.json` (matching the
    existing dated-report convention already used in that directory) and never
    overwrite an existing file, so a completed review can't be silently clobbered by
    re-running the helper.
  - `validate_qa_result()` rejects false-green verdicts: `overall` cannot be `"pass"`
    while any checklist item is `"fail"`, and `"fail"` requires at least one entry in
    `failure_reasons`. This module performs no QA itself -- there is no automated
    vision model wired in; it is the schema and the guard against a dishonest verdict
    once a human (or Claude looking at the actual image) fills one in.
- New: `tools/lena_review_proof_render_v1.py`
  - Read-only proof-review helper (only side effect: creating a missing QA scaffold).
    Given `--date` and optionally `--slot`, it resolves and reports the generated
    image path, `submit_payload.json`, `prompt_receipt.json`, `result_manifest.json`,
    and the QA result path/status for a slot, plus the slot's own wardrobe/
    environment/activity/pose/caption metadata, plus a negative-prompt-budget
    summary pulled straight from the prompt receipt. Handles missing artifacts
    gracefully (reports `exists: false` rather than crashing) so it works against
    partial/historical runs, not just a freshly completed one.
- `pipeline/kling_apilena_api_executor.py`
  - `_build_prompt_receipt()` gained explicit budget-truthfulness fields:
    `negative_prompt_original_chars`, `negative_prompt_final_chars`,
    `negative_prompt_trimmed_due_to_budget`, `negative_prompt_terms_survived`,
    `negative_prompt_terms_dropped`. The receipt now states plainly whether trimming
    happened rather than requiring the reader to infer it from char counts.

### Validation
- `py_compile` clean on all four touched/added files.
- `import pipeline.qa.lena_photo_qa` succeeds.
- Ran `tools/lena_review_proof_render_v1.py --date 2026-07-04` against the real
  (pre-Batch-3) 2026-07-04 workorders: correctly reported slot 1's real generated
  image/submit_payload/result_manifest as existing, correctly reported
  `prompt_receipt_exists: false` for all three (receipts didn't exist before Batch 3),
  and correctly reported slots 2-3's image/debug artifacts as missing (only slot 1 was
  actually rendered that day) instead of crashing.
- Manually verified `validate_qa_result()` catches a constructed false-green case
  (one checklist item set to `"fail"` with `overall` left at `"pass"`) with a clear
  error message.
- Manually verified scaffold idempotency: setting a QA file's `overall` to `"pass"` by
  hand, then re-running the proof-review helper, left the file untouched rather than
  resetting it to `"unreviewed"`.
- The three QA scaffold files created against real 2026-07-04 slots during this
  validation were deleted afterward -- they were test exhaust, not real review data,
  and one had a manually-faked `"pass"` status that should not linger in the repo.

### Explicitly not done in this batch
- No QA was actually performed on any image (no vision model wired in; this is schema
  + scaffolding only).
- No controlled proof render was run. No live generation. No publishing. `.env` was
  not touched.
- No broader multi-agent restructuring.
- Whether Kling's `negativePrompt` field truly caps near 2499 chars (flagged in
  Batch 3) is still unverified.

---

## 2026-07-06 — Batch 4b: controlled proof render + first structured QA verdict (FAIL)

### Why
Env override vars (`KLING_LENA_ELEMENT_IMAGE_URLS_JSON`, `KLING_LENA_ELEMENT_IMAGE_URLS`)
were confirmed absent from `.env`. Cleared to run exactly one controlled proof render
through the reconciled path, targeting the strongest available continuity-test slot,
followed by structured QA against the actual image.

### What changed
- `pipeline/kling_apilena_api_executor.py`
  - Added `CONTENT_BOT_KLING_TARGET_SLOT_ID` env-var filter inside `run_executor()`'s
    slot loop. Two lines: reads the var, skips any slot whose `slot_id` doesn't match
    when set. Does not touch prompt building, identity resolution, payload
    construction, or publishing -- only which slot(s) the loop considers.
- Ran fresh no-credit prep for 2026-07-06 (2026-07-05's manifest was stale after the
  date rolled over). Selected `2026-07-06-03-photo` (wc_p082, White Ribbed Tank +
  Black Leather Mini Skirt + Tall Boots, `mini_skirt_set`) as the strongest
  continuity test among the day's 3 slots -- the other two were single-piece dresses.
- Ran exactly one live render via `pipeline.kling_apilena_api_executor.run_executor()`
  with `CONTENT_BOT_KLING_EXECUTE=1` and the new target-slot filter. `processed_slots: 1`.
- Ran `tools/lena_review_proof_render_v1.py` for that slot -- confirmed image,
  `submit_payload.json`, `prompt_receipt.json`, `result_manifest.json` all exist;
  QA scaffold created.
- Filled in the QA result at
  `pipeline/asset_review/lena/2026-07-06/2026-07-06-03-photo_qa.json` after actually
  viewing the rendered image (not from metadata alone). **Overall: FAIL.**

### Root cause isolated
The submitted prompt contained no `Scene:`/`Environment:`/`Lighting:` language at all,
even though the source `image_prompt` from `lena_prompt_brain.py` correctly included
it (verified directly: `"Scene:" in source` and `"Environment:" in source` both
`True`). Batch 3's priority-tiered compaction (`_SAFETY_KEYWORD_GROUPS` /
`_SAFETY_KEYWORD_PRIORITY`) never included a scene/environment category -- under this
slot's tight budget, those sentences were classified as trimmable filler and lost the
budget race to identity/wardrobe/skin/body-shape sentences. Result: a plain gray-backdrop
bust crop with none of the specified coffee-shop context, and most of the specified
wardrobe (skirt, boots, sunglasses, hoops) and body-shape cropped out of frame,
making several QA checklist items unverifiable rather than confirmed.
`reference_mode: upper_body` for this slot was correct by design, not the bug.

### What this proof render did confirm
- Live identity resolution pulled the current approved element via a fresh API
  lookup, not a manual override (confirmed absent).
- `element_list` only in the submitted payload -- no `image_list` (Batch 1 fix held).
- The wardrobe-selection and wardrobe-continuity sentences did survive into the final
  prompt, and the visible tank top reads as real clothing, not a bra/lingerie
  substitution -- the specific 07-03 bra-top-drift failure class was not reproduced
  in what's visible.

### Explicitly not done in this batch
- No repair was made. Root cause is isolated and reported; the fix (add a
  scene/environment keyword group to the same Batch 3 function) is a recommendation
  for the next approved batch, not applied here.
- No second render was run. No publishing. `.env` was not touched.

---

## 2026-07-06 — Batch 5: scene/environment priority reorder + reserved floor (partial success, new regression found)

### Why
Approved narrow repair for the Batch 4b proof-render failure: Scene:/Environment:
language present in the source prompt was being dropped entirely during compaction.

### What changed
- `pipeline/kling_apilena_api_executor.py`
  - Added a `scene_environment` keyword group (`scene:`, `environment:`,
    `small details:`, `camera and composition`, `capture source`, `lighting:`) to
    `_SAFETY_KEYWORD_GROUPS`, inserted into `_SAFETY_KEYWORD_PRIORITY` right after
    `wardrobe_continuity`. **Functional test showed this alone was insufficient**:
    `wardrobe_selection` + `identity` + `eye_color` + `skin_no_freckle` +
    `wardrobe_continuity` already total ~4,466 raw chars against the 2,499 budget for
    this slot, exhausting it before scene's turn regardless of priority position.
  - Added a separate, narrower reserved-floor pass ahead of the normal priority loop:
    `_SCENE_FLOOR_KEYWORDS = ("scene:", "environment:")`,
    `SCENE_ENVIRONMENT_FLOOR_CHARS = 600` (file-local constant, no env override, per
    this batch's scope). Only `Scene:`/`Environment:` sentences qualify for the
    guaranteed floor -- `Lighting:`/`Small details:`/`Camera and composition:`/
    `Capture source:` stay in the normal priority pass, unchanged. A sentence that
    doesn't fit whole within the floor is trimmed via the existing word-boundary
    trimmer (`_trim_text`) rather than dropped. `PROMPT_MAX_CHARS` (2499) unchanged.
  - `_build_prompt_receipt()` gained `scene_environment_floor_reserved_chars`,
    `scene_environment_floor_chars_used`, and
    `scene_environment_survived_via_reserved_floor`, computed by rescanning the final
    compact prompt (not by threading internal build-time state out of
    `_build_compact_prompt`) -- keeps the receipt independently verifiable the same
    way every other field in it already is.

### Functional test result against the same failing slot (2026-07-06-03-photo)
- **Fixed:** `scene_environment_present` is now `true`. The compact prompt now
  contains both `Scene: leaning against a small cafe window counter, holding an
  iced coffee...` and `Environment: a narrow neighborhood coffee shop with
  mismatched two-top tables...` verbatim (422 of the 600 reserved chars used).
  `skin_no_freckle_policy_present` remains `true`.
- **New regression found:** `wardrobe_continuity_present` flipped to `false`. The
  600 chars now reserved for scene/environment came directly out of the same
  budget the wardrobe-continuity-lock sentences were using. Confirmed by direct
  inspection: 4 real continuity sentences exist in the source prompt (`"Skirt-set
  continuity lock: keep the named top and skirt as two real separate garments."`,
  the waistband/hem-length sentences, etc.) and none of them survived into this
  slot's compacted output after the floor was added.
- This is exactly the trade-off flagged as a risk before implementation (see the
  prior proposal turn, section D) -- now empirically confirmed rather than assumed.

### Explicitly not done in this batch
- The wardrobe-continuity regression above was **not** fixed. No further code change
  was made without approval.
- No live generation was run. No publishing. `.env` was not touched.
- Batch 5 is **not** being marked complete/approved pending resolution of this
  regression -- one of the two explicit validation criteria (wardrobe continuity /
  skin-no-freckle survival) was not met.

---

## 2026-07-06 — Batch 5c: narrowed the floor to Scene: only, and found a false-positive bug

### Why
Approved: shrink the reserved floor to cover only `Scene:` (not `Environment:`), return
the rest of that budget to the normal priority competition so `wardrobe_continuity` has
room again.

### What changed
- `pipeline/kling_apilena_api_executor.py`
  - `_SCENE_FLOOR_KEYWORDS` narrowed to `("scene:",)` only. `Environment:` reverted to
    the normal `scene_environment` priority pass (unchanged there).
  - Renamed `SCENE_ENVIRONMENT_FLOOR_CHARS` -> `SCENE_FLOOR_CHARS`, value `600` -> `200`
    (the slot's actual `Scene:` sentence is 153 chars; 200 gives headroom for slightly
    longer ones elsewhere without being wasteful). File-local constant, no env knob,
    per scope. `PROMPT_MAX_CHARS` unchanged.
  - Receipt field *names* kept stable (`scene_environment_floor_reserved_chars` etc.)
    per prior approval; values and docstrings updated to reflect the Scene:-only scope.

### Functional test result (same slot, 2026-07-06-03-photo)
- `scene_environment_present: true` -- **genuine**, verified: the compact prompt
  contains the actual `Scene: leaning against a small cafe window counter...` sentence
  verbatim (153/200 reserved chars used).
- `wardrobe_continuity_present: true` -- **false positive, caught before reporting
  success.** Direct inspection of the matched keyword shows it is triggered only by
  `"Do not crop awkwardly through hands or face."` (a camera-framing instruction)
  matching the `"crop"` keyword in `_SAFETY_KEYWORD_GROUPS["wardrobe_continuity"]`.
  None of the real continuity-lock text (`"Skirt-set continuity lock: keep the named
  top and skirt as two real separate garments."`, the waistband/hem-length sentences)
  is actually present in the compact prompt. This keyword ambiguity predates this
  batch (introduced in Batch 3) but only now matters, because the real continuity
  sentences no longer fit under the tighter budget and there was nothing to mask it
  with before.
- `skin_no_freckle_policy_present: true` -- largely genuine: `"beauty mark"`,
  `"pore-dot"`, and `"beauty-filter"` all match real skin-realism sentences that are
  actually present. The single most explicit sentence (`"Do not invent freckles..."`)
  is not present, but adjacent skin-authenticity language is.

### Explicitly not done in this batch
- The `"crop"` keyword false-positive was **not** fixed. No further code change was
  made without approval.
- No live generation was run. No publishing. `.env` was not touched.
- Batch 5 remains **not complete** -- the receipt cannot currently be trusted to
  truthfully report wardrobe-continuity survival, which is exactly the kind of
  false-green condition this whole engagement has been trying to eliminate.

---

## 2026-07-06 — Batch 5d: fixed the wardrobe_continuity false-positive keyword

### What changed
- `pipeline/kling_apilena_api_executor.py`
  - Removed bare `"crop"` from `_SAFETY_KEYWORD_GROUPS["wardrobe_continuity"]`.
    Replaced with the actual multi-word phrases the source prompt uses: `"crop top"`,
    `"cropped tank"`, `"crop gap"`, `"floating hem"`, `"floating high above"`,
    `"two real separate garments"`, `"full-length to the waistband"`,
    `"named hem length"`.

### Functional test result (same slot)
- `wardrobe_continuity` matched substrings: `[]` (empty) -- **trustworthy signal,
  confirms continuity is truly absent**, not a false positive. The real continuity
  sentences (10 of them, 86-205 chars each) don't fit under the tighter budget after
  the Scene: floor.
- `skin_no_freckle` matches: `['beauty mark', 'pore-dot', 'beauty-filter']` -- genuine.
- `scene_environment` matches: `['scene:']` -- genuine.

### Explicitly not done
- No continuity floor added yet. No render. No publishing. `.env` untouched.

---

## 2026-07-06 — Batch 5e: reserved continuity floor added

### What changed
- `pipeline/kling_apilena_api_executor.py`
  - Refactored the Scene: floor logic into a shared nested helper
    `_apply_reserved_floor(keywords, floor_chars)` (same behavior, reused instead of
    duplicated).
  - Added a second, separate reserved floor: `_CONTINUITY_FLOOR_KEYWORDS =
    ("continuity lock",)`, `CONTINUITY_FLOOR_CHARS = 110` (file-local constant, no env
    override). Verified `"continuity lock"` matches only the single shortest essential
    continuity sentence in this slot's source prompt: `"Skirt-set continuity lock:
    keep the named top and skirt as two real separate garments."` (86 chars).
  - `_build_prompt_receipt()` gained `wardrobe_continuity_floor_reserved_chars`,
    `wardrobe_continuity_floor_chars_used`,
    `wardrobe_continuity_survived_via_reserved_floor`, mirroring the scene fields,
    computed the same independently-verifiable way (rescanning the final compact
    prompt, not build-time state).

### Functional test result (same slot, 2026-07-06-03-photo)
- `wardrobe_continuity` matches: `['continuity lock', 'two real separate garments']`
  -- **genuine**, confirmed present verbatim in the compact prompt:
  `"Skirt-set continuity lock: keep the named top and skirt as two real separate
  garments."`
- `scene_environment` matches: `['scene:']` -- unchanged, still genuine.
- `skin_no_freckle` matches: `['beauty mark', 'beauty-filter']` -- still genuinely
  true overall, though the `"no pore-dot pattern"` sentence was displaced this round
  to make room for the continuity sentence (2 of the previous 3 matches remain).
- **Side observation, not fixed, out of this batch's scope:**
  `outerwear_underlayer_language_present` also flipped to `true` for this outfit
  (wc_p082, which has no outerwear shell and doesn't need this protection) --
  because that field's own keyword check also includes bare `"continuity lock"`,
  which now matches the skirt-set continuity sentence too, not just genuine
  outerwear-underlayer sentences. Same class of ambiguity as the `wardrobe_continuity`
  fix, but on a different field. Flagged for a future narrow fix, not addressed here.

### Explicitly not done
- The `outerwear_underlayer_language_present` ambiguity above was not fixed.
- No render was run. No publishing. `.env` was not touched.
- Batch 5 (5a-5e) is now considered **functionally validated**: Scene:, the essential
  continuity sentence, and skin-no-freckle protections all genuinely survive
  compaction for the slot that exposed the original framing failure, confirmed by
  direct substring inspection rather than trusting booleans alone.

---

## 2026-07-06 — Re-proof render on the same slot (2026-07-06-03-photo): FAIL, but meaningfully improved

### What happened
Ran exactly one live render through the reconciled path (same slot, same executor,
manual override vars reconfirmed absent). Ran the proof-review helper. Reviewed the
actual rendered image and wrote a fresh QA result to
`pipeline/asset_review/lena/2026-07-06/2026-07-06-03-photo_qa.json` (overwriting the
stale fail-verdict scaffold from the pre-Batch-5 render).

### QA verdict: FAIL (overall), with real, confirmed improvement
- **`environment_realism_scene_coherence`: PASS.** The prior flat-gray-backdrop
  failure is directly resolved -- a genuine cafe window, condensation/glass
  reflections, warm ambient lighting, and a blurred background figure are all present
  and consistent with the specified coffee-shop scene.
- **`public_scene_clothing_continuity`: PASS for the visible portion.** The tank top
  reads as real ribbed-knit clothing, not a bra/lingerie substitution -- a genuine
  confirmation the continuity-lock fix reached the actual image. Caveat: the
  skirt/waistband transition (what the continuity-lock sentence is actually about --
  "keep the named top and skirt as two real separate garments") is outside the frame,
  so this render does not test that half of the claim.
- **`face_realism_anti_generic_drift`: PASS**, improved vs. the prior render (real
  window light falloff, warm bokeh, slight natural asymmetry).
- **`wardrobe_class_fidelity`: FAIL.** Only the tank top is visible; skirt, boots,
  sunglasses, and gold hoops are all specified but unverifiable.
- **`skin_realism_no_invented_marks`: FAIL.** Same recurring freckle-density concern
  as the prior render, unconfirmable without the canonical reference photo loaded.
- **`caption_scene_coherence`: FAIL.** Venue/mood matches; the specified iced-coffee
  prop is absent from the frame.
- `body_shape_continuity`, `hands_anatomy_sanity`, `outerwear_underlayer_correctness`:
  not applicable / not assessable (out of frame; no outerwear shell in this outfit).
  The `outerwear_underlayer_language_present=true` false positive noted in Batch 5e
  was treated as non-blocking per instruction, not as a contributing failure reason.

### Practical read
Not "still failing" in the same way as before -- the two defects Batch 5 specifically
targeted (scene/environment absence, continuity-sentence absence) are both confirmed
fixed in the actual image, not just the receipt. But real, separate concerns remain
(skin realism, incomplete wardrobe visibility, missing coffee prop) that a stricter
production bar shouldn't wave through. Best characterized as **proof-worthy but not
production-ready.**

### Explicitly not done
- No repair was implemented for any of the newly/still-failing items. No second
  render. No publishing. `.env` was not touched.

---

## 2026-07-06 — Non-coding verification: canonical reference comparison, QA revised

### What happened
No code change. Downloaded (read-only, no credits) the 4 resource images from the
live "APILENA" Kling element itself -- already-fetched URLs, found in
`pipeline/kling_debug/apilena_api/2026-07-06/2026-07-06-03-photo/live_apilena_lookup_response.json`
from the render just completed. Viewed all 4 directly and compared them against the
re-proof render image.

### Findings, updated into the QA result
- **`skin_realism_no_invented_marks` corrected from FAIL to PASS.** All 4 canonical
  reference photos show consistent, moderate natural freckling across the nose and
  cheeks -- an authentic feature of this character, not drift. The render's freckle
  pattern is a plausible match, not heavier or invented. The prior fail verdict was
  appropriately cautious without a reference to compare against, but doesn't hold up
  now that one is available.
- **`identity_fidelity` newly assessed as FAIL** (previously unreviewed, no reference
  was available). Eyes/brows/face structure are a reasonably close match across all
  4 references. But hair color/pattern is a genuine, consistent mismatch: every
  reference shows a brunette base with warm caramel/honey balayage highlights; the
  render shows flat, uniform dark brunette hair with no highlighting. Skin tone also
  reads paler than every reference (secondary concern, may partly be lighting).
  The prompt's "match hair color exactly" instruction is present and intact in the
  submitted compact prompt -- this drift is not explained by a dropped instruction.
- Overall QA verdict remains FAIL, but for a materially different, more accurate set
  of reasons than before.

### Assessment: is a Batch 6 code fix indicated?
No, not on this evidence. The identity-matching instruction is already correctly
present in the submitted prompt (verified). This looks like generation-model variance
on a fine visual detail rather than a fixable defect in prompt construction or
compaction. A single instance isn't strong enough evidence to justify a targeted code
change -- recommend watching for recurrence across additional proof renders before
treating this as a pattern.

### Explicitly not done
- No code change. No second render. No publishing. `.env` was not touched.

---

## 2026-07-06 — New-slot proof render (2026-07-05-02-photo): FAIL, new root cause isolated

### Why
Approved: test full garment continuity end-to-end on a different slot with better
lower-body visibility, rather than re-running the same upper_body slot.

### Slot chosen
`2026-07-05-02-photo` -- same outfit (wc_p082, White Ribbed Tank + Black Leather Mini
Skirt + Tall Boots) as the already-tested slot, but `reference_mode: full_body`
instead of `upper_body`, public `city bench` lane. Chosen specifically to isolate
framing as the variable while holding wardrobe constant. Confirmed no prior render or
QA result existed for this slot before proceeding (fresh scaffold, not a stale
carryover).

### What happened
Ran exactly one live render through the reconciled path (manual override vars
reconfirmed absent). Ran the proof-review helper. Downloaded and compared against the
4 canonical reference photos again. Wrote a fresh QA result to
`pipeline/asset_review/lena/2026-07-05/2026-07-05-02-photo_qa.json`.

### QA verdict: FAIL, but most individual checks now pass
- **PASS:** `identity_fidelity` (hair reads notably closer to the canonical reference
  set this time -- supports treating the earlier hair-color observation as a single
  instance, not a systemic defect), `skin_realism_no_invented_marks`,
  `face_realism_anti_generic_drift`, `hands_anatomy_sanity` (coffee cup grip visible,
  normal), `environment_realism_scene_coherence`, `caption_scene_coherence` (coffee
  cup now visible in frame, a direct improvement).
- **FAIL:** `wardrobe_class_fidelity` and `public_scene_clothing_continuity`. Despite
  selecting a `full_body` reference-mode slot specifically to test the top/skirt
  waistband transition, the render is still a tight upper-body crop -- the skirt,
  boots, sunglasses, and hoops remain entirely out of frame. **The specific thing
  this render was chosen to test was not actually exercised.**

### Root cause isolated (new, distinct from Batch 5's scene/continuity gaps)
The source prompt genuinely contains a framing directive: `"Framing should clearly
show her full silhouette, outfit fit, waist-to-hip shape, legs, posture, hands, and
shoes when the scene allows."` Confirmed present in `slot["image_prompt"]`, confirmed
**absent** from the submitted compact prompt. It only matches the lowest-priority
`body_shape` keyword group (via the substring `"waist"` in `"waist-to-hip"`) and lost
the budget competition -- the same structural pattern Batch 5 already fixed for
Scene:/continuity-lock, now found on a third, different sentence.

### Explicitly not done
- No code change made (not authorized this turn). No second render. No publishing.
  `.env` was not touched.

---

## 2026-07-06 — Batch 6: reserved framing-directive floor

### What changed
- `pipeline/kling_apilena_api_executor.py`
  - Added a third reserved floor, same pattern as Batches 5c/5e, reusing the existing
    `_apply_reserved_floor(keywords, floor_chars)` helper (no new duplication):
    `_FRAMING_FLOOR_KEYWORDS = ("framing should",)`, `FRAMING_FLOOR_CHARS = 160`
    (the actual sentence is 135 chars). `"framing should"` is the literal opening of
    this one sentence type -- deliberately not a broad body_shape keyword like
    `"waist"`, per instruction.
  - `_build_prompt_receipt()` gained `framing_directive_present`,
    `framing_directive_floor_reserved_chars`, `framing_directive_floor_chars_used`,
    `framing_directive_survived_via_reserved_floor`, mirroring the scene/continuity
    fields exactly.

### Functional test result (same slot, 2026-07-05-02-photo)
Direct substring inspection of the compacted prompt, not just receipt booleans:
```
scene:      ['scene:']              -- genuine
continuity: ['continuity lock']     -- genuine
framing:    ['framing should']      -- genuine, newly fixed
skin:       ['beauty mark', 'beauty-filter']  -- genuine
```
All four required elements verbatim in the compact prompt (2494/2499 chars used, all
three floors -- 200+110+160=470 chars, ~19% of budget -- fit alongside the rest).

### Explicitly not done
- No render was run (not authorized this turn). No publishing. `.env` was not
  touched. No prompt-brain changes. No identity or contract changes.

---

## 2026-07-06 — Batch 7: garment-obedience lock (positive lock validated; negative side found incomplete)

### What changed
- `pipeline/prompting/lena_prompt_brain.py`
  - New `catalog_outfit_is_sleeveless_top_skirt_set(entry)` -- narrow, silhouette-
    class-scoped detector (skirt + tank/halter/sleeveless top, not crop).
  - Extended `public_wardrobe_continuity_lock()`'s Skirt-set branch with a single
    self-contained "Garment-obedience lock:" sentence (positive instruction naming
    the sleeveless top and forbidding sweater/turtleneck/cardigan/jacket/blazer/
    coat/scarf/long-sleeve substitution), gated on the new detector.
  - Extended `build_public_lane_negative_prompt()`'s skirt block with 11 matching
    anti-substitution negative terms, same gating.
- `pipeline/kling_apilena_api_executor.py`
  - Fourth reserved floor (`_GARMENT_OBEDIENCE_FLOOR_KEYWORDS = ("garment-obedience
    lock",)`, `GARMENT_OBEDIENCE_FLOOR_CHARS = 300`), reusing `_apply_reserved_floor`.
  - Receipt fields for the positive lock (`garment_obedience_lock_present`,
    `..._floor_reserved_chars`, `..._floor_chars_used`,
    `..._survived_via_reserved_floor`).

### Functional test (2026-07-05-03-photo, wc_p082 after prep re-run)
- **Positive prompt: all four floors genuine and verbatim** -- scene, continuity,
  framing, and the new garment-obedience lock all confirmed present by direct
  substring inspection. 2471/2499 chars.
- **Negative prompt: zero of the 11 anti-substitution terms survived.** Checked
  directly, not inferred. Batch 7 was **not** closed on this finding.

---

## 2026-07-06 — Batch 7b: negative-term reorder attempted, root cause found deeper than expected

### What changed
- `pipeline/prompting/lena_prompt_brain.py`
  - Moved the 11 anti-substitution negative terms from the end of
    `build_public_lane_negative_prompt()`'s skirt block to immediately after the base
    `extra_bits` list, ahead of every other conditional block (dress/top-crop/
    bodysuit/skirt-base/denim), per the approved "reorder, no new floor mechanism
    yet" scope.
- `pipeline/kling_apilena_api_executor.py`
  - `_GARMENT_OBEDIENCE_NEGATIVE_TERMS` tuple + 4 new receipt fields tracking
    negative-side survival independently from the positive lock
    (`garment_obedience_negative_terms_matched/survived_count/total/present`).

### Functional test result: reorder did not work
- `garment_obedience_negative_terms_matched: []` -- still zero, after regenerating
  the workorder and confirming the reordered source reached the slot.
- **Root cause is bigger than assumed.** The base `NEGATIVE_PROMPT` constant in
  `lena_prompt_brain.py` is **2734 characters by itself** -- already over the
  2499-char negative-prompt budget before `extra_bits` (the whole mechanism, not just
  the new terms) is ever added. Confirmed by directly checking whether *pre-existing*
  extra_bits terms ("mirror selfie", "bra top", "bikini-like bodice") survive compaction
  -- they don't either. `build_public_lane_negative_prompt()`'s entire output has
  apparently never reached the actual submitted negative prompt, for any outfit, not
  just this silhouette class. This predates Batch 7 and is a larger finding than this
  batch's scope, flagged here rather than acted on.
- Per instruction, stopped here rather than implementing a floor. Batch 7 is **still
  not closed.**

### Explicitly not done
- No negative-prompt floor mechanism implemented (next narrowest fix, proposed not
  built). No render. No publishing. `.env` untouched. No base-`NEGATIVE_PROMPT`
  redesign (would be broader than this batch's scope).

---

## 2026-07-06 — Batch 7c: negative-prompt reserved floor -- Batch 7 closed

### Why
Batch 7b's reorder failed because the base `NEGATIVE_PROMPT` constant (2734 chars)
already exceeds the 2499-char budget by itself -- source-order position never
mattered. The next narrowest fix is reserved budget, not reordering.

### What changed
- `pipeline/kling_apilena_api_executor.py`
  - `_build_compact_negative_prompt()` now reserves a small floor
    (`NEGATIVE_GARMENT_OBEDIENCE_FLOOR_CHARS = 380`, 11 terms total 350 chars) for
    exactly the garment-obedience anti-substitution terms
    (`_GARMENT_OBEDIENCE_NEGATIVE_TERMS`, already defined in Batch 7b), added first,
    before the rest of the deduped source terms fill whatever budget remains. This
    naturally trims the lowest-priority tail of the base list rather than reordering
    it -- exactly the mechanism proposed after Batch 7b's finding.
  - Receipt gained `negative_garment_obedience_floor_reserved_chars` and
    `negative_garment_obedience_floor_chars_used`, alongside the existing
    Batch 7b match-list fields.

### Functional test result (2026-07-05-02-photo, wc_p082)
Direct substring inspection of the actual compact negative prompt (not the receipt
alone): all 11 anti-substitution terms present verbatim, as the first 350 characters
of the string. Receipt confirms exactly: `garment_obedience_negative_terms_survived_count:
11`, `_total: 11`, `negative_garment_obedience_floor_chars_used: 350`. Positive side
unaffected and still genuine: `wardrobe_continuity_present`, `scene_environment_present`,
`framing_directive_present`, `garment_obedience_lock_present` all `true`. Compact
prompt 2498/2499 chars, compact negative 2497/2499 chars -- both within cap, tight but
compliant.

**Batch 7 is now closed.** Both the positive garment-obedience lock and its negative
anti-substitution reinforcement are confirmed, by direct inspection, to survive
compaction together with scene/continuity/framing, for the slot that exposed the
original wardrobe-substitution failures.

### Explicitly not done
- No render was run (not authorized this turn). No publishing. `.env` untouched.
  No change to the base `NEGATIVE_PROMPT` constant or the broader public-lane
  negative-prompt mechanism (tracked separately as repo-wide technical debt, not
  fixed here).

---

## 2026-07-06 — Tracked issue (not fixed): repo-wide negative-prompt budget/truthfulness gap

Recorded per explicit decision to classify this separately from Batch 7, not solve it
inside this batch.

- **Finding:** the base `NEGATIVE_PROMPT` constant in `pipeline/prompting/lena_prompt_brain.py`
  is 2734 characters by itself, already exceeding `NEGATIVE_PROMPT_MAX_CHARS` (2499)
  before any lane/outfit-specific `extra_bits` content is added.
- **Consequence:** this likely means multiple legacy/public-lane `extra_bits` blocks in
  `build_public_lane_negative_prompt()` -- not just the new garment-obedience terms --
  have not been reaching submitted payloads for any outfit. Confirmed directly: even
  pre-existing protections ("mirror selfie", "bra top", "bikini-like bodice") do not
  survive compaction under the current first-N-fit logic.
  Batch 7c's fix only reserves room for the one narrow silhouette-class block it was
  scoped to (garment-obedience anti-substitution terms) -- it does not fix this for
  any other `extra_bits` content.
- **Status:** tracked, not fixed. A later dedicated batch must redesign
  negative-prompt prioritization/truthfulness repo-wide (likely a generalized
  reserved-floor or priority-tier system on the negative side, mirroring what already
  exists on the positive side) -- out of scope for the active proof-lane thread.

---

## 2026-07-06 — Post-Batch-7 rerender: THIRD consecutive wrong-outfit render, plus new stylistic drift

### What happened
Ran the approved rerender on `2026-07-05-02-photo` (wc_p082) through the reconciled
live path. Confirmed via `prompt_receipt.json` *before* viewing the image that the
submitted prompt and negative prompt both correctly contained the full closed
Batch 7 fix (`scene_environment_present`, `wardrobe_continuity_present`,
`framing_directive_present`, `garment_obedience_lock_present` all `true`;
`garment_obedience_negative_terms_survived_count: 11/11`). Ran the proof-review
helper. Replaced the stale QA verdict (from the previous turtleneck render) with a
fresh review of this render.

### QA verdict: FAIL -- third consecutive wardrobe miss, and a new, more severe defect
- **Wardrobe class fidelity: FAIL again.** Rendered a blue-gray sweater/turtleneck +
  dark scarf -- not the specified white tank top + black mini skirt. Third
  consecutive same-slot miss despite a confirmed-correct submitted prompt each time.
- **New, separate, more severe finding: face realism categorically failed.** The
  render drifted into an illustrated/cartoon/doll-like stylized look (oversized
  eyes, painted skin texture) -- exactly what the negative prompt explicitly
  protects against (`"cartoon"`, `"anime"`, `"doll-like"` are literal terms in the
  submitted negative prompt). This is a worse realism result than any prior render on
  this slot, and a different failure axis than the wardrobe question.
- Pass: hands, environment, caption-scene coherence.

### Classification
Per the decision rule: the outfit still failed despite both new protections (positive
lock + negative terms) being confirmed present and correct in the actual submitted
payload. **Classified as recurring model-level garment noncompliance, not a pipeline
defect.** The pipeline was checked and confirmed correct before the image was even
viewed -- three renders in a row now support this being a genuine model-behavior
pattern on this specific slot/outfit/lane combination, not a fluke.

### Explicitly not done
- No code patch made in response (per decision rule: do not patch code immediately
  on this finding). No further render. No publishing. `.env` untouched.
- Repo-knowledge-layer work remains not started, per the standing decision to wait
  for this thread to close.

### Addendum: hard-fail declaration, proof lane paused
Explicitly reclassified as a **hard fail, not a near miss** -- wrong outfit and wrong
visual style, not a usable proof. Final classification confirmed: recurring
model-level noncompliance (routing bug, compaction bug, and stale-ref bug all ruled
out across three renders with independently verified-correct pipelines each time).
Further rerenders on this exact proof lane (`2026-07-05-02-photo` / wc_p082) are
**paused**. See the master file §0/§14 for the full decision memo and the two
candidate next branches.

---

## 2026-07-06 — First filesystem-native slice: `pipeline/agents/lena/40_identity_continuity/`

### Why
Direction: Branch 1 (repo-knowledge layer + first folder-native slice), since the
pipeline path is validated independent of the paused Kling proof lane.

### What changed
Created exactly five files, no code moved, no other folders created:

- `pipeline/agents/lena/40_identity_continuity/AGENT.md` -- role summary, points at
  the real owner `pipeline/identity/lena_identity.py`, explicitly states this folder
  documents rather than replaces that module.
- `pipeline/agents/lena/40_identity_continuity/RULES.md` -- must-never-do,
  must-hard-fail, human-approval-required, grounded directly in the module's actual
  functions (`assert_no_manual_reference_override`, `require_expected_photo_element`,
  `forbidden_photo_element_ids`).
- `pipeline/agents/lena/40_identity_continuity/INPUTS.md` -- env vars table + the
  three real callers, confirmed by a fresh grep this session
  (`pipeline/kling_apilena_api_executor.py`, `tools/lena_preflight.py`,
  `pipeline/lena_production_job.py`), not assumed from memory.
- `pipeline/agents/lena/40_identity_continuity/OUTPUTS.md` -- documents that this
  module returns values and raises exceptions, not an artifact. Explicitly flags the
  gap against the master doctrine's original `identity_lock.json` target (§7.5) as
  an open question, not a hidden capability.
- `pipeline/agents/lena/40_identity_continuity/CURRENT_STATE.md` -- proof status:
  identity resolution confirmed correct across every render this session, including
  the three that failed on wardrobe/style grounds -- explicitly not implicated in
  that failure.

### Validation
Grounded in a fresh `Read` of `pipeline/identity/lena_identity.py` (110 lines,
re-read in full, not recalled from earlier in the session) and a fresh `Grep` for
`from pipeline.identity import lena_identity` plus a direct check of
`kling_apilena_api_executor.py` (the first grep pattern missed it due to a path
separator quirk; caught and corrected before writing the docs).

### Explicitly not done
- No code moved. No other 10 folders created. No `state/`/`inbox/`/`outbox/`
  subdirectories (not in scope for this minimal slice). No repo-knowledge files
  created yet. No render. No publishing. `.env` untouched.

---

## 2026-07-06 — SESSION ROLLOVER SUMMARY

### What happened this session
A full containment-through-agentic-pivot arc: traced and fixed a live executor that
had silently drifted from documented safety fixes (stale-reference override
reachable, `image_list` contract violation, dropped wardrobe/scene/framing/
continuity language during prompt compaction); consolidated identity resolution into
one owner; built QA scaffolding and a proof-review helper; ran seven proof renders
total, iteratively finding and closing four distinct prompt-compaction defects
(scene/environment, continuity-lock, framing directive, garment-obedience lock +
its negative reinforcement), each found and fixed narrowly, each validated by direct
substring inspection before being reported done; ran three renders after the final
fix closed and found the remaining failure is provider/model-level, not
pipeline-level; adopted the filesystem-native pivot doctrine and two standing
continuity rules (master-file update-before-close, session-start read-first); built
the first folder-native slice.

### Exact files changed (chronological by first touch)
1. `pipeline/identity/lena_identity.py`, `pipeline/identity/__init__.py` (new)
2. `pipeline/kling_apilena_api_executor.py` (modified across nearly every batch)
3. `tools/lena_preflight.py`
4. `pipeline/lena_production_job.py`
5. `pipeline/qa/lena_photo_qa.py`, `pipeline/qa/__init__.py` (new)
6. `tools/lena_review_proof_render_v1.py` (new)
7. `pipeline/prompting/lena_prompt_brain.py`
8. `tools/LEGACY_PROVIDER_SURFACES.md`, `pipeline/config/lena_live_path_manifest_v1.json`
9. `pipeline/agents/lena/40_identity_continuity/{AGENT,RULES,INPUTS,OUTPUTS,CURRENT_STATE}.md` (new)
10. This file and `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` (both new)
11. QA artifacts under `pipeline/asset_review/lena/<date>/` (generated records, not source)

### Validations run
- `py_compile` after every code batch, no exceptions.
- Functional (no-network) tests against real, previously-generated slot data before
  every render, checking direct substrings in compact prompts/negative prompts, not
  receipt booleans alone -- this caught at least two false-positive/insufficient-fix
  situations before they were reported as done (a keyword ambiguity in
  `wardrobe_continuity_present`, and an initial floor-reorder attempt that didn't
  work).
- Seven live renders total; every one preceded by a masked `.env` presence check for
  the manual-override variables.

### Failures discovered
- Stale manual reference-image override path reachable in production (Batch 1).
- `image_list` sent alongside `element_list`, violating the photo contract (Batch 1).
- Scene/environment, continuity-lock, and framing-directive language each
  independently found dropped during prompt compaction (Batches 3, 5, 6).
- A `"crop"` keyword false positive made `wardrobe_continuity_present` lie (Batch 5d).
- Base `NEGATIVE_PROMPT` constant alone exceeds the negative-prompt budget --
  repo-wide, not outfit-specific -- tracked as separate technical debt, not fixed.
- Three consecutive wrong-outfit renders on the same slot despite a fully
  fixed and verified pipeline -- classified as model-level noncompliance.

### Decisions made
- Contain first, then harden identity, then reconcile prompt/executor, then add QA,
  in that order, before any proof render (established early, held throughout).
- No render without explicit confirmation that manual-override env vars are absent.
- No QA verdict trusted from metadata alone -- always view the actual image.
- Stale QA verdicts always explicitly replaced, never left in place.
- Reserved-floor compaction mechanism (narrow, additive, reused four times) preferred
  over reordering or broad rewrites.
- When a proof render fails, isolate the smallest responsible layer before touching
  code; when it's ruled out as code-fixable, stop rather than keep patching.
- Branch 1 (folder-native work) taken over Branch 2 (alternate provider
  investigation) since the pipeline is validated independent of image-generation
  reliability.
- Master-file update-before-close and session-start read-first adopted as standing,
  durable project rules, not one-time asks.

### Next step
Not yet decided between the next folder-native slice (`70_visual_qa/` recommended)
and the repo-knowledge-layer files. See master file §0 for full detail. No new work
started after this rollover entry.

---

## 2026-07-06 — Repo-knowledge/session-recovery layer built (post-rollover)

### Direction
User explicitly redirected work after the rollover: build the repo-knowledge/
session-recovery layer, not the next folder-native slice. Explicit constraints:
do not build `70_visual_qa/` yet, do not render, do not publish, do not move code,
do not create all agent folders. Reason given: session continuity is the biggest
operational problem -- every new Claude instance needs a reliable starting point
before more agent folders get built.

### Files created/changed
1. `pipeline/change_notes/NEXT_SESSION_START.md` (rewritten) -- now points a new
   session at the knowledge layer (REPO_MAP, LIVE_PATHS) before the master file's
   §0, and reflects the current blocker/next-step state as of this entry.
2. `pipeline/knowledge/content_bot/REPO_MAP.md` (new) -- high-level map of
   `content_bot`'s major folders and what they own; explicitly does not enumerate
   every file, `.bak_*` variant, or per-date data file.
3. `pipeline/knowledge/content_bot/LIVE_PATHS.md` (new) -- canonical live Lena
   entrypoint chain, executor truth (`kling_apilena_api_executor.py` is real and
   live; `kling_ui_executor.py` has no callers; `kling_direct_executor.py` doesn't
   exist on disk), and an active-vs-paused breakdown as of 2026-07-06.
4. `pipeline/knowledge/content_bot/AUTHORITATIVE_SURFACES.md` (new) -- per-concern
   source-of-truth table (identity, execution, QA) plus an explicit precedence
   rule for when files disagree.
5. `pipeline/knowledge/content_bot/QUARANTINED_SURFACES.md` (new) -- dead/legacy/
   doc-only surfaces and why they're not authoritative; points back to
   `tools/LEGACY_PROVIDER_SURFACES.md` as the detailed source rather than
   duplicating its full list.
6. `pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md` (new) -- exact state
   of the Kling photo proof lane, built directly from
   `pipeline/asset_review/lena/2026-07-05/2026-07-05-02-photo_qa.json` (the real
   QA verdict artifact for the third wc_p082 render), not from prose memory of it.
7. `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` -- §0
   updated (current state, files-changed list, current blocker, next approved
   step, prohibitions) and a new dated entry appended to §14.

### Grounding
Every file above was written from a fresh direct read this session: `ls` of the
repo root and `pipeline/`; `tools/LEGACY_PROVIDER_SURFACES.md`;
`pipeline/config/lena_live_path_manifest_v1.json`;
`pipeline/identity/lena_identity.py`; `pipeline/qa/lena_photo_qa.py`;
`tools/lena_review_proof_render_v1.py`; `pipeline/kling_apilena_api_executor.py`
(header + line count); the `pipeline/agents/lena/40_identity_continuity/AGENT.md`
pattern (for tone/structure consistency only); and the actual QA verdict JSON for
the paused proof slot. No claim in these files is sourced from chat memory alone.

### What was explicitly not done
- No new folder-native slice (`70_visual_qa/` or otherwise) was created.
- No render was run. No `.env` was touched. Nothing was published.
- No code was moved between files.
- Not all planned agent folders were created -- only the six knowledge/continuity
  files listed above.

### Next step
Still not decided between (a) `70_visual_qa/` (recommended, wraps the other piece
of already-proven code) and (b) starting the Branch 2 provider/conditioning
investigation into the wc_p082 wrong-outfit/style-drift failures. Ask before
picking either.

---

## 2026-07-06 — Second folder-native slice built: `pipeline/agents/lena/70_visual_qa/`

### Direction
User accepted the repo-knowledge/session-recovery layer, then approved the second
folder-native slice: `70_visual_qa/`, wrapping `pipeline/qa/lena_photo_qa.py`,
`tools/lena_review_proof_render_v1.py`, and `pipeline/asset_review/lena/`.
Explicit constraints: minimum five files only, no code moved, no render, no
publish, no Branch 2 start, no building out all remaining agent folders, no
framework.

### Files created
1. `pipeline/agents/lena/70_visual_qa/AGENT.md` -- what the agent owns and
   explicitly does not do (no automated vision model wired in; no default
   overwrite of an existing QA file; no CLI force-replace flag).
2. `pipeline/agents/lena/70_visual_qa/RULES.md` -- the stale-QA-file lesson (see
   below), false-green hard-fail conditions (code-level and reviewer-level), the
   canonical-reference-image procedure for identity/skin/hair review, and
   human-approval boundaries.
3. `pipeline/agents/lena/70_visual_qa/INPUTS.md` -- every file
   `build_review_bundle()` reads (workorder manifest, slot metadata, debug
   artifacts, existing QA file), plus the `live_apilena_lookup_response.json`
   canonical-reference source not read by the code but used by the reviewer.
4. `pipeline/agents/lena/70_visual_qa/OUTPUTS.md` -- what the code actually
   writes (a QA scaffold, only if none exists) vs. what a real verdict is (a
   human/Claude-authored file, never automated), and documented gaps (no
   automated judge, no force-replace mechanism, no cross-slot trend aggregation).
5. `pipeline/agents/lena/70_visual_qa/CURRENT_STATE.md` -- proof status grounded
   in the real, current QA verdict for `2026-07-05-02-photo`
   (overall: fail, third consecutive wardrobe miss plus new cartoon-style-drift
   finding).

### The stale-QA-file lesson (documented precisely, not just referenced)
Traced the exact mechanism in `pipeline/qa/lena_photo_qa.py` and
`tools/lena_review_proof_render_v1.py`:
- `slot_id` is stable across rerenders on the same slot (confirmed:
  `2026-07-05-02-photo` was rendered three times under the same `slot_id`).
- `save_qa_template(slot, date_str, force=False)` -- the default -- never
  overwrites an existing QA json.
- `tools/lena_review_proof_render_v1.py`'s `main()` exposes only `--date` and
  `--slot`; there is no force/overwrite flag anywhere in this CLI.
- Consequence: `build_review_bundle()`'s `qa_overall_status` field will report
  whatever verdict is already on disk for that `slot_id`, which may describe a
  **previous** render's image if a rerender happened and nobody has yet written a
  fresh verdict.
- Confirmed via grep that this has already occurred twice in this project's real
  history and was caught by a human/Claude explicitly noticing and overwriting
  the file after viewing the new image -- not by any code-level protection:
  "overwriting the stale fail-verdict scaffold from the pre-Batch-5 render" and
  "replaced the stale QA verdict (from the previous turtleneck render)."
- `RULES.md` states the operating rule directly: every new render on a
  previously-used slot requires an explicit QA replacement/update; an old
  verdict, pass or fail, must never be assumed to describe a new image.

### False-green conditions documented
Beyond what `validate_qa_result()` already enforces in code (overall can't be
`pass` while any item is `fail`; `fail` requires non-empty `failure_reasons`),
`RULES.md` documents reviewer-level false-green conditions that the validator
cannot catch: trusting a `pass` inferred from receipt-level prompt correctness
without viewing the image, and carrying a verdict over from a prior render on the
same slot without re-viewing the new one.

### Canonical-reference-image procedure documented
Grounded in the real 2026-07-06 non-coding verification entry (this file, above):
the 4 canonical reference images for the live element are already fetched during
generation and saved in that render's own `live_apilena_lookup_response.json` --
read from there rather than re-fetching, and always view them directly before
finalizing `identity_fidelity` or `skin_realism_no_invented_marks` (this project
has already reversed a verdict both ways this way: freckles FAIL to PASS, hair
unreviewed to FAIL, once real references were viewed).

### What was explicitly not done
- No code moved between files.
- No render run. No `.env` touched. Nothing published.
- Branch 2 (provider/conditioning investigation) not started.
- No further folder-native slices built beyond this one.
- No force-replace flag added to `tools/lena_review_proof_render_v1.py` --
  flagged as an open, undecided question in `RULES.md` / `OUTPUTS.md`, not
  authorized to build.

### Next step
Still not decided: no single next folder-native slice is specifically recommended
now that both previously-flagged proven-code candidates
(`40_identity_continuity/`, `70_visual_qa/`) are built. The two live options are
(a) picking a further folder-native slice, or (b) starting the Branch 2
provider/conditioning investigation. Ask before picking either.

---

## 2026-07-06 — Branch 2: provider/conditioning investigation (read-only), major finding

### Direction
User approved starting Branch 2. Explicit constraints: no render, no code, no
publish, no `.env` change. This is a provider-conditioning investigation, not a
prompt-compaction investigation (Batches 1-7 already exhausted that angle).

### Method
Read-only artifact and repo investigation. No API calls made except downloading
already-public Kling CDN image URLs already present in existing debug JSON
(zero credits, same read-only method the project used in its 2026-07-06
canonical-reference-comparison entry above).

### A. Endpoint/model/payload currently used
- Element identity lookup: `https://kling.ai/api/elements` (paginated list) +
  `https://kling.ai/api/elements/search` -- Kling's internal web-app endpoints,
  scraped via browser-session auth, not the official public REST API.
- Image submission: `POST https://api.klingai.com/v1/images/generations`
  (hardcoded default; confirmed no `KLING_IMAGE_API_URL`/`KLING_BASE_API_URL`
  override present in `.env`).
- Model: **none sent.** `KLING_IMAGE_MODEL_NAME` is absent from `.env`; the code
  (`if IMAGE_MODEL_NAME:`) only adds a `model_name` key when that env var is set.
  Confirmed by direct read of `submit_payload.json` for all 3 recent renders --
  none contain a `model_name` key.
- Payload: `{prompt, negativePrompt, aspect_ratio: "9:16", n: 1, element_list:
  [{"element_id": <int>}]}`. No `image_list`, no `resolution`, no style field.

### B/C. Element ID, source images, realism assessment
`KLING_LENA_ELEMENT_UI_ID=u_315187972322559` (name `APILENA`), 4 resources
(cover 2560x2560 + 3 secondary), tagged "character." Downloaded and viewed all 4
directly: clean, photoreal, consistent (brunette + caramel/honey balayage,
authentic freckling), no cartoon/illustrated quality anywhere. **Rules out
"bad/stylized element contents" as a root-cause category.**

### D/E. Endpoint reliability and comparison to a previous successful path
No repo doc names `/v1/images/generations` as validated for character-element
conditioning. But `pipeline/workorders/lena/README_BODYLOCK_PRODUCTION_RULES_
2026-06-24.md` (git commit `f5908ac6`, "Harden Lena publish gates and BodyLock
production path" -- currently deleted from the working tree, uncommitted,
retrieved via `git show HEAD:<path>` since the deletion hasn't been committed)
names a **different, real, tested recipe**:

- Endpoint: `POST https://api.klingai.com/v1/images/omni-image` (not
  `/v1/images/generations`).
- Model: `kling-v3-omni`, explicitly set.
- Reference payload: `element_list` + `image_list` -- **both required**
  (`tools/generation/lena_run_daily_bodylock_live_v1.py`'s `validate_payload()`
  hard-fails if `image_list` is missing or invalid).
- Resolution: `2k`. Prompt style: "Short scene-only prompt (~400 chars max) --
  no dense appearance descriptors."
- **Rejected paths, per the same doc:** element-only payload (no `image_list`)
  -- "Produced identity drift and pasted-face failures on 2026-06-24 and
  2026-06-25." A 2,172-char appearance-heavy prompt -- "overrides element
  identity."

Three real renders were viewed directly (not just their metadata) to compare
against this:
- `2026-07-04-01-photo` (pre-Batch-1; `payload_no_image_list: false` --
  element_list + image_list of the 4 live element images, but still on
  `/v1/images/generations`, no model_name, prompt ~1,900 chars): photoreal, but
  wrong eye color (green, not the contracted deep dark brown) and wardrobe
  substituted (black crop/bandeau top + denim shorts instead of the specified
  black bodysuit + jeans), despite an explicit continuity-lock sentence and
  negative terms against exactly this substitution.
- `2026-07-05-02-photo` (3rd render, current live path, element-list only,
  2,498-char compact prompt): confirmed directly -- genuine cartoon/3D-
  illustration style (Pixar-like, oversized eyes, doll-like proportions),
  matching the QA verdict already on file exactly. Wrong outfit also confirmed
  (sweater+scarf, not tank+skirt).
- `2026-07-06-03-photo` (current live path, element-list only): photoreal, good
  face/skin, but hair color mismatch (flat dark brunette vs. the reference
  set's consistent caramel/honey balayage) -- again matches the QA verdict
  already on file exactly, confirming that verdict was not stale.

None of the three actually-tested combinations on the current path match the
BodyLock recipe. Real evidence the BodyLock recipe worked at least once:
`pipeline/publishing/lena/dispatch_outbox/2026-06-24/manual_bodylock_20260624_ig_
Instagram_Feed_payload.json` (untracked/working-tree file, confirmed via
`git status`) references a real generated asset that reached the publish-
dispatch stage. The underlying image asset itself is no longer on disk.

### F. Likely failure category
**Primary:** endpoint/model not honoring element conditioning strongly (wrong/
legacy endpoint, no model specified, no image_list anchor). **Contributing:**
prompt/reference conflict (current prompts run up to 2,498 compacted chars,
already longer than the 2,172-char length BodyLock's own doc says already
failed). **Ruled out:** bad element contents (images are clean), and "provider
limitation" as a blanket claim (a working recipe existed on this same
provider). The cartoon-style output is a secondary, inconsistent symptom (1 of
3 renders, not deterministic) -- more consistent with weak conditioning
variance than a hardcoded style default (none exists in the payload).

### Flagged, not acted on
The "element_list-only" photo contract now encoded in
`pipeline/identity/lena_identity.py` (`REQUIRED_REFERENCE_BINDING_MODE =
"kling_omni_element_only_photo"`) was itself written this session (Batch 2,
2026-07-05), formalizing a same-day Batch 1 diagnosis that treated any
`image_list` in the submitted payload as a contract violation. That diagnosis
may have conflated two different things: the genuinely dangerous manual-URL-
override env-var mechanism (arbitrary, unvetted, no expiry -- correctly banned)
versus `image_list` as a payload field sourced from the live element's own
vetted resources (which the 2026-07-04 payload actually did, and which
BodyLock's doc explicitly requires). Not reversed or edited this session --
flagged for the user's explicit review and decision.

### G/H. Smallest next diagnostic step and recommended spend
One controlled, paid proof render retesting the BodyLock recipe (omni-image
endpoint, kling-v3-omni model, element_list + a single vetted image_list
anchor, ~400-char scene-only prompt, n=1, resolution 2k) on the same slot/
outfit/environment already tested 3x on the current path, isolating provider/
endpoint/model/payload-shape as the changed variable. Blocked on: the user's
explicit approval of this specific diagnostic; a decision on the image_list
anchor image (original "Goodtest1" not confirmed to still exist; current
APILENA cover image is the most likely substitute); and re-adding
`KLING_LENA_ELEMENT_ASSET_ID` + an anchor image URL to `.env` (both currently
absent -- a business decision, not a code fix). Recommended over "identity-only
proof on current path" (already effectively done 3x) and "different provider"
(premature -- this provider has a documented working recipe that hasn't been
retried).

### What was explicitly not done
No code changed. No render run. No `.env` touched. Nothing published. Reference
images downloaded to the session scratchpad directory only (outside the repo),
not saved into the repo. The "element_list-only" doctrine was not reversed.

### Next step
Not yet decided. Recommended (not yet approved): the diagnostic render above.
No render authorized until the user explicitly approves it.

---

## 2026-07-06 — BodyLock diagnostic: pre-spend memo + standalone diagnostic tooling (dry-run only)

### Direction
User rejected running "Option 1" (endpoint+model swap only, no `image_list`, on
the current executor) as still ambiguous -- it wouldn't test the actual committed
BodyLock recipe (element_list + image_list together). Approved proceeding with
"Option 2" but only as a tiny, opt-in, diagnostic-only code path, with firm
constraints: no `.env` edit, no restoring manual-URL-override behavior as a
normal path, no weakening the containment guard, no publish, no render without a
further, separate approval of the exact anchor and exact command.

### Pre-spend memo delivered (A-C)
- **A.** Quoted the exact committed BodyLock recipe from `README_BODYLOCK_
  PRODUCTION_RULES_2026-06-24.md` (git commit `f5908ac6`) and confirmed from
  `tools/generation/lena_run_daily_bodylock_live_v1.py`'s `build_payload()` that
  BodyLock's payload has **no `negativePrompt` field at all** -- a comparison
  point not surfaced in the original Branch 2 investigation.
- **B.** Full side-by-side table: endpoint, model, `element_list`, `image_list`,
  prompt length, negative-prompt length, resolution, reference source. BodyLock
  vs. current live path on every dimension.
- **C.** Named exactly which current assumptions the committed recipe
  contradicts: "element-only conditioning is sufficient" (contradicted --
  BodyLock doc calls this a tested, rejected cause of identity drift); "a long,
  dense, appearance-heavy prompt improves fidelity" (contradicted -- current
  path's 2,498-char compacted prompt is already longer than the 2,172-char
  length BodyLock's doc says already failed); "`/v1/images/generations` is
  validated for character-element conditioning" (never established anywhere in
  the repo); "a negative prompt helps identity/wardrobe fidelity" (the one
  recipe with real production evidence used none).

### D -- implementation: `tools/lena_bodylock_diagnostic_v1.py` (new file)
Built as a standalone script -- zero modification to
`pipeline/kling_apilena_api_executor.py` or any of its containment guards.
Design, mapped directly to the user's stated hard-fail requirements:

- **Opt-in only:** `_require_diagnostic_flag()` checks
  `CONTENT_BOT_BODYLOCK_DIAGNOSTIC` is `1`/`true`/`yes` before anything else runs;
  raises otherwise.
- **Containment guard reused, not rebuilt or weakened:** calls
  `pipeline.identity.lena_identity.assert_no_manual_reference_override()`
  directly -- the same function the live executor uses -- so
  `KLING_LENA_ELEMENT_IMAGE_URLS_JSON` / `KLING_LENA_ELEMENT_IMAGE_URLS` still
  hard-fail this diagnostic too.
- **Anchor is a new, diagnostic-only, per-command env var:**
  `CONTENT_BOT_BODYLOCK_ANCHOR_URL` -- read fresh from the process environment
  each run, never written to `.env`, no default, no persistence anywhere. Must
  start with `https://` or the build raises.
- **Endpoint and model hardcoded, not env-overridable:**
  `https://api.klingai.com/v1/images/omni-image` and `kling-v3-omni` are
  constants; the built payload dict is re-checked against them (not just the
  constants in isolation) so the two can't silently drift apart.
- **Every hard-fail condition the user listed is implemented and independently
  re-derived from the payload dict itself:** diagnostic flag unset; anchor
  missing/non-https; prompt empty or > 400 chars; `image_list` not exactly one
  entry; `n` not exactly 1; any negative-prompt key present at all.
- **Dry-run is the default.** Without `--execute`, the script validates and
  prints the exact payload it would submit -- zero network calls, zero credits,
  no debug folder written. Only `--execute` reaches `requests.post`.
- **Diagnostic artifacts cannot be confused with production:** on `--execute`,
  writes to a freshly timestamped, fixed-prefix folder
  (`pipeline/kling_debug/bodylock_diagnostic/bodylock_diagnostic_<UTC
  timestamp>/`, not caller-nameable) containing a `DIAGNOSTIC_NOT_PRODUCTION.md`
  marker plus submit/poll/result JSON. The timestamp-derived name makes it
  structurally impossible to land in or resemble a real dated production
  workorder folder.

### Verification performed (zero spend)
1. `python -m py_compile tools/lena_bodylock_diagnostic_v1.py` -- clean.
2. Ran with the diagnostic flag unset -- correctly raised
   `CONTENT_BOT_BODYLOCK_DIAGNOSTIC is not set to 1/true/yes -- refusing to run.`
3. Ran with the flag set but no anchor -- correctly raised
   `CONTENT_BOT_BODYLOCK_ANCHOR_URL is not set -- an anchor image URL is
   required.`
4. Ran with flag + anchor set and a 499-char prompt -- correctly raised
   `Prompt is 499 chars, exceeds the 400-char BodyLock diagnostic cap.`
5. Ran a valid dry-run: flag set, anchor set to the live APILENA element's own
   cover-image URL (from `live_apilena_lookup_response.json`), and a real
   286-char scene-only candidate prompt for the same city-bench/coffee/wc_p082
   scenario already tested 3x on the current path. Output confirmed the exact
   expected payload: `model_name: kling-v3-omni`, `element_list: [{"element_id":
   315187972322559}]` (the real live element, resolved via
   `lena_identity.require_expected_photo_element()`), one `image_list` entry,
   `aspect_ratio: "9:16"`, `resolution: "2k"`, `n: 1`, no `negativePrompt` key.
6. Confirmed via `git status --short .env` that `.env` is untouched, and via
   `ls pipeline/kling_debug/bodylock_diagnostic/` that no diagnostic debug folder
   exists on disk (dry-run mode never creates one).

### What was explicitly not done
No network call reached Kling. No credits spent. No `.env` edit of any kind. No
change to `kling_apilena_api_executor.py` or its containment guards. No render.

### Anchor decision -- presented, not made
Three candidates given to the user: (1) the live APILENA element's own current
cover/resource image -- recommended, already verified clean/photoreal this
session; (2) a specific named canonical Lena proof image -- none named yet;
(3) the original "Goodtest1" BodyLock anchor -- not confirmed to still exist
anywhere on disk or at a retrievable URL. Not decided.

### Next step
Waiting on the user's explicit approval of the exact anchor URL and the exact
`--execute` command (including final prompt text) before any real submission.
No render authorized until then.

---

## 2026-07-06 — BodyLock diagnostic executed once: rejected at submission, no image produced

### Direction
User approved exactly one real diagnostic run: anchor = the live APILENA
element's own cover image, run the previously-shown exact command with
`--execute`. Constraints: no `.env` edit, no publish, no more than one image, do
not run the normal production executor. Requested a report of the artifact
folder and whether the result looks like realistic Lena with the correct
outfit/style.

### Pre-flight checks (before spending anything)
- Re-read the freshest `live_apilena_lookup_response.json`
  (`pipeline/kling_debug/apilena_api/2026-07-06/2026-07-06-03-photo/`) and
  confirmed the cover-image URL matched exactly what was used in the earlier
  verified dry-run -- anchor still current, not stale.
- Confirmed presence (not values) of `KLING_AK`/`KLING_ACCESS_KEY`,
  `KLING_SK`/`KLING_SECRET_KEY`, and `KLING_WEB_TOKEN` in `.env` -- credentials
  available for the auth path the script needs.

### Command run (exactly once)
```
CONTENT_BOT_BODYLOCK_DIAGNOSTIC=1 CONTENT_BOT_BODYLOCK_ANCHOR_URL="https://s15-kling.klingai.com/kimg/EMXN1y8qTgoGdXBsb2FkEg55bGFiLXN0dW50LXNncBo0YWlfcG9ydGFsLzE3ODMyMTYyNTgvbER1aDBsczZBZi85ODBfZjJlN2ZjNjFfXzJfLmpwZw.origin?x-kcdn-pid=112372" python tools/lena_bodylock_diagnostic_v1.py --prompt "<286-char scene-only prompt, same wording verified in the prior dry-run>" --execute
```

### Result
The payload built and validated correctly (same shape confirmed in the prior
dry-run: `model_name: kling-v3-omni`, `element_list: [{"element_id":
315187972322559}]`, one `image_list` entry, `resolution: 2k`, `n: 1`, no negative
prompt). The submission itself was rejected by Kling:
```
HTTP 400
{"code": 1201, "message": "Element id not found: 315187972322559", "request_id": "85814f13-15a6-4450-9759-34eb59963085"}
```
No `task_id` was issued. The flow never reached polling or image generation --
**zero credits spent, no image produced**. Artifacts:
`pipeline/kling_debug/bodylock_diagnostic/bodylock_diagnostic_20260706T200037Z/`
contains `submit_payload.json` and `submit_response.json` only (no
`poll_response.json` / `result_manifest.json` -- neither stage was reached).

### Interpretation
This is a real, useful diagnostic result, just not the kind originally sought
(an image to judge for realism/outfit/style -- there is none). The same element
id resolves and generates successfully on `/v1/images/generations` (current live
path, looked up via a web-session-scraped internal Kling endpoint, cookie/
web-token auth) but is **not found** by the AK/SK-authenticated official API that
`/v1/images/omni-image` requires. Most likely explanation: this element exists
only in Kling's web-UI element registry, not in whatever registry the official
AK/SK-authenticated API checks. This reconciles with a previously-shelved,
unresolved finding already in this repo: `tools/generation/
kling_lena_element_endpoint_research_v1.py` (2026-06-14, static codebase
research, no API call) found `GET /v1/elements` returned 404 and explicitly
recorded "no confirmed path found in codebase or prior requests" for how the
official API lists or creates elements. That three-week-old open question is now
directly implicated in why the BodyLock-recipe retest could not reach
generation.

### What was explicitly not done
No image generated -- none to judge for realism/outfit/style, and the report to
the user says this plainly rather than implying a result exists. No retry with a
different element id, auth method, or endpoint. No code changed beyond running
the already-approved, already-built script exactly as designed. `.env`
untouched. `kling_apilena_api_executor.py` (the normal production executor) was
not invoked. Nothing published.

### Next step
Not yet decided. This is a new, distinct sub-problem (element-registry/auth
mismatch on the official API), separate from the original wrong-outfit/style
question, which remains open and untouched by this result. Candidates for what's
next, none approved: read-only research into the official API's element list/
create mechanism; asking Kling support/docs directly whether web-UI-created
elements are visible to AK/SK auth; or setting the BodyLock-recipe angle aside
and returning to the original question via a different diagnostic. No further
diagnostic run or retry without the user's explicit direction first.

---

## 2026-07-06 — Element-registry investigation (no-spend): no confirmed-working omni-image element found in repo history

### Direction
User precisely reclassified the diagnostic rejection: not caused by prompt,
outfit, anchor, or `image_list` -- caused by the current APILENA element ID not
being visible to the Omni/API endpoint, implying it exists in the web/UI
element registry but not the official AK/SK Omni API registry. Directed a
no-spend investigation: find whether any older element ID in this repo's
history was actually proven to work with `/v1/images/omni-image` + model
`kling-v3-omni` + AK/SK auth + `element_list`/`image_list`. Explicit
constraints: no render, no `.env` edit, no Kling call, no code change, no
publish.

### Method
`git log --all --oneline -S "<term>"` (pickaxe -- finds commits that
introduced or removed a given string, across the entire history, not just
HEAD) for `"Goodtest1"`, `"kling_image_list"`, and `"313006264506046"`. `git
show <commit>:<path>` to retrieve full file contents from commits whose files
are now deleted from the working tree (the deletions were never committed, so
this works). Direct `ls`/`grep` of every `.env.bak_*` file present on disk (11
total) for `KLING_LENA_ELEMENT_ASSET_ID` and `LENA_KLING_BODY_ANCHOR_URL`.
Repo-wide `grep` for `"313006264506046"`, `"fromElementId"`, `"elementVersion"`
to check whether the later schema appears anywhere beyond its introducing
commits. Checked `pipeline/strategy/lena/kling_face_identify_results/` (a real,
successful, unrelated AK/SK-authenticated video call, `api-singapore.klingai.
com/v1/videos/identify-face`, `generation_call_performed: true`, real credit
deduction recorded) as supporting context that AK/SK credentials themselves are
functional -- the issue is element-specific, not blanket auth failure.

### A. Any official-API-visible Lena element ID in repo history?
One candidate, **unconfirmed to have ever run live**: `u_313006264506046`.
Introduced in `tools/strategy/lena_build_kling_payload_dryrun_v1.py` (commit
`25055603`, 2026-06-25 23:33) and `tools/strategy/lena_submit_kling_payload_v1.py`
(commit `7f4fec51`, 2026-06-26 00:46) -- both timestamped *after* BodyLock's
hardening commit `f5908ac6` (2026-06-25 10:50). Uses a materially different
payload schema than BodyLock:
```json
{
  "model_name": "kling-v3-omni",
  "prompt": "...", "negative_prompt": "...",
  "fromElementId": "u_313006264506046",
  "arguments": [{"name": "elementVersion", "value": "[{\"id\": \"u_313006264506046\", \"name\": \"Lena\", \"type\": \"IMAGE\"}]"}],
  "image_list": [{"image": "<3 hardcoded CDN URLs>"}],
  "aspect_ratio": "9:16", "resolution": "2k", "n": 1
}
```
This later tooling's own guard lists are directly revealing: `BLOCKED_TERMS =
["Goodtest1", "element_list", "/v1/images/generations", "image_reference_
intensity", "face_reference_intensity", ".env.txt"]` and `BLOCKED_IDS =
["313794609092321", "313524913093322", "314409553525527", "314410301504207"]`.
This means: by 2026-06-26, this repo's own tooling explicitly treated
BodyLock's `element_list` approach and its `Goodtest1` anchor as **wrong,
superseded patterns** -- one day after BodyLock was committed as the "approved
production path." Confirmed via `git log --all -S "313006264506046"` that this
ID appears in exactly these two commits and nowhere else in the repo's entire
history. `pipeline/strategy/lena/kling_results/` (where a live run's manifest
would land) does not exist on disk and was added to `.gitignore` in the same
commit that introduced this ID -- so even a real run might not be recoverable,
but there is no positive evidence anywhere (in git history, in any handoff doc,
in any markdown) that this ID was ever actually submitted live.

### B. Does Goodtest1 (or another BodyLock anchor) still exist?
No. Confirmed via repo-wide grep (this session's earlier investigation) that
"Goodtest1" does not appear anywhere in the current working tree. Confirmed via
`git log --all -S "Goodtest1"` that it appears in exactly 4 historical commits
(`f5908ac6`, `25055603`, `7f4fec51`, `5c168dd1`) -- always as a *name*
(BodyLock's README, or a blocked-term string in later scripts), never as an
actual stored URL. Its real underlying image is unrecoverable from this repo.
By contrast, the later script's own anchor set (`LENA_CDN_REFS`, 3 real CDN
URLs tied to `u_313006264506046`) is fully recoverable via `git show` -- but
ties to the unconfirmed element in (A), not to BodyLock.

### C. Did the old BodyLock recipe ever actually succeed under AK/SK auth?
Weaker than the original Branch 2 memo implied -- genuinely uncertain, not
confirmed. `tools/generation/lena_run_daily_bodylock_live_v1.py` (git commit
`f5908ac6`) requires `KLING_AK`/`KLING_SK` (aborts otherwise, no web-token
fallback) and aborts if `KLING_LENA_ELEMENT_ASSET_ID` is unset or equals the
hardcoded `_RETIRED_ELEMENT_ID = 313524913093322`. Checked all 11 `.env.bak_*`
files present on disk:
- `KLING_LENA_ELEMENT_ASSET_ID` appears in exactly two -- `.env.before_
  element_fix_20260622_101837` and `.env.after_element_fix_20260622_101837` --
  both set to `313524913093322` (the exact retired ID this script rejects).
- It is **absent** from `.env.bak_refresh_20260625_082215` (same calendar day
  as the BodyLock hardening commit; that same file *does* have `KLING_AK`/
  `KLING_SK` present, confirming credentials existed but no valid element-asset
  ID was configured under this var name at that snapshot) and absent from
  every other backup checked (2026-06-17/18 era) and from today's `.env`.
- Net: at the one `.env` snapshot closest in time to BodyLock's own creation,
  its live runner would have hard-aborted, not succeeded.
- The one previously-cited positive signal -- `pipeline/publishing/lena/
  dispatch_outbox/2026-06-24/manual_bodylock_20260624_ig_Instagram_Feed_
  payload.json` (untracked, confirmed via `git status`) -- references asset
  filename `lena_bodylock_omni_2026-06-24-01-photo.jpg`, which matches this
  project's *normal* daily-workorder slot-naming convention
  (`<date>-NN-photo`), not `lena_run_daily_bodylock_live_v1.py`'s own output
  naming (`bodylock_daily_{label}_{suffix}.jpg`, written under `pipeline/
  content_library/lena/assets/`). This suggests the dispatched image more
  likely came from the *other* BodyLock script
  (`lena_apply_bodylock_to_daily_batch_v1.py`, which patches BodyLock settings
  into the normal daily-batch JSON) running through whatever executor was live
  in the normal pipeline that day -- not necessarily a proven standalone
  AK/SK + omni-image success matching the README's exact recipe.
- **Conclusion: cannot confirm BodyLock ever succeeded live under AK/SK auth
  with a valid, non-retired element.** Real evidence is suggestive, not
  proof, and the surviving env-var history argues against it at the one
  checkable snapshot.

### D. Can APILENA realistically be used with omni-image, based on repo evidence?
No supporting evidence anywhere in repo history, and one direct negative data
point (today's `HTTP 400 "Element id not found: 315187972322559"`). APILENA
appears only in the web-session-scraped `kling.ai/api/elements` /
`kling.ai/api/elements/search` lookup path throughout this repo's history --
never in any omni-image, AK/SK, or official-API context.

### E. Recommendation given to the user
Presented as a real choice, not resolved unilaterally:
1. Recreate Lena as an official-API-visible Kling element -- the only path
   toward the documented recipe, but explicitly framed as **unproven
   groundwork, not a restoration**: per (A)-(D), no element has ever been
   confirmed to work this way in this account's history at all.
2. Keep `/v1/images/generations` and accept its known limitations -- the only
   option with any real, current-session evidence of working, imperfectly.
3. Switch provider/path for production images -- no repo evidence either way;
   would be a third, independent investigation.
4. Ask Kling support/docs directly whether web-UI-created elements are ever
   visible to AK/SK auth, and how to create one that is -- suggested as the
   cheapest first move if pursuing option 1, since two element-ID guesses
   (APILENA, then `u_313006264506046`) have already gone unconfirmed or failed.
Not decided by the user yet.

### What was explicitly not done
No render. No code changed. No `.env` edit of any kind. No Kling API call. No
publishing. Purely git/file archaeology: `git show`, `git log -S` pickaxe
across all history, and reading `.env.bak_*` files already present on disk.

### Next step
Not yet decided among: recreate element (unproven), accept current path's
limitations, switch provider, or ask Kling support -- plus the previously
open candidates (read-only research into the official element list/create
mechanism; abandon the omni-image angle and return to the original wrong-
outfit/style question via a different diagnostic). Ask before proceeding on
any of these.

### Addendum (same day) -- corroborating evidence from existing browser captures
A background search turned up two `.har` (browser network capture) files
already present in the repo, not created this session:
`scratch/kling_elements_page.har` and `scratch/herby_kling_elements_page.har`.
Inspected the request domains only (no cookies/tokens read or printed). Neither
capture -- both from real browser sessions actively using the Kling web UI's
element/omni-image generation feature -- ever contacts `api.klingai.com` (the
official AK/SK-authenticated API). The entire flow lives under the `kling.ai`
domain: `GET /api/elements`, `/api/elements/search`, `/api/elements/latest`,
`/api/elements/query`, `POST /api/omni/submit-config-template`, `/api/omni/
intent-recognition`. This sharpens (D)/(E) above: the web UI's element-based
omni-image generation and the public `api.klingai.com` omni-image endpoint
appear to be structurally separate products on separate hosts, not two views
of one system -- strengthening the case that option 4 (ask Kling support/docs)
is the more efficient move before attempting option 1, rather than continuing
to guess at element IDs. Does not change the recommendation itself, which
remains the user's decision.

---

## 2026-07-06 — Decision: Kling Omni/BodyLock diagnostic path paused; support packet written

### Direction
User decided the HAR evidence (web-UI element flow uses `kling.ai`; official
AK/SK API uses `api.klingai.com` and cannot see APILENA) was sufficient to
stop further Kling diagnostic testing entirely -- no more guessing at payload
shapes or old element IDs. Directed preparation of a concise support packet
for Kling/APILENA support, specifying exactly what to include (element ID,
where it works/fails, exact error, HAR evidence, four questions) and exactly
what not to do: no code, no render, no `.env` edit, no Kling call, no publish.

### What was written
`pipeline/change_notes/lena_kling_omni_support_packet_2026-07-06.md` -- a
standalone support-communication document, distinct in kind from the other
continuity files (it's meant to be copied/sent externally, not read by a
future Claude session for orientation). Covers, in order:
1. Element ID `315187972322559` ("APILENA").
2. Confirmation it works via `POST /v1/images/generations`.
3. Confirmation it fails via `POST /v1/images/omni-image`.
4. The exact error (`HTTP 400`, `code: 1201`, `"Element id not found:
   315187972322559"`, with the real `request_id` from today's rejection for
   Kling's own reference).
5. The HAR evidence in plain terms: the web UI's element/omni feature calls
   only `kling.ai/api/elements*` and `kling.ai/api/omni/*`, never
   `api.klingai.com`.
6. Question: are web-UI elements visible to the official AK/SK API at all?
7. Question: how do we create/obtain an element ID valid for
   `api.klingai.com/v1/images/omni-image`?
8. Question: which payload schema is correct -- `element_list`,
   `fromElementId`, `arguments.elementVersion`, or something else -- given
   this repo has tried multiple over time without a confirmed answer.
9. Question: does `kling-v3-omni` support character-element conditioning
   through the official API at all, or only through the web app?

Written in plain, external-facing language -- no internal doctrine, batch
numbers, or repo jargon in the main body; a single "internal note" footer
points back to this changelog for anyone on our side who needs the full trace.

### Continuity files updated to state plainly
- The Kling Omni/API BodyLock path is paused pending Kling/APILENA support
  clarification -- paused as a category (no further element IDs, payload
  schemas, endpoints, or auth methods to be tried on our own judgment), not
  just paused after one failed attempt.
- `/v1/images/generations` remains the only currently working Kling image
  path, quality-limited but functional, and is explicitly unaffected by this
  pause.
- No more Kling spend on the omni-image/BodyLock thread until the support
  packet gets an answer.

### What was explicitly not done
No code written or changed. No render run. No `.env` edit of any kind. No
Kling API call. No publishing. The packet was not sent to Kling -- that
remains the user's action, not something done on their behalf.

### Next step
Waiting on Kling/APILENA support's response. The original wrong-outfit/style
question on the current live path remains open and untouched, and could be
pursued in parallel via a different diagnostic if the user chooses to -- not
started, not decided.

---

## 2026-07-06 — Kling Omni/BodyLock investigation: PARKED, clean stop (user-approved)

User approved everything above and gave a final, explicit close-out: park this
branch exactly where it is. Restated, as standing prohibitions until an
external trigger: no more Kling tests, no more element IDs, no more payload
schemas, no recreating Lena as an API-visible element unless support/docs
confirm the correct method first, no `.env` edits, no render. The only next
action on this thread is external -- sending or reading the response to
`pipeline/change_notes/lena_kling_omni_support_packet_2026-07-06.md`.

No files changed except this entry and matching closing markers added to
`NEXT_SESSION_START.md` and the master file's §0, so a future session cannot
mistake this for an active, in-progress investigation and re-open it without
the external response actually being in hand. Nothing rendered, coded, called,
or edited. `.env` confirmed untouched via `git status` before closing.

This thread is now fully parked. Next log entry on this subject should only
happen once Kling/APILENA support has actually responded.

---

## 2026-07-06 — Third folder-native slice created: `pipeline/agents/lena/60_executor/`

### Direction
With the Kling Omni/BodyLock thread cleanly parked, user approved the next
branch: build the folder-native executor slice,
`pipeline/agents/lena/60_executor/`, wrapping the real execution surfaces --
`pipeline/kling_apilena_api_executor.py`, `tools/lena_bodylock_diagnostic_
v1.py`, `pipeline/lena_production_job.py`, `tools/process_queue.py` (if
relevant), and `tools/LEGACY_PROVIDER_SURFACES.md` as legacy context.
Explicit constraints: minimum five files, no code moved, no `.env` edit, no
render, no Kling call, no publish, and explicitly do not reopen the parked
Kling Omni/BodyLock thread.

### Files created
1. `pipeline/agents/lena/60_executor/AGENT.md` -- what this folder owns (the
   map of every real execution surface: live, parked, diagnostic-only,
   dead/legacy) and what it explicitly does not own (identity resolution,
   QA verdicts, publishing -- each a different folder's or a downstream
   surface's responsibility).
2. `pipeline/agents/lena/60_executor/RULES.md` -- what must never be invoked
   casually (`CONTENT_BOT_KLING_EXECUTE=1` on the live executor; `--execute`
   on the parked diagnostic script, currently forbidden outright, not just
   gated); what requires explicit human approval; the standing rule not to
   reopen the parked Omni/BodyLock thread just because this folder documents
   it.
3. `pipeline/agents/lena/60_executor/INPUTS.md` -- every env var read by the
   live executor and the parked diagnostic script, the call chain from
   `lena_production_job.py` down to the executor, and the ownership
   boundary with prompt-building/identity/QA (each a different folder).
4. `pipeline/agents/lena/60_executor/OUTPUTS.md` -- exactly where each
   surface writes its artifacts (`pipeline/kling_debug/apilena_api/<date>/
   <slot_id>/` for the live path; `pipeline/kling_debug/bodylock_diagnostic/
   bodylock_diagnostic_<timestamp>/` for the parked path, historical only
   now), and who consumes them today.
5. `pipeline/agents/lena/60_executor/CURRENT_STATE.md` -- proof status of
   the live path, parked status of the Omni/BodyLock path (with a pointer to
   the PARKED banner as the most current statement), a concise dead/legacy
   executor-name list (cross-referencing `tools/LEGACY_PROVIDER_SURFACES.md`
   and `pipeline/knowledge/content_bot/QUARANTINED_SURFACES.md` for full
   detail rather than duplicating them), and an explicit, ordered "what to
   inspect before touching execution" list.

### Grounding
Fresh re-read of `pipeline/kling_apilena_api_executor.py` and `tools/
lena_bodylock_diagnostic_v1.py` (both already read in full earlier this
session) plus a first-time-this-session full read of `pipeline/
lena_production_job.py` and `tools/process_queue.py`. Confirmed the real call
chain directly from code: `lena_production_job.py`'s `run_lena_production()`
builds the daily manifest, then -- only if `CONTENT_BOT_KLING_EXECUTE` is
truthy -- imports and calls `pipeline.kling_apilena_api_executor.
run_executor()`, then packages outputs and runs preflight. `tools/
process_queue.py` was read and found to be a downstream publishing surface
(`PostingManager.process_queue()`), not a generation executor -- mentioned in
`AGENT.md`/`INPUTS.md` to mark the boundary, not given ownership here.

### What was explicitly not done
No code moved between files. No `.env` edit of any kind. No render. No Kling
API call. No publishing. The parked Kling Omni/BodyLock thread was not
reopened, advanced, or second-guessed -- this folder's `RULES.md` explicitly
states that documenting the pause is not authorization to end it.

### Next step
Not yet decided between a further folder-native slice (three now exist:
`40_identity_continuity/`, `70_visual_qa/`, `60_executor/`) or returning to
the original wrong-outfit/style question on the current live path via a
different diagnostic. The Kling Omni/BodyLock thread remains separately
parked, waiting on an external response to the support packet.

---

## 2026-07-06 — Fourth folder-native slice created: `pipeline/agents/lena/50_prompt_builder/`

### Direction
User approved `60_executor/` and directed the next branch: build the
folder-native prompt-builder slice, `pipeline/agents/lena/
50_prompt_builder/`, wrapping `pipeline/prompting/lena_prompt_brain.py`, the
prompt receipt fields used by `pipeline/kling_apilena_api_executor.py`, the
wardrobe/scene/framing/garment-obedience locks, and the known negative-
prompt budget issue. Explicit constraints: minimum five files, no code
moved, no `.env` edit, no render, no Kling call, no publish, do not fix the
negative-prompt budget yet, do not reopen the parked Kling Omni/BodyLock
thread.

### Files created
1. `pipeline/agents/lena/50_prompt_builder/AGENT.md` -- what this folder
   owns (source prompt/negative-prompt construction) and an explicit
   boundary statement with `60_executor/` (this folder does not own
   *compaction* -- that code physically lives in
   `kling_apilena_api_executor.py`).
2. `pipeline/agents/lena/50_prompt_builder/RULES.md` -- the core rule
   ("prompt correctness does not equal image correctness"), a real incident
   (a `"crop"` keyword false positive caused by a wording/matching-logic
   coupling issue from an earlier batch), and the exact negative-prompt
   budget numbers, explicitly marked "documented, not fixed."
3. `pipeline/agents/lena/50_prompt_builder/INPUTS.md` -- the three data
   files `lena_prompt_brain.py` reads (wardrobe catalog, environment
   catalog, photo scene bank), the real call chain
   (`tools/lena_prepare_daily_workorders_brain.py` -> `generate_prompt_
   package()` -> `apply_prompt_package_to_slot()`), and the seven-step
   assembly order.
4. `pipeline/agents/lena/50_prompt_builder/OUTPUTS.md` -- exactly which
   slot/metadata fields get written, a source-vs-compact-prompt comparison
   table, and a detailed breakdown of what the prompt receipt proves vs.
   does not prove.
5. `pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md` -- proof status
   of the construction/compaction machinery (validated -- not the source of
   the wrong-outfit/style-drift failures), and the exact negative-prompt
   overflow numbers.

### Grounding
Read `pipeline/prompting/lena_prompt_brain.py` directly (2834 lines total;
targeted reads of the header/constants block, `build_negative_prompt_for_
catalog()`, `build_public_lane_negative_prompt()`,
`public_wardrobe_continuity_lock()`, `catalog_outfit_is_sleeveless_top_skirt_
set()`, `framing_policy_for_mode()`, `generate_prompt_package()`, and
`apply_prompt_package_to_slot()` -- not a full linear read of all 2834
lines, but every function this slice's docs make a claim about). Confirmed
via `grep -rln` that the real, live caller of `generate_prompt_package()` /
`apply_prompt_package_to_slot()` is `tools/lena_prepare_daily_workorders_
brain.py` -- other matches in the repo (`patch_priority2_prompt_packages_
20260621.py`, `lena_publish_next_r2.py`, `strategy/
lena_generate_prompt_packages_v1.py`) are legacy/patch scripts, not the live
path. Measured `len(NEGATIVE_PROMPT)` directly in a live Python shell: exactly
**2734 characters**, confirming the figure already cited elsewhere in this
changelog and the master file was not a rounded guess.

### Key finding restated precisely
Base `NEGATIVE_PROMPT` constant: 2734 chars. Executor's
`NEGATIVE_PROMPT_MAX_CHARS`: 2499. **Overflow: 235 characters before a single
outfit-specific term is added** (`MIDRIFF_COVERAGE_NEGATIVE_SUFFIX`, or any
of the public-lane `extra_bits` from `build_public_lane_negative_prompt()`:
mirror-selfie, bathroom-selfie, bra-top, bikini-bodice, and outfit-class-
specific substitution terms). Exactly one reserved floor exists in the
executor (380 chars, Batch 7c) and it covers only the sleeveless-top-and-
skirt garment-obedience anti-substitution terms -- nothing else added by
`build_public_lane_negative_prompt()` has any protection at all. Documented
precisely in this slice; not fixed, per explicit instruction.

### What was explicitly not done
No code moved between files. No `.env` edit of any kind. No render. No
Kling API call. No publishing. The negative-prompt budget overflow was
measured and documented, not fixed. The parked Kling Omni/BodyLock thread was
not reopened, advanced, or referenced as something to resume -- `RULES.md`
restates the standing rule from `60_executor/RULES.md` that this folder's
existence is not grounds to revisit it.

### Next step
Not yet decided between a further folder-native slice (four now exist:
`40_identity_continuity/`, `50_prompt_builder/`, `60_executor/`,
`70_visual_qa/`), fixing the now-precisely-documented negative-prompt budget
overflow (its own dedicated decision, not a quiet patch), or returning to the
original wrong-outfit/style question on the current live path via a
different diagnostic. The Kling Omni/BodyLock thread remains separately
parked, waiting on an external response to the support packet.

---

## 2026-07-06 — Negative-prompt budget repair implemented (no render)

### Direction
User approved implementing the smallest safe fix from the negative-prompt
budget design memo. Explicit constraints: no render, no Kling call, no
publish, no `.env` edit, no reopening Kling Omni/BodyLock, no positive-prompt
change, no change to identity/wardrobe/scene/framing/positive-garment-
obedience locks. Exact scope: tiered constants in `lena_prompt_brain.py`,
reserved floors + receipt fields in `kling_apilena_api_executor.py`,
validated by `py_compile` + no-network dry-run across 6 outfit classes x
public/non-public lanes, preserving garment-obedience 11/11.

### Files changed
1. `pipeline/prompting/lena_prompt_brain.py`
2. `pipeline/kling_apilena_api_executor.py`
3. `pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md` (doc update)

### `lena_prompt_brain.py` -- exact change
Replaced the single flat `NEGATIVE_PROMPT` string (2734 chars, 139 terms)
with five tiered tuples:
- `CORE_NEGATIVE_TERMS` (21 terms, 321 chars) -- identity/face fundamentals,
  eye-color cluster, watermark/duplicate-person/extra-limbs.
- `STYLE_REALISM_NEGATIVE_TERMS` (29 terms, 516 chars) -- cartoon/anime/
  doll-like/CGI/3D-rendered/synthetic-skin cluster. Directly targets the
  exact failure category behind this session's real cartoon-style-drift
  render.
- `PUBLIC_SAFETY_NEGATIVE_TERMS` (11 terms, 240 chars) -- navel piercing/
  jewelry (deduplicated), shorts/hot-pants cluster, bra-as-outerwear/
  lingerie-in-public/bikini-as-streetwear/underwear-visible-outdoor.
- `BODY_ANATOMY_NEGATIVE_TERMS` (37 terms, 707 chars) -- body-distortion
  cluster (skinny/petite/narrow-hip/wasp-waist/etc.) + hand/anatomy cluster
  (deformed hands, extra/missing/fused fingers, bad anatomy, nail/knuckle
  variants).
- `OPTIONAL_FILL_NEGATIVE_TERMS` (39 terms, 904 chars) -- freckle/beauty-mark
  cluster, smile/lip nuance cluster, hotel-room/lighting scene-contamination
  cluster, clipping/limb-merging cluster.

`NEGATIVE_PROMPT = ", ".join(CORE + STYLE + PUBLIC_SAFETY + BODY_ANATOMY +
OPTIONAL_FILL)` -- reconstructed as the exact concatenation of all five
tiers in original order, so the constant's *value* and every consumer of it
are byte-compatible with before. Confirmed via `grep -rln "NEGATIVE_PROMPT\b"`
that no other file in the repo imports this constant's value (two other
files, `pipeline/lena_contract_workflow.py` and `pipeline/kling_apilena_
api_executor.py`, define their own unrelated local `NEGATIVE_PROMPT`
fallbacks from an env var, not imports of this one).

**Two terms dropped as confirmed exact-concept duplicates**, found by direct
indexed audit of the original 139-term list: `"navel piercing"` (index 137,
duplicate of `"belly button piercing"`, index 101) and `"belly button
jewelry"` (index 138, duplicate of `"navel jewelry"`, index 102). Verified
via a Python set-difference check (`orig_set - new_set`) that these are the
*only* two terms removed, and that zero terms were unexpectedly added --
confirmed dropped-terms set was exactly `{'belly button jewelry', 'navel
piercing'}` and added-terms set was empty. Result: 2734 -> 2696 chars, 139 ->
137 terms.

Two additional constants added, purely so the executor can use them as
floor-matching sets, **without touching `build_public_lane_negative_
prompt()`'s own inline assembly logic at all** (zero risk to what actually
gets added to the source string for any outfit/lane):
- `OUTFIT_SPECIFIC_SUBSTITUTION_TERMS` (29 terms) -- the union of the dress
  (3), crop-top (4), bodysuit (6), skirt (4), shorts (5), and outerwear (7)
  substitution-prevention terms already present inline in that function.
  Deliberately excludes the sleeveless-top-skirt garment-obedience terms,
  which are a separate, already-floor-protected class.
- `PUBLIC_LANE_SAFETY_TERMS` (6 terms) -- the clothing-safety subset of that
  function's always-added public-lane extras (`bra top`, `bikini-like
  bodice`, `triangle top`, `separated top and skirt when dress is
  specified`, `underbust exposed in public`, `bare midriff in public when
  dress is specified`). The 7 selfie-framing terms in the same inline list
  (`mirror selfie`, `phone held toward camera`, etc.) were deliberately
  excluded -- a composition preference, not a clothing-safety protection,
  per the design memo's own reasoning; they remain in the source string
  exactly as before, just not floor-protected.

### `kling_apilena_api_executor.py` -- exact change
Imported the five tiers plus the two matching-only constants from
`pipeline.prompting.lena_prompt_brain`. Added five floor-budget constants:
`CORE_NEGATIVE_FLOOR_CHARS=350`, `STYLE_REALISM_FLOOR_CHARS=550`,
`PUBLIC_SAFETY_FLOOR_CHARS=450`, `OUTFIT_SPECIFIC_SUBSTITUTION_FLOOR_
CHARS=400`, `BODY_ANATOMY_FLOOR_CHARS=750` -- each sized with headroom above
the tier's real measured content (verified: core 321, style 516, public-
safety up to 409 combined with lane extras, body-anatomy 707; outfit-
specific sized against the largest realistic double-class combination,
~341-356 chars). Confirmed by direct calculation that the four always-on
tiers' combined real content (1953 chars) leaves 546 chars of real headroom
under the 2499 cap even before the mutually-exclusive garment-obedience/
outfit-specific floor is considered -- the floor *caps* sum to more than
2499 (2880) by design, since they're ceilings, not simultaneous
reservations, and garment-obedience/outfit-specific rarely both have real
content in the same render.

Added a generic `_apply_negative_floor(term_set_lower, floor_chars)` helper
inside `_build_compact_negative_prompt()`, mirroring the pre-existing
garment-obedience floor's mechanism exactly: narrow, additive, never forces
consumption (a floor with zero matching source terms simply uses zero of its
budget, freeing that room for later floors/fill). Applied the five new
floors **strictly after** the pre-existing garment-obedience floor, whose
own code block is completely unchanged and untouched -- its available
budget and 11/11 survival behavior are identical to pre-repair production
behavior, verified by direct re-test.

Extended `_build_prompt_receipt()` with ~40 new fields: for each of the five
new floors, `negative_<floor>_terms_matched` / `_survived_count` / `_total`
/ `_present` / `_floor_reserved_chars` / `_floor_chars_used` / `_survived_
via_reserved_floor`, computed the same way the existing garment-obedience
negative fields already are -- by rescanning the final `compact_negative`
string directly (`term.lower() in compact_negative.lower()`), not by
trusting internal compaction-time state. Plus an optional-fill transparency
block (`negative_optional_fill_terms_included`, `_chars_used`, `_terms_
included_count`).

**Bug found and fixed during validation:** the first version of `negative_
optional_fill_reserved_chars` computed `NEGATIVE_PROMPT_MAX_CHARS - sum(all
six floor caps)`, which evaluated to **-381** (caps sum to 2880, over the
2499 total, by the design described above). A negative "reserved chars"
value would have been actively misleading in the receipt. Fixed to compute
from the *actual* chars consumed by each floor for that specific render
(`max(0, cap - sum(actual floor chars_used))`) -- always non-negative,
re-verified across all 12 test cases after the fix with no negative values
and `fill_used <= fill_reserved` holding in every case.

### Validation performed
1. `python -m py_compile pipeline/prompting/lena_prompt_brain.py
   pipeline/kling_apilena_api_executor.py` -- clean, twice (before and after
   the bug fix).
2. No-network dry-run: built slot dicts using the *real* `lena_prompt_
   brain.py` functions (`build_negative_prompt_for_catalog()`,
   `build_public_lane_negative_prompt()`) for 6 representative outfit
   classes (plain top, sleeveless-top+skirt, dress, bodysuit, shorts-set,
   outerwear) crossed with a real public lane and a synthetic non-public
   lane -- 12 cases total. Called `_build_compact_prompt()`,
   `_build_compact_negative_prompt()`, and `_build_prompt_receipt()` directly
   in-process -- zero network calls, zero credits, no render.
3. Confirmed for all 12 cases: `len(compact_negative) <= 2499` (measured
   range: 2488-2499). Core/style-realism/public-safety/body-anatomy floors
   all showed `survived_via_reserved_floor: true`. Garment-obedience
   remained 11/11 on its real test case (`sleeveless_top_skirt`/public),
   identical to pre-repair behavior. Outfit-specific-substitution floor
   showed non-zero survival on every public-lane case where its terms were
   actually present in source, and correctly zero (not a failure -- no
   applicable content) on non-public-lane cases, matching the pre-existing
   lane-gating this repair did not touch.
4. One partial-degradation case identified and accepted as expected, not a
   bug: `sleeveless_top_skirt`/public (the single render simultaneously
   needing all six floors -- core, style, public-safety, garment-obedience,
   outfit-specific, and body-anatomy at once) trimmed body-anatomy from
   37 to 32 surviving terms under real budget contention.
   `survived_via_reserved_floor` remained `true` (32 > 0) throughout --
   substantial, non-zero protection was still guaranteed, just not literally
   every term, which is the correct behavior for a floor under genuine
   multi-class contention.
5. `git status --short .env` returned empty at every check -- `.env` never
   touched. `find pipeline/kling_debug -newer pipeline/prompting/
   lena_prompt_brain.py` returned empty -- no render/debug artifacts created
   by the dry-run calls.

### What was explicitly not done
No code moved between unrelated files (only the two files above touched,
plus one doc update). No `.env` edit of any kind. No render. No Kling API
call. No publishing. No change to positive-prompt content, wardrobe/scene/
framing locks, or the positive-side garment-obedience lock sentence
(`public_wardrobe_continuity_lock()` and `_build_compact_prompt()` are
completely untouched). The parked Kling Omni/BodyLock thread was not
touched, reopened, or referenced as something to resume.

### Unresolved risks
- Whether this repair changes real image output on Kling is completely
  untested -- no render has been run. The repair guarantees more negative-
  prompt content reaches the submitted payload; it cannot, from a no-render
  validation alone, prove Kling honors that content any better than before
  the repair.
- `sleeveless_top_skirt`/public showed real, measured six-floor contention
  (body-anatomy trimmed to 32/37) -- worth watching if a future outfit class
  needs even more simultaneous protection than today's six classes.
- `OUTFIT_SPECIFIC_SUBSTITUTION_TERMS` and `PUBLIC_LANE_SAFETY_TERMS`
  duplicate content that also lives inline in `build_public_lane_negative_
  prompt()` -- an intentional, documented tradeoff (keeps that function's
  assembly logic byte-for-byte unchanged) but a real drift risk if those
  inline lists are ever edited without updating the matching constants,
  same category of risk as the pre-existing garment-obedience term
  duplication this repair left untouched.
- The always-on tier assignments (which term belongs to "core" vs. "style"
  vs. "optional fill") reflect a considered design judgment from the memo,
  not an empirically-validated categorization.

### Recommendation on a future one-image proof render
**Recommended, not run, not approved.** A single controlled proof render on
a previously-tested slot (e.g. `2026-07-05-02-photo`/wc_p082, which has three
documented wrong-outfit/style-drift failures this session under the
pre-repair negative prompt) would allow a direct before/after comparison of
the same outfit/scene under the repaired path. This is the logical next
diagnostic step. It requires the user's separate, explicit approval and is
not authorized by this implementation step alone.

### Next step
Waiting on the user's decision: approve the recommended one-image proof
render, pick a further folder-native slice, or return to the original
wrong-outfit/style question via a different diagnostic. The Kling Omni/
BodyLock thread remains separately parked, waiting on an external response
to the support packet.

---

## 2026-07-06 — Negative-prompt repair proof render: RUN, result FAIL (4th consecutive wrong-outfit miss)

### Direction
User approved the recommended proof render: exactly one controlled image on
the same previously-failed comparison slot, `2026-07-05-02-photo`/wc_p082,
current `/v1/images/generations` path only. Purpose: test whether the
repaired negative prompt improves the current working path. Explicit rules:
exactly one image, current path only, no Omni/BodyLock, no `.env` edit, no
publish, no batch, no alternate endpoint, no alternate element ID, save
artifacts normally, run visual QA honestly. Explicit pre-render verification
required: floors survived, compact negative <=2499, correct slot, correct
element, no `image_list`, no Omni/BodyLock path.

### Keeping this a true single-variable comparison
The real slot JSON still held its original pre-repair `negative_prompt`
(4189 chars, written 2026-07-05) -- the code repair changes what a *fresh*
prompt-build would produce, not what's already serialized on disk. Tested
whether re-running `generate_prompt_package()` for the exact same
`date_str`/`slot_id`/`media_type` would reproduce the original outfit/scene:
it did not -- the deterministic RNG seed is stable, but the wardrobe catalog
and scene bank pools it selects from have changed since 2026-07-05, so the
same seed now lands on a different outfit (`wc_p084`/`env_e004`/"car moment"
instead of `wc_p082`/`env_s006`/"city bench"). Regenerating fully would have
silently changed the outfit under test, breaking the comparison against the
3 prior failures. Instead: looked up the `wc_p082` catalog entry directly
via `load_wardrobe_catalog()`, rebuilt only its `negative_prompt` via
`build_negative_prompt_for_catalog()` + `build_public_lane_negative_prompt()`
(confirmed the slot's lane, `"city bench"`, is in `PUBLIC_SOCIAL_LANES`),
and patched only the `negative_prompt` field (plus its `metadata.
negative_prompt` duplicate) into the real workorder JSON via a small,
targeted Python script -- not the Edit/Write tool on the JSON directly (this
repo's established practice for JSON safety), and not a re-run of the full
`tools/lena_prepare_daily_workorders_brain.py` batch pipeline (which would
have touched other slots too, violating "do not run a batch"). `image_prompt`
and every other field verified byte-identical to the original after the
patch (`image_prompt`: 10668 chars, unchanged; `wardrobe_outfit_id`: `wc_p082`,
unchanged; `environment_id`: `env_s006`, unchanged).

### Pre-flight verification (before rendering, all 6 items from the user's checklist)
Ran the real patched slot through `_build_compact_prompt()`,
`_build_compact_negative_prompt()`, and `_build_prompt_receipt()` directly,
no network:
1. **Negative floors survived:** core 21/21, style-realism 29/29, public-
   safety 17/17, outfit-specific 7/29, body-anatomy 32/37, garment-obedience
   11/11 -- all `survived_via_reserved_floor: true`.
2. **Compact negative <=2499:** measured 2496 chars.
3. **Correct slot:** `wardrobe_outfit_id: wc_p082`, `environment_id: env_s006`
   confirmed in the receipt, matching the original.
4. **Correct APILENA element:** confirmed via the live element lookup at
   render time (below).
5. **No `image_list`:** guaranteed by the executor's code, which never
   constructs this key -- confirmed absent in the real `submit_payload.json`
   after the render.
6. **No Omni/BodyLock path:** `endpoint_used` in the receipt resolved to
   `https://api.klingai.com/v1/images/generations`, not `/v1/images/omni-
   image`.
Also confirmed `KLING_LENA_ELEMENT_IMAGE_URLS_JSON` /
`KLING_LENA_ELEMENT_IMAGE_URLS` absent from `.env` (presence-only check, no
values printed).

### The render
```
CONTENT_BOT_KLING_TARGET_SLOT_ID=2026-07-05-02-photo CONTENT_BOT_KLING_MAX_SLOTS=1 CONTENT_BOT_KLING_EXECUTE=1 python pipeline/kling_apilena_api_executor.py 2026-07-05
```
Exactly one slot processed (`"processed_slots": 1`). Task
`903248497381220361` succeeded. `result_manifest.json`: `element_id:
"315187972322559"`, `element_name: "APILENA"`, `provider_endpoint:
"https://api.klingai.com/v1/images/generations"`, `payload_no_image_list:
true`, `live_apilena_image_count: 4`. `prompt_receipt.json` reproduced every
pre-flight prediction exactly, character for character.

### A. Artifact folder
`pipeline/kling_debug/apilena_api/2026-07-05/2026-07-05-02-photo/` --
`submit_payload.json`, `submit_response.json`, `poll_response.json`,
`prompt_receipt.json`, `result_manifest.json`,
`live_apilena_lookup_response.json` (all overwritten with this render's real
data, superseding the 3rd-failure artifacts from earlier this session).
Generated image: `pipeline/kling_library/lena/2026-07-05/2026-07-05-02-
photo_seed.png`.

### B. Submitted prompt/negative-prompt survival summary
Compact prompt: 2498 chars (positive-side floors all present: scene-
environment, wardrobe-continuity, framing-directive, garment-obedience-lock
-- confirming the positive prompt was genuinely untouched by this repair, as
required). Compact negative prompt: 2496 chars. Negative-side floor survival
exactly as pre-flight-verified: core 21/21, style-realism 29/29, public-
safety 17/17, outfit-specific 7/29, body-anatomy 32/37, garment-obedience
11/11. `negative_prompt_terms_survived: 117` of `182` unique source terms
(`negative_prompt_terms_dropped: 65` -- all from the unprotected optional-
fill tier, exactly as designed).

### C. Visual result
Downloaded and viewed the actual generated image directly (768x1344,
resized for viewing). The subject: reddish-auburn/copper wavy hair, lighter
amber-brown eyes, light plausible freckling, glossy/smooth/idealized skin
and features (not literal cartoon, but not clean photoreal camera realism
either), wearing a mustard/yellow coat over a gray top with a mustard knit
scarf, holding a paper coffee cup, seated on a bench against a blurred urban
street background with pedestrians and greenery.

### D. Whether outfit improved
**No.** Fourth consecutive miss on this exact slot. Specified: white ribbed
tank top + black leather mini skirt + tall black boots + narrow sunglasses +
small gold hoops. Rendered: a mustard coat + scarf over a gray top --
skirt/boots/sunglasses/hoops entirely absent/unverifiable. Same structural
failure category (an unspecified outerwear layer replacing/covering the
named top) as the two prior wrong-outfit misses (previously a trench coat,
then a turtleneck sweater).

### E. Whether cartoon/style drift improved
**Yes, measurably.** This render is not a cartoon/anime/3D-illustration
failure, unlike the 3rd pre-repair render on this same slot. It does still
show a glossy, airbrushed, idealized "beauty-filter" quality (very smooth
poreless skin, glossy lips, over-clean facial geometry) that falls short of
clean photoreal camera realism, despite the relevant negative terms
(`poreless face`, `beauty filter skin`, `over-clean facial geometry`, all in
`STYLE_REALISM_NEGATIVE_TERMS`) being confirmed present in the submitted
negative prompt (29/29 survived). Partial improvement, not a clean pass.

### F. Pass/fail
Wrote a fresh, honest QA verdict to `pipeline/asset_review/lena/2026-07-05/
2026-07-05-02-photo_qa.json`, explicitly superseding the stale 3rd-failure
verdict (stale-QA-file lesson), validated via `lena_photo_qa.
validate_qa_result()` (passed, no false-green inconsistency): **overall
FAIL.** Failing checklist items: `wardrobe_class_fidelity` (4th consecutive
miss), `identity_fidelity` (hair/eye-color drift), `face_realism_anti_
generic_drift` (improved but not clean). Passing: `skin_realism_no_
invented_marks`, `public_scene_clothing_continuity`, `outerwear_underlayer_
correctness`, `hands_anatomy_sanity`, `environment_realism_scene_coherence`,
`caption_scene_coherence`. Not applicable: `body_shape_continuity`
(obscured by the coat).

### G. Stop, repair, or abandon this current Kling proof lane
**Recommendation, not a unilateral decision: stop iterating on prompt
content for this specific failure, at least for now.** With negative-prompt
protection now near-maximal and explicitly confirmed present in the
submitted payload -- and the model still substituting an unspecified
outerwear garment for the named top, a 4th consecutive time on this exact
slot -- this is strong further evidence the wrong-outfit failure is model/
provider-level, not something more prompt engineering on the current
`/v1/images/generations` path will fix. The style/cartoon-drift improvement
is real and worth keeping (the repair stays merged regardless), but it does
not carry over to wardrobe fidelity. The most promising path to actually
fixing wardrobe fidelity may be the parked Kling Omni/BodyLock thread
(external support response still pending) rather than further changes on
this path. Not deciding this unilaterally -- presented to the user as the
next decision point.

### What was explicitly not done
No `.env` edit (confirmed via `git status --short .env`, empty, both before
and after the render). No batch -- exactly one slot processed, confirmed via
`"processed_slots": 1` in the executor's own output and the
`CONTENT_BOT_KLING_MAX_SLOTS=1` + target-slot-filter combination. No
alternate endpoint or element ID -- both confirmed via the receipt/manifest
to be the current live path (`/v1/images/generations`) and the current live
element (`315187972322559`/APILENA). No Omni/BodyLock path touched,
referenced, or reopened. No publishing.

### Next step
Not yet decided: whether to treat the wrong-outfit failure as a provider-
level limit and stop further prompt-side iteration on it, pick a further
folder-native slice, or wait on the parked Kling Omni/BodyLock thread's
external response as the more promising path to actually fixing wardrobe
fidelity. Ask before proceeding on any of these.

---

## 2026-07-06 — Final classification accepted: negative-prompt repair retained; wardrobe-obedience prompt iteration stopped

### Direction
User accepted the proof-render result (FAIL on wardrobe, improved on style)
as the final word on this thread and gave an explicit, 5-point closing
classification:
1. Negative-prompt repair is retained -- not reverted, not provisional.
2. It improved style-realism protection (confirmed on the one render
   tested: no cartoon/3D-illustration drift, unlike the pre-repair 3rd
   render on the same slot).
3. It did not solve exact wardrobe obedience -- 4th consecutive outfit-
   class failure on `wc_p082`.
4. The current Kling `/v1/images/generations` path is usable only as
   quality-limited/proof-limited, not trusted for final, exact wardrobe
   production.
5. The next meaningful fix, if pursued, is a provider/conditioning strategy
   change, not more prompt tweaking.

Explicit standing rules restated: do not rerender this slot, do not do
another prompt patch aimed at wardrobe obedience, do not reopen Kling
Omni/BodyLock, do not touch `.env`, do not publish.

### Files updated (documentation only -- no code touched this turn)
1. `pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md` -- fully
   rewritten. The prior version was stale, still describing "three
   consecutive renders" and stating Branch 2 investigation "has not
   started" (both true as of an earlier point in this session, neither true
   now). Rewrote to state: four renders total (with the exact per-render
   history), the negative-prompt repair as implemented/proof-tested/
   retained (not a separate unresolved finding anymore), and the 5-point
   final classification verbatim, including explicit "what should NOT be
   retried blindly" and "paused / stopped, not abandoned" sections
   distinguishing the closed wardrobe-obedience thread from the still-
   parked, still-open Kling Omni/BodyLock thread.
2. `pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md` -- added a
   "Proof-render result (2026-07-06) -- FINAL CLASSIFICATION, repair
   retained" section immediately after the negative-prompt-budget section,
   replacing the prior "what is NOT currently proven -- no image has been
   generated to test this" framing (now answered) with the actual result
   and the accepted 5-point conclusion.
3. `pipeline/change_notes/NEXT_SESSION_START.md` -- added a "FINAL, ACCEPTED
   CLASSIFICATION" bullet at the top of the negative-prompt-repair history,
   stating all 5 points plainly, followed by the existing detailed proof-
   render bullet (kept for full technical detail). Rewrote "Exact next
   approved action" to state this thread is settled and closed rather than
   an open decision awaiting the user.
4. `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` §0
   -- "Current blocker," "Current proof status," "Next approved step," and
   "What must NOT be done next" all updated to state the classification as
   final and accepted, not a pending recommendation. Tightened the
   "do not rerender" and "do not re-patch for wardrobe obedience"
   prohibitions from soft hedges into explicit, user-confirmed, settled
   rules. Appended a new dated §14 entry (this same content, master-file
   version).

### What was explicitly not done
No code changed -- this was a documentation-only turn, closing out the
classification in every place it's tracked. No render. No `.env` edit. No
Kling call. No publish. The negative-prompt repair's actual code
(`lena_prompt_brain.py`'s tiered constants, `kling_apilena_api_executor.py`'s
six reserved floors) was not touched -- it remains exactly as implemented
and proof-tested, now formally retained rather than provisional. Kling
Omni/BodyLock was not reopened, referenced, or treated as something to
resume.

### Next step
Not yet decided: what to work on next, now that the wrong-outfit/negative-
prompt thread is closed and Kling Omni/BodyLock remains separately parked
pending an external response. Ask before proceeding.

---

## 2026-07-06 — Production QA standard corrected: exact wardrobe obedience demoted to diagnostic-only

### Direction
User issued an important, standing correction: exact wardrobe obedience had
been over-weighted this entire session as an automatic production failure.
It's a useful diagnostic (does the model literally follow the catalog
outfit text?), but it is not the actual production goal for Lena photos.

**Corrected production goal, given in full:** varied Lena photos, different
outfits over time, sexy/high-hook/viewer-grabbing, somewhat-to-moderately
revealing, platform-safe, realistic enough, coherent scene, close-enough
identity continuity, no obvious AI/cartoon/anatomy failure.

**A wardrobe substitution is acceptable** if the result is still stylish,
sexy/hooky, platform-safe, not frumpy, not boring, not repetitive, not
incoherent with the scene, and not identity-breaking. "White tank + black
mini skirt became coat/scarf" is not, by itself, an automatic production
failure.

**Hard rejects (the real production blockers):**
- Cartoon/illustration/obvious AI look
- Broken anatomy/bad hands/extra limbs
- Face identity badly off
- Boring/frumpy/non-hook outfit
- Outfit too covered or not visually compelling
- Too explicit/unsafe
- Scene makes no sense
- Same outfit/pose/location formula repeating (across posts -- not the same
  as retesting one diagnostic slot multiple times)
- Caption and image totally mismatched
- Low-quality/fake-looking output

**New production priority order:** (1) hook strength, (2) outfit variety,
(3) sexy but platform-safe styling, (4) realism, (5) identity continuity,
(6) scene variety, (7) caption/image coherence, (8) exact wardrobe
obedience -- diagnostic only, not a normal production gate.

Explicit constraints for this turn: no render, no Kling call, no `.env`
edit, no publish, no prompt-code change yet -- documentation-only
correction, applied to seven named files.

### Files updated (documentation only -- no code touched this turn)

1. **`pipeline/agents/lena/70_visual_qa/RULES.md`** -- this is the primary
   home for the corrected standard now. Added a full "Production QA
   standard correction" section right after the stale-QA-file lesson (now
   equally foundational reading), containing the corrected standard,
   priority order, and hard-reject list verbatim. Edited the "what counts as
   false-green" section: previously named three fields
   (`identity_fidelity`, `wardrobe_class_fidelity`, `public_scene_clothing_
   continuity`) that must be a deliberately-confirmed `pass` for any overall
   `pass` -- removed `wardrobe_class_fidelity` from that list, since a
   literal catalog-string mismatch is no longer, by itself, grounds to fail
   a render. Added an explicit, honest flag: `pipeline/qa/lena_photo_qa.py`'s
   actual code (`QA_CHECKLIST_FIELDS`, `validate_qa_result()`) has **not**
   been updated to match this corrected standard -- the checklist still
   treats any item's `fail` (including `wardrobe_class_fidelity`) as forcing
   `overall: fail`. This is a real, named gap between doc and code, not
   silently smoothed over -- a human/Claude reviewer must apply the
   corrected standard manually until the schema itself is updated (a
   separate, future, code-level decision). Added the schema-update question
   to "Not yet decided / not yet built."

2. **`pipeline/agents/lena/70_visual_qa/CURRENT_STATE.md`** -- added a
   "Production QA standard corrected" section at the top, before the proof-
   status section, stating the correction and its exact scope: historical
   QA JSON files (e.g. `pipeline/asset_review/lena/2026-07-05/2026-07-05-
   02-photo_qa.json`) are **not** being retroactively rewritten -- they
   remain accurate records of what was concluded under the standard in
   force when they were written. This file adds documented
   *reinterpretation* alongside them, not a rewrite of history. Reinterpreted
   the most recent real verdict (`2026-07-05-02-photo`, 4th render) inline,
   field by field: `wardrobe_class_fidelity: fail` is not itself
   disqualifying under the corrected standard -- the real concern is that
   the mustard coat+scarf substitution reads as more covered and lower-hook
   than the production goal calls for ("outfit too covered or not visually
   compelling" is a corrected-standard hard reject in its own right, just a
   narrower and more specific one than "didn't match the catalog"). The
   identity drift (hair/eye color) and residual style-realism softness
   remain real, independent concerns under either standard -- not waved
   away by this correction. Added two items to "what is not currently
   proven": whether any render this session would pass the corrected
   standard in full (hook strength, outfit variety, and sexy-but-safe
   styling have never been formally scored on any render), and whether the
   QA schema will be updated to natively support the corrected standard.

3. **`pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md`** -- added a
   "Production standard correction" section directly after the negative-
   prompt repair's "FINAL CLASSIFICATION" section, narrowing but not
   reversing it. The repair's own conclusion is unaffected: style-realism
   protection measurably improved, confirmed on the one render tested, and
   this is retained regardless of the standard correction. What changes is
   the *reason* the 4th render's outcome matters: not "wardrobe obedience
   failed" as a production-blocking fact, but "this specific substitution
   happened to also fail the corrected standard's coverage/hook bar," which
   is a narrower, more falsifiable claim. Prompt correctness still does not
   equal image correctness under either standard -- that core rule is
   unaffected by this correction.

4. **`pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md`** -- added a
   prominent "Production standard correction" section immediately after the
   file's purpose/grounding statement, before "What was validated," so it's
   the first substantive thing anyone reads in this file going forward.
   States plainly that every section below it (What failed, Classification,
   Paused/stopped) was written under the prior, now-corrected standard, and
   is preserved as historical record, not rewritten. Added a same-day
   addendum inline in the "Classification" section: "not trusted for final,
   wardrobe-exact production" should not be read as "this path can't be used
   for production" -- exact wardrobe fidelity was never the real production
   bar, and whether typical outputs on this path clear the *corrected* bar
   has not been formally assessed. That assessment, not more wardrobe-
   exactness testing, is named as the right next evaluation.

5. **`pipeline/change_notes/NEXT_SESSION_START.md`** -- added a second
   standing banner, STANDARD CORRECTION, at the very top of the file, above
   the existing PARKED (Kling Omni/BodyLock) banner -- this is now the
   first thing any future session reads, containing the full corrected
   standard, priority order, and hard-reject list, plus an explicit note
   that `pipeline/qa/lena_photo_qa.py` has not been updated to match yet.
   Updated the FINAL, ACCEPTED CLASSIFICATION bullet (from the negative-
   prompt repair closure) to cross-reference this banner and narrow points
   3 and 4 (wardrobe obedience / production-viability) rather than leaving
   them stated as if the old standard still applied. Updated "Exact next
   approved action" to add the QA-schema-update candidate as a live option.
   Fixed a stale cross-reference ("three consecutive fails") to the correct
   current count ("four"). Added an explicit "Hard prohibitions" item: do
   not judge any future render's production-worthiness by exact catalog-
   wardrobe match.

6. **`pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md`**
   §0 -- added the STANDARD CORRECTION callout directly under "Last
   updated" (mirroring the PARKED banner's visual weight), narrowed the
   "Current proof status" section with an addendum bullet, updated "Next
   approved step" to include the QA-schema-update candidate, and added two
   new "What must NOT be done next" items: don't claim the current path is
   validated for corrected-standard production (it hasn't been assessed),
   and don't judge future renders against exact wardrobe match. Appended a
   full, matching §14 entry (this same content, master-file phrasing).

### What was explicitly not done
No code changed -- `pipeline/qa/lena_photo_qa.py`'s `QA_CHECKLIST_FIELDS`
and `validate_qa_result()`, `pipeline/prompting/lena_prompt_brain.py`, and
`pipeline/kling_apilena_api_executor.py` are all untouched. The QA-schema-
update candidate is flagged as a real gap, not built. No render. No `.env`
edit. No Kling API call. No publishing. No historical QA JSON file rewritten
-- the correction is additive commentary layered alongside the historical
record, not a retroactive edit to it.

### Next step
Not yet decided: whether to update `pipeline/qa/lena_photo_qa.py`'s
checklist schema to natively score the corrected standard (a real code
change requiring separate, explicit approval), pick a further folder-native
slice, or something else entirely. Ask before proceeding.

---

## 2026-07-06 — Two session-continuity skills created (convenience wrappers only)

### Direction
User asked for two Claude Code skills to make the recurring session-start
and session-checkpoint procedures (already fully specified in
`NEXT_SESSION_START.md`) one-command instead of manually re-derived from
the continuity files each time. Explicit constraints: pointer-based only,
no new doctrine, no duplication of repo doctrine inside the skills, exactly
two skills and no more, no render/provider-call/`.env`-edit/publish/
routing-change as part of building them.

### What was built
1. `.claude/skills/lena-session-start/SKILL.md` — instructs Claude to read,
   in order, `NEXT_SESSION_START.md` in full (both banners), whatever that
   file's own "Read these first" list points to, this master file's §0, and
   the changelog's latest dated entry; to do no code/render/publish/`.env`
   edit/provider call before finishing; then to summarize current state,
   last completed step, blockers/parked branches, exact next approved step,
   and hard prohibitions, grounded only in what was just read.
2. `.claude/skills/lena-session-checkpoint/SKILL.md` — instructs Claude to
   stop new work, then update (in order) `NEXT_SESSION_START.md`, this
   master file (append a dated entry, don't rewrite doctrine), this
   changelog (append, never rewrite), and any touched
   `pipeline/agents/lena/*/CURRENT_STATE.md`, recording what changed, files
   changed, validations run, decisions made, blockers/parked branches, next
   approved step, and what must not be done — then report a clean summary.

Both skills state explicitly, near the top, that they are pointer-only:
they carry no repo doctrine, name `NEXT_SESSION_START.md`, this master
file, and this changelog as the sources of truth, and instruct Claude to
trust the live repo files over the skill if the two ever disagree.

### Files updated to record this
- `pipeline/change_notes/NEXT_SESSION_START.md` — added a short "Session
  skills (convenience wrappers, not source of truth)" section naming both
  skill files and stating they defer to the continuity files.
- `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` —
  appended a new §14 dated entry (this same content, master-file phrasing).
- This changelog entry.

### What was explicitly not done
No repo doctrine was duplicated into the skill files — both are short and
pointer-based. No other skills were created. No code changed, no render, no
Kling/OpenArt/Seedance call, no `.env` edit, no publish, no production
routing change.

### Next step
Unchanged: not yet decided whether to update the QA checklist schema, pick
a further folder-native slice, or something else. Ask before proceeding.

---

## 2026-07-06 — Visual QA code updated to match the corrected production standard (audited, approved, implemented)

### Direction
User asked for a read-only audit first (A-F: read the file, identify exactly
where wardrobe mismatch forces a fail, propose the smallest schema/code
change, explain the new verdict behavior, explain how diagnostic wardrobe
tests stay possible, then wait for approval). Audit was delivered; user then
approved implementing exactly the proposed smallest change, explicitly
scoped to only the wardrobe-gating fix (new dimensions for hook strength /
outfit variety / sexy-safe styling / scene variety explicitly deferred), with
standing constraints: no render, no provider call, no `.env` edit, no
publish, no prompt/executor/routing change, no reopening Kling Omni/BodyLock.

### Audit findings (read-only, before any edit)
- `pipeline/qa/lena_photo_qa.py` line 34 (pre-change numbering): `wardrobe_
  class_fidelity` was an ordinary entry in `QA_CHECKLIST_FIELDS`, no different
  from any hard-reject field.
- Lines 124-133 (pre-change numbering), inside `validate_qa_result()`: the
  `any_failed` computation iterated the full `QA_CHECKLIST_KEYS` tuple
  (including wardrobe), and forced a validation error whenever `overall` was
  `pass` while any field -- including wardrobe -- was `fail`. This is the
  exact mechanical point that made `wardrobe_class_fidelity: fail` alone
  sufficient to block recording `overall: pass`, confirmed against the real
  4th-render `wc_p082` QA file where wardrobe was the first-listed
  `failure_reasons` entry.
- Confirmed blast radius: the only other consumer of this module,
  `tools/lena_review_proof_render_v1.py`, only reads `qa_result.get(
  "overall")` as a passthrough string and never touches individual checklist
  keys -- unaffected by the change.
- Confirmed this matches already-agreed doctrine: `pipeline/agents/lena/
  70_visual_qa/RULES.md` already named this exact gap and already required
  human approval before touching `QA_CHECKLIST_FIELDS` or the false-green
  rules.

### Code change implemented
`pipeline/qa/lena_photo_qa.py`:
1. Added `DIAGNOSTIC_ONLY_CHECKLIST_KEYS: Tuple[str, ...] = (
   "wardrobe_class_fidelity",)` and `HARD_GATING_CHECKLIST_KEYS: Tuple[str,
   ...]` (every other existing checklist key, computed by exclusion), with a
   one-line comment pointing at `70_visual_qa/RULES.md`'s "Production QA
   standard correction" section rather than duplicating doctrine into code.
2. Reworded only the human-readable label on `wardrobe_class_fidelity` in
   `QA_CHECKLIST_FIELDS` to state it's diagnostic-only/non-gating. The key
   itself, its position, and every other field's key/label are byte-for-byte
   unchanged.
3. Changed the `any_failed` computation inside `validate_qa_result()` to
   iterate `HARD_GATING_CHECKLIST_KEYS` instead of `QA_CHECKLIST_KEYS`.
   Nothing else in the function changed: the per-key status-validity loop,
   the `overall` allowed-values check, and the `fail` requiring
   `failure_reasons` check are all untouched.

No new field was added. No field was removed or renamed. `QA_CHECKLIST_
FIELDS`/`QA_CHECKLIST_KEYS` are identical in count, order, and keys to
before -- existing QA JSON files require no migration.

### Validation performed
- `python -m py_compile pipeline/qa/lena_photo_qa.py` -- clean.
- Reloaded the real on-disk QA file
  (`pipeline/asset_review/lena/2026-07-05/2026-07-05-02-photo_qa.json`,
  `overall: fail`, driven by `identity_fidelity` and other fields beyond
  wardrobe) through `validate_qa_result()` -- still validates cleanly,
  unchanged, confirming no regression on a real historical record.
- Wrote a standalone script (not committed to the repo; run from the session
  scratch directory) that:
  - Confirmed `HARD_GATING_CHECKLIST_KEYS` ∪ `DIAGNOSTIC_ONLY_CHECKLIST_KEYS`
    == `QA_CHECKLIST_KEYS`, and that `wardrobe_class_fidelity` is in the
    diagnostic set and not in the hard-gating set.
  - **Check A:** built a QA result with every field `pass` except
    `wardrobe_class_fidelity: fail`, `overall: pass` -- `validate_qa_result()`
    returned `(True, [])`, confirming a wardrobe-only fail no longer blocks
    an overall pass.
  - **Check B:** for each of the 9 `HARD_GATING_CHECKLIST_KEYS` in turn, built
    a QA result with that one field `fail` and everything else `pass`,
    `overall: pass` -- `validate_qa_result()` correctly rejected all 9 (still
    a false-green error), and a matching `overall: fail` + `failure_reasons`
    verdict for the same field was correctly accepted. Zero regressions
    across all 9 fields.
  - Printed `ALL CHECKS PASSED`.
- No render, no Kling/OpenArt/Seedance call, no `.env` edit, no publish, no
  change to `lena_prompt_brain.py`, `kling_apilena_api_executor.py`, or any
  routing/scheduling code.

### What was explicitly deferred (per the approved scope)
Dedicated checklist fields for `hook_strength`, `outfit_variety`,
`sexy_safe_styling`, and `scene_variety` were **not** added -- flagged in
`70_visual_qa/RULES.md` as a separate, larger, future change requiring its
own explicit approval, exactly as scoped by the user's approval message.

### Files updated
1. `pipeline/qa/lena_photo_qa.py` -- the actual code change (see above).
2. `pipeline/agents/lena/70_visual_qa/CURRENT_STATE.md` -- new "QA code
   updated to match the corrected standard" section with the full validated
   detail; updated "What is NOT currently proven" to reflect the gating fix
   is done while the four new dimensions remain unbuilt.
3. `pipeline/agents/lena/70_visual_qa/RULES.md` -- closed the "Known gap, not
   yet fixed" note (now "Gap partially closed... implemented"), updated the
   false-green section to say the wardrobe exclusion is now code-enforced
   (not just doctrine), and updated the "Not yet decided / not yet built"
   list to mark the gating removal done and narrow the remaining item to the
   four new dimensions.
4. `pipeline/change_notes/NEXT_SESSION_START.md` -- added a "Current state"
   bullet documenting the implemented fix and validation; resolved the "New
   candidate next step" text from an open proposal into a "DONE" statement,
   keeping only the four deferred dimensions and the next-slice choice as
   genuinely open.
5. `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` --
   appended a new dated §14 entry (this same content, master-file phrasing).
6. This changelog entry.

### Next step
Not yet decided: whether to add the four deferred checklist dimensions (hook
strength / outfit variety / sexy-safe styling / scene variety), pick a
further folder-native slice, or something else. Ask before proceeding.

---

## 2026-07-06 — Hook/Variety QA schema v2 implemented (design memo approved, then built)

### Direction
Following the wardrobe-gating fix, the user asked for a no-code design memo
(A-I: new fields vs. separate block, gating vs. advisory per field, scoring
method, pass/fail criteria per dimension, interaction with existing
hard-gating fields, avoiding over-rejection, future formula-repetition
detection, files needing updates, no-render validation) covering how to
natively score hook strength, outfit variety, sexy-but-platform-safe
styling, and scene variety. The memo was delivered and approved with one
explicit decision resolved: use `schema_version: "2"` for new records,
keep all `schema_version: "1"` records valid without migration. The user
then approved implementing exactly that design, with the same standing
constraints as before (no render, no provider call, no `.env` edit, no
publish, no prompt/executor/routing change, variety tracker and history-
reading logic explicitly not to be built yet).

### Design recap (from the approved memo)
- **A.** Separate sibling block (`production_scoring`), not new entries in
  `QA_CHECKLIST_FIELDS` -- different kind of judgment (holistic/subjective),
  and two of the four dimensions aren't single-render properties at all.
- **B.** `hook_strength` and `styling_sexy_platform_safe` hard-gating;
  `outfit_variety_vs_recent_posts` and `scene_variety_vs_recent_posts`
  advisory only (no history-comparison mechanism exists to score them
  honestly yet).
- **C/D.** `hook_strength` scored on a 3-tier enum (`weak`/`moderate`/
  `strong`) with only `weak` gating, to avoid requiring every image to be a
  home run; `styling_sexy_platform_safe` scored pass/fail covering both
  named hard-reject extremes (too covered/frumpy vs. too explicit/unsafe);
  variety fields scored pass/fail/`not_yet_measured` with no gating effect.
- **E.** New gating checks are additive to `validate_qa_result()` --
  existing checklist logic (identity, anatomy, clothing continuity, etc.)
  is completely untouched.
- **F.** Over-rejection avoided via the 3-tier hook score (only the bottom
  tier fails) and by keeping variety fields advisory until a real tracker
  exists.
- **G.** Formula-repetition detection (outfit/pose/location) is a future,
  separate history-reading module, not built now -- sketched as a working
  name (`pipeline/qa/lena_variety_tracker.py`) in the memo, not implemented.
- **H/I.** Named the exact files needing updates and the exact
  no-render validation plan, both followed below.

### Code change implemented
`pipeline/qa/lena_photo_qa.py`:
1. `SCHEMA_VERSION` changed from `"1"` to `"2"`. Added
   `LEGACY_SCHEMA_VERSIONS_WITHOUT_PRODUCTION_SCORING = {"1"}` -- any QA
   record stamped with a legacy version in that set is validated under the
   original rules only; `production_scoring` is not required and its
   absence is not an error for those records. Existing on-disk files are
   never rewritten to `"2"` -- this only affects newly built templates.
2. Added `ALLOWED_HOOK_STRENGTH_VALUES = {"weak", "moderate", "strong",
   "unreviewed"}` and `ALLOWED_VARIETY_STATUS_VALUES = {"pass", "fail",
   "not_yet_measured", "unreviewed"}` (styling reuses the existing
   `ALLOWED_STATUS_VALUES`).
3. Added `PRODUCTION_SCORING_FIELDS` / `PRODUCTION_SCORING_KEYS` (4 fields:
   `hook_strength`, `styling_sexy_platform_safe`,
   `outfit_variety_vs_recent_posts`, `scene_variety_vs_recent_posts`) as a
   documented, ordered tuple, mirroring the existing `QA_CHECKLIST_FIELDS`
   pattern but kept structurally separate.
4. `build_qa_template()` now stamps `schema_version: SCHEMA_VERSION` (i.e.
   `"2"` for all newly built templates) and includes a `production_scoring`
   block defaulting every field to `"unreviewed"` except the two variety
   fields, which default to `"not_yet_measured"` -- an honest statement of
   current capability, not a guess.
5. `validate_qa_result()` extended additively:
   - Existing checklist-only false-green logic (`HARD_GATING_CHECKLIST_
     KEYS`, `any_failed`, the three original error messages) is completely
     unchanged.
   - New: if `schema_version` is not in the legacy set, `production_scoring`
     must be present and each of its 4 sub-fields must be a well-formed
     object with an allowed value; `hook_strength == "weak"` or
     `styling_sexy_platform_safe == "fail"` sets a new
     `production_scoring_forces_fail` flag.
   - Two new rules, parallel to (not replacing) the original three:
     `production_scoring_forces_fail and overall != "fail"` is rejected;
     `overall == "pass" and production_scoring_forces_fail` is rejected.
   - The two variety fields' values are validated for shape only (must be
     one of the allowed strings) and **never** feed into
     `production_scoring_forces_fail`, regardless of value -- structurally
     incapable of gating, matching the approved design exactly.

No history-reading logic, no variety tracker, no changes to
`lena_prompt_brain.py`, `kling_apilena_api_executor.py`, or any
routing/scheduling code. `tools/lena_review_proof_render_v1.py` was left
unchanged -- confirmed it only reads `qa_result.get("overall")` and needed
no update for this to work correctly.

### Validation performed
- `python -m py_compile pipeline/qa/lena_photo_qa.py` -- clean.
- Reloaded **every** QA JSON currently on disk (both
  `pipeline/asset_review/lena/2026-07-05/2026-07-05-02-photo_qa.json` and
  `pipeline/asset_review/lena/2026-07-06/2026-07-06-03-photo_qa.json`, both
  `schema_version: "1"`) through the updated `validate_qa_result()` -- both
  still validate with zero errors, confirming the legacy exemption works and
  neither historical record was broken.
- Built a fresh `build_qa_template()` scaffold and confirmed it validates
  cleanly in its untouched, all-`"unreviewed"`/`"not_yet_measured"` state
  (`schema_version: "2"`, no gating field literally `"weak"`/`"fail"` yet).
- Wrote a standalone script (scratch directory, not committed) proving all
  6 requested checks on synthetic `schema_version: "2"` records:
  - **A.** `hook_strength: "weak"` + `overall: "pass"` -> rejected
    (`production_scoring has a gating failure ... false-green verdict` and
    `overall is 'pass' while production_scoring has a gating failure`); the
    matching legitimate `overall: "fail"` + `failure_reasons` verdict for
    the same case -> accepted.
  - **B.** `hook_strength: "moderate"` and `"strong"`, each + `overall:
    "pass"` -> both accepted, confirming only the bottom tier gates.
  - **C.** `styling_sexy_platform_safe: "fail"` + `overall: "pass"` ->
    rejected; the matching legitimate fail verdict -> accepted.
  - **D.** Both `outfit_variety_vs_recent_posts` and `scene_variety_vs_
    recent_posts`, each tested at `"fail"`, `"not_yet_measured"`, and
    `"pass"` (6 combinations total), all paired with `overall: "pass"` ->
    all 6 accepted, confirming neither field can force a fail regardless
    of value.
  - **E.** `wardrobe_class_fidelity: "fail"` + `overall: "pass"` -> still
    accepted (regression check confirming the prior fix is untouched).
  - **F.** All 9 `HARD_GATING_CHECKLIST_KEYS`, tested individually -> each
    still forces rejection when paired with `overall: "pass"`, and each
    still validates correctly when paired with a genuine `overall: "fail"`
    + `failure_reasons`. Zero regressions across all 9.
  - Script printed `ALL CHECKS PASSED`.
- No render, no Kling/OpenArt/Seedance call, no `.env` edit, no publish, no
  prompt/executor/routing change at any point.

### What was explicitly deferred / not built
The variety-history tracker itself (working name `pipeline/qa/lena_variety_
tracker.py`) that would read recent published slots' wardrobe/environment/
pose metadata and compute a repeat-count -- explicitly out of scope for
this change per the approved design memo (G/H), not built, requires its own
future approval. `outfit_variety_vs_recent_posts` / `scene_variety_vs_
recent_posts` remain advisory-only and cannot become gating without that
tracker existing and a separate approval to wire it in.

### Files updated
1. `pipeline/qa/lena_photo_qa.py` -- the actual code change (see above).
2. `pipeline/agents/lena/70_visual_qa/CURRENT_STATE.md` -- new "Hook/variety
   schema v2" section with the full validated detail; updated "What is NOT
   currently proven" to reflect the new schema exists but hasn't scored a
   real render yet, and that the variety tracker remains unbuilt.
3. `pipeline/agents/lena/70_visual_qa/RULES.md` -- closed the gap note fully
   (was "partially closed," now "closed" across both stages), documented the
   new block and its gating rules in the false-green section, added new
   "must never do" / "human approval required" items specific to
   `production_scoring` and `SCHEMA_VERSION`, and updated "not yet decided /
   not yet built" to name the variety tracker as the sole remaining gap.
4. `pipeline/change_notes/NEXT_SESSION_START.md` -- two new bullets (one in
   "Current state," one replacing the old "still not decided" text with a
   "DONE" statement plus the narrowed remaining open questions).
5. `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` --
   appended a new dated §14 entry (this same content, master-file phrasing).
6. This changelog entry.

### Next step
Not yet decided: whether to build the variety-history tracker, score an
actual render against the new v2 schema for the first time, pick a further
folder-native slice, or something else. Ask before proceeding.

---

## 2026-07-06 — Fifth folder-native slice built: `pipeline/agents/lena/80_repair/` (documentation only)

### Direction
User asked for the repair folder-native slice next: document how failed QA
verdicts should translate into next actions, without building any repair
logic, without rendering, without calling any provider, without touching
`.env`, without publishing, without changing prompt/executor/routing code.
Minimum required files only: `AGENT.md`, `RULES.md`, `INPUTS.md`,
`OUTPUTS.md`, `CURRENT_STATE.md`. Explicit content requirements: hard-stop vs.
retryable classification; how schema v2 `production_scoring` affects repair;
concrete guidance for weak hook, too-covered/frumpy styling, unsafe/too-
explicit styling, identity drift, cartoon/style drift, anatomy/hands
failures, incoherent scene/caption mismatch; what must never cause an
endless rerender loop; and an explicit restatement that exact wardrobe
mismatch alone must never trigger repair (only when it also produces low
hook, frumpy/unsafe styling, incoherent scene, or repetition).

### What was built
Confirmed first (read-only) that no repair-logic code exists anywhere in the
repo (grepped for "repair" across `pipeline/*.py` and `tools/*.py` -- all
hits were either this session's own negative-prompt-budget-repair naming or
unrelated legacy queue/workorder-repair tooling, nothing that reads a QA
verdict and decides a next action). Grounded the new folder's target
definition in the master pivot doctrine's own §7.9 (already-approved,
predates this session's slice-building): "Convert QA failures into minimal,
scoped fixes... must not do broad rewrites for narrow failures... human
approval for any code change... hard-fail if repair scope expands beyond the
smallest responsible layer without justification."

Created `pipeline/agents/lena/80_repair/` with exactly the 5 requested files:

1. **`AGENT.md`** -- role, status (documentation-only, no real code owner
   exists), what it does/doesn't do, file list, and session-start reading
   order. States plainly that this folder recommends but cannot authorize
   repair actions.
2. **`RULES.md`** -- the substantive content:
   - **Rule zero:** exact wardrobe-catalog mismatch alone is never a repair
     trigger -- only relevant if it also produces low hook, frumpy/unsafe
     styling, incoherent scene, or (once measurable) repetition.
   - **§1, master table:** hard-stop categories (unsafe/too-explicit
     styling; identity or style drift repeated despite confirmed-intact
     protections; anatomy/hands repeated; incoherent scene/caption with
     unknown root cause) vs. retryable-capped categories (weak hook;
     frumpy/too-covered styling; identity/style drift or anatomy/hands on
     first occurrence, each with a required confirmation step first) vs. no-
     action categories (wardrobe alone; either variety field regardless of
     value).
   - **§2:** which schema v2 fields can/cannot trigger a repair conversation
     -- only `HARD_GATING_CHECKLIST_KEYS` plus `hook_strength == "weak"` /
     `styling_sexy_platform_safe == "fail"`; never `wardrobe_class_fidelity`
     or the two variety fields.
   - **§3-9:** one dedicated section per named failure type (weak hook,
     too-covered/frumpy styling, unsafe/too-explicit styling, identity drift,
     cartoon/style drift, anatomy/hands, incoherent scene/caption mismatch),
     each with a concrete default action and, where relevant, a required
     confirmation step (check `prompt_receipt.json` for floor survival, or
     check canonical reference images) before treating a failure as
     retryable rather than a hard stop.
   - **§10:** endless-loop guardrails -- hard numeric caps per category,
     mandatory stated hypothesis per retry, `wardrobe_class_fidelity` and
     `not_yet_measured` can never be the counted reason for a retry, and a
     repeated same-category failure is itself the signal to stop guessing --
     grounded directly in the real wc_p082 precedent (four renders, then an
     explicit, user-approved stop), with an explicit note that the wardrobe-
     classification reframing (Rule zero) doesn't undo that *process*
     lesson.
   - "Human approval required" and "Not yet decided / not yet built" lists,
     mirroring the pattern in `70_visual_qa/RULES.md`.
3. **`INPUTS.md`** -- what a repair decision would read (QA verdict file,
   `schema_version`, `prompt_receipt.json`, submit payload, canonical
   reference images, slot metadata/wardrobe catalog) and what it deliberately
   does not read directly (prompt-brain source, identity-resolution logic,
   executor code -- those belong to other slices; this one reads their
   output artifacts only).
4. **`OUTPUTS.md`** -- states plainly that nothing is produced today; sketches
   the aspirational `repair_patch.json`-style artifact from master §7.9 for
   future reference only (slot id, triggering field(s), hard_stop/retryable
   classification, hypothesis, layer, running retry count); names who would
   consume it if built; lists the gap against the original doctrine target.
5. **`CURRENT_STATE.md`** -- states this is a documentation-only slice with
   zero code, lists the real history each `RULES.md` section is grounded in
   (wc_p082's four-render stop, the negative-prompt repair, the Batch 5
   compaction bug, schema v2), and lists what is not yet proven (the table
   has never been applied to a real verdict; the retry caps are a reasonable
   default, not user-confirmed for this specific folder).

### What was explicitly not done
No repair code written anywhere. No render. No Kling/OpenArt/Seedance call.
No `.env` edit. No publish. No change to `lena_prompt_brain.py`,
`kling_apilena_api_executor.py`, or any routing/scheduling code. No
`repair_patch.json` or equivalent artifact created -- explicitly sketched as
aspirational only. No retry cap enforced in code -- it's a documented rule a
reviewer self-enforces.

### Files updated
1. `pipeline/agents/lena/80_repair/AGENT.md`, `RULES.md`, `INPUTS.md`,
   `OUTPUTS.md`, `CURRENT_STATE.md` -- the new slice (see above).
2. `pipeline/change_notes/NEXT_SESSION_START.md` -- new "Current state"
   bullet; resolved the prior "pick a further folder-native slice" open
   question by recording which slice was picked; updated the folder count
   from four to five in the "Exact commands/files to inspect first" list and
   the "Hard prohibitions" list (now naming the five built and five still-
   unbuilt target folders); added an explicit prohibition against treating
   `80_repair/`'s existence as authorization to write real repair code.
3. `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` --
   appended a new dated §14 entry (this same content, master-file phrasing).
4. This changelog entry.

### Next step
Not yet decided: whether to build the variety-history tracker, score a real
render (or a real `fail` verdict) against the new v2 schema/`80_repair/`
doctrine for the first time, pick a further folder-native slice, or
something else. Ask before proceeding.

---

## 2026-07-07 — Schema v2 + 80_repair doctrine applied to the existing wc_p082 image (no new render)

### Direction
User asked to apply schema v2 and the `80_repair` doctrine to the existing
`2026-07-05-02-photo`/`wc_p082` image -- explicitly no render, no provider
call, no `.env` edit, no publish, no prompt/executor/routing change, and no
rerender of this slot. Use the existing seed image at `pipeline/kling_
library/lena/2026-07-05/2026-07-05-02-photo_seed.png`. Score
`wardrobe_class_fidelity` truthfully but diagnostic-only; judge the actual
coat/scarf result on hook strength, styling, realism, identity, scene
coherence, caption coherence, and safety; then apply `80_repair`'s hard-
stop/retryable/no-repair-needed classification.

### What was done
Viewed the actual image directly (`pipeline/kling_library/lena/2026-07-05/
2026-07-05-02-photo_seed.png`) via the Read tool -- per `70_visual_qa/
RULES.md`'s "must never do" rule, no verdict is written from metadata/
receipts alone. Also read the slot's daily-workorder metadata (`pipeline/
kling_workorders/2026-07-05/daily_workorders.json`) to confirm the specified
pose/activity/caption ("sitting on a city bench... holding a paper coffee
cup and watching people pass") for `caption_scene_coherence` and
`environment_realism_scene_coherence` judgment. Checked
`pipeline/kling_debug/apilena_api/2026-07-05/2026-07-05-02-photo/live_
apilena_lookup_response.json` for canonical reference image URLs, but did
not fetch them over the network (Kling-hosted CDN URLs -- treated as
covered by "do not call any provider" for this task) -- instead relied on
the identity-drift finding already confirmed against those same references
in the prior `schema_version: "1"` review of this exact image, since this is
a re-score of one existing image, not a new independent judgment requiring a
fresh reference fetch.

### QA verdict produced (schema v2)
Wrote a standalone Python script (scratch directory) that constructs the
full `schema_version: "2"` record, validates it via `lena_photo_qa.
validate_qa_result()`, writes it to `pipeline/asset_review/lena/2026-07-05/
2026-07-05-02-photo_qa.json` (the existing path -- `slot_id` is stable
across re-reviews, per the stale-QA-file lesson this is a deliberate,
explicit replacement, not an accidental overwrite), then reloads it from
disk and re-validates. All three validation passes returned `(True, [])`.

**checklist (unchanged from the prior schema v1 review of this same
image):**
- `identity_fidelity`: **fail** -- hair reddish-auburn/copper vs. canonical
  brunette+caramel/honey balayage; eyes lighter amber-brown vs. deep dark
  brown. Reference-confirmed in the original review; not re-fetched this
  pass (see above).
- `face_realism_anti_generic_drift`: **fail** -- not cartoon/illustration,
  but residual glossy/poreless/idealized "beauty-filter" quality.
- `skin_realism_no_invented_marks`: pass.
- `wardrobe_class_fidelity`: **fail, diagnostic only** -- mustard coat/
  blazer + scarf over a gray top vs. the specified white tank + black mini
  skirt (4th consecutive miss on this slot). Recorded truthfully; explicitly
  does not gate `overall`.
- `public_scene_clothing_continuity`: pass -- full opaque coverage, no
  underwear/bra drift.
- `outerwear_underlayer_correctness`: pass (narrow technical pass).
- `body_shape_continuity`: not_applicable -- obscured by coat, seated.
- `hands_anatomy_sanity`: pass -- one hand visible gripping a coffee cup,
  plausible.
- `environment_realism_scene_coherence`: pass -- coherent urban sidewalk/
  bench scene, matches the "city bench" activity.
- `caption_scene_coherence`: pass -- coffee cup in hand matches the
  specified pose/caption.

**production_scoring (new, first real use):**
- `hook_strength`: **"moderate"** -- direct eye contact, genuine warm
  smile, engaged forward-leaning posture, coffee cup as a natural prop,
  soft directional light on voluminous hair. Not "weak"/static, but a
  standard seated coffee-shop portrait with no dynamic pose/angle, so not
  "strong" either.
- `styling_sexy_platform_safe`: **"fail"** -- too-covered end, not the
  explicit end. The buttoned wool coat + thick wrapped scarf covers the
  torso/arms almost completely, zero skin shown below the neck -- the named
  hard-reject "outfit too covered or not visually compelling," independent
  of whether it matches the catalog string.
- `outfit_variety_vs_recent_posts` / `scene_variety_vs_recent_posts`:
  **"not_yet_measured"** -- advisory only, no tracker exists, as designed.

**overall: fail** -- driven by `identity_fidelity`, `face_realism_anti_
generic_drift`, and `production_scoring.styling_sexy_platform_safe`
(three independent hard-gating fields), explicitly **not** by `wardrobe_
class_fidelity`, which is recorded but non-gating exactly as designed.
`failure_reasons` states all three real reasons and explicitly notes the
wardrobe substitution is not, by itself, one of them.

### 80_repair doctrine applied
**Classification: HARD STOP.** Two independent, converging reasons:
1. This slot already carries a separate, standing prohibition in `NEXT_
   SESSION_START.md`'s "Hard prohibitions": four prior renders, an explicit
   user-approved stop already in force, no rerender without a separately-
   approved reason. This alone forces a hard stop regardless of the
   per-dimension table.
2. Even judged fresh against `80_repair/RULES.md`'s table: three
   independent hard-gating dimensions failed simultaneously (identity,
   styling, realism), not one isolated, cleanly-attributable defect a
   scoped retry could target -- per master §7.9's "smallest responsible
   layer" hard-fail condition, a real fix attempt here would not be minimal
   or scoped.

**No repair action taken or recommended for execution.** Recorded, for
reference only and explicitly not authorized: the hypothetical repair *if*
this slot were not already capped would be re-picking a wardrobe/scene/lane
combination less prone to eliciting a full-coverage outerwear substitution,
and re-verifying identity resolution against the correct live element --
named to satisfy the "what would the repair action be" question, not as an
instruction to act.

### What this teaches about the current Kling path
Under the *old* (pre-correction) standard, this render was judged a failure
because of the wardrobe mismatch. Under the *corrected* standard + schema
v2, it is **still a failure** -- but for identity drift, too-covered
styling, and residual unrealism, never for the wardrobe substitution itself.
This is real evidence (not just a schema-design intention) that the current
`/v1/images/generations` path's actual ceiling is provider-level output
quality (identity fidelity, styling coverage, photoreal-ness), not exact-
wardrobe-obedience as this project overweighted earlier this session. This
is consistent with, not a reversal of, the standing conclusion that further
meaningful fixes on this path are a provider/conditioning question, not a
prompt-content one. Does **not** reopen the parked Kling Omni/BodyLock
thread.

### What was explicitly not done
No render. No Kling/OpenArt/Seedance call. No `.env` edit. No publish. No
change to `lena_prompt_brain.py`, `kling_apilena_api_executor.py`, or any
routing/scheduling code. No rerender of `2026-07-05-02-photo`/`wc_p082` --
the existing image was reviewed directly. No canonical-reference images
fetched over the network this pass (relied on the already-reference-
confirmed identity finding from the prior review of this same image). No
repair action executed.

### Files updated
1. `pipeline/asset_review/lena/2026-07-05/2026-07-05-02-photo_qa.json` --
   the QA record itself (data, not code), replaced with the new
   `schema_version: "2"` verdict described above.
2. `pipeline/agents/lena/70_visual_qa/CURRENT_STATE.md` -- new section on
   this first real `production_scoring` scoring of an actual render;
   updated the "Proof status" section to point at the new verdict while
   preserving the prior schema v1 review as historical record; updated
   "What is NOT currently proven."
3. `pipeline/agents/lena/80_repair/CURRENT_STATE.md` -- new section
   documenting this first real application of the decision table and its
   HARD STOP outcome; updated "What is NOT currently proven" to note the
   retryable branch of the table remains completely untested.
4. `pipeline/change_notes/NEXT_SESSION_START.md` -- new "Current state"
   bullet; resolved the prior "not yet decided" text noting this specific
   application is now done, while leaving the retryable-branch test open.
5. `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` --
   appended a new dated §14 entry (this same content, master-file phrasing).
6. This changelog entry.

### Next step
Not yet decided: whether to build the variety-history tracker, score a
*different* render to actually exercise `80_repair`'s untested retryable
branch, pick a further folder-native slice, or something else. Ask before
proceeding.

---

## 2026-07-07 — Production-style proof batch → cartoon failure → ROOT CAUSE identified via HAR analysis

### Direction
Approved a fresh production-style proof plan (NOT a diagnostic test),
optimized for hook / sexy-safe styling / outfit variety / scene variety /
realism / identity — explicitly not exact wardrobe obedience, not wc_p082,
not reopening Omni/BodyLock, no publish, no `.env`. Step 1: no-spend dry-run
of 3 candidates. Step 2: render exactly 1 (`wc_p030`/flower shop), review it,
apply schema v2 QA + `80_repair`.

### What was built and run
- Built 3 candidate slots via the real `pipeline/prompting/lena_prompt_brain.py`
  functions (forced wardrobe + scene selection through monkeypatched
  `pick_catalog_outfit_production` / `choose_scene_production`, so the outfit/
  scene were pinned but every other prompt-brain behavior — identity anchor,
  negative-prompt construction, locks — ran normally). Wrote
  `pipeline/kling_workorders/2026-07-07/daily_workorders.json`:
  - `2026-07-07-01-photo`: `wc_p030` (denim mini + crop + open blazer), Austin
    sidewalk afternoon (`env_s002`), flower-shop scene.
  - `2026-07-07-02-photo`: `wc_p034` (white faux-leather mini + crop), brunch
    patio scene (env auto-selected `env_g002`).
  - `2026-07-07-03-photo`: `wc_p062` (copper metallic halter midi dress),
    rooftop sunset (`env_r004`).
- No-spend dry-run of all 3 (`CONTENT_BOT_KLING_EXECUTE=0`): all passed.
  Verified per candidate: correct element `315187972322559`/APILENA,
  endpoint `/v1/images/generations`, `payload_no_image_list: true`, compact
  prompt ≤2499 and compact negative ≤2499 chars, every negative reserved
  floor surviving (core 21/21, style-realism 29/29, public-safety 17/17,
  body-anatomy 37/37, outfit-specific varying by outfit, scene/continuity/
  framing floors all surviving). No publish artifacts.
- Rendered exactly 1 (`CONTENT_BOT_KLING_TARGET_SLOT_ID=2026-07-07-01-photo`,
  `MAX_SLOTS=1`, `EXECUTE=1`): task `903293121000898623`, downloaded to
  `pipeline/kling_library/lena/2026-07-07/2026-07-07-01-photo_seed.png`.
- Viewed the image directly. **Result: fully cartoon / 3D-illustrated
  (Pixar-style) — the #1 corrected-standard hard reject** — despite all 29
  anti-cartoon style-realism negative terms confirmed surviving compaction.
  Candidates 2 and 3 were deliberately NOT rendered.

### User challenge → root-cause diagnostic (read-only, approved)
The user challenged the approach ("where are you getting the ref images? what
do you need to make this work?"). This triggered a read-only investigation:

1. **Viewed APILENA's actual reference images.** Extracted the 4 resource URLs
   from the saved `live_apilena_lookup_response.json`, downloaded and viewed
   them: **photoreal and correct** (warm brunette/caramel hair, dark brown
   eyes, freckles, curvy realistic body). The element/source is fine.
2. **Traced the executor payload.** `_submit_photo()` (`pipeline/kling_apilena_
   api_executor.py` ~1064-1099) resolves and verifies APILENA's reference
   image URLs, then **discards them** — they are only a presence gate. Actual
   payload: `{prompt, negativePrompt, aspect_ratio, n, element_list:
   [{element_id}]}`. **No reference image, no `model_name` pin.**
3. **HAR analysis (separately approved, read-only, sanitized).** Inspected
   `scratch/kling_elements_page.har` and `scratch/herby_kling_elements_page.har`
   with a script that redacts URLs/tokens and prints only endpoint paths +
   payload key structure. Findings (no secrets printed at any point):
   - Web app image generation = `POST kling.ai/api/omni/submit-config-template`
     (`type: mmu_omni_image`), preceded by `POST .../intent-recognition`.
     **Zero `api.klingai.com` traffic** in either HAR.
   - Submit body sends a named `inputs` array whose object carries
     `inputType:"URL"`, the **actual reference image URL** (`url` + `cover`),
     `fromElementId:"u_<id>"`, `resourceType:"ELEMENT"`; plus an `arguments`
     array pinning **`kolors_version:"3.0-omni"`**, `story_mode:false`, and an
     `omniRecognition` string; settings via `settingKeys:
     "img_resolution|aspect_ratio|imageCount"`.
   - So the web app conditions on the **real reference image + a pinned omni
     model**; the current executor does neither.
4. **Conclusion:** the wrong-outfit / identity-drift / cartoon-style failures
   are **conditioning-level, not prompt-content-level**. The realism/identity
   lever is absent from the current payload; no prompt or negative-prompt
   change can reach it. This is a more specific, actionable diagnosis than the
   prior "provider/model-level noncompliance" framing.

### Security / HAR handling
- Counted (did not print) sensitive material: 23 (small HAR) + 146 (large HAR)
  signed/token URLs (`__NS_hxfalcon` session tokens, `Signature=`/`x-kcdn-pid`
  signed CDN params). No `Cookie`/`Authorization` headers were captured in
  these particular exports, but the session tokens in URLs are sensitive.
- Git status was: **untracked but NOT git-ignored** (a stray `git add` could
  have committed them). **Fixed:** added `scratch/*.har` + `*.har` to
  `.gitignore`; confirmed both files now report ignored via `git check-ignore`.
- The HAR-analysis scripts live in the session scratchpad
  (`C:\WINDOWS\TEMP\claude\...\scratchpad`), **outside the repo** — not in
  `scratch/`, nothing committable was created. No script was written into the
  repo tree.

### Support packet sharpened
Added §5b (what the web app's request actually contains, from HAR) and a new
**Question 5** to `pipeline/change_notes/lena_kling_omni_support_packet_
2026-07-06.md`: can the official `api.klingai.com` image API accept a raw
reference/character image directly (image URL or base64), independent of the
web element registry, and if so what endpoint / model id (official equivalent
of `kolors_version 3.0-omni`) / payload fields replicate the web app's
reference-image + omni-model conditioning? This is now the highest-value
external question.

### What was explicitly NOT done
No web-app request replayed. No `kling.ai/api/omni/*` automation. No endpoint
called during analysis. No tokens/cookies/signed URLs/session params printed.
No executor code changed. No `.env` edit. No publish. No provider switch. No
further renders. Candidates 2 and 3 left unrendered. Candidate 1's QA verdict
was intentionally not written up (the thread pivoted to root cause).

### Files updated
1. `.gitignore` — added `scratch/*.har` and `*.har`.
2. `pipeline/change_notes/lena_kling_omni_support_packet_2026-07-06.md` —
   §5b + Question 5.
3. `pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md` — "ROOT CAUSE
   IDENTIFIED (2026-07-07)" section at the top.
4. `pipeline/agents/lena/60_executor/CURRENT_STATE.md` — §1a root-cause
   section + updated "what is NOT currently proven".
5. `pipeline/change_notes/NEXT_SESSION_START.md` — PARKED banner 2026-07-07
   update, new current-state bullet, new hard prohibitions (no web-app replay,
   no HAR commit), updated next-step text.
6. `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` — §0
   ROOT CAUSE banner + new §14 entry.
7. This changelog entry.

### Next step
The real fix is blocked on the support answer to Question 5. Do NOT keep
rendering on the current path expecting a different result. Non-blocked
options remain (variety-history tracker, a further folder-native slice, or
something else). Ask before proceeding.

---

## 2026-07-07 — Session checkpoint (RENDER FREEZE, next action external)

### Direction
User accepted the root-cause documentation and issued a standing directive:
**stop all Kling rendering on the current `/v1/images/generations` path**
until the support/API question (support packet Question 5) is answered or the
user explicitly approves a different test. User will send the support packet
externally. Then asked to checkpoint the session via
`.claude/skills/lena-session-checkpoint/SKILL.md`.

### A. What changed
- Recorded the explicit RENDER FREEZE directive as a new 🛑 banner at the top
  of `NEXT_SESSION_START.md` (first thing a future session reads).
- Added session-checkpoint entries to the master file and this changelog.
- The Skill tool could not invoke `lena-session-checkpoint` (created
  mid-session; harness loads the skill registry only at session start), so
  the skill's documented procedure was executed manually — its own stated
  fallback.

### B. Files changed
- `pipeline/change_notes/NEXT_SESSION_START.md` (RENDER FREEZE banner).
- `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md`
  (§14 checkpoint entry).
- This changelog entry.
(No CURRENT_STATE.md files touched — no new technical work this turn; the
prior turn's root-cause finding is already recorded across the continuity
layer.)

### C. Validations run
None — documentation-only checkpoint. No code, no render, no provider call.

### D. Decisions made
- Standing decision (user): freeze current-path rendering pending external
  support answer or explicit new approval.
- Next action is external and user-owned (send support packet / Question 5).

### E. Blockers / parked branches
- **Render freeze** on `/v1/images/generations` — blocked on support answer
  or explicit user approval of a different test.
- **Kling Omni/BodyLock** — still parked pending the same external support
  response (support packet, now carrying Question 5).
- The real image-quality fix is blocked on Question 5 (can the official API
  take a raw reference image directly?).

### F. Next approved step
External: user sends the support packet. No Claude-side action advances the
Kling thread until the response arrives. If the user wants non-blocked work
meanwhile: variety-history tracker, or a further folder-native slice — both
require explicit approval before starting.

### G. What must not be done
Do not render more images, replay web-UI requests, automate against
`kling.ai` web endpoints, change executor code, touch `.env`, publish, switch
providers, or reopen Omni/BodyLock without support clarification. Do not
commit the HAR captures (git-ignored as of this session).

### Session status
Cleanly checkpointed. Safe to end here; a future session resumes by reading
`NEXT_SESSION_START.md` (RENDER FREEZE + PARKED + STANDARD CORRECTION banners)
first, exactly as `lena-session-start` prescribes.

---

## 2026-07-07 — Local visual-reference set + preflight reference guard (no render)

### Direction
User unfroze ONLY local visual-reference work (still no rendering): save the 4
correct APILENA reference images locally, add a manifest, and add a preflight
guard that blocks any Lena image-generation payload lacking actual visual
reference image data (element_list alone insufficient). No Kling call, no
render, no `.env`, no production-routing patch.

### What was created
- `pipeline/reference_images/lena/apilena_current/` with the 4 canonical
  references, copied from the local copies downloaded during the 2026-07-07
  root-cause investigation (no Kling call):
  - `lena_ref_01_face.jpg` (element cover; face identity close-up)
  - `lena_ref_02_body_front.jpg` (front-facing full/three-quarter body)
  - `lena_ref_03_body_angle.jpg` (reclining/seated three-quarter body angle)
  - `lena_ref_04_style_anchor.jpg` (standing styled full-body fashion anchor)
  All 4 viewed directly and confirmed correct/photoreal Lena. Images are
  `*.jpg` so they are git-ignored (local-only, intended); manifest + guard are
  tracked.
- `pipeline/reference_images/lena/apilena_current/manifest.json`: element_id
  315187972322559, element_uid `u_315187972322559`, element_name APILENA,
  filenames + role + role_detail + size + sha256 per image, date_captured
  2026-07-07, source note, and `note: "canonical Lena visual references"`.
- `pipeline/reference_images/lena/apilena_reference_guard.py`: standalone
  preflight guard. `assert_lena_visual_references_present(payload)` raises
  `LenaReferenceGuardError("BLOCKED: Lena visual references are not included in
  the generation payload.")` unless the payload carries an actual image
  reference (URL, base64 data URI, or existing local image path) under a
  reference-bearing key. `element_list` is explicitly NOT counted. Includes a
  `__main__` dry-run proof.

### Deliberately NOT wired into the executor
The guard is standalone and is **not** imported by
`pipeline/kling_apilena_api_executor.py` — wiring it into the live submit path
is a production-routing change, which is frozen (RENDER FREEZE). It exists as
a preflight check + proof only.

### Dry-run proof (no network, no render)
`python pipeline/reference_images/lena/apilena_reference_guard.py`:
- CASE A (current live payload: `element_list` only) → **BLOCKED** with the
  exact message. ✓
- CASE B (payload with 4 local `reference_images`) → passes. ✓
- CASE C (web-omni-style `inputs[{url}]`) → passes. ✓
`py_compile` clean.

### Not done
No Kling call, no render, no `.env` edit, no executor/production-routing patch,
no publish, no provider switch. Render freeze intact.

---

## 2026-07-07 — Strategic pivot: content_bot reframed as horizontal media infrastructure; first Revenue Lane node (`podcast_repurpose`) scaffolded, docs only

### Direction
User approved a strategic pivot, framed explicitly as "not asking what the
infrastructure is anymore -- choosing the first profitable implementation."
`content_bot` is reframed from "AI influencer node system" to "horizontal
media production infrastructure." Lena's role changes to R&D/demo/stress-test
node -- explicitly **not** abandoned, deleted, or downgraded; her generation
stays frozen on its own separate timeline (the Kling render freeze, unrelated
to this pivot's pace). New Revenue Lane, first node: Podcast/Long-Form
Repurposing (`business_media_node` / `podcast_repurpose`). External offer: "I
turn your existing videos, podcasts, calls, and business knowledge into a
month of short-form social content." Docs-only this turn -- no code, no
Kling, no render, no `.env`, no publish, no production-routing change, no
Blotato work.

### What was created
1. **`pipeline/change_notes/business_media_node_pivot_plan.md`** -- the full
   strategic memo, 12 sections (union of every angle requested across the
   session's messages, no contradictions, nothing dropped):
   1. New positioning. 2. Revenue Lane vs. Lena R&D Lane (comparison table).
   3. First sellable offer. 4. Target customer profiles. 5. Exact proposed
   monthly deliverables (flagged as a hypothesis, not committed/priced).
   6. MVP workflow (manual, human-in-the-loop, no code). 7. Folder/node
   structure. 8. What carries over from Lena (patterns, not code -- with
   specific real file references). 9. What stays Lena-specific/isolated
   (with specific real file references). 10. 7-day build plan (docs today ->
   manual pilot pass on Day 5 -> only then consider automating anything).
   11. What not to build yet. 12. How to sell the first 3 clients manually
   (warm outreach + free pilot batch + testimonial + price discovery, no
   funnel/ads/landing page).
2. **`pipeline/nodes/business_media/podcast_repurpose/`** -- 6 lightweight
   docs, explicitly NOT the full Lena-style numbered agent-slice pattern
   (`40_identity_continuity/` .. `80_repair/`), per direction to keep this
   first node lightweight:
   - `README.md` -- what/why, external one-line pitch, file index, explicit
     "what this is NOT yet" list (not automated, not video editing, not the
     full agent-slice pattern, no Blotato).
   - `INPUTS.md` -- accepted raw media (podcast episode, YouTube video, Zoom
     call, webinar, raw iPhone clips, testimonials) + business context
     (service/product info, website copy); explicit note that no format
     schema is defined yet (manual intake for the MVP).
   - `OUTPUTS.md` -- per-clip outputs (timestamp, hook, caption, title,
     thumbnail text) and per-batch outputs (content packet, posting
     calendar, CTA variants, approval packet, analytics/iteration notes);
     explicit note that no edited video and no automated posting are
     produced.
   - `WORKFLOW.md` -- the 8-step manual MVP workflow (intake -> transcribe ->
     identify clip-worthy moments -> draft per-clip angle -> assemble packet
     -> build approval packet -> deliver -> light analytics feedback), with
     an explicit "must not automate before validated" rule.
   - `OFFER.md` -- the external pitch, who it's for, the proposed package
     (hypothesis, not priced), explicit out-of-scope list, and the
     first-3-clients sales motion summary.
   - `CURRENT_STATE.md` -- docs-only status, what exists vs. doesn't, next
     action (one manual pilot pass before any code), and an honest "what is
     NOT currently proven" list (workflow unvalidated, pricing unvalidated,
     Lena-pattern reuse unvalidated).

### What carries over from Lena vs. what stays isolated
Recorded in full in the pivot memo §8-9 and the master file's new §14 entry:
carries over as *pattern*, not code -- folder-native docs convention,
continuity-file discipline, structured QA-verdict pattern, repair-doctrine
pattern, session-continuity skill pattern, scored hook-bank shape
(`strong_hook_bank_v1.json`), and the already-infrastructure-wide
`pipeline/knowledge/content_bot/` layer (not yet updated for the new node --
flagged as a future, separate task). Stays Lena-specific: identity/prompt-
brain/executor code, wardrobe/environment/scene catalogs, the photo QA schema
and its `production_scoring` block, all five Lena agent slices, the Kling
investigation/render-freeze thread, and Lena's Instagram-specific publishing
path.

### What was explicitly not done
No code beyond Markdown scaffolding. No Kling call. No render. No `.env`
edit. No publish. No production-routing change. No Lena executor patch. No
Blotato work. No pricing commitment. No pilot run. No web-UI replay
(unrelated to this task, but reaffirmed as still in force). Verified the
target paths (`pipeline/nodes/`, the pivot memo path) did not already exist
before creating them.

### Files updated
1. `pipeline/change_notes/business_media_node_pivot_plan.md` -- new memo.
2. `pipeline/nodes/business_media/podcast_repurpose/{README,INPUTS,OUTPUTS,
   WORKFLOW,OFFER,CURRENT_STATE}.md` -- new node docs (6 files).
3. `pipeline/change_notes/NEXT_SESSION_START.md` -- new STRATEGIC PIVOT
   banner (above the RENDER FREEZE banner), updated "Read these first" list
   (added the pivot memo, noted `REPO_MAP.md` is unedited/still Lena-focused),
   new current-state bullet, two new hard-prohibition items (pivot is
   docs-only / no Blotato; Lena not abandoned by the pivot).
4. `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` --
   new pivot-context banner in §0 (clarifying this file's scope is now the
   Lena/R&D-lane sub-plan within the larger frame) + new §14 entry.
5. This changelog entry.

### Next step
Per the pivot memo's 7-day plan: run the MVP workflow by hand on one real or
sample piece of client media before writing any code, in parallel with
manual outreach toward the first pilot prospects. No code, no Kling, no
render, no Blotato until that manual validation happens. Lena's own next step
is unchanged and unaffected (external, blocked on the Kling support answer).

---

## 2026-07-07 — Kling reference-by-URL (Variant B) local no-call payload diagnostic

### Direction
Approved next step on the Lena visual-reference thread: build the exact Variant B
payload locally and prove the outgoing request would include the Lena visual
reference URL — without any Kling call, render, credit spend, `.env` edit, or executor
patch. This follows the capability matrix
(`pipeline/change_notes/lena_visual_reference_api_capability_matrix.md`) and the test
plan (`pipeline/change_notes/lena_kling_reference_by_url_test_plan.md`).

### What was built
`tools/diagnostics/lena_kling_reference_url_payload_dryrun.py` — a standalone, no-network
diagnostic. It imports **only** the existing reference guard
(`pipeline/reference_images/lena/apilena_reference_guard.py`), never the executor and
never any HTTP-submitting code. It:
- Pulls a real APILENA reference URL (the `cover` resource) from the newest existing
  local lookup artifact (`pipeline/kling_debug/apilena_api/<date>/<slot_id>/
  live_apilena_lookup_response.json`).
- Builds the **Variant B** payload:
  `{"model_name": "kling-v3-omni", "prompt": <small test>, "negative_prompt": <small
  anti-cartoon>, "aspect_ratio": "9:16", "n": 1, "image_list": [{"image": "<APILENA
  reference URL>"}]}` — **no `element_list`.**
- Builds the current **element_list-only** payload shape for contrast.
- Runs the reference guard against both and prints only sanitized payload shape (URLs
  reduced to scheme+host+16-char path prefix + redacted length; prompts reduced to
  lengths; full paths/query never printed).

### Result (py_compile clean; run once, no network)
- **Variant B PASSES the guard** — `element_list` absent, `image_list` present, visual
  reference URL detected.
- **element_list-only is BLOCKED** with exactly:
  `BLOCKED: Lena visual references are not included in the generation payload.`
- **APILENA hosted resource URLs are locally available** (6 lookup artifacts on disk,
  2026-07-04 through 2026-07-07, each with the 4 resource URLs) and **do not appear to
  carry `Expires` / `Signature` / `Key-Pair-Id` / token parameters** — the only query
  key is `x-kcdn-pid`. They look persistent (unlike the time-signed generated-image
  result URLs), though true public accessibility is unverified without a fetch (out of
  scope). Safest for a live test: R2-host the local canonical refs for a stable owned
  URL, or try the element URL as-is first.

### What this proves — and does NOT prove
Proves only that the outgoing payload **can carry** the Lena visual reference URL and
that the guard correctly distinguishes it from the (blocked) element_list-only shape.
**Does NOT prove Kling accepts or honors the payload** — dropping `element_list` from
omni-image is still unverified against the live API. That requires either one later
`n=1` live test (per the test plan §7) or support confirmation (Question 5). No such
test is authorized by this entry.

### What was explicitly not done
No Kling call. No render. No credit spend. No `.env` edit. No executor patch. No
production-routing change. RENDER FREEZE remains in force.

### Files updated
`tools/diagnostics/lena_kling_reference_url_payload_dryrun.py` (new), plus this
changelog entry, `lena_filesystem_native_agent_pivot_master.md` (§14),
`pipeline/agents/lena/60_executor/CURRENT_STATE.md`, and
`pipeline/change_notes/NEXT_SESSION_START.md`.

### Next step
Unchanged: the real fix remains blocked on the support answer to Question 5, or on an
explicitly-approved single `n=1` reference-by-URL live test (Variant B first). The local
payload path is now proven ready up to the point of the API call.

---

## 2026-07-07 — BREAKTHROUGH: Variant B live test SUCCEEDED — reference-by-URL fixes the cartoon collapse

### Direction
User gave staged approval for exactly one live Kling test to answer one question:
does official Kling AK/SK accept and honor an image_list-only APILENA reference URL
with `model_name="kling-v3-omni"`? Constraints: one `n=1` call, pure Variant B only,
no `element_list`, no `negative_prompt`, no retries, no second variant, no executor
patch, no `.env` edit, no web-UI replay, no publish. Preflight-then-explicit-"RUN"
gate was followed.

### What was run
`tools/diagnostics/lena_kling_reference_url_live_test.py --execute` with
`CONTENT_BOT_REF_URL_TEST=1` (double gate). Pure Variant B payload:
```
{
  "model_name": "kling-v3-omni",
  "prompt": "<157-char photoreal scene-only prompt>",
  "aspect_ratio": "9:16",
  "n": 1,
  "image_list": [{"image": "<APILENA cover resource URL from live lookup artifact>"}]
}
```
No `element_list`. No `negative_prompt`. Reference URL = APILENA's own `cover` CDN
resource URL (on Kling's own CDN, so Kling can fetch it), pulled from
`pipeline/kling_debug/apilena_api/2026-07-07/2026-07-07-03-photo/
live_apilena_lookup_response.json`. Preflight confirmed image_list present,
element_list absent, reference guard passes, AK/SK present, manual-override env vars
absent — before the call.

### Result — SUCCESS
- **HTTP 200, `code: 0`, `message: "SUCCEED"`.** Task `903333900062163005` created;
  poll reached `task_status: "succeed"`; one output URL returned and downloaded.
- **The endpoint accepted a pure `image_list`-only payload** (no `element_list`) under
  official AK/SK auth. The `1201 element id not found` error that blocked the element
  path is entirely bypassed — there is no element to look up.
- **Output is photoreal — decisively.** Real skin texture with pores and freckles,
  natural windblown hair, believable direct sunlight, real depth-of-field. Zero
  cartoon/3D/illustration — the exact opposite of the fully-Pixar element-only render
  from earlier the same session, with the ONLY change being that the reference image
  was actually sent.
- **Lena identity meaningfully conditioned.** Strong match to the APILENA reference
  set: warm brunette/caramel wavy hair, dark brown eyes, the same freckle pattern,
  consistent face structure, gold hoop earrings, curvy build. The reference image
  genuinely drove identity, not a generic face.
- **The cartoon collapse is resolved by sending the actual reference URL.** This
  confirms the 2026-07-07 root-cause diagnosis directly: the failures were
  conditioning-level (no reference image + no model pin), not prompt-content-level.
- **Remaining issues are normal production steering, not the blocker:** the render was
  a torso/upper-body crop in a white sports-bra-style crop top rather than the
  prompted full-body/casual-outfit — so framing, crop, wardrobe adherence, and
  publish-safety (that crop-top would trip Lena's own no-bra-as-outfit line for
  publishing) all still need the normal steering. None of that is the reference/
  identity/realism blocker, which is now solved.

### Files created by the run (5, all diagnostic — not production data)
Under `pipeline/kling_debug/reference_url_test/ref_url_test_20260707T045501Z/`:
`submit_payload.json`, `submit_response.json`, `poll_response.json`,
`result_manifest.json`, `output_0.png`.

### What was explicitly not done
Exactly one call. No retries. No second variant. No `element_list`. No
`negative_prompt`. No executor patch. No `.env` edit. No web-UI replay. No publish. No
scheduler. No batch.

### Consequence for the render freeze
The render freeze was a response to an *unsolved* cartoon/identity failure whose cause
was unknown, then known-but-unverified-fixable. That condition no longer holds: the fix
is demonstrated working end-to-end on the official API. The freeze on the OLD
element-list-only path stays (that path is confirmed bad), but the thread is no longer
"blocked, waiting on support" — it's "solved in principle, pending an approved executor
patch + a small reliability check." Support Question 5 is now answered empirically for
the omni-image image_list-only case (accepted + honored); it remains worth sending only
to clarify official field docs / multi-image / long-term URL sourcing.

### Files updated to record this
`pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` (§0 + §14),
`pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md`,
`pipeline/agents/lena/60_executor/CURRENT_STATE.md`,
`pipeline/change_notes/NEXT_SESSION_START.md`, and this entry. A separate executor-patch
proposal was drafted: `pipeline/change_notes/lena_kling_reference_url_executor_patch_
proposal.md` (proposal only — no code).

### Next step
Review the executor-patch proposal. No executor change, render, or Kling call until the
proposal is explicitly approved. A small reliability check (a few more n=1 reference-by-
URL renders) is worth doing before trusting consistency, but only under explicit
approval.

---

## 2026-07-07 — Executor patched for reference-by-URL mode (code change, dry-run validated, no render)

### Direction
Approved to patch the Lena Kling photo submit path so it builds the proven Variant B
reference-by-URL payload. Scope: `pipeline/kling_apilena_api_executor.py`,
`_submit_photo()`. Constraints: model_name kling-v3-omni; image_list with the APILENA
reference URL; omit element_list by default; omit negative_prompt for this first
validation; keep n=1 and 9:16; run `apilena_reference_guard` before submit; block
element_list-only payloads; sanitize reference URLs in logs; never print full CDN/
signed URLs; never send local C:\ paths; no `.env` change; use the existing APILENA
hosted resource URL source (no R2 yet); validate via py_compile + dry-run only.

### What changed (`pipeline/kling_apilena_api_executor.py`)
- Imports: added `from urllib.parse import urlsplit` and
  `from pipeline.reference_images.lena import apilena_reference_guard`.
- Constants: added `OMNI_IMAGE_SUBMIT_URL` (`{API_BASE}/v1/images/omni-image`) and
  `REFERENCE_IMAGE_MODEL_NAME` (default `"kling-v3-omni"`).
- New `_sanitize_reference_url()` — scheme+host + short path prefix only, never the
  full path/query.
- New **`build_reference_url_photo_payload(slot, image_urls)`** — the single source of
  truth for the Variant B payload. Pure/no-network. Picks the first https reference
  URL (raises if none — never sends a C:\ path or empty ref), builds
  `{model_name: "kling-v3-omni", prompt, aspect_ratio: "9:16", n: 1, image_list:
  [{"image": <url>}]}`, asserts no element_list, and asserts the reference guard
  passes before returning.
- `_submit_photo()` now: builds the payload via that helper (with `reference_guard_
  blocked` / `reference_payload_build_failed` error branches); runs
  `assert_lena_visual_references_present(payload)` again as defense-in-depth before
  submit; submits + polls the omni-image endpoint (`OMNI_IMAGE_SUBMIT_URL`) instead of
  `/v1/images/generations`; still computes the compact negative prompt but only for the
  telemetry receipt, NOT the payload; updated the success metadata + result_manifest to
  reference-by-URL mode (`reference_binding_mode: kling_omni_image_reference_by_url`,
  `payload_has_image_list/no_element_list/no_negative_prompt: true`, sanitized
  reference + output URLs); the returned dict now carries only sanitized URLs.
- The no-spend branch + top-level return updated to report `OMNI_IMAGE_SUBMIT_URL` and
  `payload_has_image_list`/`payload_no_element_list` (removed the stale
  `payload_no_image_list`).

### Validation (no network)
- `python -m py_compile pipeline/kling_apilena_api_executor.py` — clean. Read back the
  patched region to confirm no edit duplication.
- Dry-run proof (scratch script): monkeypatched `_http_json`,
  `_resolve_live_apilena_image_urls`, and `_download_file` to raise if called, then
  built the payload via the REAL `build_reference_url_photo_payload()` using reference
  URLs read from a saved lookup artifact and a real 2026-07-07 workorder slot. Proved:
  `model_name=="kling-v3-omni"`, image_list present, reference is https (no C:\ path),
  element_list absent, negative_prompt absent, n==1, 9:16, reference guard passes, the
  old element_list-only shape is BLOCKED, and **0 network calls attempted**. All
  assertions passed.

### Not done
No Kling call. No render. No publish. No scheduler. No batch. No second variant. No
negative-prompt A/B. No `.env` edit. No R2 hosting. `tools/lena_preflight.py` left
unchanged (the in-executor guard covers the safety requirement).

### Next step
Exactly one n=1 patched-path live test (real executor wiring), then QA — under explicit
approval only ("RUN PATCHED PATH TEST").

---

## 2026-07-07 — Patched-path live test SUCCEEDED end-to-end + first schema-v2 QA PASS

### Direction
Approved "RUN PATCHED PATH TEST": exactly one n=1 render through the real patched
executor to test wiring (not final creative quality). Then log + write the schema-v2 QA
verdict. Constraints: no retries, no batch, no second variant, no negative_prompt, no
element_list, no `.env`, no publish, no scheduler.

### What ran
`CONTENT_BOT_KLING_TARGET_SLOT_ID=2026-07-07-02-photo CONTENT_BOT_KLING_MAX_SLOTS=1
CONTENT_BOT_KLING_EXECUTE=1 python pipeline/kling_apilena_api_executor.py 2026-07-07`.
Target slot `2026-07-07-02-photo` (wardrobe `wc_p034`, scene `env_g002` brunch patio) —
a never-rendered slot, chosen to preserve the earlier cartoon render's evidence.

### Result — SUCCESS
- **The patched production executor succeeded end-to-end.** `ok: true`, `status:
  downloaded`, task `903345804994285660`, endpoint `/v1/images/omni-image`.
- **Submitted payload verified** (from `submit_payload.json`): `model_name=
  "kling-v3-omni"`, `image_list` reference-by-URL present, **element_list absent,
  negative_prompt absent**, n=1, 9:16. The result_manifest records
  `payload_has_image_list/no_element_list/no_negative_prompt: true` and sanitized URLs.
- **Output downloaded to the production library path**
  `pipeline/kling_library/lena/2026-07-07/2026-07-07-02-photo_seed.png`.
- **Photoreal** (real skin texture/pores/freckles, natural hair, golden-hour light, real
  depth of field, coherent brunch-patio scene). **Lena identity strongly conditioned**
  (matches APILENA: hair, dark brown eyes, freckle pattern, gold hoops, curvy build).
  **No cartoon collapse.**
- **Wardrobe/framing were acceptable enough for the API proof** — and notably better
  than the element-only cartoon path: rendered a black ribbed crop top + white mini
  skirt (≈ `wc_p034`) with sunglasses pushed up in hair (matches the brunch pose spec).
- **Reliability is still n=2 total** on the reference-by-URL path (standalone Variant B
  + this patched path). Wiring is confirmed; consistency is NOT yet proven, so this is
  not unattended-production ready.

### Schema-v2 QA verdict (written this turn)
`pipeline/asset_review/lena/2026-07-07/2026-07-07-02-photo_qa.json`, validated via
`lena_photo_qa.validate_qa_result()` (schema v2). **overall: PASS** — the first
schema-v2 QA pass this session. Per field:
- Checklist: `identity_fidelity`, `face_realism_anti_generic_drift`,
  `skin_realism_no_invented_marks`, `public_scene_clothing_continuity`,
  `body_shape_continuity`, `hands_anatomy_sanity`, `environment_realism_scene_
  coherence`, `caption_scene_coherence` = pass; `outerwear_underlayer_correctness` =
  not_applicable; `wardrobe_class_fidelity` = pass (diagnostic-only, close match).
- production_scoring: `hook_strength` = **strong**; `styling_sexy_platform_safe` =
  **pass** (sexy crop+mini, real clothing, platform-safe, on the revealing end but
  within doctrine/IG norms); both variety fields = not_yet_measured.
- **`overall: pass` is a QA-layer verdict against the corrected standard — NOT a
  publish authorization.** The record sets `publish_ready: false`: publishing still
  requires explicit operator sign-off (image + caption) and the path is only n=2.

### What was explicitly not done
Exactly one render. No retries, no batch, no second variant, no negative_prompt, no
element_list, no `.env` edit, no publish, no scheduler, no reliability queue, no further
patching.

### Files updated
QA: `pipeline/asset_review/lena/2026-07-07/2026-07-07-02-photo_qa.json` (new). Logs:
this changelog entry, `lena_filesystem_native_agent_pivot_master.md` (§0 + §14),
`pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md`,
`pipeline/agents/lena/60_executor/CURRENT_STATE.md`,
`pipeline/change_notes/NEXT_SESSION_START.md`.

### Next step
Recommended single next step: a small reliability check (2-3 more n=1 patched-path
renders on fresh slots) before trusting the path for unattended production — under
explicit approval only. No publish without separate operator approval of image+caption.

---

## 2026-07-07 — Reliability check: 2 more patched-path n=1 renders, BOTH PASS (reference-by-URL now consistency-proven)

### Direction
Approved a small reliability check: exactly 2 patched-path n=1 renders on fresh Lena
slots, one at a time, to confirm the reference-by-URL executor path is consistently
photoreal + Lena-conditioned. Stop immediately on any technical or hard visual failure.
No batch, no retries, no negative_prompt, no element_list, no `.env`, no publish, no
scheduler, no executor patching.

### Renders (both through the patched executor, verified pure Variant B)
- **Render 1/2 — `2026-07-07-03-photo`** (wc_p062 copper metallic halter midi dress,
  rooftop sunset). Task `903349357289414713`, `status: downloaded`. Payload verified:
  `model_name="kling-v3-omni"`, image_list reference-by-URL, no element_list, no
  negative_prompt. **PASS:** photoreal, strong APILENA identity match, no cartoon; a
  real elegant fitted metallic halter midi dress (well-matched to wc_p062), fully
  platform-safe; hook **strong**. QA:
  `pipeline/asset_review/lena/2026-07-07/2026-07-07-03-photo_qa.json` (`overall: pass`,
  `publish_ready: false`).
- **Render 2/2 — `2026-07-05-03-photo`** (wc_p086 red tank + black cargo maxi skirt,
  flower shop). Task `903349874073796628`, `status: downloaded` (targeted with
  MAX_SLOTS=1 so the frozen wc_p082 on the same date was skipped, not touched). Payload
  verified pure Variant B. **PASS:** photoreal, strong APILENA identity match, no
  cartoon; real red crop tank + midriff (platform-safe), bottom rendered as black cargo
  PANTS instead of the specified cargo maxi skirt (wardrobe substitution, diagnostic-
  only, non-gating); hook **strong**. QA:
  `pipeline/asset_review/lena/2026-07-05/2026-07-05-03-photo_qa.json` (`overall: pass`,
  `publish_ready: false`).

### Result
**Both passed.** Reference-by-URL is now **4-for-4 photoreal + identity-matched + no
cartoon** (standalone Variant B, patched slot 02, plus these 2 reliability renders),
across distinct outfits (crop+mini, metallic midi dress, red tank + cargo) and scenes
(brunch, rooftop, flower shop). **The patched Kling reference-by-URL path is
reliability-proven enough for controlled production** -- but publishing remains
**operator-approved only** (explicit sign-off on image + caption; no publish authorized
yet). Wardrobe/framing steering (e.g. cargo-pants substitution) is normal production
variance, not an API failure.

### What was explicitly not done
Exactly 2 renders, one at a time. No batch, no retries, no negative_prompt, no
element_list, no web-UI replay, no `.env` edit, no publish, no scheduler, no executor
patching.

### Files updated
QA: two new `*_qa.json` (above). Logs: this changelog entry,
`lena_filesystem_native_agent_pivot_master.md` (§0 + §14),
`pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md`,
`pipeline/agents/lena/60_executor/CURRENT_STATE.md`,
`pipeline/change_notes/NEXT_SESSION_START.md`.

### Next step
No render/publish without explicit approval. The natural next gate is operator
approval of a specific image + caption for a first controlled publish (still requires
Nicolas's explicit go), or continued controlled production under approval. Nothing is
authorized automatically.

---

## 2026-07-07 — First controlled publish packet created (DRAFT, operator-review-required)

### Direction
Prepare one controlled publish packet only, for the strongest reliability-check
candidate. No publish, no schedule, no render, no Kling call, no `.env`, no batch, no
auto-approve.

### What was created
- **Image:** `pipeline/kling_library/lena/2026-07-07/2026-07-07-03-photo_seed.png`
  (wc_p062 copper metallic halter midi dress, rooftop sunset; patched reference-by-URL
  path, task `903349357289414713`).
- **Packet:** `pipeline/publish_packets/lena/2026-07-07/
  LENA_PUBLISH_PACKET_2026-07-07-03-photo.md` (the normal Lena publish-packet path).
- Contents: image path, QA summary (**overall PASS**, `publish_ready: false`), 5 caption
  options (each ≤3 hashtags), one soft CTA, one Story poll idea, one pinned-comment
  idea, IG/FB/TikTok platform notes, and a final operator approval checklist (no box
  checked).
- **Recommended caption:** "the sunset showed up. so did I." (#goldenhour #rooftopstyle
  #citylights).

### Status
Packet is **DRAFT / operator-review-required.** Publishing needs explicit operator
sign-off on image + caption + platform. **Nothing was posted, scheduled, queued, or
auto-approved.** No publish, scheduler, render, Kling call, `.env` edit, or batch.

### Files updated
Packet (new) + this changelog entry, `lena_filesystem_native_agent_pivot_master.md`
(§14), `pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md`,
`pipeline/change_notes/NEXT_SESSION_START.md`.

### Next step
Operator review of the packet. Nothing publishes without Nicolas's explicit
"approved to publish" on a specific image + caption. No automatic action.

---

## 2026-07-07 — Queue entry + dry-run for first controlled publish, then a live-publish bug found and fixed (no post made)

### Direction
User approved: create the queue entry for the packet's recommended image+caption, then
dry-run only. Later, user gave explicit final approval ("APPROVED TO PUBLISH:
2026-07-07-03-photo, caption A, Instagram — run --live") to attempt the real live
publish.

### Queue entry + dry-run (approved, no side effects)
Created `pipeline/queue/2026-07-07-03-photo.json` (media_path, caption "the sunset
showed up. so did I." + 3 hashtags, `platforms: ["instagram"]`, `avatar_nickname:
"Lena"`, `image_engine: "kling_image_3.0"`, full `image_prompt`, source slot/task/QA/
packet traceability, `operator_review_required: true`, `approved_for_live_publish:
false`). Validated against the real contract validator (`instagram_queue_bridge.
validate_post_payload()`, read-only) — passed. Ran `python tools/process_queue.py
--media-type photo --date 2026-07-07` (no `--live`) — `dry_run: true`, `backend:
"local"`, queue file untouched (`moved_to: null`).

### Live publish attempt — FAILED SAFELY, before any network call
Ran `python tools/process_queue.py --live --media-type photo --date 2026-07-07` per
explicit approval. **Result: `success_count: 0`, `failed_count: 1`.** The queue entry
failed local contract validation (`"Lena contract violation: metadata.avatar_nickname
must be Lena"`, repeated 3x = `max_attempts`) and was moved to `pipeline/queue/failed/
2026-07-07-03-photo.json`. **Confirmed no R2 upload, no Meta Graph API call, no
Instagram post occurred** — the failure happened inside local contract validation,
before `instagram_graph_adapter.py`'s HTTP call was ever reached.

### Root cause (pre-existing bug, not specific to this queue entry)
`PostingManager.validate_post()` (`pipeline/posting_manager.py`) discarded the queue
JSON's original `metadata` dict entirely and replaced it with only
`{media_size_bytes, media_sha256}` before passing it to the publisher module. This
meant `avatar_nickname`, `image_engine`, and `image_prompt` never reached
`instagram_queue_bridge._validate_contract()` for ANY queue entry going through
`process_queue.py --live` with `publisher_backend: module` — a latent, previously-
unknown gap between `posting_manager.py` and its own adapter's contract, not something
introduced by or unique to this specific post.

### Fix (approved, minimal, scoped to the one method)
`pipeline/posting_manager.py`, `validate_post()`: metadata is now built by copying the
original queue JSON's `metadata` dict (if present) and merging in `media_size_bytes` /
`media_sha256`, instead of discarding it:
```python
original_metadata = data.get("metadata")
metadata = dict(original_metadata) if isinstance(original_metadata, dict) else {}
metadata.update({"media_size_bytes": ..., "media_sha256": ...})
```

### Validation (no network)
- `py_compile pipeline/posting_manager.py` — clean.
- No-network diagnostic (monkeypatched `urllib.request.urlopen` and
  `requests.request/post/get` to raise if called): ran the real `validate_post()` on
  the failed queue file, then the real `instagram_queue_bridge.validate_post_payload()`
  on the resulting payload. Proved: `avatar_nickname` survives ("Lena"), `image_engine`
  survives ("kling_image_3.0"), `image_prompt` survives (10,031 chars),
  `media_size_bytes`/`media_sha256` correctly added, and **contract validation now
  passes** (`{"ok": true, ...}`). Zero network calls made (no `AssertionError` raised).

### Queue file restored
Moved `pipeline/queue/failed/2026-07-07-03-photo.json` back to `pipeline/queue/
2026-07-07-03-photo.json`, stripping `last_error`/`failed_at_utc`/`publish_attempts`
(clean state; caption/media/metadata otherwise unchanged). Re-ran the dry-run command
(`python tools/process_queue.py --media-type photo --date 2026-07-07`, no `--live`) —
`ok: true`, `success_count: 1`, `failed_count: 0`, queue file still in place
(`moved_to: null`).

### What was explicitly not done
No publish, no R2 upload, no Meta Graph call, no Instagram post (at any point — the
failed attempt never reached the network). No scheduler. No `.env` edit. No render, no
Kling call, no image/caption/platform change.

### Files updated
`pipeline/posting_manager.py` (the fix), `pipeline/queue/2026-07-07-03-photo.json`
(restored), plus this changelog entry,
`lena_filesystem_native_agent_pivot_master.md` (§14),
`pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md`,
`pipeline/change_notes/NEXT_SESSION_START.md`.

### Next step
**Live retry is ready, pending explicit approval.** No automatic retry — waiting for
the same kind of explicit "APPROVED TO PUBLISH..." phrase before running `--live`
again.

---

## 2026-07-07 — Live publish retry: metadata fix confirmed working, but Meta/Instagram auth failed (no post created)

### Direction
Per explicit approval ("APPROVED TO PUBLISH: 2026-07-07-03-photo, caption A, Instagram
— run --live"), retried the live publish after the metadata-preservation fix.

### What happened
`python tools/process_queue.py --live --media-type photo --date 2026-07-07` →
`success_count: 0`, `failed_count: 1`. **No Instagram post was created.**

**The metadata preservation fix worked as intended** — the entry passed local contract
validation this time and reached the real publish adapter (unlike the prior attempt,
which failed before reaching it at all). Tracing `pipeline/publisher/
instagram_graph_adapter.py`:
1. No public media URL was supplied in the queue payload, so `resolve_public_media_url()`
   fell through to its R2 auto-upload path (`pipeline.media_host.r2_uploader.
   upload_file_to_r2`, key pattern `lena/queue-media/2026-07-07/2026-07-07-03-photo.png`).
   **This R2 upload succeeded** — confirmed because execution proceeded to a real Meta
   API call, which requires a resolved URL.
2. `create_media_container()` called the real Meta Graph API 3 times
   (`graph.instagram.com`), and Meta rejected all 3 with a genuine, Meta-issued error
   (real `fbtrace_id` values, not locally fabricated):
   ```
   OAuthException, code 190: "Error validating access token: You cannot access the app
   till you log in to www.instagram.com and follow the instructions given."
   ```

### Result
- **No Instagram post was created.**
- **Root cause is an external Meta/Instagram auth/account challenge — NOT the queue
  metadata bug**, which is confirmed fixed and working correctly. The stored access
  token is invalid/expired and Meta is asking for a direct account login.
- Queue file moved to `pipeline/queue/failed/2026-07-07-03-photo.json` (with
  `last_error`/`publish_attempts` recorded from this attempt).
- **Possible cleanup note:** a real object may now exist in the configured R2 bucket
  from this failed attempt (`lena/queue-media/2026-07-07/2026-07-07-03-photo.png` or
  similar) — should be cleaned up or intentionally reused later. Not deleted this turn.

### What was explicitly not done
No retry. No `.env` edit. No R2 object deletion. No token regeneration. No further Meta
calls. No render, no Kling call, no scheduler, no other publish.

### Files updated
This changelog entry, `lena_filesystem_native_agent_pivot_master.md` (§14),
`pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md`,
`pipeline/change_notes/NEXT_SESSION_START.md`.

### Next step
**Do not retry live publish until the Meta/Instagram token or account issue is fixed**
externally (re-login at instagram.com and/or a fresh long-lived access token). Once
fixed, a fresh explicit "APPROVED TO PUBLISH..." is required before any retry.

---

## 2026-07-07 — Session checkpoint: token fixed → first live Instagram publish succeeded → provenance patch built → commit blocked on unrelated pre-existing hook issue

### Direction
Session context running low; user asked to update the handoff before ending. This
entry covers everything since the last changelog entry: token validation, the first
successful live publish, the provenance-receipt patch (implemented and validated), and
the current git-commit blocker.

### A. What changed
1. **Token/account validation (read-only, no publish):** confirmed
   `META_INSTAGRAM_ACCESS_TOKEN`/`META_IG_USER_ID` present (names only, no values
   printed); ran a token/account check via the real adapter API path
   (`graph.instagram.com`) using the adapter's own alias-resolution helper
   (`_required_env`) — returned username `lenadelapineapple.official`, matching the
   intended account.
2. **Queue restored + dry-run passed:** `pipeline/queue/failed/2026-07-07-03-photo.json`
   restored to `pipeline/queue/2026-07-07-03-photo.json` (failure bookkeeping cleared);
   `python tools/process_queue.py --media-type photo --date 2026-07-07` (no `--live`)
   passed cleanly.
3. **First live Instagram publish SUCCEEDED**, under explicit "APPROVED TO PUBLISH:
   2026-07-07-03-photo, caption A, Instagram — run --live": `python tools/
   process_queue.py --live --media-type photo --date 2026-07-07` → `success_count: 1`.
   Instagram media id `18154201054431808`; permalink `https://www.instagram.com/p/
   Daf8-NgFDSu/` (confirmed via a separate read-only follow-up GET). Queue file moved
   to `pipeline/queue/published/2026-07-07-03-photo.json` (+ sibling
   `.receipt.json`, pre-patch shape).
4. **Read-only provenance audit**, then an **approved additive patch** (scope: two
   files only):
   - `pipeline/publisher/instagram_graph_adapter.py::publish_post()` — one extra
     non-fatal read-only GET, against the **published media id** (explicit
     correction: not the creation/container id), fetching `permalink`/
     `instagram_media_type`/`instagram_timestamp`; these three plus
     `instagram_media_id` now returned in the adapter's result dict.
   - `pipeline/posting_manager.py` — the `receipt` dict now flattens
     `instagram_media_id`/`permalink`/`instagram_media_type`/`instagram_timestamp`/
     `caption_variant` out of the nested publish response (safe `.get()` chains, so
     other backends/dry-runs don't break); `_move_post()` now merges
     `published_post_path` (the final moved-to path) into the receipt before writing
     it.
5. **Validated, no network:** `py_compile` clean on both files; an isolated
   diagnostic (monkeypatched `urllib.request`/`requests` to raise on any call) proved
   the flattening logic against a synthetic response shaped exactly like the patched
   adapter's real output, proved it degrades safely (empty dict) for non-Instagram/
   dry-run shapes, and proved `_move_post()` writes `published_post_path` + all
   provenance fields correctly using an isolated temp directory — **the real
   published item and its existing receipt were deliberately left untouched, not
   backfilled**, per explicit instruction.
6. **Cleanup:** removed exactly two `.pyc` files generated by this session's
   `py_compile` calls (`pipeline/__pycache__/posting_manager.cpython-314.pyc`,
   `pipeline/publisher/__pycache__/instagram_graph_adapter.cpython-314.pyc`) —
   confirmed via timestamp; no other repo clutter touched.
7. **Commit attempted, currently BLOCKED on a pre-existing, unrelated issue.** Staged
   exactly `pipeline/posting_manager.py` and `pipeline/publisher/
   instagram_graph_adapter.py` (confirmed via `git diff --cached --name-only` —
   nothing else staged). `git commit -m "Add Instagram live publish provenance
   receipts"` failed: `.git/hooks/pre-commit` (a pre-commit-framework-generated
   script) hardcodes `--config=.pre-commit-config.yaml`; that file does not exist
   anywhere in the repo (confirmed via repo-wide search and `git log --all`, which
   shows it existed and was referenced in two historical commits but is gone now,
   with the hook never removed/regenerated to match); `.venv` is also absent from
   disk, so the hook falls through to a system-wide `pre-commit` install
   (`/c/Python314/Scripts/pre-commit`) which then fails immediately on the missing
   config, before examining any file content. **Confirmed unrelated to the two
   files' content.** Both target files also turned out to have **zero git history**
   — they were never committed in the first place (installed out-of-band before this
   session via an earlier "Instagram Direct Publisher Patch"), so they show as
   untracked (`??`), not modified.

### B. Files changed
`pipeline/publisher/instagram_graph_adapter.py`, `pipeline/posting_manager.py` (both
untracked in git, edits on disk, currently staged, not yet committed). Queue-lifecycle
data files touched by the publish itself: `pipeline/queue/2026-07-07-03-photo.json` →
moved to `pipeline/queue/published/2026-07-07-03-photo.json` (+ its
`.receipt.json`). Two disposable `.pyc` files removed.

### C. Validations run
Token/account check (read-only GET, real adapter path). Dry-run
(`process_queue.py`, no `--live`). `py_compile` on both patched files (twice — once
after patching, once again immediately before staging). Isolated no-network diagnostic
for the provenance patch (synthetic payloads + temp-dir `_move_post()` test). `git
status`/`git diff --cached --name-only` checks before and after staging.

### D. Decisions made
- Proceed with live publish once token check passed and dry-run passed (per explicit
  approval each step).
- Implement the provenance patch as proposed (permalink queried against the
  **published** media id, per explicit correction).
- Do not backfill the existing published receipt.
- Do not clean up general repo clutter — only the two session-generated `.pyc` files.
- Do not bypass the broken pre-commit hook without a fresh explicit approval, even
  though it's confirmed unrelated to file content.

### E. Blockers / parked branches
- **Git commit blocked** on the pre-existing, broken `.git/hooks/pre-commit` /
  missing `.pre-commit-config.yaml` — unrelated to Lena/publisher work, not yet
  resolved. Three options on the table for the user: bypass with `--no-verify` for
  this one commit (recommended), recreate `.pre-commit-config.yaml`, or stop and
  handle it separately.
- **Possible R2 cleanup item, still open:** the earlier failed publish attempt (before
  the token fix) likely left a real object in the configured R2 bucket
  (`lena/queue-media/2026-07-07/2026-07-07-03-photo.png` or similar) — not deleted,
  not yet resolved either way.
- Kling render freeze / Kling Omni/BodyLock / business pivot: all unchanged, not
  touched this session's tail.

### F. Next approved step
Resolve the git-commit blocker per the user's decision. Everything else (Lena render
freeze, publish-approval discipline, business pivot) remains exactly as last recorded
— nothing else is pending action.

### G. What must not be done
No render, no Kling call, no `.env` edit, no further publish without explicit
approval, no R2 deletion without explicit approval, no `--no-verify` without a fresh
explicit approval, no touching the Kling executor, no unrelated repo cleanup, no
backfilling the existing published receipt.

## 2026-07-07 (continued) — git-commit blocker resolved

Investigated the broken hook directly: `.git/hooks/pre-commit` is a
`pre-commit`-framework-generated script (untracked, local-only, not part of
the repo) hardcoding `--config=.pre-commit-config.yaml`; that config file
does not exist anywhere in git history or the working tree, and `.venv` is
also absent, so the hook falls through to a system-wide `pre-commit` install
that fails immediately on the missing config — confirmed unrelated to any
file content, including the two staged publisher files.

Presented the user three options (remove the stale hook / `--no-verify` /
stop). **User chose: remove the stale hook.** Deleted `.git/hooks/pre-commit`
(safe — untracked, local-only, was a pure no-op-that-fails since no config
backs it). Re-verified only `pipeline/posting_manager.py` and
`pipeline/publisher/instagram_graph_adapter.py` were staged
(`git diff --cached --name-status`), then committed clean as `8870a82b`
"feat: add Instagram Graph publisher and posting manager" — no
`--no-verify` used, nothing else staged or committed.

**Next approved step:** none pending on this thread — it's closed. Lena
render/publish threads remain in their last recorded state (render freeze
narrowed but in force; no further publish without explicit approval).

## 2026-07-07 (continued) — Git-durability + info-hierarchy checkpoint

### Direction
Priority explicitly set to Lena autonomy (photo lane first, video later), not
`business_media`. A read-only audit found the entire proven Lena photo chain
(executor, identity, QA, production job, preflight, scheduler/env/queue glue,
prompt brain repairs, Kling contract) existed only on local disk — never
committed to git, in any commit, ever (`git log --all` empty for those paths)
— a durability risk given how much of this session's work depends on it. A
second audit then found `information_hierarchy/Projects/Lena Influencer
Node/Instructions/Instructions.md` was stale: it named the retired
`hcr_001`/`wc_p045`/BODYLOCK-era scripts as the "official" pipeline, two of
which are already deleted from the working tree.

### A. What changed
1. **Audited candidate live-path files** (read-only): confirmed 9 of 11 were
   untracked (`pipeline/kling_apilena_api_executor.py`, `pipeline/identity/
   lena_identity.py`, `pipeline/qa/lena_photo_qa.py`, `pipeline/
   lena_production_job.py`, `tools/lena_preflight.py`, `pipeline/scheduler.py`,
   `pipeline/scheduler_jobs.py`, `pipeline/env_loader.py`, `tools/
   process_queue.py`), and 2 were tracked-but-modified (`pipeline/prompting/
   lena_prompt_brain.py`, `pipeline/config/lena_kling_contract.json`). Ran a
   masked secret-pattern scan on all candidates plus every later cached diff
   before each commit — zero hardcoded secrets found; only env-var *names*
   (`KLING_AK`/`KLING_SK`/`KLING_WEB_TOKEN`) read via `os.environ.get(...)`,
   the expected pattern.
2. **Batch A committed (`3bf932ab`):** `pipeline/identity/lena_identity.py`,
   `pipeline/qa/lena_photo_qa.py`, `pipeline/kling_apilena_api_executor.py`,
   `pipeline/lena_production_job.py`, `tools/lena_preflight.py` — tracked
   byte-for-byte as-is, `py_compile` clean, no behavior change.
3. **Batch B committed (`2c49b348`):** `pipeline/scheduler.py`, `pipeline/
   scheduler_jobs.py`, `pipeline/env_loader.py`, `tools/process_queue.py` —
   same treatment, `py_compile` clean, no behavior change.
4. **Batch C reviewed then committed (`81056cb3`):** the pending diffs on
   `pipeline/prompting/lena_prompt_brain.py` (the already-implemented
   negative-prompt tiering repair, identity/skin-realism language, and
   catalog-driven scene/wardrobe/environment selection replacing old
   `random.choice` calls) and `pipeline/config/lena_kling_contract.json`
   (video-count fields all set to `0`, `photos_per_day` 2->3, schedule slot
   swapped from video to photo) were reviewed in full, `py_compile`/JSON-valid
   confirmed, secret-scanned clean, and confirmed to contain only the
   documented repairs with no unrelated content before committing.
5. **Content-packet builder wiring audited** (read-only, no edits): confirmed
   `tools/strategy/lena_build_content_packet_dryrun_v1.py` is tracked/modified
   (small, cosmetic wording diff, left uncommitted/untouched), reads a
   separate recipe/hook/wardrobe/environment catalog system, writes to
   `pipeline/strategy/lena/content_packets/` (last real output 2026-07-01,
   predating the reference-by-URL breakthrough) using its own prompt schema,
   and never reads rendered images, QA schema v2, reference-by-URL artifacts,
   queue files, or publish receipts. Confirmed via direct comparison against a
   real 2026-07-07 workorder that the two prompt schemas are structurally
   unrelated. Conclusion: this script is an upstream ideation/planning aid,
   not the live publish-packet builder; the real gap is a not-yet-built
   `90_content_packet/` slice.
6. **Information-hierarchy correction committed (`a0407bc2`):** rewrote the
   "Current Production-Proof Loop" section of `information_hierarchy/
   Projects/Lena Influencer Node/Instructions/Instructions.md` to state the
   real live chain, label the content-packet builder as ideation-only, note
   the `90_content_packet/` gap (with `95_publish_gate/` explicitly deferred
   until a real packet artifact exists), note video is disabled/photo-first,
   and note the studio element is reserved for a later out-of-scope video
   lane. Relabeled the old `hcr_001`/`wc_p045` "Known result status" bullets
   as superseded historical record rather than current guidance. Secret-scanned
   clean; only this one file staged and committed (the rest of
   `information_hierarchy/` remains untracked, deliberately not staged).

### B. Files changed (committed)
`pipeline/identity/lena_identity.py`, `pipeline/qa/lena_photo_qa.py`,
`pipeline/kling_apilena_api_executor.py`, `pipeline/lena_production_job.py`,
`tools/lena_preflight.py` (`3bf932ab`); `pipeline/scheduler.py`, `pipeline/
scheduler_jobs.py`, `pipeline/env_loader.py`, `tools/process_queue.py`
(`2c49b348`); `pipeline/prompting/lena_prompt_brain.py`, `pipeline/config/
lena_kling_contract.json` (`81056cb3`); `information_hierarchy/Projects/Lena
Influencer Node/Instructions/Instructions.md` (`a0407bc2`).

### C. Validations run
`py_compile` on every `.py` file before each commit; JSON-load validation on
`lena_kling_contract.json`; masked secret-pattern scan (token/secret/
password/bearer/authorization/access_token/api_key/META_INSTAGRAM_
ACCESS_TOKEN/KLING_*KEY/R2_*) against every cached diff before each commit —
zero hardcoded secrets found in any batch; exact-staged-set checks
(`git diff --cached --name-status`) before every commit.

### D. Decisions made
- Split the git-durability work into three approval-gated batches (core
  execution / queue+scheduling glue / prompt+contract) rather than one large
  commit, so each diff stayed reviewable.
- Track the untracked files exactly as-is, no opportunistic cleanup or
  refactor bundled in.
- Correct only the one stale information-hierarchy file, not the whole
  `information_hierarchy/` tree, and stage only that one file, not the
  directory.
- Leave `tools/strategy/lena_build_content_packet_dryrun_v1.py` itself
  untouched — it's harmless, dry-run-only, and any redesign is a separate,
  future, explicitly-approved decision.

### E. Blockers / parked branches
None new. `business_media`/`podcast_repurpose` remains explicitly paused per
direction ("priority is Lena, not business_media, sales, or outreach right
now") — not touched this checkpoint.

### F. Next approved step
None yet decided. Two candidates discussed, neither started: (1) design
(docs-only) a `90_content_packet/` folder-native slice — a real tool that
builds a publish packet from an actual QA-passed render, the confirmed next
build target ahead of `95_publish_gate/`; (2) a further reliability check on
the reference-by-URL photo path (currently 4-for-4, still a small sample) —
this one would call Kling and needs explicit per-render approval. Neither is
authorized yet.

### G. What must not be done
No code edits to the executor, identity, QA, prompt brain, or content-packet
builder beyond what's already committed above. No Kling call, no render, no
publish, no R2 upload, no `.env` edit, no video API work, no studio-element
use, no `business_media`/sales/outreach work, no broad repo cleanup.

## 2026-07-07 (continued) — 90_content_packet slice checkpoint

### Direction
Following the git-durability checkpoint, a read-only audit of `tools/
strategy/lena_build_content_packet_dryrun_v1.py`'s wiring (recorded in the
prior changelog entries) found it disconnected from the real live chain and
recommended a real, future `90_content_packet/` folder-native slice as the
next build target ahead of `95_publish_gate/`. Approved to design (docs-only)
that slice.

### A. What changed
1. **Read-only design pass** grounded in the existing five-slice pattern
   (`40_identity_continuity/` through `80_repair/`) and the one real,
   hand-built precedent on disk
   (`pipeline/publish_packets/lena/2026-07-07/
   LENA_PUBLISH_PACKET_2026-07-07-03-photo.md`), traced end to end against
   real artifacts: the workorder JSON, the QA JSON (schema v2), the queue
   item that was actually processed, and its publish receipt.
2. **`pipeline/agents/lena/90_content_packet/` created**, docs-only, with
   the standard five files:
   - `AGENT.md` -- role, no-code-owner status, how a future session should
     use the folder.
   - `RULES.md` -- Rule zero (no QA pass, no packet), a must-never-do list
     (no Kling/render/publish/R2/`.env`, never auto-approve or set
     `approved_for_live_publish: true`, never treat the old dry-run builder
     as an input, never write directly into live `pipeline/queue/`), a
     human-approval-required list, and why this slice precedes
     `95_publish_gate/`.
   - `INPUTS.md` -- exact required/optional artifacts (workorder JSON,
     rendered image path, QA JSON with `production_scoring`, optional Kling
     result manifest/prompt receipt) and what it explicitly does not read.
   - `OUTPUTS.md` -- the intended publish-packet Markdown structure (10
     sections, mirrored from the real precedent), an intended optional
     queue-JSON draft shape, and an explicit "no builder code exists yet"
     gap statement.
   - `CURRENT_STATE.md` -- dated status: docs/design only, the one real
     precedent named explicitly, what doesn't exist yet, what's not
     currently proven.
3. **Committed as `61ae69b3`** "docs: add Lena content packet agent slice" --
   staged-set verified exact (five files, all `A`), cached diff reviewed in
   full before commit, masked secret scan clean (only generic policy-sentence
   hits on "authorization"/"secrets", no credential values).

### B. Files changed (committed)
`pipeline/agents/lena/90_content_packet/AGENT.md`, `RULES.md`, `INPUTS.md`,
`OUTPUTS.md`, `CURRENT_STATE.md` (`61ae69b3`).

### C. Validations run
Exact-staged-set check (`git diff --cached --name-status`) before commit;
masked secret-pattern scan against the cached diff (zero hardcoded secrets);
manual cross-check of every documented input/output path against the real
2026-07-07-03-photo artifacts (workorder, QA JSON, queue item, receipt) to
ground the design in what actually happened, not assumption.

### D. Decisions made
- Design the slice as pure documentation, matching the established
  five-slice pattern exactly, rather than writing any packet-builder code in
  the same pass.
- Leave `tools/strategy/lena_build_content_packet_dryrun_v1.py` completely
  untouched -- documented as ideation-only, not repurposed or edited.
- Explicitly sequence `90_content_packet/` ahead of a future
  `95_publish_gate/`, since the gate needs a real packet artifact to gate
  and none exists yet from tooling (only the one hand-built example).

### E. Blockers / parked branches
None new. `business_media`/`podcast_repurpose`, video API work, and the
studio element remain untouched/paused per standing direction.

### F. Next approved step
Not yet decided. Two candidates named, neither started: (1) a read-only
scoping pass for what real `90_content_packet` packet-builder code would
need -- still requires separate explicit approval before any code is
written; (2) a further, explicitly-approved Kling reliability check on the
reference-by-URL photo path (would call Kling, needs per-render approval).
`95_publish_gate/` remains explicitly deferred.

### G. What must not be done
No packet-builder code without separate explicit approval. No edits to
`tools/strategy/lena_build_content_packet_dryrun_v1.py`. No Kling call, no
render, no publish, no R2 upload, no `.env` edit, no secrets printed, no
video API work, no studio-element use, no `business_media`/sales/outreach
work, no broad repo cleanup.

## 2026-07-07 (continued) — Publish packet builder -- Batches 1+2

### Direction
Following the read-only scoping pass for `90_content_packet` packet-builder
code, approved to implement it in two small, explicitly-approved batches:
Batch 1 (read-only resolver) first, then Batch 2 (Markdown packet writing)
as a separate approval.

### A. What changed
1. **Batch 1 (`346d0006`) -- created `tools/lena_build_publish_packet_v1.py`,
   read-only resolver.** Resolves a named `--date`/`--slot` against
   `pipeline/kling_workorders/<date>/daily_workorders.json`, resolves and
   existence-checks the rendered image path, resolves the QA path via
   `pipeline/qa/lena_photo_qa.py`, runs `validate_qa_result()`, hard-fails
   unless `overall == "pass"`, resolves optional debug/result-manifest
   artifacts. Writes nothing. **Confirmed and deliberately avoided reusing
   `tools/lena_review_proof_render_v1.py`'s `build_review_bundle()`**,
   because it calls `lena_photo_qa.save_qa_template()`, which writes an
   unreviewed QA scaffold file the first time a slot has no QA file
   (`force=False` means "never overwrite," not "never write") -- correct for
   a review helper, wrong for a resolver that must hard-fail with zero
   writes. Validated: `py_compile` clean; positive case against the real
   QA-passed `2026-07-07-03-photo` slot succeeded; two negative cases (a real
   slot with no QA file at all, `2026-07-07-01-photo`; a real slot with QA
   `overall: fail`, `2026-07-05-02-photo`) both aborted cleanly, zero files
   written, exit 1.
2. **Batch 2 (`ea139e69`) -- extended the same file with Markdown packet
   assembly and non-clobber write logic.** Adds `build_caption_options()`
   (deterministic, mechanical caption-option drafts grounded in the
   workorder's own caption/lane/wardrobe/environment metadata -- explicitly
   not creative copywriting, no generation call involved) and
   `build_packet_markdown()` (the 10-section format from
   `90_content_packet/OUTPUTS.md`: header with an explicit "does not approve
   or publish anything" statement, image/scene/wardrobe/environment/task-id
   details, QA summary including `publish_ready`/`publish_ready_reason`,
   3-5 caption options each capped at 3 hashtags, soft CTA, optional Story
   poll, optional pinned comment, platform notes, a fully unchecked operator
   approval checklist, and closing notes). `write_packet()` writes to
   `pipeline/publish_packets/lena/<date>/LENA_PUBLISH_PACKET_<slot_id>.md`,
   non-clobber by default (aborts with `PacketWriteError` unless `--force`),
   `--force` overwrites only that exact resolved file (explicit directory
   guard). New CLI flags `--out-dir` and `--force`; **no `--live`,
   `--approve`, or `--queue` flag added.** No queue-draft writing exists in
   this batch. Validated: `py_compile` clean; a no-`--force` run against the
   real existing hand-built packet path aborted cleanly, packet confirmed
   untouched via mtime check; a `--out-dir scratch/
   lena_packet_builder_validation` run succeeded, wrote one file, contents
   inspected (all required elements present, matched the real precedent's
   task id `903349357289414713`), then the entire scratch output directory
   was deleted; `pipeline/queue/` confirmed untouched via mtime check across
   both batches.

### B. Files changed (committed)
`tools/lena_build_publish_packet_v1.py` -- created read-only (`346d0006`),
extended with Markdown writing (`ea139e69`).

### C. Validations run
`py_compile` on both commits. Real-artifact positive/negative resolver
tests (QA-pass, missing-QA, failing-QA). Real non-clobber-abort test against
the existing hand-built packet (confirmed untouched by mtime). Real write
test to an isolated scratch directory (inspected, then deleted). `git
status`/mtime checks confirming `pipeline/queue/` and the real publish
packet were never modified. Exact-staged-set checks before each commit.
Manual review of both cached diffs confirming no imports of
`pipeline.posting_manager`, `tools.process_queue`,
`pipeline.kling_apilena_api_executor`, `pipeline.env_loader`, `requests`, or
`urllib` in either batch.

### D. Decisions made
- Split into two commits (resolver, then writer) matching the two explicitly
  approved batches, rather than one combined commit.
- Explicitly reject reusing `build_review_bundle()` once its
  `save_qa_template()` side effect was confirmed, in favor of a
  purpose-built read-only equivalent.
- Keep caption-option generation purely mechanical/template-based (grounded
  in real workorder metadata, no generation call) rather than attempting
  creative copywriting in code.
- Defer queue-draft writing (Batch 3) and `95_publish_gate/` to separate,
  later, explicitly-approved steps.

### E. Blockers / parked branches
None new. `business_media`/`podcast_repurpose`, video API work, and the
studio element remain untouched/paused per standing direction.

### F. Next approved step
Not yet decided. Batch 3 (`--queue-draft` JSON emission, to a clearly
non-live path, `approved_for_live_publish` hardcoded `false`) remains
optional and deferred, needing its own separate approval. A further,
explicitly-approved Kling reliability check remains a separate, alternative
track. `95_publish_gate/` remains deferred until packet/queue-draft behavior
is settled.

### G. What must not be done
No queue-draft writing without separate explicit approval. No writes to
`pipeline/queue/`. No `--live`/`--approve`/`--queue` flag added without
separate explicit approval and design review. No Kling call, no render, no
publish, no R2 upload, no `.env` edit, no secrets printed, no video API
work, no studio-element use, no `business_media`/sales/outreach work, no
broad repo cleanup.

## 2026-07-07 (continued) — Publish packet builder -- Batch 3

### Direction
Following a read-only scoping pass for the Batch 3 `--queue-draft` design
(schema, safety fields, output path, guard requirements), approved to
implement it in `tools/lena_build_publish_packet_v1.py` -- the last of the
three originally-scoped batches.

### A. What changed
1. **Committed as `e9edb3d9`** "feat: add Lena queue draft output" --
   added an optional `--queue-draft` CLI flag to the existing resolver +
   Markdown-writer script. No other file touched.
2. **Queue-draft output path:** `<out-dir>/<date>/<slot_id>_queue_draft.json`
   via `resolve_queue_draft_output_path()`, default out-dir
   `pipeline/publish_packets/lena/` (same base as the Markdown packet) --
   **never `pipeline/queue/`**.
3. **Hard guard added:** `_assert_not_inside_live_queue()` resolves the
   intended queue-draft path and the live `pipeline/queue/` root to
   absolute paths and raises `QueueDraftGuardError` if the target equals or
   is nested under the live queue directory. **Wired to run in `main()`
   before any write this run** (including the Markdown packet) whenever
   `--queue-draft` is passed -- a bad `--out-dir` aborts the whole run with
   zero files written, not just the queue-draft part.
4. **Queue-draft content** (`build_queue_draft()`, pure function, no I/O):
   `post_id`, `media_path`, `media_type: "photo"`, `platforms: ["instagram"]`,
   `caption` (hardcoded placeholder string, never auto-selected -- RULES.md),
   `approved_for_live_publish: false` (hardcoded), `operator_review_required:
   true` (hardcoded), and a `metadata` block with `publish_packet_path`
   (pointer back to the Markdown packet), `qa_path`, `qa_overall`,
   `source_date`, `source_slot_id`, `generated_by`, `queue_draft_only: true`
   (hardcoded), plus `source_task_id`/`wardrobe_outfit_id`/
   `reference_binding_mode` when available.
5. **Non-clobber write** (`write_queue_draft()`): same pattern as the
   Markdown packet -- aborts unless `--force`, `--force` overwrites only the
   exact resolved file, explicit directory guard.
6. **Validated:** `py_compile` clean; positive test (`--out-dir scratch/
   lena_packet_builder_validation --queue-draft`) wrote both files, contents
   inspected (`approved_for_live_publish: false`, `operator_review_required:
   true`, `metadata.queue_draft_only: true`, placeholder caption present,
   `metadata.publish_packet_path` correctly points at the Markdown packet);
   two guard tests (`--out-dir pipeline/queue --queue-draft` and `--out-dir
   pipeline/queue/something --queue-draft`) both aborted cleanly, exit 1,
   zero files written; `find pipeline/queue -newermt "10 minutes ago" -type
   f` empty across every test; real existing hand-built packet confirmed
   untouched via mtime check; scratch output inspected then deleted.

### B. Files changed (committed)
`tools/lena_build_publish_packet_v1.py` -- extended with `--queue-draft`
support (`e9edb3d9`).

### C. Validations run
`py_compile`. Real positive write test to an isolated scratch directory
(both packet and queue draft written, inspected, deleted). Two real guard
tests proving `--out-dir pipeline/queue` and a subdirectory variant both
abort before any write. `pipeline/queue/` and the real existing publish
packet confirmed untouched via mtime checks across every test. Exact-
staged-set check before commit. Manual review of the cached diff confirming
no new imports beyond what Batches 1-2 already used.

### D. Decisions made
- Run the live-queue guard before the Markdown packet write (not just
  before the queue-draft write) whenever `--queue-draft` is requested, so a
  misconfigured `--out-dir` can never produce a partial write.
- Hardcode all four safety fields (`approved_for_live_publish`,
  `operator_review_required`, `queue_draft_only`, the placeholder caption)
  in code rather than exposing any of them as CLI-settable.
- Default the queue-draft location to the same base directory as the
  Markdown packet (`pipeline/publish_packets/lena/`) rather than inventing a
  third artifact location.

### E. Blockers / parked branches
None new. `business_media`/`podcast_repurpose`, video API work, and the
studio element remain untouched/paused per standing direction.

### F. Next approved step
Not yet decided. All three originally-scoped batches for
`tools/lena_build_publish_packet_v1.py` are now complete. `95_publish_gate/`
is the next reasonable docs-only design target (the packet/queue-draft
behavior it would gate is now settled), but building it needs its own
separate approval, same as every other slice this session.

### G. What must not be done
No `--live`/`--approve`/publish flag added without separate explicit
approval and design review. No writes to `pipeline/queue/`. No Kling call,
no render, no publish, no R2 upload, no `.env` edit, no secrets printed, no
video API work, no studio-element use, no `business_media`/sales/outreach
work, no broad repo cleanup.

## 2026-07-07 (continued) — 95_publish_gate slice checkpoint

### Direction
Following completion of all three batches of `tools/lena_build_publish_
packet_v1.py`, a read-only scoping pass defined the future `95_publish_
gate/` slice -- the durable human approval decision record sitting between
`90_content_packet/` and live publish. Approved to create it docs-only,
matching every prior slice's genesis.

### A. What changed
1. **`pipeline/agents/lena/95_publish_gate/` created**, docs-only, with the
   standard five files:
   - `AGENT.md` -- role, no-code-owner status, sequencing rationale
     (this slice needed `90_content_packet/`'s real packet/queue-draft
     artifact to exist first, per that slice's own RULES.md).
   - `RULES.md` -- Rule zero (records decisions, never makes them),
     required-inputs list, seven hard blocks (placeholder caption, >3
     hashtags, QA not `pass`, missing packet, missing expected queue draft,
     missing/false `metadata.queue_draft_only`, unclear operator approval),
     safe handling of the queue draft's three existing safety fields (all
     stay untouched forever -- approval recorded as a separate artifact,
     with the explicit note that `posting_manager.py` doesn't even read
     `approved_for_live_publish` as a code-level gate), a "must never do"
     list (no `pipeline/queue/` writes, no `process_queue.py`/
     `posting_manager.py` calls), and a human-approval-required list.
   - `INPUTS.md` -- the five required inputs (packet, QA-verdict-via-
     pointer, queue draft when expected, final chosen caption, operator
     approval statement) and what it explicitly does not read.
   - `OUTPUTS.md` -- two unbuilt output concepts (a future approval-
     decision artifact, format undecided; human-readable manual promotion
     instructions only, never an automated file move) and an explicit gap
     statement that nothing is built.
   - `CURRENT_STATE.md` -- dated status: docs-only, no code, explicit list
     of what does not exist (no artifact builder/reader, no queue promotion
     tool, no publish automation added), and the two next-step candidates.
2. **Committed as `3a4c1412`** "docs: add Lena publish gate agent slice" --
   staged-set verified exact (five files, all `A`), cached diff reviewed in
   full before commit, masked secret scan clean (zero hits).

### B. Files changed (committed)
`pipeline/agents/lena/95_publish_gate/AGENT.md`, `RULES.md`, `INPUTS.md`,
`OUTPUTS.md`, `CURRENT_STATE.md` (`3a4c1412`).

### C. Validations run
Exact-staged-set check (`git diff --cached --name-status`) before commit;
masked secret-pattern scan against the cached diff (zero hits); manual
cross-check of every documented rule/field against the real
`tools/lena_build_publish_packet_v1.py` code (confirmed
`posting_manager.py` does not read `approved_for_live_publish` as a gate,
grounding this slice's "separate artifact, not a mutated flag" design
decision).

### D. Decisions made
- Design this slice as pure documentation, matching the established
  six-slice pattern exactly, rather than writing any approval-artifact code
  in the same pass.
- Explicitly forbid this slice, now or ever, from writing into
  `pipeline/queue/` -- a stronger, more permanent prohibition than
  `90_content_packet/`'s own (which only forbids it for that slice's
  current scope); `95_publish_gate/RULES.md` states this boundary stays a
  human, manual action indefinitely.
- Record any future approval decision as a separate artifact rather than
  mutating the queue draft's own safety fields, since
  `posting_manager.py` doesn't enforce those fields anyway -- the real
  safety value is the durable record, not a flag flip.

### E. Blockers / parked branches
None new. `business_media`/`podcast_repurpose`, video API work, and the
studio element remain untouched/paused per standing direction.

### F. Next approved step
Not yet decided. Read-only scoping for a future approval-record
checker/builder remains the named next candidate, still requiring separate
explicit approval before any code is written. A further Kling reliability
check remains a separate, unrelated, alternative track.

### G. What must not be done
No approval-artifact code without separate explicit approval. No code that
writes into `pipeline/queue/`, ever, in any form. No Kling call, no render,
no publish, no R2 upload, no `.env` edit, no secrets printed, no video API
work, no studio-element use, no `business_media`/sales/outreach work, no
broad repo cleanup.

## 2026-07-07 (continued) — Approval record checker/writer -- Batches 1+2

### Direction
Following the `95_publish_gate/` docs-only slice creation, a read-only
scoping pass defined the future approval-record checker/builder. Approved
to implement it in two batches: Batch 1 (read-only checker, all hard-fail
rules) first, then Batch 2 (`--record`/`--force` writing) as a separate
approval.

### A. What changed
1. **Batch 1 (`bd4b6135`) -- created `tools/lena_record_publish_approval_v1.py`,
   read-only checker.** Reuses (imports, does not duplicate)
   `tools/lena_build_publish_packet_v1.py`'s `resolve_packet_inputs()`,
   `resolve_packet_output_path()`, `resolve_queue_draft_output_path()`,
   `QUEUE_DRAFT_CAPTION_PLACEHOLDER`, and `LIVE_QUEUE_ROOT` -- so the
   placeholder string and the live-queue guard can never drift out of sync
   between the two tools. Validates: publish packet exists; QA re-validated
   to `overall == "pass"` (never trusted from a cached claim); queue draft
   exists and carries `metadata.queue_draft_only: true`; queue-draft path
   is not inside `pipeline/queue/`; approved caption is not the placeholder
   and has <=3 hashtags; `--approved-by` is non-empty; `--confirm` exactly
   matches the required phrase `"I approve this for live publish"`. Prints
   a dry-run JSON summary including the future approval record and
   human-readable promotion instructions. Writes nothing. Validated:
   `py_compile` clean; a real run against the actual `2026-07-07-03-photo`
   slot correctly hit the missing-queue-draft hard-fail (none exists
   non-live); a scratch queue draft was generated via the already-committed
   packet builder to exercise the full positive path and all other
   hard-fails (placeholder caption, >3 hashtags, wrong confirm phrase,
   queue draft inside `pipeline/queue/`, empty `--approved-by`) -- all
   behaved as designed, `files_written_this_run: []` in every case,
   `pipeline/queue/` confirmed untouched via mtime check.
2. **Batch 2 (`68bba745`) -- extended the same file with `--record` and
   `--force`.** Adds `write_approval_record()`: writes the approval
   artifact to `<out-dir>/<date>/<slot_id>_approval.json` (default
   `pipeline/publish_packets/lena/`), guarded against
   `pipeline/queue/` via `_assert_not_inside_live_queue()` (reused), non-
   clobber by default (`ApprovalWriteError` unless `--force`), `--force`
   overwrites only the exact resolved file with an explicit directory
   guard. No `--live`/`--publish`/`--approve-and-publish`/queue-promotion
   flag added. Validated: `py_compile` clean; a positive `--record` test
   against a scratch packet+draft wrote exactly one file, inspected and
   matched the exact 14-field schema; a non-clobber retry (no `--force`)
   aborted cleanly; a `--force` retry overwrote the exact scratch file with
   updated content; two live-queue-guard tests (`--out-dir pipeline/queue`
   and `--out-dir pipeline/queue/something`, both with `--record`) aborted
   before any write (caught by the earlier missing-packet check in this
   particular CLI path; the dedicated live-queue guard function was
   additionally unit-tested directly in isolation and confirmed to
   independently block both cases); all three re-tested hard-fails
   (placeholder caption, >3 hashtags, wrong confirm phrase) still aborted
   cleanly with `--record` present; `pipeline/queue/` and the real existing
   publish packet confirmed untouched via mtime checks throughout; scratch
   output inspected then deleted.

### B. Files changed (committed)
`tools/lena_record_publish_approval_v1.py` -- created read-only (`bd4b6135`),
extended with `--record`/`--force` writing (`68bba745`).

### C. Validations run
`py_compile` on both commits. Real-artifact tests against the actual
`2026-07-07-03-photo` slot (missing-queue-draft hard-fail confirmed).
Scratch-directory positive/negative tests for every hard-fail rule across
both batches. Non-clobber and `--force` write tests against a scratch
approval artifact. Live-queue-guard tests (CLI-level and direct unit-level).
`pipeline/queue/` and the real publish packet confirmed untouched via mtime
checks after every test. Exact-staged-set checks before each commit. Manual
review of both cached diffs confirming no imports of `pipeline.
posting_manager`, `tools.process_queue`, `pipeline.kling_apilena_api_executor`,
`pipeline.env_loader`, `requests`, or `urllib`.

### D. Decisions made
- Split into two commits (checker, then writer) matching the two explicitly
  approved batches.
- Reuse (import) the packet builder's placeholder constant and live-queue
  guard concept rather than re-typing them, to eliminate drift risk between
  the two tools.
- Guard the approval-artifact output path independently in
  `write_approval_record()`, on top of the queue-draft path's own guard in
  the Batch 1 checker -- defense-in-depth even though the current check
  ordering means the packet-existence check is what actually fires first
  for a `pipeline/queue`-pointed `--out-dir`.
- Require an exact-match confirm phrase (not a general truthy flag) as a
  deliberate typo/accident guard before recording any approval.

### E. Blockers / parked branches
None new. `business_media`/`podcast_repurpose`, video API work, and the
studio element remain untouched/paused per standing direction.

### F. Next approved step
Not yet decided. The full Lena photo chain (render -> QA -> packet -> queue
draft -> approval record) is now built and documented; the final live step
(manual promotion into `pipeline/queue/` + `tools/process_queue.py --live`)
remains manual by design, not automated, and no change to that boundary is
proposed. A further Kling reliability check remains a separate, unrelated,
alternative track.

### G. What must not be done
No queue-promotion code without separate explicit approval and design
review far beyond this session's scope. No writes to `pipeline/queue/`. No
Kling call, no render, no publish, no R2 upload, no `.env` edit, no secrets
printed, no video API work, no studio-element use, no
`business_media`/sales/outreach work, no broad repo cleanup.

---

## 2026-07-07/08 — Frame-logic + expression/gaze layers committed; reliability render; compaction-budget redesign

### A. What changed
Six sequential pieces of work, in order:

1. **Frame-logic layer** added to `pipeline/prompting/lena_prompt_brain.py`:
   `Frame logic:` paragraph (frame_action, frame_evidence_objects,
   frame_forbidden_objects, camera_intent, body_visibility_rule,
   scene_coherence_note) inserted right after `Scene:` in every generated
   prompt, sourced from new `pipeline/prompt_banks/lena/
   lena_frame_logic_bank_v1.json` (26 lanes, covers the 17 active + 9
   currently-blocked production lanes). Directly targets the gap that caused
   the earlier `2026-07-05-01-photo` attempt-1 QA fail (wine-bar-patio and 4
   other nightlife lanes had zero frame/evidence-contract data at all).
2. **Executor floor for frame logic**: two reserved floors in
   `_build_compact_prompt()` (`_FRAME_LOGIC_ACTION_FORBIDDEN_FLOOR_*` for
   `Frame logic:`/`Avoid:`, `_FRAME_LOGIC_SUPPORT_FLOOR_*` for the remaining
   sub-clauses) -- a real 200-slot pre-floor test showed the paragraph was
   dropped in effectively every real slot without them.
3. Both committed as `feat: add Lena frame logic prompt layer` (`b41495e6`),
   via careful hunk-level staging (a HEAD-vs-working-tree reconstruction, not
   `git add -p`) to exclude a pre-existing, separately-authored, still-
   uncommitted "expression/gaze diversity layer" edit in the same file.
4. **Expression/gaze layer** added the same way: `choose_expression_gaze_
   production()` / `format_expression_gaze_line()`, new `lena_expression_
   gaze_bank_v1.json` (15 combos), `LANE_EXPRESSION_TAG_ALLOWLIST` (26 lanes),
   a real recency guard (`_recent_expression_gaze_ids()`, scans the last 5
   dated `pipeline/kling_workorders/` folders / 6 slots on disk). Audited
   read-only first: confirmed no identity-drift language in any of the 15
   combos, confirmed the bank JSON existed on disk but was untracked. Its own
   executor floor (`_EXPRESSION_GAZE_FLOOR_*`) added and validated the same
   way (0/200 -> 200/200 survival). Committed as `feat: add Lena expression
   gaze rotation` (`93abc27c`), same careful-staging technique.
5. **Reliability render on the repaired `2026-07-05-01-photo` slot.**
   Surgically refreshed only that slot's embedded entry in `daily_workorders.
   json` (+ sidecar) to carry the new prompt -- confirmed via tracing
   `_load_manifest()`/`_submit_photo()` that the executor reads exclusively
   from `daily_workorders.json`'s embedded `slots[]`, never the standalone
   sidecar file. Archived attempt 1's failed artifacts (seed PNG, debug dir,
   QA json) to `*_attempt1_failed_alcohol_focal_body_drift.*` paths (moved,
   not deleted) before running attempt 2. One real Kling render approved and
   run: task `903633841376596038`, reference-by-URL, `kling-v3-omni` --
   succeeded technically. QA verdict (schema v2): **`overall: fail`** on
   `body_shape_continuity` only. Everything the new layers were built to fix
   worked: alcohol non-focal (frame logic reframed the base scene's "glass in
   hand" away from a raised/focal read), frame-logic evidence/forbidden
   objects correctly reflected, expression natural and non-identity-breaking,
   wardrobe/identity/environment/caption all pass. Per QA-fail rules: stopped,
   no packet, no queue draft, no approval record, no publish. Attempt 2's
   artifacts are NOT yet archived (deliberately left in place per explicit
   instruction, pending a decision on attempt 3).
6. **Body-shape continuity investigation (read-only)** found three
   independent, unfixed contributing causes: (a) `build_reference_url_photo_
   payload()` omits `negative_prompt` entirely from the payload (matching the
   original successful live-test design) -- `BODY_ANATOMY_NEGATIVE_TERMS`
   never reaches Kling on this path regardless of compaction; (b) the actual
   reference image sent is `image_list[0]` from `_extract_live_element_urls()`,
   which walks the APILENA element's registered resources in registration
   order with no content-aware selection -- the one used for the attempt-2
   render measured 2558x2560 (near-square, `resourceKey: "cover"`), and none
   of the element's 4 registered resources are portrait/vertical-oriented like
   a real full-body reference photo; (c) **the executor never reads
   `reference_mode` or `reference_priority` at all** -- a whole-file grep
   found zero matches -- so the prompt-brain's `REFERENCE_MODE_POLICIES`/
   `REFERENCE_PRIORITY`/`reference_priority_for_mode()` machinery has no
   effect on which reference image actually gets sent. None of these three
   are patched.

### B. Files changed
- `pipeline/prompting/lena_prompt_brain.py` -- frame-logic layer, expression/
  gaze layer (both committed).
- `pipeline/prompt_banks/lena/lena_frame_logic_bank_v1.json`,
  `lena_expression_gaze_bank_v1.json` -- both new, both committed.
- `pipeline/kling_apilena_api_executor.py` -- frame-logic floor (committed in
  `b41495e6`), expression floor (committed in `93abc27c`), a later attempted
  20-char body-shape floor (implemented, tested, then explicitly reverted via
  `git checkout`, never committed), and the compaction-budget redesign patch
  described in the next entry (implemented, validated, **not yet committed**).
- `pipeline/kling_workorders/2026-07-05/daily_workorders.json` +
  `2026-07-05-01-photo.json` (sidecar) -- surgically refreshed, untracked
  artifacts (never git-tracked either way).
- `pipeline/kling_library/lena/2026-07-05/` and `pipeline/kling_debug/
  apilena_api/2026-07-05/` and `pipeline/asset_review/lena/2026-07-05/` --
  attempt-1 artifacts archived (moved, not deleted); attempt-2 artifacts
  written, not yet archived.

### C. Validations run
`py_compile` on every patch. Real `_build_compact_prompt()` runs against the
real `2026-07-05-01-photo` slot at every stage. Real 200-slot survival tests
(not simulated) confirming marker survival before each commit and before/
after each floor change. Direct image viewing + real schema-v2 QA scoring for
the attempt-2 render. A whole-file grep confirming `reference_mode`/
`reference_priority` are never read by the executor. Direct inspection of the
real `live_apilena_lookup_response.json` debug artifact to get the actual
registered-resource dimensions.

### D. Decisions made
- Careful hunk-level (not `git add -p`) staging to keep the frame-logic and
  expression/gaze commits each isolated from the other, unrelated,
  pre-existing uncommitted edit in the same file.
- Reference-mode/negative-prompt/reference-image-selection findings from the
  body-shape investigation are documented but explicitly NOT patched yet --
  each flagged as needing its own separate approval, per explicit instruction
  not to broaden scope past what was approved for a given task.
- The first body-shape floor attempt (700 chars) was rejected after it broke
  identity survival on a real slot; rather than silently picking a smaller
  "safe-looking" number, a full sweep was run, which surfaced the pre-existing
  ~21% identity-failure rate; the resulting 20-char no-op was explicitly
  reported as a placeholder, not shipped as a feature, then reverted entirely.
- The proper fix (a dedicated core identity/body-shape floor using existing
  source sentences, not new executor-authored text) was simulated with a
  standalone reimplementation of the floor algorithm before being approved and
  implemented for real, to avoid another surprise regression.

### E. Blockers / parked branches
- The compaction-budget redesign patch is implemented and validated but
  **uncommitted**, awaiting Nicolas's review of the validation report.
- Attempt 2's render/debug/QA artifacts are not yet archived.
- The three body-shape contributing-cause findings (negative-prompt omission,
  reference-image selection, inert reference_mode) remain open and unfixed.
- No attempt 3 is approved.

### F. Next approved step
Nicolas reviews the uncommitted executor redesign patch; if approved, commit
it as its own change. Separately (own approval needed): archive attempt 2's
artifacts before any attempt 3; decide whether/how to address the three
body-shape contributing causes; decide whether to pursue attempt 3 at all
before those are addressed, given body-shape drift may recur even with the
compaction fix.

### G. What must not be done
No render, no publish, no queue/promotion, no approval record, no `.env`
edit, no cleanup, no commit of the pending executor patch without explicit
review. No archiving of attempt 2's artifacts without explicit approval. No
further body-shape floor size changes without re-running the full 200-slot +
real-target-slot validation described above.

---

## 2026-07-08 — First successful live Lena publish this session (checkpoint)

### A. What changed
No code changed in this entry -- this is a checkpoint recording a milestone
already reached via prior approved steps. `2026-07-05-01-photo` published
live to Instagram: permalink `https://www.instagram.com/p/Dag-lAQFFvj/`,
media ID `18086313821391447`, published `2026-07-08T02:33:31+0000`, caption
"one quick patio stop and suddenly it was a whole night" + `#softstyle
#neutralstyle #outfitdetails`. QA schema-valid, `overall: pass`,
`publish_ready: true`.

### B. Files changed
None (checkpoint only). Referenced artifacts: `pipeline/queue/published/
2026-07-05-01-photo.json` + its `.receipt.json` (authoritative post-publish
record); `pipeline/publish_packets/lena/2026-07-05/
2026-07-05-01-photo_approval.json` (pre-publish signoff, deliberately left
unrewritten, still reads `promotion_status: "not_yet_promoted"` by design).

### C. Validations run
None new -- this checkpoint follows the full validation chain already
recorded in the 2026-07-07/08 entry above and the intervening session turns
(local contract validation passed, real R2/Meta/Graph calls succeeded,
receipt confirmed, no other queue item processed).

### D. Decisions made
Approval record is treated as an immutable pre-publish artifact and will
never be rewritten to reflect post-publish outcomes; the queue's published
receipt is the authoritative source of truth for what actually happened.
Saved to Claude's cross-session memory as
`feedback_approval_record_vs_receipt_doctrine.md`.

### E. Blockers / parked branches
None on this slot. Seven future tasks identified, none scoped or started:
post-publish receipt-linking tool; pose/body-language rotation audit;
camera-source realism audit; prop interaction rules audit; micro-story/
moment-before-after layer; recent-repeat memory expansion
(environment_id/camera_intent/reference_mode); reference-selection/body-
conditioning investigation (negative-prompt omission, image_list[0]
selection, inert reference_mode/reference_priority).

### F. Next approved step
None pending on this slot. Any of the 7 future tasks requires its own
explicit approval before starting.

### G. What must not be done
Do not rewrite the approval record. Do not re-promote or republish this
slot. Do not delete any archived failed-attempt artifact. Do not start any
of the 7 future tasks without separate explicit approval.

---

## 2026-07-08 (later in session) — Pose/attitude layer, Visual Hook / Allure QA gate, Higgsfield provider pivot

### A. What changed
Seven commits landed, in order: `9c53281e` (pose/body-language rotation
layer), `ef5dad4f` (wardrobe/environment visual-hook weighting),
`8f5261be` (pose/expression attitude weighting), `5b53d7a3` (QA schema-v3
allure hard gate), `7f9ab9aa` (visual QA `RULES.md` reviewed and
committed), `331f0d1c` (Higgsfield provider-transition doc), `d082c170`
(Higgsfield no-live-call dry-run diagnostic). Two real live renders were
attempted and both QA-failed for real, different reasons -- neither was a
wasted step; each exposed a real gap that was then closed with code, not
just doctrine.

1. **Pose/body-language rotation** (`9c53281e`): new
   `pipeline/prompt_banks/lena/lena_pose_body_language_bank_v1.json` (12
   neutral/modifier combos), `choose_pose_body_language_production()` wired
   into `lena_prompt_brain.py`, new `Pose:` compaction floor in
   `kling_apilena_api_executor.py`. Validated: 200-slot survival, all prior
   markers intact.
2. **Attempt 1** (`2026-07-04-02-photo`, morning apartment/wc_p047):
   surgical splice-refresh (only new layers added, original scene/wardrobe
   preserved), one approved live render, task `903717132796563465`.
   **QA-failed** after direct operator review: body_shape_continuity fail
   (wide-leg trousers hid the hip/thigh line the pose was meant to prove),
   plus a prop-logic fail (pouring vessel read as another cup, not a
   creamer/pot). Saved as cross-session memory
   `project_lena_pose_proof_2026-07-04-02-photo_fail.md` and
   `feedback_qa_body_sexiness_calibration.md` (Claude's own QA judgment had
   under-scrutinized body-shape/prop-plausibility, corrected).
3. **Candidate search + attempt 2** (`2026-07-07-01-photo`, flower
   shop/wc_p030, denim-mini-skirt/crop-top/open-blazer -- a fitted,
   pose-visible outfit chosen specifically to fix attempt 1's failure
   mode): attempt-1's original *cartoon-era* failed render on this slot
   was archived first (`*_attempt1_failed_cartoon_3d_pre_reference_url.*`,
   moved not deleted), then one approved live render, task
   `903723240236523560`. Technically clean (pose clearly visible, frame
   logic reflected, no cartoon drift, identity held) -- **QA-failed anyway**
   after a major doctrine correction from Nicolas: "not enough allure / sexy
   IT-girl energy... too cute, safe, and lifestyle-boring... technically
   coherent images that do not feel like Lena" are real failures, not
   passes. Saved as major cross-session memory
   `project_lena_visual_hook_allure_doctrine.md`. A related correction,
   `feedback_nightlife_alcohol_not_prohibited.md`: nightlife/social/going-
   out settings are fully allowed; the only real guardrail is alcohol
   non-focality (hero/focal/promotional/intoxication/unwanted-centering),
   never the setting itself -- prior audit phrasing ("no alcohol/nightlife
   issue") was corrected going forward.
4. **Visual Hook / Allure Gate, read-only audit then patch** (`ef5dad4f`):
   found `lena_wardrobe_catalog_v1.json`'s `body_visibility`/
   `coverage_level` fields and `lena_environment_catalog_v1.json`'s `mood`
   field already existed but were never read by selection. Added
   `_body_visibility_hook_weight()` and `_environment_allure_weight()` to
   `lena_prompt_brain.py` -- additive-only, floored at 1, never hard-bans;
   validated via a real before/after distribution shift (e.g. flower-shop
   wardrobe draws shifted from 13.6%/81.8%/4.5% to ~26.8%/~73.2%/0% across
   full_body/three_quarter/waist_to_head) and a full 200-slot marker
   survival re-check.
5. **Pose/expression attitude weighting, read-only audit then patch**
   (`8f5261be`): found the pose bank had zero attitude-coded entries by
   design and the expression bank had only 3 of 15. Added `attitude_level`
   (neutral/moderate/high) to every existing combo, added 6 new
   high-attitude poses (`pose_p013`-`pose_p018`: hand-on-hip, hip-shift-
   chin-down, wall-lean-hip-pop, three-quarter-angle-curve-visible,
   hair-touch-confident-gaze, squared-confident-stance) and 2 new
   high-attitude expressions (`exp_g016`, `exp_g017`), plus
   `_pose_attitude_weight()`/`_expression_attitude_weight()` in
   `lena_prompt_brain.py`. Validated: 1000-draw distributions clearly favor
   high/moderate without eliminating neutral; all attitude levels still
   appear across 4 different lanes at 300 draws each.
6. **QA schema-v3 allure hard gate, read-only audit then patch**
   (`5b53d7a3`): `pipeline/qa/lena_photo_qa.py` bumped to
   `SCHEMA_VERSION = "3"`, new `LEGACY_SCHEMA_VERSIONS_WITHOUT_ALLURE_GATE
   = {"1", "2"}` so existing on-disk "1"/"2" QA files (including both real
   failed renders above) validate **unchanged** -- confirmed via direct
   reload, not assumed. Six new `production_scoring` fields:
   `allure_level` (none forces `overall: fail`), `it_girl_energy` (fail
   forces `overall: fail`), `body_visibility_score`/`outfit_hook_score`/
   `pose_attitude_score` (advisory only this first pass, deliberately not
   gating yet), `feed_worthy_reason` (required non-empty once a record is
   finalized pass/fail). Validated with 9+ synthetic checks covering every
   gating combination (false-green rejections both directions, advisory
   fields not forcing fail alone, empty-reason rejection on finalized
   records).
7. **`pipeline/agents/lena/70_visual_qa/RULES.md` reviewed and committed**
   (`7f9ab9aa`): this file (and its whole directory) had substantial real
   pre-existing content but had never once been committed. Read-only
   reviewed for accuracy against the just-shipped schema-v3 code (every
   referenced constant/field name cross-checked and confirmed to exist),
   found zero stale/conflicting content, committed as-is. Sibling files
   (`AGENT.md`/`CURRENT_STATE.md`/`INPUTS.md`/`OUTPUTS.md`) deliberately
   left untracked/unreviewed.
8. **250-sample no-render audit**: confirmed the full stack (wardrobe +
   environment + pose + expression weighting, all 14 prior compaction
   markers, QA-v3 template scaffold) works together in memory, before any
   further render was considered. Zero files written, zero API calls.
9. **Provider pivot: Higgsfield established as the committed forward
   direction** (Nicolas's decision). A read-only repo-side audit found the
   selection/QA/publish layers already provider-agnostic; only the executor
   and Kling's element-based identity mechanism are actually Kling-specific.
   A read-only **official-docs-only** verification (higgsfield.ai/cli,
   higgsfield.ai/mcp, the official CLI and Python-SDK GitHub READMEs -- no
   scraping, no browser automation, no install, no login) established CLI
   over MCP as the right first integration route (Higgsfield's own MCP page
   recommends CLI for Claude-Code-class agents) and documented real,
   unresolved blockers: no documented prompt-length limit, no documented
   negative-prompt support, no native dry-run mode, no documented output-
   download-to-file path, Soul character identity (20+ reference photos)
   does not map 1:1 from Kling's single-hosted-element mechanism, auth
   token refresh/storage undocumented, per-model pricing undocumented, and
   a genuine content-moderation/NSFW risk given Lena's sexy-but-platform-
   safe strategy (Higgsfield's own Soul model blocks NSFW prompts; the SDK
   has a terminal `NSFW` job-status value).
10. **`331f0d1c`** (docs-only): added a "Provider transition in progress:
    Higgsfield" section to `tools/LEGACY_PROVIDER_SURFACES.md` recording all
    of the above plus a 7-step future sequence. Committed via an
    **index-only `git hash-object`/`git update-index` technique**, not
    `git add -p` -- this file already carried real, unrelated, pre-existing
    2026-07-05 uncommitted drift with zero unchanged context line
    separating it from the new section (`git add -p --split` literally
    returned "Sorry, cannot split this hunk" when tried). The index-only
    method constructed HEAD's content plus only the new section, verified
    byte-for-byte, and committed that -- leaving the older drift exactly as
    it was in the working tree, untouched.
11. **`d082c170`**: added `tools/diagnostics/lena_higgsfield_payload_dryrun.py`
    -- stdout-only, zero subprocess/network/Higgsfield-SDK imports (verified
    by grep), reads a real slot and prints a Higgsfield command/contract
    summary (model placeholder, raw prompt/negative-prompt lengths,
    intended-but-never-executed CLI shape, expected output path, proposed
    `pipeline/higgsfield_debug/...` manifest path, identity-strategy
    placeholder, 8 risk flags). Validated against two real slots; zero
    files written either time.
12. **Explicitly recommended NOT done**: rewriting `LIVE_PATHS.md`/
    `AUTHORITATIVE_SURFACES.md`/the live-path manifest to call Kling
    "legacy" -- read-only audit concluded those statements are still
    factually true today (Higgsfield has no working executor yet) and
    changing them now would be misleading, not accurate.

### B. Files changed
`pipeline/prompt_banks/lena/lena_pose_body_language_bank_v1.json` (new, then
extended with `attitude_level` + 6 combos), `lena_expression_gaze_bank_v1.json`
(extended with `attitude_level` + 2 combos), `pipeline/prompting/
lena_prompt_brain.py` (pose layer wiring, 4 new weighting helper functions),
`pipeline/kling_apilena_api_executor.py` (new `Pose:` compaction floor only),
`pipeline/qa/lena_photo_qa.py` (schema v3), `pipeline/agents/lena/
70_visual_qa/RULES.md` (newly tracked), `tools/LEGACY_PROVIDER_SURFACES.md`
(Higgsfield section only, via index-only staging -- pre-existing 2026-07-05
drift on this file deliberately left uncommitted), new
`tools/diagnostics/lena_higgsfield_payload_dryrun.py`. Two real render
artifacts + two real QA files (`2026-07-04-02-photo`, `2026-07-07-01-photo`,
both `overall: fail`) plus one archived failed-cartoon-render pair
(`2026-07-07-01-photo` attempt 1).

### C. Validations run
`py_compile` on every Python file touched. Real 200/250-slot
`generate_prompt_package()` + `_build_compact_prompt()` survival sweeps after
every patch (pose layer, wardrobe/environment weighting, attitude weighting)
-- always 100% on all 14 tracked markers. Real distribution-shift
measurements (before/after weighting) on real catalog data, not simulated.
9+ synthetic QA-v3 validator checks covering every new gating combination.
Real reload of all pre-existing on-disk QA files (schema "1" and "2")
confirming zero regression. Two real live Kling renders, each followed by
direct image viewing and a real QA verdict (both `fail`, for different,
specific, documented reasons). Static-analysis (grep-based) confirmation
that the new Higgsfield dry-run tool imports zero network/subprocess/SDK
surfaces.

### D. Decisions made
Technical coherence is not sufficient for a Lena QA pass -- allure/IT-girl/
scroll-stopping energy is now a hard, code-enforced gate, not just written
doctrine. Nightlife/social settings are never themselves a risk signal --
only alcohol focality is. New QA-v3 fields launch mostly gating
(`allure_level`, `it_girl_energy`) with three fields deliberately advisory-
only for this first pass, to force structured reviewer attention without
over-constraining before real usage data exists. Provider-transition
doctrine is recorded as "committed direction" (in `LEGACY_PROVIDER_SURFACES.md`)
separately from "current technical reality" (in `LIVE_PATHS.md`/
`AUTHORITATIVE_SURFACES.md`, deliberately left unchanged) -- these must not
be conflated until Higgsfield actually has a working, QA-reviewed render.

### E. Blockers / parked branches
`tools/LEGACY_PROVIDER_SURFACES.md`'s pre-existing 2026-07-05 drift is
reviewed (accurate, every referenced file confirmed to exist, no doctrine
conflict) but **not yet committed** -- needs one more explicit approval. No
third pose-proof render attempted yet. No Higgsfield executor exists --
blocked on explicit approval for CLI install + login before any of that
work starts. `business_media`/`podcast_repurpose` and ElevenLabs both remain
untouched and paused; ElevenLabs was confirmed (read-only) to already have
substantial pre-existing, dormant code from an earlier paused video/podcast
lane, not to be touched.

### F. Next approved step
None of the following is pre-approved -- each needs its own explicit
instruction: (1) commit the reviewed `LEGACY_PROVIDER_SURFACES.md` drift
(message: `docs: correct Lena canonical live-path routing legend`); (2) a
third pose/body-language proof render using the now-complete weighting +
QA-v3 stack, starting with a fresh read-only candidate search; (3) Higgsfield
executor skeleton work, gated on separate CLI install/login approval first.

### G. What must not be done
Do not rewrite `LIVE_PATHS.md`/`AUTHORITATIVE_SURFACES.md`/the live-path
manifest to call Kling legacy yet. Do not delete/rename/clean any Kling path
(`kling_library/`, `kling_debug/`, `kling_workorders/`). Do not install,
login, or call the Higgsfield CLI/SDK without separate explicit approval. Do
not build an OpenAI image-generation path, a Kling fallback, or broad multi-
provider routing. Do not integrate ElevenLabs or touch its existing dormant
code. Do not rerender either failed pose-proof slot without separate
approval. Do not touch the remaining untracked `70_visual_qa/` sibling files.
Do not commit `LEGACY_PROVIDER_SURFACES.md`'s pre-existing drift bundled with
anything else.

## 2026-07-08 (continuity checkpoint) — Higgsfield-native prompt/photo-dump/library tooling landed undocumented; multi-axis curator built uncommitted

### A. What changed
This entry is itself the fix for a documentation gap: 8 real commits landed
after `d082c170` with zero entry in `NEXT_SESSION_START.md`, this changelog,
or the master doc's §0, and a further real patch landed on top of the
newest of those commits without ever being committed. Nothing in this
entry is new code -- it is a read-only inspection (`git log`, `git diff
--stat`, `git show`) plus running the one dry-run diagnostic that was
already sitting validated-but-uncommitted, to confirm it still works before
recording it accurately.

1. **Correction:** the previous entry above (`2026-07-08 (later in
   session)`) lists `tools/LEGACY_PROVIDER_SURFACES.md`'s reviewed
   2026-07-05 drift as "not yet committed -- needs one more explicit
   approval" (see its §E). That is now stale -- it was committed as
   `fa4b2b2c` (`docs: correct Lena canonical live-path routing legend`).
2. **8 commits recorded, in order, none previously documented:**
   `fa4b2b2c` (committed the `LEGACY_PROVIDER_SURFACES.md` drift, see
   above), `1b7f2a48` (`docs: add Lena AI creator disclosure layer` --
   disclosure copy/policy/media-kit-schema/persona files), `c5d5faf6`
   (`feat: add Higgsfield-native Lena prompt-pack builder` --
   `generate_higgsfield_prompt_package()` in `pipeline/prompting/
   lena_prompt_brain.py`), `e8d2858b` (`fix: move Higgsfield Soul selection
   out of prompt text` -- Soul reclassified as provider config/metadata,
   `soul_selection_mode: provider_config_not_prompt_text`), `9fc84356`
   (`fix: prevent Higgsfield crop conflicts`), `b4e85687` (`fix: sanitize
   Higgsfield wardrobe and pose prompts` -- wardrobe/silhouette sanitizer,
   high-hook fitted-wardrobe fallback, straight-jeans/casual/shape-hiding
   block coverage), `fb13a12f` (`feat: add Higgsfield photo dump prompt
   dry-run` -- `generate_higgsfield_photo_dump_pack()` plus `tools/
   diagnostics/lena_higgsfield_photo_dump_dryrun.py`, deterministic,
   stdout-only), `9f5bcb7d` (`feat: add Higgsfield prompt library dry-run`
   -- **current committed HEAD**; `tools/diagnostics/
   lena_higgsfield_prompt_library_dryrun.py` committed at 244 lines,
   generates many photo-dump packs by calling the single-pack builder once
   per pack with deterministic slot prefixes). `negative_prompt_enabled`
   stayed `False` and no heavy body-overcorrection language was
   reintroduced anywhere across this range.
3. **Multi-axis model-hook curator found as uncommitted WIP on top of
   `9f5bcb7d`, inspected, compiled, and run (not written by this
   checkpoint -- it already existed on disk).**
   `tools/diagnostics/lena_higgsfield_prompt_library_dryrun.py` carries a
   603-line working-tree version against a 244-line committed version (a
   359-line uncommitted diff). It adds `--select-top N` /
   `--show-selected-prompts`: hard-excludes any prompt failing the
   existing pack-level validation (framing, wardrobe casual-terms,
   scene/action conflicts, Soul leak, negative-prompt-disabled,
   heavy-overcorrection, pose-scene match, low-hook filler, a basic
   unsafe/explicit-term check), scores survivors on five independent axes
   (wardrobe/pose/expression/scene/camera -- explicitly not a
   wardrobe-only search, matching the standing "sexy is not just mini
   dresses" correction), and greedily selects the top N with soft
   lane/silhouette diversity caps (max 2 each, relaxed only if needed to
   fill N). `pipeline/prompting/lena_prompt_brain.py` was not touched.

### B. Files changed
None, by this checkpoint itself. The 8 commits in item 2 above already
touched `pipeline/prompting/lena_prompt_brain.py`,
`tools/diagnostics/lena_higgsfield_payload_dryrun.py`,
`tools/diagnostics/lena_higgsfield_photo_dump_dryrun.py`,
`tools/diagnostics/lena_higgsfield_prompt_library_dryrun.py`,
`tools/LEGACY_PROVIDER_SURFACES.md`, root `SKILL.md`, and the Lena
disclosure/persona files under `pipeline/influencer_nodes/lena/` -- all
prior to this checkpoint, all already committed. The only uncommitted code
in the working tree relevant to this checkpoint is the curator patch on
`tools/diagnostics/lena_higgsfield_prompt_library_dryrun.py` (item 3
above), which this checkpoint did not author.

### C. Validations run
`git log --oneline`, `git diff --stat`, and `git show --stat` across the
`d082c170..9f5bcb7d` range to enumerate the undocumented commits and
confirm none touched `NEXT_SESSION_START.md`/the master doc/this
changelog. For the uncommitted curator: `python -m py_compile
tools/diagnostics/lena_higgsfield_prompt_library_dryrun.py` (clean); one
real run with `--date 2026-07-08 --library-prefix july08 --packs 3
--count-per-pack 10 --select-top 5 --show-selected-prompts` (30/30
hard-validation pass, 0 excluded, 5/5 selected across 3 lanes and 4
silhouettes); a grep across the file confirming no
`subprocess`/`requests`/`urllib`/`socket` import and no file-write call.
No render, no network call, no Higgsfield/Kling call, no publish, no queue
promotion, no R2, no `.env` access, no install/login, no cleanup/delete/
move, no approval-record edit, no commit.

### D. Decisions made
Continuity docs are updated by inspecting real `git log`/`git diff`
against their own claimed state, not by trusting the most recent banner's
self-report -- this checkpoint found the banners were 8 commits and one
full uncommitted feature behind reality. The uncommitted curator is
recorded as exactly that (uncommitted WIP, validated, not committed) --
this checkpoint does not commit it, since committing code was explicitly
out of scope for this pass.

### E. Blockers / parked branches
The multi-axis model-hook curator (`tools/diagnostics/
lena_higgsfield_prompt_library_dryrun.py`, +359 uncommitted lines) is
validated and ready for review but **not committed** -- needs its own
explicit approval, separate from this documentation checkpoint.
`pipeline/prompt_banks/lena/lena_wardrobe_catalog_v1.json` still carries
separate, unrelated, pre-existing uncommitted drift -- untouched, not in
scope. `pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md` was
identified as a secondary staleness gap (it wraps `lena_prompt_brain.py`,
which received real committed changes in the `d082c170..9f5bcb7d` range)
but was explicitly excluded from this checkpoint's scope -- still stale,
not fixed here.

### F. Next approved step
None of the following is pre-approved -- each needs its own explicit
instruction: (1) review and commit the multi-axis curator patch; (2) a
Higgsfield executor skeleton, gated on separate CLI install/login approval
first, unchanged from the prior entry; (3) optionally, a follow-up doc
checkpoint for `50_prompt_builder/CURRENT_STATE.md`.

### G. What must not be done
Do not commit the curator patch without separate explicit approval. Do not
touch `pipeline/prompt_banks/lena/lena_wardrobe_catalog_v1.json`. Do not
touch `pipeline/prompting/lena_prompt_brain.py`,
`pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md`, prompt banks,
Kling files, or anything in `pipeline/queue/`/publish/R2/`.env`. Do not
render, call Higgsfield/Kling live, install/login, or touch the untracked
dirty pile beyond what is already documented above.

## 2026-07-09 — Motorcycle glam pillar built, corrected twice, 5 commits

### A. What changed
Built a full motorcycle content pillar for Lena from scratch, in 5
separately-approved, separately-validated commits, each with a real
200-prompt dry-run before commit:

1. **`06813da7` `feat: add Lena motorcycle glam prompt lane`** -- first
   real motorcycle content. One lane (`motorcycle street glam`, matte-
   black sport bike), a dedicated in-code wardrobe pool (5 variants, kept
   out of the shared catalog so its safety boundaries stay under direct
   code control), 7 pose variants swapped in for moto-lane images the same
   way the pack builder already swaps generic pose variants, a safety
   lock, and curator archetype (`motorsport_street_glam`) / broad-group
   (`motorsport_or_vehicle_editorial`) recognition.
2. **`c9f89552` `feat: expand Lena motorcycle glam prompt pillar`** --
   Nicolas's correction: the first lane proved the plumbing worked but was
   creatively too narrow. Expanded to 7 lanes: `heritage moto pinup`,
   `antique cruiser editorial`, `custom chopper eye candy`, `garage grease
   glam`, `bike wash bikini`, `desert roadside cruiser`, plus the original.
   Added 5 more lane-restricted wardrobe variants (moto_w06-w10: halter+
   jeans, cut-off denim shorts, coveralls, two bikini-adjacent combos) and
   expanded `HIGGSFIELD_PHOTO_DUMP_MOTO_SCENE_KEYWORDS` so the new lanes'
   "cruiser"/"chopper" action text still triggers moto-specific pose
   selection. **Bug caught and fixed pre-commit**: `garage grease glam`/
   `bike wash bikini` were pulling from the *entire* wardrobe pool instead
   of their themed-only variants -- a 200-sample run showed zero coveralls/
   bikini draws despite those being the whole point of those two lanes.
   Fixed via `HIGGSFIELD_MOTO_EXCLUSIVE_WARDROBE_LANES`, restricting those
   two lanes to their tagged variants only; reran and confirmed exact
   1:1 match between themed-variant draws and lane draws.
3. **`2cc6b204` `feat: add real motorcycle anchors and seductive moto
   styling`** -- two corrections bundled in one commit. (a) Real historic
   motorcycle model anchors: `HIGGSFIELD_MOTO_MODEL_ANCHORS`, 20 approved
   names (Indian Chief/Scout/101 Scout/Four, Harley Knucklehead/Panhead/
   WLA/Hydra-Glide/Duo-Glide/Shovelhead/Sportster Ironhead, Vincent Black
   Shadow/Triumph Bonneville/Norton Commando as occasional extras, 6
   chopper anchors), lane-restricted and drawn via `rng.choice()` the same
   way wardrobe already is, injected into a new `_higgsfield_moto_realism_
   clause()` function replacing the old fixed "a real parked motorcycle"
   wording. (b) Skin-forward wardrobe/pose/expression expansion after
   Nicolas flagged the safety lock read as conservative, not platform-
   safe: 6 new wardrobe variants (moto_w11-w16: bandeau, tied crop tops,
   open-jacket-over-bikini), 5 new seductive-but-editorial poses (arched
   posture, hand on thigh/waistband, boot on foot peg), and a brand-new
   moto-only Expression pool (`HIGGSFIELD_PHOTO_DUMP_EXPRESSION_VARIANTS_
   MOTO`, 4 variants) swapped in the same way pose already is -- the first
   time this system has had per-lane expression variety instead of one
   single global Expression line. **Two bugs caught and fixed pre-commit,
   both self-inflicted collisions with the curator's own term lists**: the
   word "sheer" inside the rewritten safety lock's "non-sheer fabric"
   false-triggered `HOOK_WARDROBE_TERMS`' "sheer" reward term (crediting a
   safety negation as a sexy cue -- moto score briefly read 20 instead of
   the correct 19); the word "explicit" inside "no legs-spread or sexually
   explicit posing" false-triggered `UNSAFE_EXPLICIT_TERMS`' "explicit"
   hard-exclusion, silently hard-excluding all 50 moto prompts in a test
   run (39/50 excluded) from ever reaching curation. Both reworded ("no
   see-through material anywhere", "overtly sexual posing"), both reran
   clean (0/50 excluded, curator picks restored).
4. **`356a66e3` `fix: enforce motorcycle authenticity and text hygiene`**
   -- Nicolas's first hard-QA correction, after the first real Higgsfield
   visual test: fake/gibberish AI lettering on background signage, and
   generic/inaccurate bike anatomy with invented logos, were both real
   render failures. Added an anatomy-match clause (tank shape/engine
   layout/exhaust pipes/wheels-spokes/seat/forks/handlebars visually
   matching the named real model) and a text-hygiene clause (blank/aged/
   blurred signage only, no gibberish lettering) to both realism-clause
   variants (named-model and unnamed-street-glam), removed the vague
   "Indian-style"/"Harley-style" scene-bank placeholders (3 lanes) now
   that a real model name comes from code, and added 3 new reporting-only
   diagnostics (`motorcycle_model_anchor_present`, `moto_logo_
   authenticity_clause_present`, `background_text_hygiene_clause_present`,
   plus `fake_text_avoidance_present`) plus a manual-generation doctrine
   comment (hide/crop in post, real reference images, or verified logo add
   in post -- three fallback options if prompt text alone proves
   insufficient). **Bug caught and fixed pre-commit**: the word "fake" in
   "...over a fake one" is one of the pipeline's pre-existing `BANNED_
   PUBLIC_TERMS` (the AI-disclosure-avoidance sanitizer applied to every
   assembled Higgsfield prompt) and got silently stripped, leaving broken
   grammar ("...over a one"). Reworded to "an invented one," reran clean.
5. **`a1639bb0` `fix: hide motorcycle logos and remove text surfaces`** --
   Nicolas's second, stricter correction, after reviewing more real
   renders: "no readable logo" still implicitly allowed a small/blank
   badge to be visible; the real rule is that logos are never visible at
   all -- hidden/covered/obscured by construction (turned away from
   camera, cropped out, blocked by hand/helmet/jacket, lost in shadow or
   glare), real or invented, verified or not. Likewise "blank/blurred
   signs" became "no sign-shaped objects at all" -- a blank sign is still
   a sign-shaped thing for the model to hallucinate text onto. Rewrote
   both realism-clause variants accordingly; removed sign objects entirely
   from 3 scene-bank lanes (`heritage moto pinup`, `antique cruiser
   editorial` dropped their sign phrases outright; `desert roadside
   cruiser`'s gas-station sign became a silhouette-with-lights, no
   signage); replaced the 2 prior-commit reporting checks with 3 new ones
   matching the escalated clause (`moto_logo_hidden_clause_present`,
   `no_visible_motorcycle_logo_clause_present`, `no_text_surfaces_clause_
   present`), kept `fake_text_avoidance_present` and the model-anchor
   check unchanged. **Bug caught and fixed pre-commit**: the new `no_text_
   surfaces` check's signature phrase, `"no readable text surfaces"`,
   didn't actually occur in the clause text (which reads "...labels, *or*
   readable text surfaces...", not "*no* readable text surfaces" as one
   phrase) -- first run showed 0/30 present; fixed by correcting the
   signature to `"readable text surfaces"` (the substring that's actually
   there), reran to 30/30.

### B. Files changed
All 5 commits touched exactly the same 3 files each time (never more, per
explicit per-commit approval): `pipeline/prompting/lena_prompt_brain.py`,
`pipeline/prompt_banks/lena/lena_photo_scene_bank_v1.json` (the live scene
source -- was untracked in git before this pillar's work began; `06813da7`
brought it under version control for the first time, since it's the only
mechanism that actually determines which lanes generate, `PHOTO_SCENES` in
`lena_prompt_brain.py` being long-dead code), `tools/diagnostics/
lena_higgsfield_prompt_library_dryrun.py`. No wardrobe-catalog, Kling,
queue, publish, R2, or `.env` file was ever touched across any of the 5
commits.

### C. Validations run
Every commit: `python -m py_compile` on the two `.py` files, then a real
`python tools/diagnostics/lena_higgsfield_prompt_library_dryrun.py --date
2026-07-09 --library-prefix <run-name> --packs 20 --count-per-pack 10
--select-top 20 --show-prompts --show-selected-prompts` dry-run (200
prompts), inspected in full before approval. Final state (post-`a1639bb0`):
all 10 pre-existing hard checks 200/200, `hard-excluded: 0`,
`motorcycle_model_anchor_present` 28/28, `moto_logo_hidden_clause_present`
30/30, `no_visible_motorcycle_logo_clause_present` 30/30, `no_text_
surfaces_clause_present` 30/30, `fake_text_avoidance_present` 30/30. Zero
render, Higgsfield/Kling call, network access, file write, or `.env`
read at any point across all 5 commits and their validation runs --
enforced by the diagnostic tool's own construction (stdout-only, no
subprocess/network/SDK import, confirmed by grep each time).

### D. Decisions made
Real model anchors and skin-forward styling are both permanent production
doctrine now, not experiments -- confirmed twice by Nicolas after seeing
real dry-run output. Logo/text-hygiene is the more consequential decision:
prompt-text mitigation is documented as necessary but explicitly
insufficient on its own (Higgsfield has no ground-truth reference for "the
real 1948 Indian Chief" beyond its own training data) -- the manual-
generation doctrine comment in `lena_prompt_brain.py` records three real
production fallbacks (hide/crop in post, real reference images, verified
logo add in post) as the actual answer if prompt text alone doesn't hold
up once more real renders are reviewed. Diagnostic checks for QA
correctness (model anchor, logo-hidden, text-surfaces, fake-text) are
deliberately kept reporting-only, never folded into curator scoring --
scoring answers "how hot is this," these checks answer "is this safe to
send," and conflating the two would be a category error.

### E. Blockers / parked branches
No Higgsfield executor exists yet -- everything in this pillar is still
dry-run prompt generation, not a real API call. The logo-hidden/text-
hygiene prompt-side mitigation has not yet been tested against a real
Higgsfield render since the `a1639bb0` escalation -- the one real visual
test that happened (which triggered the `356a66e3` correction) predates
it. Several exact manual-test prompts (slot_id/score/model-anchor/full
text) were extracted and handed off across this session's later turns,
ready for the next real visual test whenever that's approved.

### F. Next approved step
None of the following is pre-approved -- each needs its own explicit
instruction: (1) a real manual Higgsfield visual test of the post-
`a1639bb0` logo-hidden prompts, to confirm whether prompt-text mitigation
alone is sufficient or whether one of the three documented fallback
options is needed in production; (2) a Higgsfield executor skeleton
(unchanged from prior entries, still gated on separate CLI install/login
approval); (3) folding the motorcycle pillar's real-model-anchor pattern
back into the non-moto lanes, if useful (not discussed, not scoped).

### G. What must not be done
Do not render, call Higgsfield/Kling live, install/login, publish, promote
the queue, or touch R2/`.env` for this pillar without separate explicit
approval. Do not remove the reporting-only nature of the 5 moto QA checks
by folding them into `HOOK_*` scoring. Do not soften the logo-hidden or
no-text-surfaces clauses without an explicit Nicolas correction the way
the two prior escalations happened. Do not touch the wardrobe-catalog
drift or the rest of the pre-existing untracked dirty pile.

## 2026-07-09 (later in session) — Body/silhouette anchor committed, motorcycle paused from default production, Higgsfield Prompt Enhancer doctrine recorded

### A. What changed
Three real commits landed on top of the motorcycle pillar (HEAD moved
`a1639bb0` -> `1a01add9` -> `7ad7ac6a`), reversing priority back to
Lena's body/identity coming before any prop or scene:

1. **`1a01add9` `fix: prioritize Lena silhouette and pause motorcycle
   defaults`** -- added a new, always-on `HIGGSFIELD_BODY_SILHOUETTE_
   ANCHOR` constant to `pipeline/prompting/lena_prompt_brain.py`, inserted
   into every Higgsfield prompt (`generate_higgsfield_prompt_package()`)
   immediately after `HIGGSFIELD_FRAMING_LINE` and before `Scene:` --
   global, not motorcycle-specific. This deliberately reverses the
   2026-07-08 decision (recorded in this same changelog) to remove a
   heavier silhouette block as an overcorrection risk; real motorcycle-
   lane output showed the opposite failure -- hips reading narrow, the
   bike distracting from Lena -- so Nicolas explicitly re-authorized it.
   Same commit added all 7 motorcycle lanes to `production_blocked_lanes`
   in `pipeline/prompt_banks/lena/lena_photo_scene_bank_v1.json` --
   motorcycles are paused from default generation, not deleted; still
   fully available for explicit opt-in/manual testing. A real conflict
   was found and fixed in the same session: the diagnostic curator's own
   `HEAVY_BODY_OVERCORRECTION_TERMS` list (`tools/diagnostics/
   lena_higgsfield_photo_dump_dryrun.py`) still contained `"wide hips"`
   from the 2026-07-08 removal-era check, which hard-excluded 50/50
   prompts once the new anchor reintroduced that exact phrase -- fixed by
   dropping only the literal conflicting term and adding real
   overcorrection terms (`impossible anatomy`, `cartoonish proportions`,
   `exaggerated fake proportions`, `extreme body distortion`,
   `unrealistic hip size`, `fetishized proportions`) in its place.
2. **`7ad7ac6a` `fix: clarify Lena structural hip silhouette anchor`** --
   Nicolas's follow-up correction: a hip-pushed pose alone was producing
   outputs where the pose read wide but Lena's actual underlying body
   still looked narrow. Reworded the anchor to explicitly separate body
   shape from pose -- hips must read structurally wider than the waist
   "even standing straight in a neutral stance," "not something created
   only by a hip-pushed pose," with a "visible outward hip flare" and a
   lower body that "must never look straight, narrow, or column-shaped."
   Same file only, same insertion point, no other files touched.

Both commits were validated before landing: `py_compile` clean, and a
real `tools/diagnostics/lena_higgsfield_prompt_library_dryrun.py`
50-prompt dry-run (5 packs x 10) after each commit -- all 10 hard-gating
checks 50/50, curator selecting 10/10 requested, zero motorcycle prompts
generated by default in either run.

### B. New Higgsfield Prompt Enhancer doctrine (docs-only, no code change)
Nicolas ran a real side-by-side manual comparison directly in the
Higgsfield UI (outside this repo -- no executor exists yet) and found
Prompt Enhancer OFF produced measurably weaker Lena results: less premium
fashion finish, flatter image quality, a weaker hip/body read, and less
natural creator/influencer polish, versus the earlier Prompt-Enhancer-ON
velvet rooftop outputs. New standing doctrine, recorded here and in
`tools/LEGACY_PROVIDER_SURFACES.md` (the provider-configuration source of
truth):

- **Higgsfield Prompt Enhancer: ON** for all Lena manual Higgsfield tests
  and future production, unless Nicolas explicitly says otherwise.
- This is a **provider/UI/API setting, not prompt text** -- never write
  "use prompt enhancer" (or similar) inside `image_prompt`/`prompt`
  strings. Consistent with how Soul selection is already handled
  (`soul_selection_mode: "provider_config_not_prompt_text"` in
  `generate_higgsfield_prompt_package()`) -- Prompt Enhancer joins Soul
  selection as provider-config metadata for a future executor to read and
  act on, not prompt content.
- **Current creative benchmark**: the earlier enhancer-ON rooftop velvet
  midi dress outputs are the reference standard for Lena's silhouette --
  narrow waist, hips clearly wider than the waist, visible outward hip
  flare, fitted wardrobe tracing the waist-to-hip curve, realistic but
  curvy, no prop blocking the hips. Any future manual test or executor
  output should be judged against this benchmark.
- Restated alongside (unchanged, not new): negative prompt stays disabled
  by default; Lena Soul is selected in provider/UI, never written into
  prompt text; motorcycle lanes remain paused/opt-in
  (`production_blocked_lanes`); the body silhouette anchor remains
  top production priority over props/scenes.

No Higgsfield executor exists yet, so there is no code path today that
could even set a Prompt Enhancer flag -- this doctrine is recorded now so
the eventual executor skeleton (still gated on separate CLI install/login
approval, per `tools/LEGACY_PROVIDER_SURFACES.md`) builds it in from the
start rather than needing a later correction.

### C. What must not be done
Do not write "prompt enhancer" language into any prompt string -- it is
provider config, not prompt text. Do not re-litigate the 2026-07-08 vs.
2026-07-09 silhouette-anchor reversal without new evidence -- the current
anchor (structural, pose-independent hip language) is the settled state.
Do not re-enable motorcycle lanes in `production_blocked_lanes` without
explicit instruction. Do not start Higgsfield executor code, CLI
install/login, or any live provider call from this entry alone -- each
remains separately gated per `tools/LEGACY_PROVIDER_SURFACES.md`'s
future implementation sequence.

## 2026-07-09 (later in session) — Body test succeeded on the medium-frame anchor; framing crop found as the next open issue

### A. What happened
After four iterative rounds on `HIGGSFIELD_BODY_SILHOUETTE_ANCHOR` this
session (`1a01add9` -> `7ad7ac6a` -> `aa38b2ee` -> `13ed28f1` ->
`1d7cf3c9`, the last being the "slightly thicker fit-curvy medium frame"
tune), Nicolas reviewed a real manual Higgsfield test image and confirmed
the body target is now working: a black fitted mini/bodycon dress,
neutral standing pose, showing wide-set pelvis, hips clearly wider than
the waist, fuller upper thighs, a fit-curvy medium frame -- not
skinny/runway-thin, not plus-size, not cartoonish -- and, importantly,
the shape reads correctly even without a hip-pop pose doing the work
(the exact thing the last few anchor revisions were trying to prove).
This is a docs-only checkpoint -- no code changed in producing this
entry.

### B. The catch: not publishable, benchmark only
The same image that proves the body target has its head cropped out of
frame, so it cannot be used as a post asset. Nicolas designated it a
body/silhouette benchmark reference only. This surfaces a separate,
previously-undiagnosed problem: `HIGGSFIELD_FRAMING_LINE` (`pipeline/
prompting/lena_prompt_brain.py`) already states "showing the complete
outfit from head to shoes with a little space below the shoes," yet a
real render still cropped above the head. Not yet diagnosed (unclear
whether this is a framing-line wording weakness, a Higgsfield
Prompt-Enhancer interaction, or something else) and not patched -- no
code change was approved this turn.

### C. Standing doctrine, recorded (docs-only)
1. **Anchor is confirmed working -- do not re-tune
   `HIGGSFIELD_BODY_SILHOUETTE_ANCHOR` without new evidence.** Five
   rounds of iteration on this exact constant is enough; further changes
   need a real new finding, not a hunch.
2. **Next open issue is framing, not body shape**: force full
   head-to-shoes composition, no crop above the head, no cut-off face.
   Still unpatched, still needs its own explicit approval before any
   code change.
3. **Future body-proof test doctrine**: use fitted bodycon mini dresses
   or fitted mini skirts (not loose wardrobe); require full head-to-shoes
   framing; neutral or mostly-neutral stance (isolates body shape from
   pose, consistent with how the last several manual-test candidates in
   this session were hand-picked); once body AND framing both pass,
   return to more natural, varied fashion poses for actual production
   content rather than staying in neutral-proof mode indefinitely.
4. Full creative-benchmark update (superseding the prior rooftop velvet
   midi dress reference, which remains valid as a secondary reference):
   recorded in `tools/LEGACY_PROVIDER_SURFACES.md`'s "Higgsfield
   provider-configuration doctrine" section.

### D. What must not be done
Do not touch `HIGGSFIELD_BODY_SILHOUETTE_ANCHOR` again without a new,
specific finding -- it is confirmed working. Do not start a framing-line
code patch without separate explicit approval, even though the problem
is now identified. Do not touch motorcycles, scene bank, or the curator
from this entry. No render, no Higgsfield/Kling call, no publish, no
queue/R2/.env, no install/login, no cleanup, no commit occurred producing
this checkpoint.

## 2026-07-09 (later in session) — Complete production benchmark locked: full-body rooftop black-dress render is a PASS

### A. What happened
The framing gap identified in the prior entry was fixed and committed as
`9c787c17` (`fix: reinforce Lena full-body framing`) -- a new always-on
`HIGGSFIELD_FRAMING_REINFORCEMENT` constant inserted after `Camera:` and
before `Lighting:` in every Higgsfield prompt, giving full head-to-shoes
framing a second, later mention in the prompt (the hip/waist message
already had this redundancy via the wardrobe suffix; framing previously
did not). Validated 50/50 on all hard-gating checks, byte-identical body
anchor, zero motorcycle prompts, before commit.

Nicolas then reviewed a real Higgsfield render on the same rooftop/black
dress concept used throughout this session's body-testing and confirmed
it a **PASS on every dimension at once**: full head-to-shoes framing,
face/identity, hips reading clearly, the waist-to-hip curve, the
fit-curvy medium frame, no runway-skinny read. This is the first render
this session where body, framing, identity, outfit, and realism all
worked together in one complete, publishable-shaped image -- not just
one dimension in isolation on a test crop.

### B. Two benchmarks, different purposes
Nicolas explicitly distinguished these rather than treating one as
simply "better": the earlier cropped neutral-stance black fitted
mini/bodycon output (recorded in the prior entry) actually showed
*slightly more dramatic* hip width when judged on body shape alone --
but it was not publishable (head cropped) and only proved one
dimension. The new rooftop black-dress render is the correct **complete
production benchmark** going forward because every dimension works
together in a real, usable image, which is what production content
actually requires. The neutral-stance benchmark remains the sharper
reference specifically for body-shape-in-isolation review, not for
judging overall production readiness.

### C. LOCKED -- do not re-tune without new evidence
- `HIGGSFIELD_BODY_SILHOUETTE_ANCHOR` (commits `1a01add9` ->
  `7ad7ac6a` -> `aa38b2ee` -> `13ed28f1` -> `1d7cf3c9`): body/hips/frame
  = PASS, confirmed on a real complete render, not just dry-run
  validation.
- The framing reinforcement (`9c787c17`,
  `HIGGSFIELD_FRAMING_REINFORCEMENT`): framing = PASS, no more head/foot
  crop.
- Explicit instruction: stop chasing tiny body/framing improvements
  without new evidence of a real, specific problem. Five anchor
  iterations plus one framing fix is enough for now.

Unchanged, restated: Prompt Enhancer stays ON; Lena Soul stays selected
in provider config/UI, never prompt text; negative prompt stays disabled
by default; motorcycle lanes remain paused/opt-in only
(`production_blocked_lanes`).

### D. Next work direction
Move beyond body/framing tuning into broader normal Lena content testing
and production-readiness: varied scenes, wardrobe, and natural
(non-neutral) fashion posing for real content, rather than continuing
neutral-stance body-proof iteration. No specific next task chosen or
approved by this entry -- this is a stopping-point checkpoint, not a new
work order.

### E. What must not be done
Do not re-tune `HIGGSFIELD_BODY_SILHOUETTE_ANCHOR` or the framing
reinforcement without a new, specific finding -- both are locked as
working. Do not touch motorcycles, scene bank, wardrobe catalog, or the
curator from this entry. No code was changed producing this checkpoint
-- docs only. No render, no Higgsfield/Kling call, no publish, no
queue/R2/.env, no install/login, no cleanup, no commit occurred
producing this checkpoint.

## 2026-07-09 (later in session) — Expression/gaze wiring fixed, scene-vs-expression compatibility fixed, then real production-readiness renders reopened the body-consistency question

### A. What changed
Two more real commits landed on top of the "complete production benchmark
locked" checkpoint, closing out the expression-diversity defect this
session had been building toward:

1. **`fa8da078` `fix: wire Lena expression gaze variation into
   Higgsfield`** -- a 120-prompt readiness audit (done as part of
   selecting a 5-prompt manual-test set) found every single Higgsfield
   prompt used the identical fixed `Expression:` line
   (`HIGGSFIELD_EXPRESSION_REINFORCEMENT_LINE`) regardless of what
   `choose_expression_gaze_production()` actually selected --
   `expression_gaze_id`/`label` varied in metadata but never reached the
   real prompt text, causing literal contradictions (e.g. Expression
   claiming "direct eye contact" while the Scene said "looking down at
   the flowers"). Fixed in `pipeline/prompting/lena_prompt_brain.py`:
   `_higgsfield_safe_expression_text()` now uses the real selected bank
   text, falling back to a small neutral line
   (`HIGGSFIELD_EXPRESSION_SAFE_FALLBACK`, "relaxed natural expression,
   composed face") only for one known pose-conflicting ID (`exp_g008`).
   Also fixed the moto-lane expression-variant swap (which did a literal
   string-replace on the old fixed line) and the diagnostic's own
   `expression_reinforcement_present` check, which had been tautological.
   Validated 120/120 on all hard checks, 12 distinct final Expression
   strings (up from 1), byte-identical body anchor and framing
   reinforcement.
2. **`106be898` `fix: prevent Lena scene expression gaze conflicts`** --
   real bank text sometimes still contradicted the scene (e.g. museum
   "studying" a painting selected alongside a forward-gaze "direct eye
   contact" combo). Added a narrow, evidence-based
   `HIGGSFIELD_EXPRESSION_FORWARD_GAZE_IDS` set (6 of 17 bank combos that
   assert forward/camera gaze) and `HIGGSFIELD_EXPRESSION_SCENE_AWAY_GAZE_TERMS`
   (7 exact away-gaze scene phrases actually observed in real
   contradictions) -- if a forward-gaze combo is selected against a
   matching away-gaze scene phrase, it falls back to the same neutral
   line. Deliberately did not touch `exp_g007` (internally coherent with
   "looking down" scenes) or attempt to solve every possible
   scene-vs-expression mismatch (a separate away-vs-away-gaze
   contradiction class was found and left open, see part C below).
   Validated 120/120, 0/120 unresolved contradictions after the fix
   (verified by independently re-checking final prompt text, not just
   trusting the generator's own metadata).

Both commits followed the same discipline as every prior body/framing
fix this session: narrow, evidence-based, `py_compile` + real dry-run
validation before commit, byte-identical body anchor and framing
reinforcement reconfirmed each time.

### B. Production-readiness selection, then 3/3 real renders failed body continuity
With expression variety and body/framing both believed locked, a
120-candidate pool was generated and 5 genuinely diverse, non-motorcycle
prompts were selected for manual Higgsfield testing (coffee shop/flower
shop casual-editorial, a rooftop copper-bronze metallic dress, a
coffee-shop crop-top+mini-skirt fit-check, a lobby-cocktail-bar fuchsia
dress, a brunch-patio candid). This selection pass itself surfaced two
more honest system limitations, recorded for future reference: (a)
`wardrobe_silhouette_class` metadata is frequently stale relative to the
real rendered wardrobe text (multiple `jeans_based`/`athleisure_or_lounge`
labels actually resolved to a hardcoded fallback "corset mini dress"),
and (b) the system has exactly 5 real pose-text variants total, so
table/bar/restaurant lanes are structurally forced into the same pose and
camera line.

Nicolas then manually rendered 3 of the 5 selected prompts in Higgsfield
and judged **all 3 a body-continuity FAIL** against the locked rooftop
black-dress benchmark: the rooftop copper-bronze dress (too narrow
pelvis/hips, "too runway-slim"), the coffee-shop white mini skirt
("closer, but still fails"), and the brunch plum skirt ("too skinny
through hips/lower body, generic slim-influencer proportions"). This
directly contradicted the "complete production benchmark locked" verdict
recorded in the entry above -- **that verdict is not retracted (the one
rooftop black-dress render really did pass), but it is now understood to
not generalize**: the same locked, byte-identical body anchor and
framing reinforcement did not reliably reproduce the target body across
3 separate, varied production-content renders.

### C. Read-only diagnostic chain that followed (no further code changes)
A careful, evidence-gated diagnostic sequence followed, each step
approved individually, each one read-only (no render/code/docs change
except where explicitly noted):

1. **A/B/C prompt-structure comparison** (the 2 known-good manual tests
   vs. the 3 failed renders): found the body anchor's wording, length,
   and position are **byte-identical in every Higgsfield prompt this
   system generates** -- confirmed programmatically, always 998 chars,
   always immediately after the framing line. This ruled out "the anchor
   text/position differs between success and failure" as an explanation.
   Also found a same-lane counter-example (rooftop sunset produced both
   the confirmed benchmark success and one of the 3 failures), further
   weakening any pose- or scene-specific explanation. Flagged (not
   fixed): a real garment-length correlation (2 of 3 failures used
   midi-length dresses vs. the doctrine's mini/bodycon recommendation),
   and a genuinely new, uncaught contradiction class (an away-gaze scene
   paired with a *different* away-gaze expression that itself conflicts,
   e.g. "looking out the window" scene + "looking down at an object in
   her hands" expression -- outside the forward-gaze-only fix's scope).
2. **Controlled same-prompt repeatability test** (Nicolas-run, Enhancer
   ON, 3 identical generations of one hand-built neutral-stance black
   bodycon rooftop test prompt, no seed fixed): produced **materially
   different body geometry across all 3** -- confirms real generation
   variance exists independent of prompt wording (which was held
   perfectly constant). All 3 outputs also showed real compositing/
   background artifacts (duplicated vertical strips, collage-like
   duplicated border blocks, red rectangular bands), a second, parallel
   defect.
3. **Controlled Enhancer ON vs. OFF test** (same prompt, 3 generations
   each): **Enhancer OFF showed materially fuller body/hip preservation
   in 3/3**, closer to the locked benchmark, vs. 2/3 slimmer-drifting
   results under ON. OFF introduced two new observed failure modes not
   present in the body-consistency finding itself: head-cropping in 2/3
   and wardrobe-type drift (mini dress rendered as a bodysuit/romper) in
   1/3. Conclusion recorded carefully, per explicit instruction, as
   evidence that Enhancer is *a* contributing factor to body slimming,
   not proof of sole causation, and not yet a production doctrine change.
4. **Controlled framing-sentence-placement A/B test** (Enhancer OFF for
   both; Version A = existing single framing-reinforcement sentence in
   its current position; Version B = identical prompt with that exact
   sentence repeated verbatim as the final sentence; 2 generations each):
   **repetition did not help and plausibly hurt** -- full-head-present
   rate went 1/2 (Version A) to 0/2 (Version B). This directly rules out
   "just say the framing instruction again" as a fix, at least under
   Enhancer OFF, and is a deliberately different outcome than the
   original framing-reinforcement fix (`9c787c17`), which *did* work --
   the two are not the same intervention (that fix added a second
   mention where there had been only one; this test duplicated a
   sentence that was already being reinforced once).
5. **Ranked next-step recommendation** (not yet started): check whether
   Higgsfield exposes a real aspect-ratio/canvas/crop control separate
   from prompt text (near-zero cost, could explain both the cropping and
   the compositing artifacts at once) before trying a shorter prompt
   (to test instruction-competition) or investigating a reference/
   body-conditioning mechanism (higher-value for the body-consistency
   question specifically, but slower and requires its own approval
   chain). Explicitly recommended against running another blind
   isolated-variable prompt-wording test without a specific new
   hypothesis.

### D. Decisions made
- Body target is **not** production-ready despite the earlier "locked"
  verdict -- that verdict is narrowed to "this one anchor/framing
  combination can produce the target body," not "reliably does."
- Do not re-tune `HIGGSFIELD_BODY_SILHOUETTE_ANCHOR` again -- every test
  this session held it byte-identical and still found variance, which is
  evidence *against* a wording fix, not for one.
- Do not adopt the Version B (repeated framing sentence) change.
- Enhancer OFF is the current *provisional test setting* for body-
  consistency experiments (not yet a production default change).
- Next real step is a **lookup**, not a render: check for a Higgsfield
  aspect-ratio/framing control outside prompt text.

### E. Blockers / parked branches
- Root cause of body-geometry variance is still unknown (could be seed
  behavior, Enhancer, base-model sampling, Soul conditioning, or another
  provider mechanism) -- explicitly not claimed as identified.
- The away-vs-away-gaze expression/scene contradiction class (item C.1)
  remains open and unfixed, by explicit instruction.
- The stale-wardrobe-metadata and 5-pose-variant-ceiling findings from
  the production-readiness selection remain open, unfixed, by explicit
  instruction (out of scope for the body-consistency thread).
- No Higgsfield reference/body-conditioning research has started yet.

### F. Next approved step
None of the following is pre-approved -- each needs its own explicit
instruction: (1) check whether Higgsfield exposes a real aspect-ratio/
framing/canvas control separate from prompt text; (2) if not, a
controlled shorter-prompt test to check instruction-competition; (3)
research (not yet build) a Higgsfield reference/body-conditioning
mechanism; (4) a further isolated-variable test, only once informed by
(1).

### G. What must not be done
Do not re-tune `HIGGSFIELD_BODY_SILHOUETTE_ANCHOR`. Do not adopt the
Version B framing-repetition change. Do not turn Enhancer back ON as a
doctrine change without further evidence. Do not run another blind
prompt-wording variant without a specific, evidence-based hypothesis.
Do not touch motorcycles, scene bank, wardrobe catalog, or the curator
from this entry. No render, no Higgsfield/Kling call, no publish, no
queue/R2/.env, no install/login, no cleanup occurred producing any part
of this diagnostic chain beyond the 2 commits named in part A -- items
B and C were entirely read-only/manual-render-reviewed, not
code/doc-driven.

## 2026-07-09 (later in session) — Nicolas-approved preferred body benchmark chosen: 9:16 Version-B control render, Enhancer OFF

### A. What changed
No code changed. Nicolas reviewed the two successful 9:16 Version-B
control renders referenced in the diagnostic chain above (the ones that
finally preserved full-head framing after the UI aspect ratio was
explicitly switched from 3:4 to 9:16) and explicitly selected the first
of the two over the second as his new preferred gold-standard Lena body
benchmark, superseding the earlier rooftop black-dress "complete
production benchmark locked" image.

### B. Nicolas's verdict (recorded as authoritative)
"Her body is like perfect." / "I'd say this one is my favorite." This is
Nicolas's explicit visual judgment, not an independently re-derived
body-shape assessment -- it is recorded as project truth on his
authority, the same way every prior render verdict in this file has been.

### C. Nicolas-approved preferred Lena body benchmark (disciplined description)
Narrow waist, clear waist-to-hip contrast, naturally broad hip line,
fit-curvy medium frame, proportional full bust, realistic toned legs,
and an overall silhouette Nicolas considers the ideal Lena body. Neutral
stance; face/identity reads correctly as Lena.

### D. Exact successful generation conditions
- Lena Soul selected
- Prompt Enhancer OFF
- Negative prompt OFF
- Higgsfield UI aspect ratio explicitly set to 9:16
- Version B black-bodycon rooftop control prompt (repeated final framing
  line included)
- Current committed body anchor (`HIGGSFIELD_BODY_SILHOUETTE_ANCHOR`)
  unchanged
- Current framing wording unchanged

### E. New evidence on the aspect-ratio question
At 3:4, the Version B framing test failed full-head framing 2/2. After
explicitly switching the Higgsfield UI to 9:16, the next two Version B
outputs both preserved the full head; Nicolas selected the first over
the second as his preferred result.

### F. Do not overstate causation
- 9:16 alone is not claimed to have solved every prior body-variance
  issue.
- Prompt Enhancer OFF alone is not claimed to guarantee the body.
- Prior failures are not claimed to share one single cause.
- The earlier variance evidence (3/3 failed production-readiness
  renders) is not erased or retracted by this checkpoint.
What is recorded is only the **strongest successful configuration
observed so far, and Nicolas's explicit preferred visual benchmark**
(parts C-D above), not a closed root cause.

### G. Decisions made
- This image is now Nicolas's preferred Lena body benchmark, superseding
  the rooftop black-dress benchmark for body-target purposes, and
  explicitly chosen over the second successful 9:16 result.
- Do not rewrite or re-tune the body anchor.
- Do not change framing wording.
- Do not replace this benchmark without Nicolas's explicit approval.
- Do not resume blind prompt-wording experiments.

### H. Blockers / what remains open
- The body-consistency reopening from the entry above is narrowed, not
  closed: this is one more successful data point under a specific
  configuration and Nicolas's preference, not proof the configuration
  generalizes across all production content.
- The away-vs-away-gaze expression/scene contradiction class, stale
  wardrobe metadata, and 5-pose-variant ceiling from the entry above
  remain open and unfixed.

### I. Next approved step
None pre-approved. This entry is a docs-only checkpoint of a visual
decision already made on existing renders.

### J. What must not be done
No render, no Higgsfield/Kling call, no publish, no queue/R2/`.env`, no
install/login, no code change, no cleanup, no commit occurred producing
this checkpoint. Do not touch the unrelated dirty working-tree pile.

## 2026-07-09 (later in session) — Body-consistency workstream closed for now: flower-shop three-run test completes the generalization evidence

### A. What changed
No code changed. Nicolas ran the exact original flower-shop readiness
prompt (`readiness2-pack007-10-photo`) three times under the current
successful configuration (Lena Soul selected, Prompt Enhancer OFF,
negative prompt OFF, Higgsfield UI aspect ratio 9:16, no fixed seed,
anchor/framing unchanged, no banked phrase added) and reviewed all
three outputs.

### B. Flower-shop three-run result
- Image 1: good overall result, body fuller than earlier skinny
  failures, hips improved, wardrobe stayed close to the requested long
  black cargo skirt.
- Image 2: weakest of the three on hip/body shape -- hips read somewhat
  straighter/narrower than images 1 and 3.
- Image 3: Nicolas's explicit verdict -- "3 is the best one." Strongest
  of the three on hip width and waist-to-hip contrast, best lower-body
  silhouette, closest to the target body direction. **Separately**, a
  wardrobe-adherence failure: the requested black cargo maxi skirt
  drifted into black cargo pants. Recorded as a body PASS and a
  wardrobe-compliance miss on the same image -- the two are not
  conflated.
- General lesson confirmed: long/loose column garments can conceal the
  hip-to-thigh transition and make body evaluation ambiguous --
  concealed hips under loose garments are not automatic evidence of
  body failure.

### C. Cumulative evidence for closing the body workstream
1. Nicolas-approved black-dress benchmark (9:16, Enhancer OFF).
2. Successful coffee-shop generalization pass (`readiness2-pack000-00-photo`).
3. Successful brunch-patio generalization pass (`readiness2-pack000-02-photo`).
4. Flower-shop three-run test (`readiness2-pack007-10-photo`), image 3
   selected by Nicolas as strongest on hips/body.

### D. Decision
"Body direction is now sufficiently validated across the approved
benchmark and multiple varied production scenes to stop active body
tuning and move forward. The body anchor remains frozen. Future body
work should reopen only if new real-production evidence shows renewed
narrow-hip or runway-slim drift."

Frozen for body-consistency purposes, do not re-tune without new
body-failure evidence: `HIGGSFIELD_BODY_SILHOUETTE_ANCHOR` and current
body/framing wording. The current successful Lena full-body image
baseline remains: Soul selected, Enhancer OFF, negative prompt OFF, UI
aspect ratio 9:16. `HIGGSFIELD_BODY_SILHOUETTE_REINFORCEMENT` was
evaluated and not added. The banked "pronounced waist-to-hip ratio"
phrase stays banked, untested, for a future isolated A/B test only if
renewed narrow-hip drift appears in real production.

**Not frozen:** other prompt-assembly logic (wardrobe, pose, expression,
environment, automation) remains open for future work -- this closure is
scoped to body-consistency tuning only, not a freeze on all future
prompt engineering.

**Not claimed:** universal perfection, guaranteed future consistency
across all possible content, or that the wardrobe-adherence miss on
image 3 is resolved.

### E. What remains open (outside the body workstream, not closed by this entry)
- Wardrobe adherence / wardrobe-metadata mismatch (stale
  `wardrobe_silhouette_class` labels, garment-type drift under loose
  silhouettes -- e.g. maxi skirt -> cargo pants on flower-shop image 3).
- Long/loose garments concealing hip-to-thigh visibility (evaluation
  ambiguity, not necessarily a body failure).
- The 5-pose-variant ceiling (table/bar/restaurant lanes structurally
  forced into the same pose/camera line).
- The away-vs-away scene-expression contradiction class (left open by
  the `106be898` fix, scoped to forward-gaze-only).
- Fake/gibberish text in environment signage/menu boards (flagged on the
  coffee-shop retest, not yet addressed).
- Broader production automation/readiness beyond body/framing tuning.

### F. What must not be done
No render, no Higgsfield/Kling call, no publish, no queue/R2/`.env`, no
install/login, no code change, no cleanup, no commit occurred producing
this checkpoint. Do not re-tune the body anchor or body/framing baseline
without new real-production body-failure evidence. Preserve Soul
selected + Enhancer OFF + negative prompt OFF + UI 9:16 as the current
Lena full-body image baseline unless new evidence justifies changing it.
Do not add `HIGGSFIELD_BODY_SILHOUETTE_REINFORCEMENT` or the banked
phrase preemptively.

## 2026-07-09 (later session) — Higgsfield production-readiness hardening: 5 commits (wardrobe metadata, environment text risk, Phase 1 pose wiring, downward-object gaze conflict, live-contradiction pose fix)

### A. What changed
Five narrow, evidence-based fixes to the Higgsfield generation path in
`pipeline/prompting/lena_prompt_brain.py` (plus two diagnostic-tool files
for the first two), each individually diagnosed on a 120-candidate seeded
`build_library_report()` pool, proposed as a minimal scoped diff,
implemented, validated against a captured pre-patch baseline, and
committed only after explicit approval. HEAD advanced
`1d742f24 -> cca6c1b2 -> 5b90e36a -> db688b47 -> 13b82cf7 -> 10f9b1d7`.

**1. `cca6c1b2` `fix: add effective Higgsfield wardrobe metadata`**
`wardrobe_silhouette_class` was computed from the raw catalog entry
*before* the Higgsfield-only safe-wardrobe fallback substitution could
run, so it could disagree with the actual rendered `Wardrobe:` text. A
120-sample audit found 17/120 confirmed real cases (12 stale-after-
fallback, 5 a pre-existing substring-matching gap in the raw
classifier). Fix: added `effective_wardrobe_silhouette_class`, computed
from the final wardrobe text via a new shared classifier
(`classify_effective_wardrobe_silhouette()`), returned alongside the
unchanged raw field. The diagnostic tool's own duplicate classifier was
retired in favor of importing the shared one. **`wardrobe_silhouette_class`
itself, Kling's `generate_prompt_package()`, Kling sexy/skin-showing
scoring, and Kling recency memory are all untouched** -- a real
consumer audit found Kling depends on the raw field's exact legacy
vocabulary. Validated: 120/120 raw field unchanged, 120/120 effective
field populated and text-verified, 120/120 `image_prompt` byte-identical
to baseline, 0 Kling references to the new field/function.

**2. `5b90e36a` `fix: reduce Higgsfield environment text risk`**
5 live scene-bank environment phrases (coffee-shop "handwritten menu
board", grocery-run "handwritten price signs", sidewalk-dinner "menu
stands", airport "gate signs blurred", record-store "posters on the
wall") explicitly invited fake/gibberish rendered text -- 23/120 in
audit, concentrated 100% in whichever lane drew (coffee shop, sidewalk
dinner). Fix: a Higgsfield-only exact-phrase substitution
(`HIGGSFIELD_TEXT_SURFACE_REPLACEMENTS` / `_higgsfield_safe_environment_text()`)
swapping each for an equally rich non-text detail (e.g. "espresso
machine and pastry case"), operating only on the in-memory
`environment_text` string inside `generate_higgsfield_prompt_package()`
-- **does not touch the shared scene-bank JSON** (also read by Kling) and
does not add a universal negative clause (would contradict the scene's
own positive instruction). Validated: 0/120 post-patch hits (was 23),
97/120 byte-identical, 23/120 changed by exactly the approved
substitution, richness manually spot-checked as preserved. **Important
caveat: this removed the five known prompt-created text-surface
invitations found in the audit; provider-side hallucinated/gibberish
text on unrequested surfaces remains a separate unresolved risk.**

**3. `db688b47` `fix: wire standing-safe pose bank into Higgsfield`**
The single-image builder always used one hardcoded pose line
(`HIGGSFIELD_POSE_REINFORCEMENT_LINE`); the pack builder swapped that
for one of only 5 hardcoded mirror/car/table/generic variants. Meanwhile
a real 18-combo, lane-filtered, attitude-weighted pose bank was selected
every time (`choose_pose_body_language_production()`) but its text was
always discarded -- the same "selected but inert metadata" pattern as
fix #1 above, confirmed via `pose_body_language_id`/`label` never
matching rendered text (0% match rate). **Phase 1**: wired the real bank
text into Higgsfield for standing-safe categories only -- added an
`exclude_tags` parameter to `choose_pose_body_language_production()`
(default `None`, Kling's call site unaffected byte-for-byte) and
`HIGGSFIELD_POSE_PHASE1_EXCLUDED_TAGS = frozenset({"seated", "in_motion"})`,
excluded via a strict filter that raises rather than falling back to the
unfiltered pool. `seated`/`in_motion` stay excluded this phase because
`_higgsfield_sanitize_scene_action()` still rewrites sitting/walking
scene language into standing equivalents -- restoring those pose
categories now would recreate the scene/pose contradiction that
sanitizer exists to prevent. The old pack-level civilian substitution
mechanism was reconciled (gated to moto-lanes-only, which are exempted
from the bank-wiring and keep the old fixed line so the mechanism's
search string still matches) rather than left to silently no-op with
stale metadata. Result: 5 -> 13 unique rendered pose texts, hip-push
language 88% -> 19%, 0% seated/in-motion leakage, 100%
`pose_body_language_id` <-> rendered-text match (was 0%), no lane
100%-pose-locked (was 6 lanes). Two disclosed, non-blocking watch-items
(not fixed, evidence-gated for later): `pose_p005`/`pose_p006`
("leaning against the counter"/"the railing") occasionally drawn for
`rooftop sunset`, whose scene text doesn't literally name either surface
(2/120); the "mirror outfit check" lane lost its dedicated
mirror/phone-check gesture (no bank equivalent exists) but a
supplementary probe found it remains compatible with the 8 generic poses
it now draws, no hard contradiction. Motorcycle lanes exempted, fully
unchanged.

**4. `13b82cf7` `fix: prevent Higgsfield downward-object gaze conflicts`**
The existing scene-vs-expression compatibility check
(`_higgsfield_expression_scene_conflict_terms()`, from the `106be898`
fix) only ever inspected `HIGGSFIELD_EXPRESSION_FORWARD_GAZE_IDS` against
away-gaze scene text -- any other expression, including every "away"
gaze combo, was never checked at all. A 120-sample audit found this gap
is mostly harmless (13 "soft tension" cases -- a camera-adjacent/
generic-away expression paired with a camera-leaning scene reads as
normal photographic variety, deliberately left unsuppressed) but
`exp_g013` ("looking down at an object in her hands") is a real
exception: unlike `exp_g007` (which resolves back to the camera in its
own text), it names a concrete, unconditional away-target, and 3/3 real
occurrences conflicted (car moment's "looking out the window" x2,
brunch patio's "glancing toward the camera" x1). Fix: added
`HIGGSFIELD_EXPRESSION_DOWNWARD_OBJECT_CONFLICT_IDS = {"exp_g013"}` and
a matching narrow term list, checked via a second branch in the same
function -- `_higgsfield_safe_expression_text()` required no changes,
since it already falls back generically on any non-empty conflict list.
Deliberately excludes "looking down at the flowers" (flower shop) and
any bare "looking down"/"glancing down" scene phrasing -- the flowers
can plausibly be the referenced object, confirmed via direct unit check
(`conflict_terms == []`). Validated: 3/3 `exp_g013` conflicts fixed,
117/120 byte-identical, 3/120 changed by exactly the Expression:
substitution, all 4 named soft-tension IDs (`exp_g002`/`exp_g003`/
`exp_g006`/`exp_g009`) confirmed unchanged, `exp_g017` checked as a
watch-item and found already camera-compatible (no fix needed).
Metadata truth preserved and explicitly reported, not glossed over:
`expression_gaze_id`/`label` still reflect the *originally selected*
`exp_g013`/`looking_down_at_object` even when the fallback renders --
`expression_text` is the field that reflects the real rendered text, and
`expression_safe_fallback_used`/`fallback_reason`/`conflict_terms`
disclose the substitution honestly, same pre-existing pattern as
`exp_g008`'s pose-conflict fallback.

**5. `10f9b1d7` `fix: enforce scene-compatible Higgsfield poses`**
A narrow Phase 2 pre-step/live-contradiction fix, not full Phase 2.
Three lanes' scene-bank action text is never touched by any
`HIGGSFIELD_SCENE_ACTION` rewrite ("sitting on a [city] bench..."/
"walking through an airport terminal..." -- none match "sitting at"/
"sitting in"/"seated at"/"walking across"/"walking away from"), so under
Phase 1 (standing-safe only) they could draw a universal standing pose
while the scene text still said sitting/walking. **Active live
production fix:** `city bench` was active in default production; the
exact seeded pool reproduced 2/2 contradictory `city bench` prompts
before the fix (scene said "sitting on a city bench," selected poses
were standing/hip-angled). Fix: a new
`HIGGSFIELD_REQUIRED_POSE_ID_BY_LANE` map bypasses normal
`choose_pose_body_language_production()` selection entirely for the
mapped lanes, forcing a specific real bank combo instead -- structural
prevention, not probabilistic reduction. After the fix: 0/2
contradictions, both `city bench` candidates use `pose_p012`, rendered
text matches the real bank entry exactly. **Latent defensive mappings,
not current live production failures:** `gym cooldown` -> `pose_p012`
and `airport day` -> `pose_p011` are covered the same way, but **both
lanes are currently in `production_blocked_lanes` and cannot appear in
current default production** -- verified via `get_production_scene_pool()`
and a 300-sequence direct sweep finding zero real draws of either.
`pose_p007` remains fully excluded (0/7 eligible lanes were clean in the
earlier diagnosis); `apartment doorway` deliberately not included (a
softer, unconfirmed case, left for Phase 2B). Validated: `city bench`
2/2 -> 0/2 contradictions, `pose_body_language_id`/rendered-text match
120/120, 0 seated/in-motion leakage outside the 3 mapped lanes, `pose_p007`
0/120, body anchor/framing/expression-gaze/wardrobe-metadata/environment-
sanitizer all unchanged, motorcycles 0/120, zero Kling references to the
new symbols. Separate, pre-existing, unrelated finding surfaced by a
`gym cooldown` targeted probe: a full end-to-end package for that lane
currently fails earlier, at wardrobe selection ("no safe wardrobe
catalog entries remain for lane 'gym cooldown'") -- confirmed unrelated
to this pose fix and moot in practice since the lane is already blocked
from production; not fixed, not in scope.

### B. Files changed
- `pipeline/prompting/lena_prompt_brain.py` (all five commits)
- `tools/diagnostics/lena_higgsfield_photo_dump_dryrun.py` (commits 1-2 only)
- `tools/diagnostics/lena_higgsfield_prompt_library_dryrun.py` (commits 1-2 only)

### C. Validations run
Each commit: `python -m py_compile` on changed files; a real
`build_library_report("2026-07-09", "<prefix>", packs=12, count_per_pack=10)`
120-image dry-run against a captured pre-patch baseline, diffed
byte-for-byte; `HIGGSFIELD_BODY_SILHOUETTE_ANCHOR`/`HIGGSFIELD_FRAMING_LINE`/
`HIGGSFIELD_FRAMING_REINFORCEMENT` presence re-confirmed 120/120 every
time; motorcycle count re-confirmed 0/120 every time; grep-confirmed zero
references to any new symbol in any Kling file every time. Commit 5
additionally used clearly-labeled targeted local probes (not
default-production evidence) for `gym cooldown`/`airport day`, since
both are blocked from the seeded pool by `production_blocked_lanes`.

### D. Decisions made
All five fixes retained as committed. Phase 1 pose wiring intentionally
excludes `seated`/`in_motion` broadly -- explicitly not a final state.
Commit 5 is an explicitly-scoped narrow pre-step (3 named lanes only),
not broader Phase 2 -- **a narrow Phase 2 pre-step/live-contradiction fix
was implemented and committed in `10f9b1d7`; broader seated/in-motion
restoration remains separately scoped and unimplemented.** The two pose
watch-items, the mirror-lane narrowing, and the `gym cooldown`
wardrobe-selection finding are accepted, disclosed tradeoffs/notes, not
blockers, per explicit approval.

### E. Blockers / parked branches
- Broader Phase 2: the other 5 seated-compatible lanes, `pose_p007`
  entirely, broader pose-aware `_higgsfield_sanitize_scene_action()`
  rewiring, and `pose_p011` restoration beyond the currently-forced
  `airport day` defensive mapping -- diagnosed (read-only), not
  implemented.
- `apartment doorway` -- unconfirmed future Phase 2B candidate, not
  included in commit 5.
- `pose_p005`/`pose_p006` literal-surface mismatch on `rooftop sunset`
  (2/120) -- disclosed, not fixed, low priority.
- Mirror outfit-check lane's lost dedicated gesture -- disclosed, not
  fixed, no bank equivalent authored.
- `gym cooldown`'s pre-existing, unrelated wardrobe-selection failure
  (no safe catalog entries for that lane) -- disclosed, not fixed, moot
  while the lane stays production-blocked.
- Bookstore lane's low-hook hard-exclude (pre-existing, unrelated to any
  of these five fixes, confirmed via `variety_warnings` during Phase 1
  validation) -- not touched.

### F. Next approved step
None of the following is pre-approved -- broader Phase 2 needs its own
explicit approval, same discipline as every fix above: restoring
`pose_p007` or `pose_p012` for the other 5 seated-compatible lanes,
restoring `pose_p011` beyond `airport day`, extending coverage to
`apartment doorway`, and/or revisiting
`_higgsfield_sanitize_scene_action()`'s sitting/walking rewrite rules to
make them pose-aware generally.

### G. What must not be done
No render, no Higgsfield/Kling call, no publish, no queue/R2/`.env`, no
install/login, no cleanup occurred producing any of these five commits
beyond the code changes themselves. Do not re-tune the body anchor,
framing, or provider configuration. Do not touch the shared scene-bank,
environment-catalog, wardrobe-catalog, expression-bank, or pose-bank
JSON files. Do not change Kling behavior. Do not reopen the closed
body-consistency workstream without new real-production evidence. Do
not describe `gym cooldown` or `airport day` as current live production
failures -- both are production-blocked. Do not describe broader Phase 2
as complete or seated/in-motion poses as broadly restored.

---

## 2026-07-10 — First real Higgsfield live executor proof, two executor
## bugs found and fixed, free-generation billing investigated and left
## explicitly unresolved

### A. What changed
`pipeline/higgsfield_lena_api_executor.py` (first committed docs-only-safe
at `3f7719a6`, "dry-run default, no live call yet") was exercised live for
the first time this session, against the real, authenticated `higgsfield`
CLI v1.1.10 (job type `text2image_soul_v2`; Lena's confirmed Soul
`id=1f1200e4-1cc9-4504-ac1c-3304b687e3c1`, `name=Lena`, `type=soul_2`).

- **First controlled live attempt** (`readypack0709-pack008-07-photo`,
  `--live`) failed before any provider contact: `subprocess.run(["higgsfield",
  ...], shell=False)` does not perform Windows `PATHEXT` resolution, so it
  could not find the real `higgsfield.CMD` on PATH. Zero API contact, zero
  job creation, zero credit spend. **Fix (approved, applied):** resolve the
  binary via `shutil.which()` at the subprocess-spawn boundary only, keep
  `shell=False`, route spawn failures through the existing
  `ProviderCallError` path instead of an uncaught traceback. The logical
  provider-command contract (`build_provider_argv()`) is unchanged.
- **Second controlled live attempt succeeded** -- confirmed via account
  transaction history (`-0.12` credit deduction, exact match to the
  `generate cost` estimate) and `generate list --json` (real job
  `3c669124-bb27-4ef3-bcb3-e1363708ab84`, `status: completed`, prompt/
  `custom_reference_id`/`aspect_ratio` all exact-matched to the request).
  **This is the first real image this entire Higgsfield build has ever
  produced.** Visual assessment: strong Lena identity, wardrobe,
  environment, realism, and hook. **Failed** the seated-pose stress test
  this exact candidate was chosen to prove (`pose_p012`/"sitting on a city
  bench" did not visually land -- she rendered standing) and showed a real
  hand/anatomy defect. Confirms real visual QA on real renders remains
  mandatory; prompt-side correctness does not guarantee provider-side
  compliance.
- That same successful response exposed a **second real executor bug**:
  the original `_collect_result_urls()` recursively walked the entire
  parsed JSON tree for any http(s)-looking string and found 3 (the real
  `result_url`, a `min_result_url` thumbnail, and an unrelated
  `params.style.url` style-preset asset), incorrectly tripping the ">1
  result URL" fail-closed path on every successful job. **Fix (approved,
  applied):** `_canonical_result_urls()` reads only the top-level
  `result_url` field of the response; `min_result_url` and anything nested
  are never treated as a generation output. Fail-closed semantics
  (0 URLs -> fail, >1 -> fail) preserved exactly.

### B. Files changed
- `pipeline/higgsfield_lena_api_executor.py` (the two fixes above only)

### C. Validations run
Both fixes: `py_compile` clean; a focused in-process unit test of
`_canonical_result_urls()` against the real (sanitized) response shape
(single job dict, list-of-one, and no-`result_url` cases); a full
`--dry-run` re-run of the exact accepted slot
(`readypack0709-pack008-07-photo`) confirming the prompt SHA-256
(`4927a748eb54883962c351b385b98310e99784e23a12b4af08cf6365bddc9f7c`),
`custom_reference_id` (`1f1200e4-1cc9-4504-ac1c-3304b687e3c1`), and
`job_type` (`text2image_soul_v2`) all remained byte/value-identical
throughout every step; zero provider/network calls or files written under
dry-run (`pipeline/higgsfield_library/`/`pipeline/higgsfield_debug/`
confirmed absent). `git status`/`git diff` confirmed only these two
functional changes exist in the file -- no retry/reroll/fallback/batch/
queue/publish/R2/`.env` behavior was added, `enhance_prompt` was left
untouched (evidence: the real completed job's own params already showed
`enhance_prompt: false` with the flag never sent -- matches the desired
baseline by omission, no code change needed).

### D. Free-generation billing investigation (separate from the code fixes,
### explicitly left unresolved)
The Higgsfield UI shows "2938 free Soul 2.0 gens left." A full, complete
account transaction history (83 transactions, cursor exhausted -- not a
sample) was pulled and forensically analyzed: 71 `"Higgsfield Soul V2"`
transactions, 62 billed `$0`, 9 billed `-0.12`. **Confirmed, not
inferred:** a free job exists with `batch_size: 1`, conclusively disproving
a batch-size-causes-free theory; free and paid jobs are identical across
every visible recorded parameter (`batch_size`, `use_relax`,
`enhance_prompt`, `quality`, `style_id`, `custom_reference_id`); UI-
originated activity has produced both free and paid Soul V2 jobs (the
first 7-in-a-row paid burst on 2026-07-08 evening predates this executor's
existence entirely), so "UI=free/CLI=paid" is not a valid rule. Every
rolling-window (1/2/5/10/15/30/60-minute), silence-gap, and same-UTC-day
cumulative-count rule tested was systematically disproven by concrete
counter-examples -- most decisively, our own CLI call was the very first
Soul V2 generation of its entire calendar day (`same_day_count_before: 0`)
and was still billed, directly falsifying any daily-quota-exhaustion
theory. **No reliable throttle rule can currently be encoded from
historical evidence, and no CLI/API-exposed control (parameter, response
field, or transaction field) was found that determines free-vs-paid
billing.** This is recorded as an open provider-entitlement question, not
an engineering gap in this repo.

### E. Decisions made
Both executor fixes retained as committed. The free-generation billing
question is explicitly NOT solved and must not be described as resolved
in any future session. Standing architecture decision (Nicolas): the
one-shot executor stays simple; billing/economics policy belongs in a
future orchestration/policy layer above the executor, never invented from
contradictory evidence; the 2,938 free Soul 2.0 generations remain
strategically important but are to be pursued as a separate provider-
entitlement/support question; the main Lena pipeline must not be frozen
indefinitely waiting for that question to resolve.

### F. Blockers / parked branches
- Free-vs-paid Soul V2 billing mechanism: unresolved. Next step (not yet
  started, not yet approved) is direct Higgsfield support clarification,
  not further inference from transaction timing.
- Seated-pose provider-compliance miss and the hand/anatomy defect on the
  one real render produced: disclosed, not fixed -- no prompt or code
  change was made in response to this single visual result. A broader
  pose-compliance investigation would need more real renders, not assumed
  from one data point.

### G. What must not be done
No additional live generation, no publish, no queue promotion, no R2, no
`.env` change, no install/login change, no credential exposure, no
cleanup of the unrelated dirty pile occurred producing this checkpoint
beyond the two live attempts and the read-only billing investigation
described above. Do not claim the free-generation question is resolved.
Do not invent a throttle rule not supported by the historical evidence.
Do not freeze the Lena pipeline indefinitely on the free-generation
question.

---

## 2026-07-10 (later session) — Higgsfield outputs bridged into Lena visual
## QA; automated vision reviewer built and validated (simulated only);
## blocked on a missing ANTHROPIC_API_KEY before any live Anthropic call

### A. What changed
Two batches of work, one committed, one not.

**Committed (`f0dbb03a`, `feat: bridge Higgsfield outputs into Lena visual
QA`):**
- `pipeline/qa/lena_photo_qa.py`: one new hard-gating checklist field,
  `pose_action_scene_compliance` -- "does the rendered physical state/
  action match what the intended scene explicitly requires, rather than
  merely looking stylistically similar" (seated vs standing, holding vs
  not, walking vs static, mirror/eating/driving logic, etc.). General
  semantic-compliance field, deliberately not a special-cased
  `city_bench -> must be seated` rule -- the first proven example (two
  consecutive real renders of `readypack0709-pack008-07-photo`) is cited
  in-code as the evidence, not encoded as a lane-specific check. No
  validator change was needed: `HARD_GATING_CHECKLIST_KEYS` is computed
  dynamically from `QA_CHECKLIST_KEYS` minus `DIAGNOSTIC_ONLY_CHECKLIST_
  KEYS`, so the new field became hard-gating and covered by the existing
  false-green loop purely by being added to the field tuple.
- `tools/lena_higgsfield_qa_bridge_v1.py` (new): the Higgsfield-side
  counterpart to `tools/lena_review_proof_render_v1.py`. Reads a real
  `pipeline/higgsfield_debug/<date>/<slot_id>/result_manifest.json` +
  `saved_image_path`, adapts it into the slot-shaped dict `lena_photo_qa.py`
  expects, and calls the existing `save_qa_template()`/`load_qa_result()`
  unchanged -- zero parallel QA logic. Fails closed (`ResolveError`) if the
  manifest or image can't be resolved; explicitly leaves `environment_id`
  as `None` rather than inventing one, since Higgsfield's manifest has no
  such field (disclosed, not papered over).
- Three real QA records written under `pipeline/asset_review/lena/
  2026-07-09/` for the three Soul 2.0 images generated this session, via
  direct Claude visual review (not automated): `readypack0709-pack008-07-
  photo` = **overall: fail** (sole reason: `pose_action_scene_compliance`
  -- second consecutive real render showing standing, not seated);
  `readypack0709-pack004-08-photo` and `readypack0709-pack003-08-photo` =
  **overall: pass**, with caveats recorded in field notes (hand ambiguity,
  wardrobe-cutout interpretation, minor body-anchor softness) rather than
  manufactured hard failures. `reviewed_by` states the review method
  explicitly (direct pixel review, no automated model) -- reused the
  existing field for provenance rather than inventing a new one.
- `pipeline/agents/lena/70_visual_qa/OUTPUTS.md`: corrected one stale
  claim ("no other file invokes `lena_photo_qa`") -- `tools/lena_build_
  publish_packet_v1.py` is a second real consumer, and its `_resolve_qa()`
  ("Rule zero -- no QA pass, no packet") is a real, already-working hard
  gate, Kling-shaped in slot/image resolution but provider-agnostic in its
  actual QA-gating logic. Proven directly: replayed Rule Zero's exact
  gating logic against all 3 real QA records -- `readypack0709-pack008-07-
  photo` (fail) would be BLOCKED, the other two (pass) would be ALLOWED.

**Uncommitted, built and validated this session (not yet proven against a
real model):**
- `pipeline/qa/lena_vision_reviewer.py` (new): a separate Anthropic-
  powered automated reviewer module, deliberately scoped to exactly 3 of
  the 10 checklist fields (`pose_action_scene_compliance`, `hands_anatomy_
  sanity`, `environment_realism_scene_coherence`). Identity (`identity_
  fidelity`, `skin_realism_no_invented_marks`) and all `production_scoring`
  fields are left `unreviewed` -- per `70_visual_qa/RULES.md`, identity/
  skin judgments require canonical Lena reference images, which the
  Higgsfield path does not capture anywhere yet (a real, disclosed
  prerequisite gap, not something this module works around). Uses
  Anthropic's tool-use (forced `tool_choice`) for strict structured output
  instead of free-text JSON parsing; a separate strict parser re-validates
  every field against the real allowed-value set independently of what the
  model claims, degrading any malformed/unconfident field to `unreviewed`
  rather than guessing. **Hard rule enforced in code, not just
  documented:** `merge_vision_review_into_qa()` can never set `overall:
  "pass"` by itself -- only `"fail"` (a real automated hard-gating failure
  found) or `"unreviewed"` (record still incomplete, since 7 of 10
  checklist fields and all of `production_scoring` remain unjudged after
  this module runs). Recommended model: `claude-sonnet-5`. Required
  package: `anthropic`. Required env var: `ANTHROPIC_API_KEY`. The
  package-import boundary is deliberately lazy (`import anthropic` only
  inside the one function that makes the live call) so the rest of the
  module stays importable/testable with zero network access and no
  package installed.
- Validated **only** via simulated (hand-written, matching already-known
  ground truth, NOT model-generated) responses run through the real
  parser -> merge -> `lena_photo_qa.validate_qa_result()` path, against
  fresh scaffolds for all 3 known slots: Candidate A -> `overall: fail`
  (correct), Candidates B and C -> `overall: unreviewed` (correct -- no
  automated field failed, but the record is still incomplete, so `pass` is
  correctly withheld). One real bug found and fixed during this
  validation: schema v3 requires a non-empty `production_scoring.
  feed_worthy_reason` once `overall` is finalized; the merge function
  previously left it empty when forcing a fail, which `validate_qa_result()`
  correctly rejected. Fixed by having the merge function state honestly
  that hook/aesthetic quality "was not assessed by this automated pass"
  rather than fabricating a judgment it never made.

### B. Files changed
- Committed (`f0dbb03a`): `pipeline/qa/lena_photo_qa.py`, `tools/
  lena_higgsfield_qa_bridge_v1.py`, `pipeline/agents/lena/70_visual_qa/
  OUTPUTS.md`, and 3 new files under `pipeline/asset_review/lena/
  2026-07-09/`.
- Uncommitted: `pipeline/qa/lena_vision_reviewer.py`.

### C. Validations run
`py_compile` clean on all new/changed files. Direct proof (not assumed)
that the new checklist field is hard-gating: `pose_action_scene_
compliance=fail` + `overall=pass` is rejected as false-green;
`pose_action_scene_compliance=fail` + `overall=fail` validates; all 10
`HARD_GATING_CHECKLIST_KEYS` individually re-tested with zero regressions;
`wardrobe_class_fidelity` reconfirmed still diagnostic-only. All 3 real QA
records validate with zero errors. Rule Zero's exact gating logic replayed
against all 3 real records, confirmed to block/allow correctly. The vision
reviewer's prompt construction was run against real bridge data for all 3
slots (proves the input contract works against real metadata); its parser/
merge logic was proven against simulated responses for all 3 slots
(proves the plumbing, not real model behavior). `git status`/`git diff`
confirmed only the intended files changed at every step; the large
pre-existing `pipeline/asset_review/` tree (2026-06-12 through 2026-07-07)
and the other four `70_visual_qa/*.md` files were explicitly excluded from
staging by inspection, not assumption.

### D. Decisions made
`pose_action_scene_compliance` added as approved, hard-gating, general
(not lane-special-cased). No new `overall` status vocabulary added --
`unreviewed` + field notes remains the mechanism for representing
uncertainty, including automated uncertainty. The automated reviewer is
architecturally separated into five roles (executor / bridge / vision
reviewer / schema+validator / Rule Zero) and must not be collapsed into
one script. `claude-sonnet-5` approved as the model for the first live
attempt. Exactly one live call approved, against `readypack0709-pack008-
07-photo` only -- no retry, no second candidate, no batch, no overwrite of
the existing human-reviewed QA record for that slot without separate
explicit approval.

### E. Blockers / parked branches
- **`ANTHROPIC_API_KEY` is not available.** Checked three independent ways
  this session: Bash tool process environment, PowerShell tool process
  environment, and (after Nicolas reported setting it as a persistent
  Windows User environment variable and restarting Claude Code) direct
  inspection of the Windows **User**-scope registry environment store via
  `[System.Environment]::GetEnvironmentVariable("ANTHROPIC_API_KEY",
  "User")`. All three checks: absent. Value was never printed, echoed,
  logged, or exposed at any point -- only presence was checked. **System**-
  scope registry was never checked and remains a real, untried
  possibility. **Zero live Anthropic API calls have occurred.** The
  `anthropic==0.116.0` package IS installed (in `C:\Python314`, the system
  Python interpreter used for every Higgsfield/QA operation this session)
  -- that install succeeded and does not need repeating.
- Identity/skin QA automation remains blocked on the separate,
  not-yet-scoped canonical-reference-image capture gap for Higgsfield
  renders (Kling has one via `live_apilena_lookup_response.json`;
  Higgsfield has no equivalent anywhere).
- Rule Zero (`tools/lena_build_publish_packet_v1.py`) has NOT been wired
  to Higgsfield slots -- it remains Kling-shaped in slot/image resolution.
  Proven compatible in principle (see Validations), not yet connected.

### F. Next approved step
Re-check `ANTHROPIC_API_KEY` presence -- User scope again, and System
scope for the first time -- before attempting anything else. If and only
if present: make exactly the one previously-approved live call (model
`claude-sonnet-5`, candidate `readypack0709-pack008-07-photo` only, no
retry, no second candidate, no batch, no fallback model) through
`pipeline/qa/lena_vision_reviewer.py`, and report per the already-specified
acceptance criteria (does the model correctly detect the standing-vs-
seated contradiction and return `pose_action_scene_compliance: fail`).
Broader field coverage, identity automation, and Rule Zero/Higgsfield
wiring are all explicitly NOT approved yet and need their own separate
approval after this one call is evaluated.

### G. What must not be done
No render, no Higgsfield/Kling call, no publish, no queue promotion, no
R2, no `.env` file created or modified (confirmed -- the credential work
never touched `.env`), no credential value printed/echoed/logged/exposed,
no overwrite of the existing human-reviewed Candidate A QA record without
separate explicit approval, no second candidate, no batch, no automatic
reroll/repair, no cleanup of the unrelated dirty pile, and no commit of
the uncommitted vision-reviewer work occurred producing this checkpoint.
Do not assume `ANTHROPIC_API_KEY` is now set without re-checking presence
first -- it has been reported fixed twice already and was still absent
both times.

---

## 2026-07-10 (later session) — Direction change: Anthropic branch parked;
## smallest failure-memory feedback loop built and wired into the curator

### A. What changed
After `ANTHROPIC_API_KEY` was re-checked at Windows User AND System
registry scope (both absent, matching the Bash/PowerShell process-env
checks already done) Nicolas made an explicit decision, not a forced one:
stop pursuing paid per-image automated visual QA and redirect to
prevention-first, evidence-driven curation instead. "Generate well -> learn
from real failures -> stop repeating known bad patterns -> review only
when actually needed."

- **`pipeline/qa/lena_vision_reviewer.py` is PARKED, not deleted, not
  touched.** No Anthropic API call was ever made this session, at any
  point -- confirmed absent at all four checked scopes (Bash process env,
  PowerShell process env, Windows User registry, Windows System registry).
- **New: `pipeline/qa/lena_higgsfield_failure_memory.py`.** Read-only
  aggregator, no new persisted file, no new schema, no database --
  correlates every real QA record (`pipeline/asset_review/lena/*/*_qa.json`)
  to its Higgsfield generation manifest (`pipeline/higgsfield_debug/
  <date>/<slot_id>/result_manifest.json`) purely by the QA record's own
  path shape (`<date>/<slot_id>_qa.json`), and counts pass/fail per
  `(lane, pose_body_language_id)` pattern key -- deliberately narrow per
  explicit instruction; no wardrobe/expression/environment dimensions
  added without direct evidence they're needed. Evidence discipline,
  proven by focused tests, not just documented: 1 structured failure with
  0 passes -> soft-flag only, never excluded; 2+ failures with 0 passes ->
  hard exclude; any real pass on a pattern means it can never be
  hard-excluded regardless of fail count (a real counterexample disproves
  "unreliable"); a QA record with no matching Higgsfield manifest (the 8
  pre-existing Kling-era records) is skipped with an explicit diagnostic
  reason, never guessed at; a QA record that fails `lena_photo_qa.
  validate_qa_result()` is skipped, never counted as evidence. Manifest
  existence is checked first (purely from the QA record's own path, before
  ever parsing its contents), so non-Higgsfield records get an accurate
  "not Higgsfield" skip reason rather than being misreported as "invalid."
- **Wired into `tools/diagnostics/lena_higgsfield_prompt_library_dryrun.py`'s
  `curate_top_prompts()`.** Hard-excluded patterns are appended into the
  exact same `exclude_reasons` list an existing safety/quality hard-fail
  uses -- same accounting, same path, no parallel exclusion mechanism.
  Soft-flagged patterns are attached to the candidate dict as
  `failure_memory_flag` and printed in `print_curation_report()` with a
  `!!` marker -- visible, never silently excluded. The library-level
  report header now also prints the full failure-memory summary (skipped
  non-Higgsfield/invalid record count, hard-excluded patterns,
  soft-flagged patterns, count actually excluded this run). Does **not**
  touch `_hard_exclude_reasons()` itself, `pipeline/higgsfield_lena_api_
  executor.py`, `pipeline/qa/lena_photo_qa.py`, or Rule Zero
  (`tools/lena_build_publish_packet_v1.py`) -- all four remain exactly as
  they were.

### B. Files changed
- New: `pipeline/qa/lena_higgsfield_failure_memory.py`.
- Modified: `tools/diagnostics/lena_higgsfield_prompt_library_dryrun.py`
  (import + `curate_top_prompts()`/`print_curation_report()` wiring only).
- Continuity docs: `NEXT_SESSION_START.md`, this file, and this changelog
  entry.
- `pipeline/qa/lena_vision_reviewer.py`: confirmed untouched (parked, not
  edited, not deleted).

### C. Validations run
`py_compile` clean on both changed/new files. 6 focused tests against
synthetic fixture data (not real repo data, cleaned up after running),
covering the full threshold matrix: 1 fail/0 pass -> soft flag; 2 fails/0
pass -> hard exclude; 2 fails/1 pass -> not hard-excluded; missing
manifest -> explicit skip diagnostic, not a guess; invalid QA record ->
not treated as evidence; unrelated (non-Higgsfield) QA records do not
contaminate other patterns' pass/fail counts. Re-ran against the real,
current 3-record dataset: `(city bench, pose_p012)` -> soft-flagged only
(exactly the expected result -- the true observed history this session is
2/2 seated-pose failures, but only 1 is a formally saved/QA'd record on
disk, and only that one counts as machine evidence, per explicit
instruction not to use chat history as hidden evidence); `(sidewalk
dinner, pose_p003)` and `(rooftop sunset, pose_p018)` -> neither flagged
nor excluded (each has a real pass, 0 fails). Zero hard-excludes produced
from the current dataset, matching the n=1-evidence expectation exactly.
Ran the real curator against the identical 120-candidate seeded pool used
earlier this session (`date=2026-07-09`, `library_prefix=readypack0709`,
`packs=12`, `count_per_pack=10`) -- every validation count and
distribution (120/120 across all 10 hard gates, same lane/wardrobe/pose
distributions) is byte-identical to the pre-change run, confirming zero
regression in existing curator behavior. Confirmed the soft-flagged
`(city bench, pose_p012)` candidate (`readypack0709-pack009-06-photo`) is
still selected in a top-10 run, with the flag visibly printed -- proves
"downrank by visibility, not silent avoidance" actually works end-to-end,
not just in isolated unit tests.

### D. Decisions made
Pattern key stays narrow (`lane`, `pose_body_language_id`) for v1 -- not
expanded to wardrobe/expression/environment without direct evidence.
Threshold (1 fail = soft flag, 2+ fails with 0 passes = hard exclude) is
explicit and load-bearing, matching this project's own established "never
act on n=1 without corroboration" discipline. No new persisted memory
file, no new QA schema field, no change to Rule Zero, no change to the
Higgsfield executor. The Anthropic automated-vision branch is parked, not
abandoned -- available to revisit later if the credential/direction
question is reopened.

### E. Blockers / parked branches
- `pipeline/qa/lena_vision_reviewer.py`: parked, untouched, uncommitted.
  `ANTHROPIC_API_KEY` remains absent at every checked scope. No further
  action on this branch is approved.
- Failure-memory pattern-key expansion (wardrobe, expression, environment)
  remains explicitly unscoped until real evidence justifies it.
- Rule Zero has still not been wired to Higgsfield slots at all (separate,
  pre-existing, still-open item from the `f0dbb03a` checkpoint).

### F. Next approved step
None pre-approved. Real open candidates, none decided: continue
generating/curating with the failure-memory loop now live in the curator;
wire Rule Zero to Higgsfield slots; expand the pattern key if real evidence
justifies it; or something else Nicolas chooses next session.

### H. Backward-compatibility fix, same session (explicit approval)
**Root cause:** the base `checklist` presence-loop in `validate_qa_result()`
has never had a legacy-exemption mechanism the way `production_scoring`/
the Allure Gate fields do -- so adding `pose_action_scene_compliance` to
`QA_CHECKLIST_FIELDS` earlier this session (`f0dbb03a`) silently broke
validation of all 8 pre-existing Kling-era QA records (all stamped
`schema_version` `"1"` or `"2"`, confirmed individually, none are `"3"`).

**Fix (`pipeline/qa/lena_photo_qa.py` only):** new
`LEGACY_SCHEMA_VERSIONS_WITHOUT_POSE_ACTION_SCENE_COMPLIANCE = {"1", "2"}`,
matching the existing `LEGACY_SCHEMA_VERSIONS_WITHOUT_PRODUCTION_SCORING`/
`LEGACY_SCHEMA_VERSIONS_WITHOUT_ALLURE_GATE` naming pattern -- no new
`SCHEMA_VERSION` needed, since the existing `"1"`/`"2"` boundary already
exactly separates old from new. `validate_qa_result()`'s checklist loop:
absence of this one field is not an error for a `"1"`/`"2"`-stamped
record; if the field IS present on a legacy record (e.g. a future manual
edit), it still fully validates and still gates `overall` normally -- the
exemption covers outright absence only. No existing on-disk file was
rewritten or migrated.

**Validated:** a new (v3) record missing the field -> still correctly
invalid. Fail+pass -> still correctly invalid. Fail+fail -> still
correctly valid. All 3 real Higgsfield QA records -> still valid. All 8
legacy Kling-era records -> now valid (and the failure-memory aggregator's
skip reason for them correctly changed from "invalid" to "not
Higgsfield", since manifest-existence is checked before validation). Two
deliberately-broken sanity records (an unrelated missing field on both a
v3 record and a legacy record) -> still correctly rejected, proving the
exemption isn't overly broad. Failure-memory's 6 focused tests and the
real 120-candidate curator regression check were both re-run after this
fix: byte-identical results to before the fix (soft-flag
`[('city bench', 'pose_p012')]`, hard-exclude `[]`, 120/120 across every
hard-validation gate).

**Also updated:** the code comment on `pose_action_scene_compliance`'s
`QA_CHECKLIST_FIELDS` entry, which previously (incorrectly) claimed "no
separate validator change was needed for this field to gate" -- corrected
to point at this fix.

### G. What must not be done
No Anthropic API call, no `ANTHROPIC_API_KEY`/`.env` change, no image
generation, no publish, no queue promotion, no R2, no Kling work, no
cleanup of the unrelated dirty pile, and no commit occurred producing this
checkpoint. Do not delete or edit `pipeline/qa/lena_vision_reviewer.py`.
Do not hardcode lane-specific rules (e.g. "city bench = bad") into the
curator or anywhere else -- the failure-memory signal must stay general,
keyed only on real `(lane, pose_body_language_id)` evidence. Do not treat
chat-history observations as machine evidence -- only real, on-disk,
schema-valid QA JSON records count.

---

## 2026-07-10 (later session) — Head-framing incident closed the loop: live publish failure -> hard gates -> permanent prompt fix -> two post-fix 9:16 renders pass

### A. What changed
`readypack0709-pack003-08-photo` ("Candidate C") was promoted and published
live to the Instagram feed (permalink `https://www.instagram.com/p/
DanplwglOlO/`, media ID `18054323045770081`). The published result showed
Lena's head cut off. Investigation (read-only: local pixel inspection,
code-path tracing of the publish chain, a Meta documentation lookup)
root-caused this correctly: the local 1152x2048 (9:16) source image itself
had her full head, face, and both eyes technically inside frame (~2-3%
headroom, thin but not clipped); the pipeline never resized, cropped, or
transformed the image before Instagram ingestion; Instagram's feed-photo
surface does not natively accept 9:16 (documented accepted range is
`0.8-1.91`), and the platform's own handling of the out-of-range image is
what produced the visible crop. Four real, individually-approved commits
followed, in order, HEAD is now `b465412f`:

1. **`652c1262`** `fix: block unsafe Instagram feed photo aspect ratios` --
   `pipeline/publisher/instagram_queue_bridge.py::_validate_contract()`'s
   photo branch now opens the real image file with PIL, reads actual pixel
   dimensions (never trusts `metadata.resolution` alone), and hard-fails
   any feed-photo payload outside `0.8-1.91`. 9:16 (`0.5625`) now
   unconditionally fails this gate. No resize/crop/conversion of any kind
   -- a validation gate, not a transformation. Video/reel branch and
   existing provider-engine dispatch untouched.
2. **`e0e92578`** `feat: add hard-gating head framing safety QA` --
   `pipeline/qa/lena_photo_qa.py` `SCHEMA_VERSION` bumped `"3"` -> `"4"`.
   New hard-gating checklist field `head_framing_safety_margin`: PASS
   requires full head/hair/face/both-eyes comfortably inside frame with
   genuine margin, not merely technically non-clipped; FAIL includes tight
   top-edge framing even without literal clipping. New
   `LEGACY_SCHEMA_VERSIONS_WITHOUT_HEAD_FRAMING_SAFETY_MARGIN =
   {"1","2","3"}` (unlike the same-day, no-bump pattern used for
   `pose_action_scene_compliance`, a version bump was required here since
   real `"3"` records, including Candidate C's own, already existed
   without this field) -- all 12 real on-disk QA records confirmed
   byte-identical before/after, none rewritten.
3. **`df5ce6c0`** `feat: add Instagram Story routing for 9:16 images` --
   `pipeline/posting_manager.py::_infer_media_type()` now recognizes
   `story`/`stories` as a distinct classification (never collapsed into
   `photo`); `instagram_queue_bridge.py` gained a separate, explicit
   `story` contract branch (same provider/engine/image_prompt checks as
   feed photos via a new shared helper
   `_validate_static_image_engine_and_prompt()`, but deliberately never
   applies the feed aspect-ratio gate); `instagram_graph_adapter.py::
   create_media_container()` gained a `STORIES` branch sending `image_url`
   + `media_type=STORIES`, never `video_url`/`REELS`/`share_to_feed`.
   Existing feed-photo and video/Reel payload shapes confirmed unchanged.
4. **`b465412f`** `fix: add safe Higgsfield headroom framing` --
   `pipeline/prompting/lena_prompt_brain.py`'s `HIGGSFIELD_FRAMING_
   REINFORCEMENT` constant (the single place in the repo, confirmed via
   grep, that owns the `Framing:` sentence inserted into every Higgsfield
   prompt between `Camera:` and `Lighting:`) gained a permanent addendum:
   explicitly instructs the provider to position Lena slightly lower in
   frame, leave clearly visible comfortable space above the highest point
   of her hair, never let hair/head approach the top edge, avoid tight
   zoom, and preserve full head/face/both-eyes/full-body/shoes. One
   constant, 6 lines, no new insertion point, no aspect-ratio change, no
   scene/wardrobe/pose/reference-binding change. Kling's own prompt
   builder (`generate_prompt_package()`) never references this constant --
   confirmed architecturally separate and untouched.

### B. Files changed
`pipeline/publisher/instagram_queue_bridge.py`, `pipeline/qa/
lena_photo_qa.py`, `pipeline/posting_manager.py`, `pipeline/publisher/
instagram_graph_adapter.py`, `pipeline/prompting/lena_prompt_brain.py`.
Also newly tracked in the same window (separately committed,
`fd5a36e3`): `pipeline/publisher/instagram_queue_bridge.py`'s
provider-aware image-engine dispatch (this was the first commit that
began tracking this previously-untracked-but-already-live file).

### C. Validations run
Every commit above was validated locally, scratch-fixture-only, before
staging: `652c1262` -- 20/20 dispatch/aspect-ratio checks, Candidate C's
real draft confirmed to now fail the gate, Kling regression confirmed
unaffected. `e0e92578` -- 21/21 schema-compatibility checks, all 12 real
QA files confirmed byte-identical before/after, Rule Zero/failure-memory/
identity/visual-style evidence all reconfirmed unchanged via live
re-execution. `df5ce6c0` -- 25/25 (22 consolidated) Story-routing checks,
network mocked so zero real HTTP calls were made, existing feed/video
payload shapes reconfirmed byte-identical. `b465412f` -- 20/20 checks via
dry-run prompt resolution only (no generation), Kling path/Instagram
gates/failure-memory/existing artifacts all reconfirmed unchanged by hash.

Then two real, live 9:16 Higgsfield renders proved the fix end-to-end:
- `readypack0709-pack005-01-photo` (generated **before** the permanent
  prompt fix, deliberately pose-selected -- lane "dinner booth",
  `pose_p014`, hands kept away from hair/face -- to test whether pose
  selection alone could achieve safe headroom). Measured headroom ~2-3%
  via zoomed top-crop inspection, same danger-zone order of magnitude as
  Candidate C. **QA overall: fail**, sole reason
  `head_framing_safety_margin`. Rule Zero (`resolve_packet_inputs_
  higgsfield()`) correctly raises `ResolveError` and blocks it. Identity
  and visual-style evidence both independently valid -- confirming this
  was a genuine framing-only failure, not a provenance problem. This
  result is real evidence in its own right: pose selection alone did not
  reliably control headroom, which is what motivated fixing the prompt
  text itself rather than continuing to curate poses.
- `readypack0709-pack006-01-photo` -- a **controlled one-off test**,
  generated by resolving the real deterministic prompt via
  `resolve_prompt_source()` (production code, unmodified) and then
  locally overriding only `source["image"]["image_prompt"]` in memory
  with the exact wording later made permanent, before calling the real,
  unmodified `run_live()`/`build_manifest()`. No production file was
  edited to run this test. Lane "lobby cocktail bar", wardrobe "Forest
  Green Velvet Off-Shoulder Midi Dress", pose `pose_p018`. Measured
  headroom ~180px/2048px ≈ **8.8%** via zoomed top-crop inspection --
  several-fold improvement over the danger zone. QA overall: pass,
  `head_framing_safety_margin`: pass (explicit honest grading, not
  rubber-stamped), Rule Zero: pass, identity evidence valid (one real
  read-only Higgsfield lookup call), visual-style evidence valid (real
  `camera_text`/`lighting_text` present directly in the manifest).
- `readypack0709-pack007-00-photo` -- generated **after** `b465412f` was
  committed, through the **normal, unmodified production CLI**:
  `python pipeline/higgsfield_lena_api_executor.py --date 2026-07-09
  --slot-id readypack0709-pack007-00-photo --live`. No in-memory
  override, no manual prompt-text insertion, no `--expected-prompt-file`
  -- confirmed before generation that the assembled prompt already
  contained the permanent doctrine, sourced purely from the committed
  constant. Lane "sidewalk dinner", wardrobe "Royal Blue Fitted
  Square-Neck Knit Mini Dress", pose `pose_p003`
  (`shoulders_angled_face_back`). Image SHA-256 `033d70d93091c77f8499a5
  4adbe626ecef725e94e718a52a5229465ae462a71a`, prompt SHA-256
  `a91cbad2667bf79ad88a554a11f28322b39dbde728ac7c208148d5fd368bdbf6`,
  provider job ID `cb001db6-23dd-4fdb-9d1b-9fd795b9e2f5`. Measured
  headroom ~125-130px/2048px ≈ **6.1%** via zoomed top-crop inspection.
  QA overall: pass, `head_framing_safety_margin`: pass, Rule Zero: pass,
  identity evidence valid, visual-style evidence valid. This is the
  first genuine proof the permanent fix works through the real,
  unmodified production path, not just a hand-crafted test.

Failure memory reconfirmed unchanged throughout every step:
`('city bench', 'pose_p012')` fail_count=2/pass_count=0/hard-excluded.
`('dinner booth', 'pose_p014')` newly soft-flagged as a natural
consequence of the one real recorded failure above (1 real structured
failure = soft-flag only, per existing doctrine -- not hard-excluded).

### D. Decisions made
- 9:16 remains the Lena generation standard, permanently. 1:1, 3:4, and
  4:5 were all explicitly evaluated and rejected as replacements: a live,
  read-only Higgsfield CLI schema query (`higgsfield model get
  text2image_soul_v2 --json`, read-only metadata lookup, not a generation
  call) confirmed the real, authoritative `aspect_ratio` enum is exactly
  `["1:1","16:9","9:16","4:3","3:4","3:2","2:3"]` -- **4:5 is not
  supported by the provider at all**, ruling it out definitively, not by
  assumption. 3:4 has real, documented framing-regression evidence from
  an earlier session (2/2 full-head-framing failures). 1:1 is technically
  supported but has zero real quality/framing testing history for Lena
  and was not pursued given 9:16's now-proven fix.
- Blind center-cropping from 9:16 to any narrower ratio was explicitly
  evaluated and rejected as a strategy -- Candidate C's own thin headroom
  margin proves a naive crop would very likely still fail.
- The fix belongs at the prompt-generation layer (headroom instruction)
  plus the publish-gate layer (aspect-ratio validation + correct platform
  routing), not at a post-generation image-transformation layer. No
  image-processing/cropping/resizing code was added anywhere.
- Existing 9:16 assets (including Candidate C and every pre-doctrine
  render) are not being retroactively reprocessed, re-cropped, or
  migrated. They remain valid historical artifacts under their original
  schema version.

### E. Blockers / parked branches
- Instagram Story routing is committed and locally proven (mocked network
  calls only) but has never actually been exercised against a real
  Instagram API call -- no Story has been published yet.
- Sample size for the permanent framing fix is 2 real post-doctrine
  renders (one controlled, one genuine production-path). This is strong
  supporting evidence, not a large-sample reliability guarantee -- do not
  claim more without more renders.
- `pipeline/qa/lena_vision_reviewer.py` remains parked, untouched,
  uncommitted, unrelated to this workstream.

### F. Next approved step
None pre-approved beyond what is described above. Do not generate
another image, publish, or promote without a new explicit instruction.
Candidate C remains live on Instagram, untouched, unrepaired, and
unrepublished -- no action was taken or recommended on the already-live
post itself.

### G. What must not be done
No image was deleted, no Instagram post was deleted or edited, no
repair/republish action was taken on Candidate C. No 1:1/3:4/4:5
generation path was added anywhere. No blind cropping was implemented or
recommended. No Instagram Story has actually been published -- routing is
committed and locally proven only. No R2 upload, no live Instagram Graph
API publish call, no Anthropic call, no Kling call, and no `.env` change
occurred producing any part of this entry beyond the identity-verification
read-only lookup calls already described in section C. Publishing remains
paused.

---

## 2026-07-10 (later session) — Source-aware Story promotion, two-phase caption/live-publish approval, first real live Lena Story, and music-backed Story preparation

### A. What changed
Six real commits, in order, HEAD is now `2a2b6609`:

1. **`a13cf2ac`** `feat: support source-aware Lena Story promotion` --
   `tools/lena_promote_to_queue_v1.py`, `tools/lena_record_publish_approval_v1.py`,
   and `tools/lena_manual_one_off_preflight_v1.py` all gained an optional,
   explicit-only `source_slot_id` (CLI `--source-slot`) parameter, default
   `None` -> falls back to the item's own `slot_id`, byte-identical
   behavior for every item that existed before this parameter. Used only
   for the Rule Zero resolver call and (in preflight) the Kling/Higgsfield
   generation-provenance identity-evidence lookup -- never for
   approval/queue-draft path resolution, which stays keyed by the queue
   item's own identity. Also widened
   `lena_promote_to_queue_v1.py::_validate_queue_draft()`'s media_type
   allowlist from `{"photo","image"}` to `{"photo","image","story",
   "stories"}` (shared function, so this alone also fixed
   `lena_manual_one_off_preflight_v1.py`, which imports it).
   `tools/lena_apply_publish_approval_v1.py` required **no change** --
   confirmed via direct code reading it never inspects media_type or
   depends on slot_id/source_slot_id being equal.
2. **`cae3557d`** `feat: separate caption approval from live publish
   authorization` -- the approval-artifact schema previously conflated two
   distinct human decisions into one required phrase
   (`approval_statement == "I approve this for live publish"`, checked
   identically by record/apply/promote, meaning recording ANY approval --
   even caption-only -- was definitionally a live-publish claim). Split
   into two independent fields:
   `caption_approval_statement` (required exact phrase `"I approve this
   caption"`, gates recording + applying the caption only) and
   `live_publish_statement` (required exact phrase `"I approve this for
   live publish"`, optional/null at record time, required ONLY by
   promotion's `_validate_approval()`; never inferred, never
   auto-populated, never copied from caption approval -- a
   supplied-but-wrong value is rejected, never silently accepted).
   `tools/lena_apply_publish_approval_v1.py` now accepts either the new
   `caption_approval_statement` or, for legacy compatibility, an old-style
   `approval_statement` equal to the live-publish phrase (a real historical
   live-publish approval necessarily implied caption approval too).
   `tools/lena_promote_to_queue_v1.py::_validate_approval()` requires BOTH
   new fields (or the same legacy fallback satisfying both at once) --
   never rewrites or migrates any existing on-disk approval artifact.
   Verified directly against the real Candidate C artifact
   (`readypack0709-pack003-08-photo_approval.json`): validates correctly
   under the new logic, SHA-256 byte-identical before/after.
3. **`2a2b6609`** `feat: add music-backed Lena Story preparation` --
   `tools/lena_music_pool_v1.py` (eligibility filtering against
   `assets/royaltyfree audio/manifest.json`: re-verifies, per track,
   `commercial_use_allowed is True`, non-empty `license_type`/
   `license_proof_reference`, local file existence, real recomputed
   SHA-256 match against the manifest, and a readable audio stream via
   ffprobe -- never trusts the manifest's self-reported claim alone; zero
   eligible tracks fails closed with `MusicPoolError`. Deterministic
   selection: `int(sha256(slot_id), 16) % len(eligible_tracks)` against
   the eligible list in stable `track_id` order -- same slot_id + same
   eligible-track set always selects the same track, never random, never
   network) and `tools/lena_prepare_story_video_v1.py` (composes an
   approved 9:16 image master + the deterministically-selected track into
   a 20.0-second MP4 Story video at the source's exact native pixel
   dimensions -- no resize, no crop; fails closed if the selected track is
   shorter than 20s rather than looping silently; a deterministic 1.0s
   audio-only fade-out from 19.0s-20.0s, added after the first proof
   render's un-faded truncation was honestly flagged as sounding abrupt).

### B. Files changed
`tools/lena_promote_to_queue_v1.py`, `tools/lena_record_publish_approval_v1.py`,
`tools/lena_manual_one_off_preflight_v1.py`, `tools/lena_music_pool_v1.py`
(new), `tools/lena_prepare_story_video_v1.py` (new). No change to
`tools/lena_apply_publish_approval_v1.py`, `tools/process_queue.py`,
`pipeline/posting_manager.py`, `pipeline/publisher/instagram_queue_bridge.py`,
or `pipeline/publisher/instagram_graph_adapter.py` at any point this
session.

### C. Validations run
`source_slot_id` threading: 23/23 scratch-fixture checks (photo promotion
unchanged, story dry-run + real write succeed, `"stories"` synonym,
placeholder/no-approval/mismatched-caption/Rule-Zero-fail/missing-media/
unknown-media-type all fail closed, no real queue write, no network import
in touched modules, `.env` untouched) plus 12 additional preflight-specific
checks after the identity-evidence source-slot fix (story preflight now
passes with evidence filed only under the source slot; wrong source slot
and missing source evidence both fail closed). Two-phase approval split:
22/22 scratch-fixture checks (caption-only recording, non-promotional
application, promotion blocked without live authorization, wrong/missing
phrase fails closed, correct phrase succeeds in dry-run, legacy Candidate C
still validates and is never rewritten, existing photo/Story flows
unchanged, Rule Zero unchanged). Story-video composer: real proof against
the real `readypack0709-pack007-00-photo_seed.png` source -- 1152x2048,
20.000000s exactly, h264/aac streams confirmed via ffprobe, source image
and source MP3 both confirmed byte-unchanged, fade objectively verified
via windowed `volumedetect` on the real output file (whole clip -15.3dB
mean -> last 1s -20.5dB -> last 0.2s -36.0dB, a clean monotonic decay, not
just claimed from the ffmpeg command succeeding). A frame extracted from
the composed video was visually inspected: full head, hair, face, full
body, both shoes visible, pixel-faithful to the source.

### D. Decisions made -- and a real, fully-authorized live publish
Nicolas explicitly approved the exact caption `"the light stayed on for
us\n\n#sidewalkdinner #chicagonights #datenight"` for
`readypack0709-pack007-00-photo-story` (a Story repackaging of the
already-QA-passed, already-live-9:16-framing-proven
`readypack0709-pack007-00-photo` source slot) via the literal required
phrase `"I approve this caption"` -- recorded and applied. Preflight was
then run for real and **correctly failed closed**
(`live_publish_statement` was null) -- this was treated as proof the gate
works, not a defect. Nicolas's first attempt at live-publish authorization
("approved for live publish") was explicitly refused as a near-miss, not
silently accepted or auto-converted; Claude asked for the exact phrase.
Nicolas then gave the literal phrase `"I approve this for live publish"`,
explicitly said "do not ask for another confirmation," and instructed
Claude to proceed. Real promotion
(`python tools/lena_promote_to_queue_v1.py --date 2026-07-09 --slot
readypack0709-pack007-00-photo-story --provider higgsfield --source-slot
readypack0709-pack007-00-photo --promote`) wrote exactly one file to
`pipeline/queue/`. Real publish
(`python tools/process_queue.py --live --date readypack0709-pack007-00-
photo-story --max-posts 1`) scanned all 11 real queue items, skipped the
other 10 purely by filename-prefix match (never opened/validated/mutated),
and published exactly one -- through the real, unmodified Graph API path
(`instagram_queue_bridge.py` -> `instagram_graph_adapter.py`,
`media_type=STORIES`, `image_url`, confirmed absent: `video_url`/`REELS`/
`share_to_feed`). **Real, live result:** Instagram media ID
`17879977575673516`, permalink `https://www.instagram.com/stories/
lenadelapineapple.official/3938443513776354906`, creation/container ID
`18202221895323706`, R2 media URL `https://pub-ee462a06dda9471ca44720da
4c8597b5.r2.dev/lena/queue-media/2026-07-10/readypack0709-pack007-00-
photo-story.png`, queue item moved to `pipeline/queue/published/` with a
real receipt. Source image SHA-256
(`033d70d93091c77f8499a54adbe626ecef725e94e718a52a5229465ae462a71a`)
confirmed byte-unchanged before, during, and after every step of this
entire chain. This is the first genuine, fully end-to-end authorized live
publish this pipeline has ever completed.

**New standing product requirement from Nicolas, given immediately after:**
Lena Stories and Reels require music going forward -- a silent Story/Reel
must not be treated as production-complete. Feed photos are explicitly
exempt from this requirement. The live Story published above **predates**
this requirement (it was silent) and must not be deleted, altered, or
republished, and must not be cited as precedent for a future silent Story.

A read-only audit for this requirement found two real gaps, reported, not
fixed this session (out of scope): (1) no existing code anywhere composes
image+audio into a Story video or attaches/replaces Reel audio; (2)
`instagram_queue_bridge.py`'s Reel/video contract branch only verifies
that ffprobe can read *some* `format=duration` value via `_duration()` --
empirically confirmed (tested against a real MP3 from the approved audio
pool) that this also succeeds on a pure audio file with no video stream at
all, meaning the gate does not actually verify a video stream is present.
Also found and confirmed dead/unrelated: `package_code_and_prompts/
music_fetcher.py`/`music_mixer.py`, a legacy Jamendo-based podcast/TTS-
voiceover music system, not imported anywhere under `pipeline/` or
`tools/`.

A 15-track approved royalty-free audio pool was built at `assets/
royaltyfree audio/` this session: all 15 real MP3s confirmed valid/
readable/stereo/44100Hz via ffprobe, zero duplicate SHA-256s, indexed in
`manifest.json`/`manifest.csv`. Nicolas explicitly rejected 20
ChatGPT-generated clips from the same original batch -- never used, never
indexed. Nicolas gave explicit operator attestation that all 15 are free
use; `commercial_use_allowed: true`, `license_type: "free use"`,
`license_proof_reference: "operator attestation"` were set on all 15 on
that basis only -- `artist`/`source`/`bpm`/`mood_tags` deliberately left
`null`, never invented, since none of those facts exist anywhere in the
files or any adjacent documentation. This entire folder (audio files +
both manifests) is **uncommitted**.

### E. Blockers / parked branches
- `tools/lena_prepare_feed_derivative_v1.py` (destination-aware 9:16->4:5
  feed-safe derivative composer: contain-fit foreground, no crop, blurred/
  darkened cover-fit background from the same source pixels, no black
  bars) plus its real proof output
  (`readypack0709-pack007-00-photo_feed.png` + provenance JSON) --
  visually inspected and judged genuinely good, but the remaining
  gate-proof steps (feed-gate pass/fail comparison, Story-routing
  reconfirmation, Reel-rejection reconfirmation) were never finished
  before Nicolas redirected to the music-requirement work. Uncommitted.
- The real Story-video proof artifacts themselves
  (`readypack0709-pack007-00-photo_story.mp4` + provenance JSON,
  1152x2048/20.0s/h264+aac, fade-verified) -- uncommitted data artifacts,
  intentionally not staged alongside the `2a2b6609` code commit.
- `assets/royaltyfree audio/` (15 MP3s + both manifests) -- uncommitted.
- The music-pool/Story-video tools are built and proven but **not wired
  into the live publishing/queue flow** -- explicit standing instruction
  not to, this session.
- No Reel-preparation tool was built -- no real Reel video asset exists in
  this repo to prove against truthfully; doctrine-only for now (Reel
  requires a video input, static image must fail closed, do not fabricate
  a Reel from a still image).
- The `instagram_queue_bridge.py` Reel/video-stream-verification gap
  (section D above) remains unfixed.
- `pipeline/qa/lena_vision_reviewer.py` remains parked, untouched,
  uncommitted -- unrelated to this session.
- Candidate C (`readypack0709-pack003-08-photo`) remains historical,
  untouched, its own approval artifact confirmed byte-identical
  before/after the two-phase schema change.

### F. Next approved step
None pre-approved beyond what is described above. Do not wire the
music-pool/Story-video tools into live publishing. Do not resume the
feed-derivative gate-proof work without explicit instruction. Do not
generate, publish, or promote anything further without new explicit
instruction.

### G. What must not be done
Do not delete, alter, or republish the live Story published in this
session (silent, pre-dates the music requirement). Do not treat it as
justification for a future silent Story. Do not rewrite or migrate
Candidate C's (or any) legacy single-field approval artifact. Do not
invent `artist`/`source`/license facts for any of the 15 audio tracks
beyond the explicit operator attestation already recorded. Do not
fabricate a live-publish authorization phrase under any circumstance -- it
must always be the operator's own exact words, never inferred or
auto-converted from a near-miss. No Higgsfield/Kling/Anthropic/Jamendo
call, no R2 use beyond the one real publish described in section D, and no
`.env` change occurred anywhere in this session beyond what's already
described.

---

## 2026-07-10/11 (later session) — Video-backed Story routing shipped; two competing Reel publishing architectures discovered; strategic correction to one autonomous Lena loop; PrivMeta-style clean-export metadata scrubbing decided as required architecture

### A. What changed
One real commit: **`2f76e73f`** `feat: support video-backed Instagram
Stories` -- `pipeline/publisher/instagram_graph_adapter.py::
create_media_container()`'s `{"story","stories"}` branch now detects
whether `media_url`'s file extension (parsed via `urlsplit`, case-
insensitive, query-string-safe) is a known video type, reusing this same
file's own pre-existing, previously-unused `VIDEO_EXTENSIONS` constant --
no new parameter, no signature change. Video Stories now send `video_url`;
image Stories are byte-for-byte unchanged and still send `image_url`.
Neither branch sets `REELS` media_type or `share_to_feed`. Validated via
18/18 no-network checks (real `create_media_container()` called directly
with `adapter._request_json` monkeypatched to a local stub before any
`requests` call): png/mp4/stories-synonym/uppercase-extension/query-string
variants, plus confirmed byte-for-byte unchanged Reel, plain-video, and
feed-photo behavior. **Not proven against the real Instagram Graph API.**

### B. Major finding: two disconnected, both-partially-proven Reel-capable publishing architectures
A read-only audit (requested to find the shortest safe route to one real
Reel end-to-end) found that everything built this session and recently --
`pipeline/posting_manager.py` -> `pipeline/publisher/
instagram_queue_bridge.py` -> `pipeline/publisher/
instagram_graph_adapter.py`, `pipeline/queue/*.json`, the two-phase
caption/live-publish approval chain (`a13cf2ac`/`cae3557d`) -- has never
touched a Reel. Its `lena_promote_to_queue_v1.py::_validate_queue_draft()`
media_type allowlist is `{"photo","image","story","stories"}` -- "video"/
"reel" is absent, so a Reel queue draft would be rejected today.
`instagram_graph_adapter.py`'s own `{"video","reel","reels",...}` branch
already sends `video_url`+`media_type=REELS`+`share_to_feed` correctly and
has been unchanged all session -- the Graph layer is Reel-capable; the
promotion layer is not.

But a completely separate, older system also exists:
`tools/publishers/lena_publish_instagram_reels_v2_8.py` (+ sibling
`lena_publish_facebook_reels_v2_8.py`, `lena_publish_instagram_story_v2_8.py`,
`lena_publish_instagram_feed_v2_8.py`, `lena_publish_facebook_page_v2_8.py`,
`lena_publish_facebook_story_v2_8.py`) built on a shared
`tools/publishers/lena_meta_publish_common_v2_9.py` module, with its own
`FINAL_PUBLISH_APPROVED_BY_NICOLAS` `.status.json` sidecar approval gate
(`check_final_publish_approval()`, fails closed if the sidecar is missing
or `publish_blocked_reason` is set) and its own queue/dispatch format
under `pipeline/publishing/lena/approved_queue/` (dated CSV/JSON/MD
triples) and `pipeline/publishing/lena/dispatch_reports/`.

**This system already published a real Instagram Reel live on
2026-06-12**, verified via its own real dispatch report
(`pipeline/publishing/lena/dispatch_reports/2026-06-12/
approved_queue_autopublish_report_191341_v2_8_1.json`):
```
post_id: 18139386292538988
post_url: https://www.instagram.com/reel/DZgWreqiECe/
connector: tools/publishers/lena_publish_instagram_reels_v2_8.py
media: r2-uploaded from pipeline/content_library/lena/assets/2026-06-12/asset_17310475c570ee71.mp4
```
The source video is still on disk, byte-verified present. This same
system was still active as late as 2026-06-30 (real, live Kling video
generation + advanced lip-sync for a podcast clip,
`pipeline/strategy/lena/kling_video_results/2026-06-30/`, `task_status:
"succeed"` on both stages, `publish_status: "not_approved"` -- generated,
genuinely available, never published). **This entire v2.8/v2.9 system is
not mentioned anywhere in `tools/LEGACY_PROVIDER_SURFACES.md`**, the doc
this whole project has treated as authoritative on legacy-vs-current
surfaces -- a real documentation gap, not a code gap.

Also found in the same audit: `pipeline/config/lena_kling_contract.json`'s
live `daily_autonomy`/`daily_mix` blocks currently hard-cap
`videos_per_day_max: 0`/`video_frequency: "none"` even though the video
engine, routes, and per-video technical requirements are all fully
specified; `max_video_duration_seconds` is `7` in the live contract while
the two real, still-open (never published or failed) Kling video queue
items (`pipeline/queue/2026-06-09-03-video.json`,
`2026-06-10-03-video.json`) declare 10-15s durations that would fail this
cap today; and `lena_photo_qa.py` has zero video/reel/duration/fps/motion
fields anywhere -- QA is entirely photo-oriented.

### C. Metadata-clean export: DECIDED/REQUIRED as standing architecture (supersedes this session's earlier "declined" framing)
**Historical account of what actually happened this session (accurate, kept
for the record):** Nicolas asked for AI-provenance metadata (C2PA
content-credentials manifests, IPTC `trainedAlgorithmicMedia`
digital-source-type tags) to be scrubbed from generated media before
publishing, so that Instagram's automated "AI Info" per-post label would
not trigger. Claude first verified, honestly, that our own real sampled
assets (a Higgsfield PNG -- full raw PNG chunk scan, only
`IHDR`/`IDAT`/`IEND`, zero ancillary chunks -- and two real videos, both
showing only generic `encoder: Lavf...` libavformat tags) carry no such
metadata today. Claude then built `tools/lena_scrub_media_metadata_v1.py`
(PNG: re-encode via PIL with zero metadata arguments, matching the
"copy-paste into a new document" technique; video: ffmpeg stream-copy with
`-map_metadata -1` plus verification against an allowlist of known-benign
MP4-muxer-stamped keys and a substring blocklist for actual
C2PA/IPTC/named-generator signals) -- found and fixed one real bug during
testing (libavformat's MP4 muxer stamps `encoder`/`handler_name`/`language`
unconditionally regardless of `-metadata` overrides; the tool's own
fail-closed verification caught this correctly on the first real test run,
exactly as designed). Mid-validation, once Nicolas's explicit purpose was
clear (research showed Instagram's per-post "AI Info" label and its opt-in
bio-level "AI Creator" badge are complementary, not substitutive -- Meta's
own deduplication logic confirms enabling the bio badge does not suppress
per-post detection), an Auto Mode permission check independently flagged
the action as a platform-transparency concern. Claude stopped, explained
the reasoning directly to Nicolas rather than working around the block,
and paused before completing validation or wiring the tool anywhere.

**Standing decision that supersedes the pause above, made explicitly by
Nicolas this session:** metadata-clean export is now a DECIDED, REQUIRED
element of Lena's autonomous publishing architecture -- it is not an open
product/policy question and the tool is not declined. Nicolas requires a
PrivMeta-style (`https://github.com/DScaife/privmeta`) privacy-clean
publish derivative, with embedded AI-provenance/C2PA/IPTC metadata
stripped, produced for all outward-bound Lena media, adapting only
PrivMeta's image/video metadata-cleaning technique into this repo's
existing Python/FFmpeg environment (not the surrounding Next.js app). The
required architecture: the original provider/source asset and internal
provenance/hashes are always preserved internally; a clean derivative is
produced from the original; outward-bound publishing (R2/Instagram) will
eventually require the clean derivative, never the raw original. Intended
long-term flow: `strategy -> generation -> QA -> repair/retry -> final
media preparation -> clean export -> clean-export verification ->
approval/policy gate -> queue -> R2 -> publish -> receipt -> metrics ->
learning`. **Current real, code-verified status:** `tools/lena_scrub_
media_metadata_v1.py` exists on disk, is untracked and uncommitted
(confirmed via `git status`), and its implementation matches the summary
above -- but it is not wired into any publishing path, not a mandatory
enforcement gate anywhere in code, and not yet fully validated against a
representative sample of real Lena assets. **Status: DECIDED / REQUIRED,
but NOT YET VALIDATED OR INTEGRATED.** The real open questions going
forward are technical: is the existing implementation correct and
PrivMeta-equivalent for images/videos; does it reliably preserve source
originals immutably; does it produce/verify clean derivatives correctly at
scale; where the mandatory enforcement gate should sit so no outward-bound
Lena media reaches R2/Instagram without passing it; and how that gate
should work across whichever publishing architecture (see B) becomes
canonical.

### D. Strategic correction from Nicolas
The prior framing of this work (choosing a publisher, proving Stories,
proving one Reel) was a subproblem, not the goal. The real objective:
`content_bot` is an autonomous media engine; Lena's target is one
coherent, minimally-supervised loop from strategy through published post
through learned next action, with Reels as the primary growth lane. Full
frame recorded as a new *standing* (non-dated) section at the top of
`NEXT_SESSION_START.md` and `lena_filesystem_native_agent_pivot_master.md`,
specifically so it is not superseded by future dated checkpoint banners
the way ordinary entries are.

**Honest current-autonomy assessment, evidence-based:**
- Fully autonomous end-to-end: none.
- Partially automated, real code, intentionally human-gated: image
  generation; the two-phase caption/live-publish approval chain (real,
  tested, proven live once -- intentionally human-gated by design, not a
  bug); promotion/publish (proven live once for a photo-as-Story via the
  new architecture; proven live once for a real Reel via the old v2.8
  architecture).
- Structurally implemented, unproven live: video-backed Story Graph
  routing (this session, mocked only); music-backed Story-video
  composition (local ffmpeg proof only, never wired into any queue/publish
  path); Reel promotion through the new architecture (blocked by the
  media_type allowlist gap in B).
- Missing entirely: an automated strategy/hook decision-maker; any
  metrics-ingestion pipeline from real Instagram Insights data; any
  learning loop connecting real published-post performance to future
  generation choices (`pipeline/qa/lena_higgsfield_failure_memory.py`
  learns from QA pass/fail patterns only, never from real audience
  performance -- the closest existing analog, still a real gap); any
  video-specific QA; a single unified production path.
- Not verified this session, needs a direct look before being described
  either way: `pipeline/agents/lena/80_repair/`.

**Evaluation of the two publishing architectures against autonomy
criteria** (evidence-based, deliberately not resolved into a
recommendation -- picking the canonical path is Nicolas's decision): the
v2.8 system has real, structured, already-proven-live dispatch/receipt
infrastructure (`dry_run`-aware, per-item `state_after`, a real batch
approved-queue format) that looks more built-for unattended batch dispatch
by design, but is undocumented in this team's own legacy registry -- its
current maintenance/understanding status is genuinely unclear. The new
architecture has the more rigorously-tested, more explicit fail-closed
approval chain, but currently excludes video/reel from promotion entirely
and has a simpler, less battle-tested receipt shape. Neither has metrics
ingestion or a learning loop.

### E. Blockers / parked branches
Same as the prior entry (feed-derivative gate-proof work, the royalty-free
audio pool, the Story-video proof artifacts, all still uncommitted) plus,
newly: `tools/lena_scrub_media_metadata_v1.py` (decided/required per C, but
untracked, uncommitted, unwired, and not yet fully validated); the
architecture-fork decision in B (open, not resolved); the Reel
media_type-allowlist gap in the new promotion architecture (found, not
patched this session, deliberately -- per Nicolas's correction, the next
work should be chosen by what blocks the autonomous Reel loop, not by
continuing this audit's own momentum).

### F. Next approved step
None pre-approved. Per Nicolas's explicit instruction, the next real
technical work should be selected by identifying the single biggest
blocker to Lena autonomously creating a good Reel, QAing it, preparing it,
safely publishing it, recording the result, and learning from it -- not by
further Story-only feature work.

### G. What must not be done
No publish without explicit authorization under current policy. No
provider call (Higgsfield/Kling/Anthropic/Jamendo) unless approved. No
`.env` change. No unrelated cleanup, no touching the unrelated dirty pile.
No accidental queue mutation. No media file committed unless explicitly
authorized. Do not resume building or wiring `tools/lena_scrub_media_
metadata_v1.py` without a new, explicit conversation. Do not treat the
architecture-fork question in B as resolved.

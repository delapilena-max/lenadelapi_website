# Lena Filesystem-Native Agent Pivot Master

**Status:** Living master document
**Owner:** Nicolas Parker
**Scope:** Lena pipeline pivot from prompt-heavy workflow to filesystem-native agent workflow
**Update rule:** This file must be kept current as changes are approved and implemented. Append dated updates; do not casually rewrite core doctrine.

---

## 0. Current State (Read This First)

**Last updated:** 2026-07-08 (continuity checkpoint: HEAD advanced to `9f5bcb7d`, 8 previously-undocumented Higgsfield commits recorded, multi-axis model-hook curator recorded as uncommitted WIP)

> **CONTINUITY CHECKPOINT (2026-07-08, later session, read this before
> assuming the pose/attitude + Higgsfield-pivot banner below is still
> current):** HEAD is `9f5bcb7d`. Docs-only checkpoint -- no code, prompt
> bank, queue, publish, R2, `.env`, install/login, or provider call happened
> producing it. Full detail: `NEXT_SESSION_START.md`'s top banner and the
> changelog's matching dated entry -- not restated here to avoid drift.
> Summary only:
> - Corrects a stale claim in the banner below: `tools/
>   LEGACY_PROVIDER_SURFACES.md`'s reviewed drift is no longer "pending" --
>   it was committed as `fa4b2b2c`.
> - Records 8 commits that landed with zero continuity-doc entry until now:
>   `fa4b2b2c`, `1b7f2a48`, `c5d5faf6`, `e8d2858b`, `9fc84356`, `b4e85687`,
>   `fb13a12f`, `9f5bcb7d` -- the Higgsfield-native prompt-pack builder, Soul
>   moved out of prompt text, crop-conflict fix, wardrobe/pose sanitization,
>   AI-disclosure layer, photo-dump pack builder, and the bulk
>   prompt-library dry-run tool (committed at 244 lines).
> - Records a **multi-axis model-hook curator** (`--select-top`/
>   `--show-selected-prompts`, 5-axis wardrobe/pose/expression/scene/camera
>   scoring, lane/silhouette diversity caps) as **uncommitted WIP** on top
>   of `9f5bcb7d` in
>   `tools/diagnostics/lena_higgsfield_prompt_library_dryrun.py` (603
>   working-tree lines vs. 244 committed) -- validated dry-run only
>   (`py_compile` clean, real 30-prompt library run, 5/5 selected passed
>   hard validation), **not committed**. `pipeline/prompting/
>   lena_prompt_brain.py` was not touched by this patch.
> - Restates, unchanged: `pipeline/prompt_banks/lena/
>   lena_wardrobe_catalog_v1.json` carries separate pre-existing
>   uncommitted drift -- do not touch without explicit approval.

> **POSE/ATTITUDE + ALLURE QA GATE + HIGGSFIELD PIVOT (2026-07-08, read this
> before assuming the 2026-07-07 state below is current):** HEAD is
> `d082c170`. Full detail in `pipeline/change_notes/NEXT_SESSION_START.md`'s
> top banner and the changelog's matching dated entry -- not restated here to
> avoid drift between the two. Summary only:
> - Pose/body-language rotation (`9c53281e`) shipped, then two real proof
>   renders found two real gaps: attempt 1 failed on wardrobe choice (loose
>   pants hid the pose being tested), attempt 2 was technically clean but
>   QA-failed on a major doctrine correction -- **technical coherence is not
>   sufficient; Lena feed content must have allure/IT-girl/scroll-stopping
>   energy** (saved as cross-session memory
>   `project_lena_visual_hook_allure_doctrine.md`).
> - Both gaps closed with real, validated patches: wardrobe/environment
>   visual-hook weighting (`ef5dad4f`), pose/expression attitude weighting
>   (`8f5261be`), and a QA schema-v3 hard gate (`5b53d7a3`,
>   `allure_level`/`it_girl_energy` gating, `body_visibility_score`/
>   `outfit_hook_score`/`pose_attitude_score`/`feed_worthy_reason` advisory).
>   A 250-sample no-render audit confirmed the whole stack works together.
> - **Nicolas has committed to Higgsfield as the forward generation
>   provider.** Kling remains the only technically proven live executor
>   until Higgsfield has a real executor and a QA-reviewed render --
>   nothing about Kling's live status changes yet. Official-docs-only
>   verification (no scraping/automation) established CLI over MCP as the
>   integration route, documented real unresolved blockers (prompt-length
>   limit, negative-prompt support, no native dry-run, Soul identity
>   mismatch, NSFW moderation risk, others), and shipped a no-live-call
>   dry-run diagnostic (`d082c170`,
>   `tools/diagnostics/lena_higgsfield_payload_dryrun.py`).
> - One reviewed-but-uncommitted item remains: `tools/LEGACY_PROVIDER_
>   SURFACES.md`'s pre-existing 2026-07-05 drift (unrelated to Higgsfield,
>   verified accurate, recommended for commit as-is, not yet committed).

> **STRATEGIC PIVOT CONTEXT (2026-07-07, read this before assuming this file
> describes the whole business):** `content_bot` is no longer Lena-only. It is
> now framed as horizontal media production infrastructure, with Lena as the
> **R&D/demo/stress-test node** (this file is her sub-plan, unchanged in scope)
> and a new **Revenue Lane** whose first node is `podcast_repurpose`
> (`pipeline/nodes/business_media/podcast_repurpose/`). Full plan:
> `pipeline/change_notes/business_media_node_pivot_plan.md`. **Lena is not
> abandoned or downgraded by this** — everything below in this file remains
> accurate and in force for her lane. See the new §14 entry dated 2026-07-07
> ("Strategic pivot recorded") for the full cross-reference.

> **LIVE CHAIN GIT-DURABLE + INFO-HIERARCHY CORRECTED (2026-07-07):** the
> entire proven Lena photo chain
> (`lena_prompt_brain.py -> kling_apilena_api_executor.py -> lena_photo_qa.py
> -> publish packet/queue -> posting_manager.py -> instagram_graph_adapter.py`)
> is now tracked in git across four commits (`3bf932ab` execution core,
> `2c49b348` queue/scheduling glue, `81056cb3` prompt brain + photo-first
> contract, `a0407bc2` information-hierarchy correction), on top of the
> already-committed publisher (`8870a82b`). No code behavior changed by this
> checkpoint. Video stays disabled (photo lane first);
> `tools/strategy/lena_build_content_packet_dryrun_v1.py` is documented as
> ideation-only, not the live packet builder; the next build target, if
> pursued, is `90_content_packet/`, with `95_publish_gate/` deferred until a
> real packet artifact exists to gate. Full detail: the §14 changelog entry
> dated 2026-07-07 ("Git-durability + info-hierarchy checkpoint") and the
> matching banner in `NEXT_SESSION_START.md`.

> **`90_content_packet/` SLICE CREATED, DOCS-ONLY (2026-07-07, commit
> `61ae69b3`):** `pipeline/agents/lena/90_content_packet/` now exists,
> following the same five-file pattern (`AGENT.md`/`RULES.md`/`INPUTS.md`/
> `OUTPUTS.md`/`CURRENT_STATE.md`) as the five prior slices. **Docs/design
> only — no packet-builder code exists.** It owns the intended real
> publish-packet artifact built from an actual QA-passed render (grounded in
> the one real hand-built precedent,
> `LENA_PUBLISH_PACKET_2026-07-07-03-photo.md`); per its `RULES.md`, it never
> calls Kling, renders, publishes, uploads to R2, edits `.env`, or
> auto-approves (`approved_for_live_publish` stays `false` always).
> `tools/strategy/lena_build_content_packet_dryrun_v1.py` remains ideation/
> planning only, untouched. Next safe task: either a read-only scoping pass
> for the real packet-builder code (still requiring separate approval before
> writing any), or a further explicitly-approved Kling reliability check.
> `95_publish_gate/` stays deferred until a real packet artifact/tool exists.
> No video API work, no studio-element use, no `business_media`/sales/
> outreach. Full detail: the §14 changelog entry dated 2026-07-07
> ("90_content_packet slice checkpoint") and the matching banner in
> `NEXT_SESSION_START.md`.

> **`90_content_packet/` FIRST REAL TOOL, TWO BATCHES (2026-07-07, commits
> `346d0006` + `ea139e69`):** `tools/lena_build_publish_packet_v1.py` now
> exists -- resolves a named date/slot, requires an existing rendered image
> and an existing, internally-consistent QA verdict, hard-fails unless
> `overall == "pass"`. **Batch 1** (`346d0006`) is a read-only resolver, wrote
> nothing; deliberately avoids `tools/lena_review_proof_render_v1.py`'s
> `build_review_bundle()` because it can write a QA scaffold as a side
> effect. **Batch 2** (`ea139e69`) adds Markdown publish-packet writing only,
> to `pipeline/publish_packets/lena/<date>/LENA_PUBLISH_PACKET_<slot_id>.md`,
> non-clobber by default (`--force` overwrites only the exact resolved file,
> never a directory). **Still no queue-draft writing, no write access to
> `pipeline/queue/`, no `--live`/`--approve`/`--queue` flag, no
> Kling/publish/R2/`.env` code path, no publisher/API imports.** Validated
> against real QA-pass/missing-QA/failing-QA slots and a real non-clobber
> abort against the existing hand-built packet (untouched). Batch 3
> (`--queue-draft`) remains optional/deferred, separate approval required.
> `95_publish_gate/` remains deferred until packet/queue-draft behavior is
> settled. Full detail: the §14 changelog entry dated 2026-07-07 ("Publish
> packet builder -- Batches 1+2") and the matching banner in
> `NEXT_SESSION_START.md`.

> **`90_content_packet/` BATCH 3 COMMITTED, ALL THREE BATCHES COMPLETE
> (2026-07-07, commit `e9edb3d9`):** `tools/lena_build_publish_packet_v1.py`
> now supports optional `--queue-draft`, writing to
> `<out-dir>/<date>/<slot_id>_queue_draft.json` (default under
> `pipeline/publish_packets/lena/`, never `pipeline/queue/`). A hard guard
> (`_assert_not_inside_live_queue()`) runs before any write this run when
> `--queue-draft` is passed and rejects `--out-dir pipeline/queue` and
> `--out-dir pipeline/queue/something` -- confirmed by test. Queue-draft
> fields are hardcoded safe: `approved_for_live_publish: false`,
> `operator_review_required: true`, `metadata.queue_draft_only: true`,
> placeholder-only caption, pointer back to the Markdown packet. Still no
> `--live`/`--approve`/publish flag, still no
> `posting_manager`/`process_queue`/publisher-API/Kling-executor/
> `requests`/`urllib`/`env_loader` import anywhere in the tool. `pipeline/
> publish_packets/lena/` and `pipeline/queue/` remain untracked,
> pre-existing, untouched. **`95_publish_gate/` is now the next reasonable
> docs-only design target** -- the packet/queue-draft behavior it would gate
> is settled. Video API, the studio element, and `business_media`/sales/
> outreach remain out of scope. Full detail: the §14 changelog entry dated
> 2026-07-07 ("Publish packet builder -- Batch 3") and the matching banner
> in `NEXT_SESSION_START.md`.

> **`95_publish_gate/` DOCS-ONLY SLICE CREATED (2026-07-07, commit
> `3a4c1412`):** `pipeline/agents/lena/95_publish_gate/` now exists,
> following the standard five-file pattern. **Docs-only -- no code/tool
> exists yet.** Owns the future durable human approval decision record,
> sitting between `90_content_packet/` and live publish; does not build
> packets or queue drafts, does not QA images, does not move/copy files
> into `pipeline/queue/`, does not run `tools/process_queue.py`, does not
> call `posting_manager.py`, does not publish or auto-approve. Preserves
> the safety doctrine as hard blocks (once any code exists): placeholder
> caption, >3 hashtags, QA not `pass`, missing packet, missing expected
> queue draft, missing/false `metadata.queue_draft_only`, or unclear
> operator approval. Queue-draft fields (`approved_for_live_publish:
> false`, `operator_review_required: true`, `metadata.queue_draft_only:
> true`) stay permanently untouched -- any future approval is a *separate*
> artifact, never a mutation of the draft. **Next safe task: read-only
> scoping for a future approval-record checker/builder**, still needing
> separate explicit approval. A further Kling reliability check remains a
> separate, unrelated track. Video API, the studio element, and
> `business_media`/sales/outreach remain out of scope. Full detail: the
> §14 changelog entry dated 2026-07-07 ("95_publish_gate slice checkpoint")
> and the matching banner in `NEXT_SESSION_START.md`.

> **`95_publish_gate/` FIRST REAL TOOL, TWO BATCHES (2026-07-07, commits
> `bd4b6135` + `68bba745`):** `tools/lena_record_publish_approval_v1.py`
> now exists. **The full Lena photo chain is now: photo render -> QA pass
> -> publish packet -> queue draft -> approval record**, with the final live
> step (manual promotion into `pipeline/queue/` + `tools/process_queue.py
> --live`) staying manual, not automated. **Batch 1** (`bd4b6135`) is a
> read-only checker: validates the packet exists, the queue draft exists
> with `metadata.queue_draft_only: true`, re-validates QA `overall ==
> "pass"`, validates the approved caption (not the placeholder, <=3
> hashtags), validates `--approved-by` non-empty and `--confirm` matches
> the required exact phrase -- writes nothing. **Batch 2** (`68bba745`)
> adds `--record`/`--force`: writes a durable approval artifact to
> `<out-dir>/<date>/<slot_id>_approval.json` (default under `pipeline/
> publish_packets/lena/`, never `pipeline/queue/`), non-clobber by default,
> recording post id/date/packet path/queue-draft path/QA path+overall/
> approved caption/hashtag count/platforms/approved-by/approval statement/
> timestamp/`manual_one_off_confirmed: true`/`promotion_status:
> "not_yet_promoted"`. **Never modifies the queue draft, never writes into
> `pipeline/queue/`, never calls `tools/process_queue.py` or
> `posting_manager.py`, never publishes; no `--live`/`--publish`/
> `--approve-and-publish`/queue-promotion flag exists.** `pipeline/
> publish_packets/lena/` and `pipeline/queue/` remain untracked,
> pre-existing, untouched. A further Kling reliability check remains a
> separate, unrelated track. Video API, the studio element, and
> `business_media`/sales/outreach remain out of scope. Full detail: the
> §14 changelog entry dated 2026-07-07 ("Approval record checker/writer --
> Batches 1+2") and the matching banner in `NEXT_SESSION_START.md`.

> **ROOT CAUSE IDENTIFIED (2026-07-07) — AND SOLVED IN PRINCIPLE (2026-07-07,
> same day, later):** the wrong-outfit / identity-drift / cartoon-style
> failures are **conditioning-level, not prompt-level.** The current executor
> sends `element_list:[{element_id}]` only — it fetches APILENA's (photoreal,
> correct) reference images, verifies them, then **discards them**, and sends
> **no `model_name`/version pin**. **FIX CONFIRMED:** an approved single `n=1`
> live test with a **pure `image_list`-only payload** (`model_name:
> "kling-v3-omni"`, `image_list:[{"image":"<APILENA reference URL>"}]`, NO
> `element_list`) returned **HTTP 200 / SUCCEED** and produced a **photoreal,
> identity-matched** Lena — resolving the cartoon collapse by sending the
> actual reference URL, and bypassing the `1201` element-registry error
> entirely. **EXECUTOR PATCHED + PATCHED-PATH TEST PASSED 2026-07-07:**
> `_submit_photo()` builds the reference-by-URL payload
> (`build_reference_url_photo_payload()`, guard-enforced, element_list/
> negative_prompt absent); one approved n=1 patched-path render (slot
> `2026-07-07-02-photo`, task `903345804994285660`) **succeeded end-to-end** —
> photoreal, identity-matched, no cartoon, and earned the **first schema-v2 QA
> PASS** this session (`overall: pass`, `publish_ready: false`). Reliability is
> n=2 total (not unattended-production ready); publish still needs operator
> sign-off. What remains: a small reliability check + normal production
> steering. **Do NOT render or call Kling again without explicit approval.** Do not
> replay the web-app `kling.ai/api/omni/*` endpoints, do not automate against
> the web session, do not switch providers. HAR captures (`scratch/*.har`)
> hold session tokens — git-ignored, never commit. Full detail:
> `pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md` + the §14 entries
> dated 2026-07-07 (root cause; Variant B breakthrough; executor patched).

> **STANDARD CORRECTION (2026-07-06):** exact wardrobe obedience is not the
> production goal. It was over-weighted as an automatic production failure
> earlier this session. The corrected standard: varied outfits over time,
> sexy/high-hook/viewer-grabbing, somewhat-to-moderately revealing, platform-
> safe, realistic enough, coherent scene, close-enough identity continuity,
> no obvious AI/cartoon/anatomy failure. Priority order: (1) hook strength,
> (2) outfit variety, (3) sexy-but-platform-safe styling, (4) realism,
> (5) identity continuity, (6) scene variety, (7) caption/image coherence,
> (8) exact wardrobe obedience — diagnostic only. Full standard and hard-
> reject list: `pipeline/agents/lena/70_visual_qa/RULES.md`. This narrows,
> but does not reverse, the 4th render's classification below.

> **PARKED, not "in progress."** The Kling Omni/BodyLock thread is closed
> until an external event happens: a response to
> `pipeline/change_notes/lena_kling_omni_support_packet_2026-07-06.md`. Until
> then: no more Kling tests, no more element IDs, no more payload schemas, no
> element recreation without support/docs confirming the correct method, no
> `.env` edits, no render on this thread. Do not treat re-reading this file as
> an invitation to pick the investigation back up or propose a next diagnostic
> -- there isn't one until the external response arrives.

### Where we are now
Batches 1-7 (containment through garment-obedience lock, positive + negative) are
fully implemented and functionally validated. The Kling proof lane
(`2026-07-05-02-photo` / wc_p082) was pushed to three real renders after the Batch 7
fix closed, and all three still produced the wrong outfit -- ruled out as a pipeline
defect, classified as provider/model-level noncompliance, and paused. The
repo-knowledge/session-recovery layer and two folder-native slices
(`40_identity_continuity/`, `70_visual_qa/`) were built and accepted. The user then
directed starting **Branch 2** (provider/conditioning investigation), read-only:
no render, no code, no publish, no `.env` change. That investigation found the
current live path (`kling_apilena_api_executor.py`, endpoint `/v1/images/
generations`, no model specified, `element_list` only) diverges from a
git-committed recipe (`README_BODYLOCK_PRODUCTION_RULES_2026-06-24.md`, commit
`f5908ac6` -- currently deleted from the working tree, uncommitted) that
documented a different endpoint (`/v1/images/omni-image`), model
`kling-v3-omni`, `element_list` + `image_list` together, and a ~400-char prompt
as the approved production path, and named element-only submission and long
prompts as tested-and-rejected causes of identity drift. **Caution (see below):
a later investigation found this recipe's own real-world success is less
certain than first described here.**

The user then approved proceeding toward a diagnostic retest of that recipe, with
firm boundaries: no permanent `.env` edit, no restoring manual-URL-override
behavior as a normal path, no weakening the containment guard, no publish, no
render yet. A small, standalone, opt-in-only diagnostic script was built
(`tools/lena_bodylock_diagnostic_v1.py`) to satisfy this: it never touches `.env`,
never imports/modifies the live executor, reuses the same manual-override
hard-fail guard from `pipeline/identity/lena_identity.py`, and only accepts
diagnostic-only env vars (`CONTENT_BOT_BODYLOCK_DIAGNOSTIC`,
`CONTENT_BOT_BODYLOCK_ANCHOR_URL`) passed inline per-command, never persisted.

The user then approved exactly one real diagnostic run, anchor = the live
APILENA element's own cover image. **Result: Kling rejected the submission
before any generation task was created.** `POST /v1/images/omni-image` (AK/SK
auth) returned `HTTP 400 {"code": 1201, "message": "Element id not found:
315187972322559"}`. Zero credits spent (no `task_id` issued). This is a new,
distinct finding: the same element id works fine on `/v1/images/generations`
(web-session-scraped lookup, current live path) but is invisible to the
AK/SK-authenticated official API used by the omni-image endpoint -- suggesting
this element may only exist in Kling's web-UI element registry, not the
AK/SK-visible one. **No BodyLock-recipe image has been produced or judged.**
A follow-up no-spend investigation (below) then found no element ID has ever
been confirmed working on the omni-image endpoint anywhere in this repo's
history, and two pre-existing HAR browser captures corroborated that the
web-UI element system and the official API appear structurally separate. The
user judged this sufficient to **park the entire Kling Omni/BodyLock thread**:
a support packet was written
(`pipeline/change_notes/lena_kling_omni_support_packet_2026-07-06.md`), and no
further Kling testing, element IDs, payload schemas, or element creation are
authorized until an external response arrives. See the PARKED banner at the
top of this section for the current, authoritative statement.

With that thread parked, the user directed building the **third folder-native
slice**: `pipeline/agents/lena/60_executor/`, wrapping the live executor, the
parked diagnostic script, the daily orchestrator, and legacy-executor context.
Then the **fourth folder-native slice**: `pipeline/agents/lena/
50_prompt_builder/`, wrapping `pipeline/prompting/lena_prompt_brain.py` --
source prompt/negative-prompt construction, wardrobe/scene/framing/garment-
obedience locks, and what the executor's prompt receipt does/does not prove.
Four slices now exist: `40_identity_continuity/`, `50_prompt_builder/`,
`60_executor/`, `70_visual_qa/`. That slice's `CURRENT_STATE.md` documented
the negative-prompt budget overflow precisely (2734 chars vs. a 2499-char
cap). The user then approved a design memo for the smallest safe fix (no
code), then approved implementing it, then approved one proof render to test
it. **Implemented 2026-07-06** (`lena_prompt_brain.py`'s `NEGATIVE_PROMPT`
restructured into five tiered constants; `kling_apilena_api_executor.py`'s
negative-prompt compaction extended with five new reserved floors alongside
the pre-existing, unchanged, still-11/11 garment-obedience floor; validated
via `py_compile` + no-network dry-run only across 6 outfit classes x 2 lane
types). **Proof render run 2026-07-06 on the same previously-failed slot
(`2026-07-05-02-photo`/wc_p082, current `/v1/images/generations` path only,
exactly one image): result FAIL.** Every predicted negative floor survived
exactly as validated (garment-obedience 11/11, core 21/21, style-realism
29/29, public-safety 17/17, body-anatomy 32/37) -- but this was the **4th
consecutive wrong-outfit miss** on this exact slot (a mustard coat + scarf
outerwear substitution instead of the specified tank top + mini skirt), plus
identity drift (hair/eye color). Style/cartoon-drift **did** measurably
improve (not a full cartoon/3D-illustration failure this time, unlike the
3rd pre-repair render) -- but wardrobe fidelity did not. This is strong
further evidence the wrong-outfit failure is model/provider-level, not
prompt-content-level, since near-maximal negative-prompt protection is now
guaranteed present and it still happened.

### Last completed step
Ran the approved proof render to test the negative-prompt budget repair.
Target: `2026-07-05-02-photo`/wc_p082, the same slot with 3 prior documented
wrong-outfit/style-drift failures, on the current `/v1/images/generations`
path only (no Omni/BodyLock, no `image_list`, no alternate element).
Pre-flight: to keep this a true single-variable comparison, the positive
prompt/wardrobe/scene/environment were left byte-identical to the 3 prior
failed attempts -- only the slot's `negative_prompt` field was refreshed
(via `build_negative_prompt_for_catalog()` + `build_public_lane_negative_
prompt()` against the live `wc_p082` catalog entry directly, patched into
the real workorder JSON with a small Python script, not the full workorder-
prep pipeline, since re-running that would have re-randomized the outfit/
scene choice against the now-different catalog/scene-bank state). Verified
via dry-run before rendering: all six negative floors would survive
(garment-obedience 11/11, core 21/21, style-realism 29/29, public-safety
17/17, body-anatomy 32/37, outfit-specific 7/29), compact negative 2496/2499
chars, correct element (`315187972322559`/APILENA), no `image_list`.

Ran exactly one image: `CONTENT_BOT_KLING_TARGET_SLOT_ID=2026-07-05-02-photo
CONTENT_BOT_KLING_MAX_SLOTS=1 CONTENT_BOT_KLING_EXECUTE=1 python
pipeline/kling_apilena_api_executor.py 2026-07-05`. Task `903248497381220361`
succeeded; the receipt confirmed every pre-flight prediction exactly.
Viewed the actual generated image directly and wrote a fresh QA verdict
(`pipeline/asset_review/lena/2026-07-05/2026-07-05-02-photo_qa.json`,
explicitly superseding the stale 3rd-failure verdict, validated via
`lena_photo_qa.validate_qa_result()`): **overall FAIL.**
- Wardrobe class fidelity: **FAIL, 4th consecutive miss** -- a mustard coat
  + scarf outerwear substitution instead of the specified white tank top +
  black mini skirt, the same structural failure category (outerwear
  replacing the named top) as the two prior wrong-outfit misses, despite
  now-near-maximal negative-prompt protection confirmed present.
- Identity fidelity: FAIL -- hair drifted reddish-auburn/copper, eyes read
  lighter amber-brown, both off the canonical APILENA reference.
- Face realism: FAIL but **improved** -- not a full cartoon/3D-illustration
  failure this time (unlike the 3rd pre-repair render), though still a
  glossy/airbrushed/idealized quality inconsistent with clean photoreal
  camera realism.
- Hands, environment, caption-coherence, public-scene-continuity (for what's
  visible), outerwear-underlayer-correctness: all passed.

**Conclusion: the repair measurably improved style/cartoon-drift but did not
fix the wardrobe-substitution failure.** With negative-prompt protection now
near-maximal and the same failure category still occurring, this is strong
further evidence the wrong-outfit failure is model/provider-level, not
something more prompt engineering on this path will fix. `.env` confirmed
untouched throughout (`git status --short .env` empty before and after);
exactly one image generated; nothing published; Kling Omni/BodyLock not
touched or reopened.

Before this (same day): implemented the negative-prompt budget repair. In
`pipeline/prompting/
lena_prompt_brain.py`: replaced the flat `NEGATIVE_PROMPT` string (2734
chars, 139 terms) with five tiered constants -- `CORE_NEGATIVE_TERMS` (21),
`STYLE_REALISM_NEGATIVE_TERMS` (29), `PUBLIC_SAFETY_NEGATIVE_TERMS` (11),
`BODY_ANATOMY_NEGATIVE_TERMS` (37), `OPTIONAL_FILL_NEGATIVE_TERMS` (39) --
plus two new additive-only constants exposed purely for the executor's floor
matching (`OUTFIT_SPECIFIC_SUBSTITUTION_TERMS`, 29 terms; `PUBLIC_LANE_
SAFETY_TERMS`, 6 terms), without touching `build_public_lane_negative_
prompt()`'s own inline assembly logic at all. `NEGATIVE_PROMPT` is
reconstructed as the exact concatenation of the five tiers (2696 chars, 137
terms) -- only two confirmed exact-duplicate terms removed (`"navel
piercing"`, `"belly button jewelry"`, paraphrases of terms already present),
verified by direct set-difference audit against the original 139-term list
that nothing else was dropped or altered.

In `pipeline/kling_apilena_api_executor.py`: added an import of the five new
tier constants plus the two matching-only constants; added five new floor-
budget constants (`CORE_NEGATIVE_FLOOR_CHARS=350`, `STYLE_REALISM_FLOOR_
CHARS=550`, `PUBLIC_SAFETY_FLOOR_CHARS=450`, `OUTFIT_SPECIFIC_SUBSTITUTION_
FLOOR_CHARS=400`, `BODY_ANATOMY_FLOOR_CHARS=750`); extended
`_build_compact_negative_prompt()` with a new `_apply_negative_floor()`
helper (mirroring the existing garment-obedience floor's mechanism exactly)
applied for each of the five new tiers, strictly *after* the pre-existing
garment-obedience floor so that floor's available budget and proven 11/11
behavior are completely unchanged; extended `_build_prompt_receipt()` with
matched/survived-count/total/present/reserved-chars/chars-used/survived-
boolean fields for each new floor plus an optional-fill transparency block.
Found and fixed one bug during testing: an initial optional-fill "reserved
chars" field computed via naive cap subtraction went negative (floor caps
sum to 2880, over the 2499 total) -- fixed to compute from actual per-render
floor consumption instead, always non-negative.

Validated via `py_compile` (both files) and no-network dry-run calls against
fabricated slot dicts built from the real `lena_prompt_brain.py` functions,
across 6 outfit classes (plain top, sleeveless-top+skirt, dress, bodysuit,
shorts-set, outerwear) x 2 lane types (public, non-public) = 12 cases. Every
case's compact negative prompt measured 2488-2499 chars (always at or under
the cap). Every always-on floor (core/style-realism/public-safety/body-
anatomy) survived in all 12 cases. Garment-obedience re-confirmed 11/11 on
its real test case, unchanged. One case (`sleeveless_top_skirt`/public, the
single highest-pressure render) showed body-anatomy trimmed to 32/37 under
real multi-floor contention -- expected graceful degradation, not a failure.
No render, no Kling call, no `.env` edit, no change to positive-prompt
behavior or wardrobe/scene/framing/garment-obedience lock content.

Before this (same day): built `pipeline/agents/lena/50_prompt_builder/` --
five files
(`AGENT.md`/`RULES.md`/`INPUTS.md`/`OUTPUTS.md`/`CURRENT_STATE.md`), wrapping
`pipeline/prompting/lena_prompt_brain.py`. No code moved. Grounded in a fresh
read of the real module (2834 lines -- read the header, `NEGATIVE_PROMPT`
constant, `build_negative_prompt_for_catalog()`/`build_public_lane_negative_
prompt()`, `public_wardrobe_continuity_lock()` (the garment-obedience/
continuity lock generator), `framing_policy_for_mode()`,
`generate_prompt_package()` (the main assembly function), and
`apply_prompt_package_to_slot()`), plus a direct measurement
(`len(NEGATIVE_PROMPT)`) confirming the negative-prompt constant is exactly
2734 chars against a 2499-char cap. Explicitly documents the boundary with
`60_executor/`: this folder owns source-prompt *construction*, not
*compaction* (which physically lives in `kling_apilena_api_executor.py`).
Covers, per explicit instruction: what the Prompt Builder owns; which
files/functions are authoritative; source vs. compact prompts; how wardrobe/
scene/framing/garment-obedience locks are created; what prompt receipt fields
prove and don't prove; the known negative-prompt overflow (documented, not
fixed, per explicit instruction); why prompt correctness does not equal image
correctness (with the real 11/11-terms-present-yet-wrong-outfit evidence
restated); and what to inspect before changing prompt logic.

Before this (same day): built `pipeline/agents/lena/60_executor/` -- five
files, wrapping `pipeline/kling_apilena_api_executor.py` (live path),
`tools/lena_bodylock_diagnostic_v1.py` (parked path),
`pipeline/lena_production_job.py` (orchestrator), and
`tools/LEGACY_PROVIDER_SURFACES.md` (legacy context). Does not reopen or
advance the parked Kling Omni/BodyLock thread -- documents that it's parked,
does not un-park it.

Before that (same day): a read-only, no-spend investigation into whether any
element ID in this repo's history has ever been confirmed to work on the
AK/SK-authenticated omni-image endpoint. Searched git history (including
deleted/uncommitted files, via `git show`/pickaxe across all commits) and all
11 `.env.bak_*` snapshots on disk (2026-06-17 through 2026-06-25). Found:
- A second, later element ID (`u_313006264506046`, different payload schema --
  `fromElementId`/`elementVersion`, not `element_list`) committed one day after
  BodyLock (`25055603`/`7f4fec51`, 2026-06-25/26). That later tooling's own
  `BLOCKED_TERMS`/`BLOCKED_IDS` explicitly reject BodyLock's own approach
  (`element_list`, `Goodtest1`) and four other element IDs. No evidence this
  ID was ever run live anywhere in the repo -- its results directory was never
  created and was gitignored the same day it was introduced.
- "Goodtest1" is only ever a name, never a stored URL, anywhere in the repo.
- `KLING_LENA_ELEMENT_ASSET_ID` (BodyLock's required env var) is set to the
  known-retired ID `313524913093322` in the only two `.env` backups where it
  appears (both 2026-06-22), and is **absent** from the 2026-06-25 backup
  (same day as the BodyLock hardening commit) and every other snapshot,
  including today's `.env`. BodyLock's live runner would have aborted, not
  succeeded, under that configuration.
- The one previously-cited positive signal (2026-06-24 publish-dispatch
  record) uses a filename matching the *normal* daily-workorder naming
  convention, not BodyLock's own live-runner output naming -- weakening
  confidence that it proves a standalone AK/SK + omni-image success.
- **No element ID has been confirmed, with real evidence in this repo, to
  work on the AK/SK-authenticated omni-image endpoint** -- not APILENA, not
  BodyLock's own (never captured), not `u_313006264506046` (never run).
- Two pre-existing `.har` browser captures already in the repo corroborated
  this: neither ever contacts `api.klingai.com`, only `kling.ai`.

The user judged this sufficient and directed a clean stop: a support packet
was written (`pipeline/change_notes/lena_kling_omni_support_packet_2026-07-
06.md`), and the Kling Omni/BodyLock thread is now **parked** -- no further
Kling testing, element IDs, payload schemas, or element creation until an
external response arrives. `.env` untouched throughout; no code changed
beyond the standalone diagnostic script (built earlier); nothing called or
published.

### Files changed this session (see §14 for full per-batch detail)
- `pipeline/kling_apilena_api_executor.py` -- Batches 1, 2, 3, 5a-5e, 6, 7, 7b, 7c
  (containment guard, identity delegation, prompt/negative reconciliation, four
  reserved compaction floors, negative-prompt reserved floor).
- `pipeline/identity/lena_identity.py` (new, Batch 2), `pipeline/identity/__init__.py` (new).
- `pipeline/qa/lena_photo_qa.py` (new, Batch 4), `pipeline/qa/__init__.py` (new).
- `tools/lena_review_proof_render_v1.py` (new, Batch 4).
- `tools/lena_preflight.py` -- Batches 1, 2 (payload-truth check, identity delegation).
- `pipeline/lena_production_job.py` -- Batch 2 (identity delegation).
- `pipeline/prompting/lena_prompt_brain.py` -- Batch 7 (garment-obedience lock +
  anti-substitution negative terms, silhouette-class-scoped).
- `tools/LEGACY_PROVIDER_SURFACES.md`, `pipeline/config/lena_live_path_manifest_v1.json`
  -- Batch 1 (corrected stale executor references).
- `pipeline/change_notes/lena_agentic_pivot_changelog.md` (new, running technical log).
- `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` (this file, new).
- `pipeline/agents/lena/40_identity_continuity/{AGENT,RULES,INPUTS,OUTPUTS,CURRENT_STATE}.md` (new).
- QA artifacts written/replaced under `pipeline/asset_review/lena/<date>/` for each
  proof render (not source code -- generated review records).
- `pipeline/change_notes/NEXT_SESSION_START.md` (rewritten this session to point at
  the new knowledge layer first).
- `pipeline/knowledge/content_bot/REPO_MAP.md`,
  `pipeline/knowledge/content_bot/LIVE_PATHS.md`,
  `pipeline/knowledge/content_bot/AUTHORITATIVE_SURFACES.md`,
  `pipeline/knowledge/content_bot/QUARANTINED_SURFACES.md`,
  `pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md` (all new; the
  repo-knowledge/session-recovery layer).
- `pipeline/agents/lena/70_visual_qa/{AGENT,RULES,INPUTS,OUTPUTS,CURRENT_STATE}.md`
  (new; second folder-native slice, wraps the QA schema/scaffold module, the
  read-only review-bundle helper, and the QA artifact directory).
- No files changed by the Branch 2 read-only investigation itself. Reference
  images were downloaded to the session scratchpad directory only (outside the
  repo), not saved into the repo.
- `tools/lena_bodylock_diagnostic_v1.py` (new) -- the opt-in diagnostic runner.
  No other file modified to build it; does not touch `kling_apilena_api_executor.py`
  or `.env`.
- `pipeline/kling_debug/bodylock_diagnostic/bodylock_diagnostic_20260706T200037Z/`
  (new; generated diagnostic artifacts, not source code) -- `submit_payload.json`
  and `submit_response.json` from the one approved `--execute` run. No
  `poll_response.json` or `result_manifest.json` -- the flow never reached
  polling because the submission itself was rejected.
- `pipeline/change_notes/lena_kling_omni_support_packet_2026-07-06.md` (new;
  support-communication document, not a continuity file).
- `pipeline/agents/lena/60_executor/{AGENT,RULES,INPUTS,OUTPUTS,CURRENT_STATE}.md`
  (new; third folder-native slice, wraps the live executor, the parked
  diagnostic script, the daily orchestrator, and legacy-executor context).
- `pipeline/agents/lena/50_prompt_builder/{AGENT,RULES,INPUTS,OUTPUTS,CURRENT_STATE}.md`
  (new; fourth folder-native slice, wraps `pipeline/prompting/
  lena_prompt_brain.py` -- source prompt/negative-prompt construction).
- `pipeline/prompting/lena_prompt_brain.py` -- negative-prompt budget repair:
  `NEGATIVE_PROMPT` restructured into five tiered constants plus two
  matching-only constants (`OUTFIT_SPECIFIC_SUBSTITUTION_TERMS`,
  `PUBLIC_LANE_SAFETY_TERMS`); 2 confirmed-duplicate terms removed
  (2734 -> 2696 chars). No other content changed.
- `pipeline/kling_apilena_api_executor.py` -- negative-prompt budget repair:
  new tier imports, five new floor-budget constants, `_apply_negative_floor()`
  helper, five new floor applications in `_build_compact_negative_prompt()`
  (after the unchanged, pre-existing garment-obedience floor), and ~40 new
  receipt fields in `_build_prompt_receipt()`.
- `pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md` (updated, not
  new) -- negative-prompt budget section rewritten from "documented, not
  fixed" to "repaired," with exact before/after numbers and validation
  results.
- `pipeline/kling_workorders/2026-07-05/daily_workorders.json` -- the
  `2026-07-05-02-photo` slot's `negative_prompt` field (and its duplicate in
  `metadata.negative_prompt`) refreshed to the repaired tiered content
  (4189 -> 4151 chars); `image_prompt` and every other field left
  byte-identical.
- `pipeline/kling_debug/apilena_api/2026-07-05/2026-07-05-02-photo/` --
  overwritten with this render's real artifacts (`submit_payload.json`,
  `submit_response.json`, `poll_response.json`, `prompt_receipt.json`,
  `result_manifest.json`, `live_apilena_lookup_response.json`), superseding
  the 3rd-failure artifacts from earlier this session.
- `pipeline/kling_library/lena/2026-07-05/2026-07-05-02-photo_seed.png` --
  overwritten with this render's actual generated image.
- `pipeline/asset_review/lena/2026-07-05/2026-07-05-02-photo_qa.json` --
  fresh QA verdict written, explicitly superseding the stale 3rd-failure
  verdict, per the stale-QA-file lesson.

### Current blocker
No code-level blocker in the pipeline path (still validated). **The Kling
Omni/BodyLock diagnostic thread is parked**, by explicit user decision,
pending Kling/APILENA support clarification -- not an open blocker to solve,
a closed thread waiting on an external event. A support packet was written:
`pipeline/change_notes/lena_kling_omni_support_packet_2026-07-06.md` -- ready
to send, not yet sent by us (sending it is the user's action, not something we
do). With that thread cleanly parked, the third (`60_executor/`) and fourth
(`50_prompt_builder/`) folder-native slices were built, the negative-prompt
budget overflow that slice documented was repaired in code, and a proof
render confirmed the repair improves style/cartoon-drift but does not fix
wardrobe-substitution -- the 4th consecutive wrong-outfit failure on this
slot. **User has now accepted the final classification (2026-07-06):** the
repair is retained (real style-realism improvement); wardrobe obedience did
not improve; this specific slot's prompt-content iteration is stopped, not
paused; the current `/v1/images/generations` path is usable only as quality-
limited/proof-limited, not trusted for wardrobe-exact production; the next
meaningful fix, if pursued, is a provider/conditioning strategy change (the
parked Kling Omni/BodyLock thread), not more prompt tweaking. No code-level
blocker remains on this thread -- it's closed, not open. Separately,
whether to revisit the "element_list-only"
doctrine now encoded in `pipeline/identity/lena_identity.py` (written this
session, based on a same-day diagnosis that may have conflated the banned
manual-URL-override mechanism with `image_list` as a payload field in general --
see changelog for full reasoning) remains flagged for the user's review, not
decided, and not touched.

### Current proof status
- **Pipeline/code path: validated.** Identity resolution (element `315187972322559`,
  "APILENA"), `element_list`-only submission, and scene/continuity/framing/
  garment-obedience compaction survival (positive and negative) all confirmed
  correct by direct artifact inspection across every render this session.
- **Image generation on the tested proof slot: failing on wardrobe, better
  explained, and now settled as a closed classification.** Four consecutive
  renders on `2026-07-05-02-photo` (wc_p082) all produced the wrong outfit
  (renders 1-2: sweater+scarf; render 3: turtleneck+scarf plus cartoon-style
  drift; render 4, post negative-prompt repair: mustard coat+scarf, style-
  drift improved). The live path uses a different endpoint/model/payload
  shape than the one documented recipe this repo has real evidence of
  working (BodyLock, 2026-06-24) -- that thread is separately parked. Fully
  up to date: `pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md`
  (rewritten 2026-07-06 with the final classification below).
- **The negative-prompt budget overflow is repaired (2026-07-06), proof-
  render-tested, and RETAINED as a final, accepted outcome.** Base
  `NEGATIVE_PROMPT` restructured into five tiered constants (2734 -> 2696
  chars); the executor's compaction applies 6 reserved floors (5 new + the
  pre-existing garment-obedience one, unchanged). A real render on
  `2026-07-05-02-photo`/wc_p082 confirmed every floor survived exactly as
  predicted (garment-obedience 11/11, core 21/21, style-realism 29/29,
  public-safety 17/17, body-anatomy 32/37). **User-accepted final
  classification:** style/cartoon-drift protection improved (real,
  measured); wardrobe obedience did not improve (4th consecutive miss);
  the repair is kept regardless; further prompt-content iteration on this
  exact wardrobe failure is stopped, not paused; the current
  `/v1/images/generations` path is usable only as quality-limited/proof-
  limited, not trusted for wardrobe-exact production; the next meaningful
  fix, if pursued, is a provider/conditioning strategy change, not more
  prompt tweaking. Full detail:
  `pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md`,
  `pipeline/asset_review/lena/2026-07-05/2026-07-05-02-photo_qa.json`, and
  the changelog's repair + proof-render entries.
- **Production standard corrected, same day, narrowing the above:** "wardrobe
  obedience did not improve" and "not trusted for wardrobe-exact production"
  were written under a standard that treated exact catalog match as the
  production bar. That standard was wrong. Under the corrected standard
  (§0 banner above), the 4th render's real concern is that the substituted
  coat+scarf reads as too covered/low-hook, not that it missed the catalog
  string -- and whether this path is production-viable under the *corrected*
  standard has not been formally assessed. See `pipeline/agents/lena/
  70_visual_qa/RULES.md` for the full corrected standard.

### Next approved step
**The wardrobe-obedience/negative-prompt thread is settled and closed
(user-accepted final classification, 2026-07-06)** -- see the "Current proof
status" bullet above for the 5-point classification. Nothing further is
approved on that specific thread; it is not an open question waiting on a
decision anymore. Two things remain genuinely open:
- **Kling Omni/BodyLock (parked):** waiting on a response to the support
  packet. Nothing on this specific thread proceeds until then. When a
  response arrives, it will determine which of the previously-presented
  options apply -- (1) recreate as an official-API-visible element, (2) keep
  `/v1/images/generations` and accept its known limitations, (3) switch
  provider/path, (4) whatever Kling support actually says. Per the accepted
  classification, this thread (not more prompt work) is the more plausible
  route to fixing wardrobe fidelity, if and when it reopens.
- **What to do meanwhile:** not yet decided. New candidate from the standard
  correction: update `pipeline/qa/lena_photo_qa.py`'s checklist schema to
  natively score the corrected standard (hook strength, outfit variety,
  sexy-but-safe styling, etc.) instead of gating on exact wardrobe match --
  flagged in `70_visual_qa/RULES.md`, not decided, requires explicit approval
  (a code change). No specific next folder-native slice is recommended
  (four exist now: `40_identity_continuity/`, `50_prompt_builder/`,
  `60_executor/`, `70_visual_qa/`). **Read this file and the changelog fresh
  at the start of the next session and ask before proceeding.**

### What must NOT be done next
- **Do not run any further Kling Omni/BodyLock diagnostic of any kind** --
  no `tools/lena_bodylock_diagnostic_v1.py --execute` retry, no new element ID,
  no new payload schema (`fromElementId`, `arguments.elementVersion`, or
  anything else), no new endpoint or auth method. This entire avenue is
  explicitly stopped pending the support packet's response, not paused for a
  single retry.
- Do not attempt to create a new Kling element via any API call on your own
  judgment -- option 1 (recreate as official-API-visible) is presented, not
  approved, and would be a real, spend-adjacent account action.
- Do not send the support packet on the user's behalf, and do not treat its
  creation as authorization to act on hypothetical answers before they
  actually arrive.
- Do not add a `.env`-backed default, config file, or any persistence mechanism
  for `CONTENT_BOT_BODYLOCK_ANCHOR_URL` -- it must stay a per-command, inline-only
  env var per the user's explicit instruction not to re-add image URL vars to
  `.env`.
- Do not modify `pipeline/kling_apilena_api_executor.py` or its containment guards
  as part of this diagnostic work -- the diagnostic script is deliberately
  standalone precisely so the live executor never needs to change.
- Do not patch `kling_apilena_api_executor.py` or `lena_prompt_brain.py` again on the
  basis of the wrong-outfit renders -- that's been ruled out as a code-fixable
  problem three times over. (Does not apply to the already-approved,
  already-implemented negative-prompt budget repair, which is unrelated to
  that theory.)
- Do not unilaterally reverse or edit the "element_list-only" doctrine in
  `pipeline/identity/lena_identity.py` based on the BodyLock finding -- flagged for
  the user's review, not decided.
- **User-accepted final classification (2026-07-06): do not rerender
  `2026-07-05-02-photo`.** Not "needs a new reason" -- explicitly closed.
  Four consecutive same-slot wardrobe failures, the last one under near-
  maximal negative-prompt protection, is the accepted, final evidence.
- **Do not do another prompt/negative-prompt patch aimed at fixing wardrobe
  obedience on this exact failure.** User-instructed, explicit: "stop
  further prompt/content iteration on this exact slot." This is a settled
  conclusion, not a hedge -- the theory has failed on this exact symptom
  four times in a row, the last one with the strongest prompt-side
  protection this repo has ever assembled for it.
- Do not re-patch or re-tune the six negative-prompt reserved floors (budgets,
  term-set membership) without a concrete new finding unrelated to wardrobe
  obedience -- the repair itself is retained and accepted as successful for
  style-realism; the current numbers were validated against 12
  representative cases plus one real render.
- The current `/v1/images/generations` path is accepted as **quality-
  limited / proof-limited for the exact-wardrobe-match diagnostic** -- do
  not represent it as *proven* production-viable under the corrected
  standard either, since that hasn't been formally assessed yet.
- **Do not judge any future render's production-worthiness against exact
  catalog-wardrobe match.** Apply the corrected standard from the §0 banner
  (hook strength, outfit variety, sexy-but-safe styling, realism, identity
  continuity, scene variety, caption coherence, in that priority order) --
  see `70_visual_qa/RULES.md` for the full standard and hard-reject list.
- Do not build any further folder-native slice without explicit approval --
  four exist now (`40_identity_continuity/`, `50_prompt_builder/`,
  `60_executor/`, `70_visual_qa/`); do not build out the remaining ones
  without approval, one at a time.
- Do not add a force-overwrite flag to `tools/lena_review_proof_render_v1.py` or
  otherwise change how stale QA verdicts are replaced without approval -- flagged
  as "not yet decided" in `70_visual_qa/RULES.md` and `OUTPUTS.md`, not authorized
  to build.
- Do not touch `.env`. Do not publish. Do not skip the session-start read-first
  protocol (§11.3 / continuity rules below).

### Is any render/code/publish action paused?
**Yes.** The Kling Omni/BodyLock diagnostic path is paused pending Kling/
APILENA support clarification (support packet prepared, not yet answered). Any
further diagnostic run, render, or element-creation action on that thread is
blocked until then. The current `/v1/images/generations` path remains usable
for its existing purpose and is not affected by this pause -- it's simply the
only currently working Kling path, quality limitations and all. **The
negative-prompt budget repair is implemented, validated, and proof-render-
tested** -- one approved render ran on `2026-07-05-02-photo`, result FAIL on
wardrobe/identity, improved on style/cartoon-drift. No further render on
this or any slot is authorized without a new, separate, specific reason. No
publishing has occurred or is authorized at any point in this project's
history so far.

> **Frame-logic + expression/gaze layers committed; reliability render found a
> deeper compaction-budget problem; a redesign fix is implemented but
> uncommitted (2026-07-07/08):** `pipeline/prompting/lena_prompt_brain.py` now
> has two new committed layers, each with its own executor compaction floor --
> `feat: add Lena frame logic prompt layer` (`b41495e6`) and `feat: add Lena
> expression gaze rotation` (`93abc27c`). A reliability render on the repaired
> `2026-07-05-01-photo` slot (task `903633841376596038`, one real Kling credit
> spend, attempt 1's failed artifacts archived first) came back QA **fail**, but
> confirmed both new layers work exactly as designed (alcohol non-focal,
> frame-logic objects reflected, expression natural) -- the sole failure was
> `body_shape_continuity`, root-caused to three separate, still-unfixed issues
> (negative-prompt omitted from the reference-by-URL payload; the actual
> APILENA reference image sent is likely a face/bust-oriented square crop, not
> a full-body shot; the executor never reads `reference_mode`/
> `reference_priority` at all) plus a **pre-existing, previously-undiscovered
> compaction-budget saturation**: identity/eye-color content has never had a
> reserved floor and was already silently failing in ~21% of sampled slots
> before this investigation even started. A redesign (new core identity/
> body-shape contract floor using four existing source sentences + three
> trimmed existing floors, confined entirely to
> `pipeline/kling_apilena_api_executor.py`) is implemented and validated
> (200/200 on all 13 tracked markers, real function, real 200-slot test) but
> **not committed** -- awaiting Nicolas's review. Attempt 2's render artifacts
> are not yet archived. No attempt 3 approved. Full detail: the top banner of
> `NEXT_SESSION_START.md` and the matching changelog entry dated 2026-07-07/08.

---

## 1. Executive Decision

Lena is pivoting away from a prompt-heavy, over-bundled workflow and toward a **filesystem-native agent architecture**.

This means:

- **The folder is the agent.**
- **Markdown files are the instructions, contracts, memory, and rules.**
- **The runtime is the model reading the correct folder and doing the job.**
- **Specialization comes from structure, not from a giant agent platform.**

This is not a request for a bloated multi-agent framework.
This is a request for a clean, auditable, horizontally scalable operating method where different Claude instances can become different agents by reading different directories.

---

## 2. Why This Pivot Is Happening

The previous Lena workflow hit an architecture ceiling.

Problems observed:

- too many responsibilities were packed into prompt logic
- identity, continuity, prompt building, QA, repair, and packaging were blurred together
- stale reference paths could stay reachable even when a new winner element existed
- real executor behavior drifted away from the written live-path docs
- preflight and metadata could look compliant while real payload behavior was not
- fixes often became large, fragile patches in overloaded files instead of clean, owned repairs

The problem is not simply "write better prompts."
The problem is **ownership, structure, and trustworthy contracts**.

---

## 3. Architectural Doctrine

### 3.1 Core doctrine

Use **folder structure as the operating system** for agents.

Each agent role should be understandable from its directory alone:

- who it is
- what it does
- what it reads
- what it writes
- what it must never do
- what requires human approval
- what must hard-fail

### 3.2 Design philosophy

Prefer:

- explicit files over hidden state
- markdown contracts over vague runtime behavior
- append-only artifacts over silent mutation
- readable English over clever abstractions
- narrow stage outputs over giant in-memory chains
- reusable folder patterns over custom agent machinery

### 3.3 What this is not

This is **not**:

- a giant framework project
- a product-style "agent platform" rebuild
- hidden orchestration for its own sake
- a replacement of good existing code just because it is old

---

## 4. Non-Negotiable Lena Photo Contract

The Lena photo lane must obey all of the following:

1. **Current approved Lena photo identity comes from one authoritative source only.**
2. **Stale or deprecated Lena refs must hard-fail, not silently fall back.**
3. **Normal Lena photo generation must not use manual image URL override paths.**
4. **The live approved photo identity must resolve from the active Lena photo element path.**
5. **Studio / LenaStudio identities must not leak into normal photo posts.**
6. **Wardrobe continuity and public-scene clothing logic must survive prompt building and compaction.**
7. **Source negative-prompt transport must be truthful and auditable.**
8. **Preflight must verify execution truth, not just self-reported metadata.**
9. **Human approval remains required before publish.**
10. **No proof render should be declared successful from metadata alone.**

---

## 5. Current Known State at Time of Pivot

*Historical snapshot from when this file was created. For current state, see §0 at the top of this file.*

### 5.1 Containment / hardening already completed

The following work is already in place and should be treated as current state unless later superseded:

- containment work was done to stop the stale manual image-reference override path from silently winning
- the active path now has a centralized Lena photo identity owner
- the real executor path was reconciled to use the stronger workorder-built prompt rather than a weaker parallel prompt builder
- prompt receipts now record prompt/negative-prompt truth more honestly
- structured QA scaffolding exists for proof review
- proof-review helper tooling exists

### 5.2 Important current caution

A controlled proof render has not yet been accepted as final proof of the new path.
The system is healthier, but this pivot is **not finished** until the first reconciled proof render is reviewed against the actual image.

### 5.3 Manual override rule

Manual Lena image URL override env paths are not part of the normal live photo lane. They are a debug-only footgun and must not silently re-enter production.

---

## 6. Filesystem-Native Agent Layout (Target)

Below is the target folder-first operating model. Names can be adjusted slightly to fit repo conventions, but the structure should remain simple and explicit.

```text
pipeline/agents/lena/
  00_master/
    AGENT.md
    MASTER_PIVOT.md
    CHANGELOG.md
    CURRENT_STATE.md

  10_strategy/
    AGENT.md
    INPUTS.md
    OUTPUTS.md
    RULES.md
    state/
    inbox/
    outbox/

  20_life_context/
    AGENT.md
    INPUTS.md
    OUTPUTS.md
    RULES.md
    state/
    inbox/
    outbox/

  30_creative_direction/
    AGENT.md
    INPUTS.md
    OUTPUTS.md
    RULES.md
    state/
    inbox/
    outbox/

  40_identity_continuity/
    AGENT.md
    INPUTS.md
    OUTPUTS.md
    RULES.md
    state/
    inbox/
    outbox/

  50_prompt_builder/
    AGENT.md
    INPUTS.md
    OUTPUTS.md
    RULES.md
    state/
    inbox/
    outbox/

  60_executor/
    AGENT.md
    INPUTS.md
    OUTPUTS.md
    RULES.md
    state/
    inbox/
    outbox/

  70_visual_qa/
    AGENT.md
    INPUTS.md
    OUTPUTS.md
    RULES.md
    state/
    inbox/
    outbox/

  80_repair/
    AGENT.md
    INPUTS.md
    OUTPUTS.md
    RULES.md
    state/
    inbox/
    outbox/

  90_content_packet/
    AGENT.md
    INPUTS.md
    OUTPUTS.md
    RULES.md
    state/
    inbox/
    outbox/

  95_publish_gate/
    AGENT.md
    INPUTS.md
    OUTPUTS.md
    RULES.md
    state/
    inbox/
    outbox/
```

---

## 7. Folder Role Definitions

### 7.1 `00_master/`

Purpose: Top-level human-readable truth for the pivot and current operating posture.
Required markdown:

- `AGENT.md`
- `MASTER_PIVOT.md`
- `CHANGELOG.md`
- `CURRENT_STATE.md`

Reads: approved decisions, batch updates, change notes
Writes: master state summaries, approved change log
Human approval: all doctrine changes
Hard-fail: conflicting sources of truth

### 7.2 `10_strategy/`

Purpose: Decide what Lena should try to achieve next.

Writes: `content_brief.json`
Reads: metrics memory, campaign state, current business goals
Must not do: write prompts, choose final identity, publish anything
Human approval: strategy shifts, niche shifts, campaign pivots
Hard-fail: if strategy output tries to act like a final prompt

### 7.3 `20_life_context/`

Purpose: Make Lena's daily world coherent.

Writes: `life_context.json`
Reads: `content_brief.json`, world-state/history, lane constraints
Must not do: final prompt writing or publish decisions
Human approval: major canon changes
Hard-fail: impossible or incoherent scene/context combinations

### 7.4 `30_creative_direction/`

Purpose: Turn strategy + life context into visual intent.

Writes: `creative_brief.json`
Reads: `content_brief.json`, `life_context.json`, wardrobe catalogs, lane rules
Must not do: resolve Lena identity source or submit payloads
Human approval: major aesthetic doctrine changes
Hard-fail: if wardrobe/action/environment contradict scene logic

### 7.5 `40_identity_continuity/`

Purpose: Own Lena identity truth and continuity rules.

Writes: `identity_lock.json`
Reads: current approved identity source, forbidden/deprecated refs, contract rules
Must not do: invent fallback refs
Human approval: changing the approved live Lena element or canonical visual identity
Hard-fail: stale/manual/debug reference path enters the normal photo lane

### 7.6 `50_prompt_builder/`

Purpose: Build the provider-facing prompt package from approved upstream artifacts.

Writes: `prompt_package.json`
Reads: `creative_brief.json`, `identity_lock.json`, catalog logic, negative-prompt source
Must not do: strategy, publishing, hidden fallback simplification
Human approval: major prompt doctrine changes
Hard-fail: if key continuity clauses are lost or source prompt is missing

### 7.7 `60_executor/`

Purpose: Submit the approved payload through the real live path.

Writes: `submit_payload.json`, `result_manifest.json`, `prompt_receipt.json`
Reads: `prompt_package.json`, executor contract
Must not do: weaken prompt logic on the fly, override identity truth, silently use debug refs
Human approval: none for dry-run, explicit approval for paid/live proof runs
Hard-fail: contract violation, manual override path, forbidden identity source

### 7.8 `70_visual_qa/`

Purpose: Judge the actual generated output using a structured review.

Writes: `qa_result.json`
Reads: image artifact, `submit_payload.json`, `prompt_receipt.json`, slot metadata
Must not do: rewrite prompts or silently auto-pass
Human approval: pass/fail on proof images
Hard-fail: false-green QA, or pass verdict while checklist contains failures

### 7.9 `80_repair/`

Purpose: Convert QA failures into minimal, scoped fixes.

Writes: `repair_patch.json` or equivalent scoped repair artifact
Reads: `qa_result.json`, relevant catalog/contract/module
Must not do: broad rewrites for narrow failures
Human approval: any code change
Hard-fail: if repair scope expands beyond the smallest responsible layer without justification

### 7.10 `90_content_packet/`

Purpose: Build the publish-ready packet from validated assets.

Writes: `content_packet.json`
Reads: approved proof asset, caption draft, CTA, reply angles, metrics hypothesis
Must not do: invent asset quality that QA did not approve
Human approval: packet approval before publish
Hard-fail: missing approved asset or missing required packet fields

### 7.11 `95_publish_gate/`

Purpose: Final pre-publish safety and readiness gate.

Writes: `publish_decision.json`
Reads: `content_packet.json`, publish rules, policy rules, approval state
Must not do: publish without explicit approval
Human approval: required
Hard-fail: unsafe content, missing approval, contract mismatch, banned caption behavior

---

## 8. Reuse / Split / Quarantine Guidance

### 8.1 Reuse as-is or near-as-is

These kinds of components are worth preserving if they are already behaving well:

- current centralized Lena identity owner
- current preflight truth-checking direction
- current prompt receipt direction
- current proof-review helper / QA scaffold direction
- publish gate logic that is already narrowly scoped
- content packet builder pieces that are already well-bounded

### 8.2 Files that should be split, not endlessly enlarged

Overloaded logic should be broken across folder-owned responsibilities rather than continually patched in place.
Priority split targets include:

- giant prompt-brain files that currently mix visual doctrine, wardrobe logic, continuity logic, negatives, and other responsibilities
- content-packet builders that currently combine scene selection, creative logic, and packet assembly
- any file that is acting as strategy + creative direction + identity + executor glue all at once

### 8.3 Files to quarantine or treat as non-authoritative

Legacy, dead, or conflicting files should be clearly marked as such instead of left ambiguous.
Examples of what should be quarantined when applicable:

- doc-only executors with no callers
- abandoned or absent executor paths still named in stale docs
- dead legacy generators that are generic and not Lena-specific
- duplicate identity-resolution implementations after centralization

---

## 9. Minimal Migration Path

**Phase 0 — Already underway**

- contain live-path footguns
- centralize identity truth
- reconcile executor prompt path
- add proof-review and QA scaffolding

**Phase 1 — Immediate next real checkpoint**

- remove or disable stale manual reference override paths outside normal production use
- run exactly one controlled proof render through the reconciled path
- review the actual image using structured QA
- isolate the smallest responsible repair if the proof fails

**Phase 2 — Folder-firstization**

Without rewriting the whole system, begin expressing the system through agent folders and explicit artifacts:

- strategy folder writes `content_brief.json`
- life-context folder writes `life_context.json`
- creative-direction folder writes `creative_brief.json`
- identity folder writes `identity_lock.json`
- prompt-builder folder writes `prompt_package.json`
- executor folder writes receipts/manifests
- QA folder writes `qa_result.json`

**Phase 3 — Multi-instance horizontal scaling**

Once folder contracts are stable:

- different Claude instances can operate from different folders
- one instance can do QA while another does strategy
- a future Lena-like node can be created by duplicating folder structure and changing markdown/state
- scaling comes from contract discipline, not extra runtime machinery

---

## 10. Operating Rules for Claude Going Forward

Claude should follow this operating posture:

1. Read the relevant folder before acting.
2. Treat markdown contracts as real operating instructions.
3. Prefer the smallest correct change.
4. Do not build platform-style complexity unless explicitly required.
5. Do not invent hidden fallback paths.
6. Do not silently rely on stale docs over real call-path inspection.
7. When a failure happens, identify the smallest responsible layer.
8. Append updates to living documents rather than scattering truth across ad hoc notes.
9. Keep folder contracts readable by humans.
10. Use explicit artifacts and receipts so work is inspectable after the fact.

---

## 11. Updating This Master File

### 11.1 Update rules

This file must be updated when any of the following happen:

- a new batch is approved or completed
- an operating contract changes
- a folder role is added, split, or removed
- a new source of truth is established
- a legacy/conflicting path is quarantined or retired
- a proof render changes confidence in the live path

### 11.2 Update style

- append dated updates under the changelog section or linked changelog file
- update current-state summaries carefully
- do not casually rewrite doctrine sections
- if doctrine changes, state why and who approved it

### 11.3 Hard rule: update-before-close (established 2026-07-06)

No meaningful project step is complete until this file is updated. Not optional --
this is part of the work itself, not a follow-up task.

For every meaningful step, both of the following are required:

1. update the **§0 Current State** summary at the top of this file
2. append a dated session-log entry under §14 describing what changed

A "meaningful step" includes: any approved code batch, any proof render, any QA
verdict, any diagnosis that changes confidence or direction, any source-of-truth
discovery, any live-path correction, any quarantine/retirement decision, any blocker
discovery, any change to the next approved step.

Required behavior:

- before starting work in a new session, read this file first
- after completing a meaningful step, update this file before reporting completion
- when reporting back, explicitly say whether this file was updated
- if this file was not updated, the step is not considered closed

§0 must always answer: where we are now, what was just finished, what is blocked, and
what the next approved step is. This file is the continuity layer between sessions --
it must not drift behind the real project state.

---

## 12. Suggested Companion Files

This master file should eventually live beside:

- `CURRENT_STATE.md`
- `CHANGELOG.md`
- `ACTIVE_CONTRACTS.md`
- `QUARANTINED_SURFACES.md`
- `FIRST_IMPLEMENTATION_SLICE.md`

These can be added incrementally. Do not block the pivot on building every file at once.

---

## 13. Next Approved Step

The next meaningful operational checkpoint is:
one controlled proof render through the reconciled live path, followed by structured QA against the actual image.

No broader filesystem-native migration should outrun proof that the repaired photo path actually behaves correctly.

---

## 14. Changelog Seed

**2026-07-06 — Pivot master created**

- created living master document for Lena filesystem-native agent pivot
- locked doctrine around folder-native agents rather than framework-heavy agent machinery
- documented folder-based target architecture
- documented migration path from current state
- declared this file a living source of truth for the pivot

**2026-07-06 — First controlled proof render: FAIL, root cause isolated**

- Ran exactly one controlled proof render through the reconciled live path
  (`2026-07-06-03-photo`, wc_p082 two-piece tank+skirt, the strongest available
  continuity-test slot that day) after confirming the manual override env vars were
  absent. Full detail in `pipeline/change_notes/lena_agentic_pivot_changelog.md`
  (Batch 4b).
- Made one narrow, isolated addition to support this: a
  `CONTENT_BOT_KLING_TARGET_SLOT_ID` filter in `kling_apilena_api_executor.py`'s
  `run_executor()` loop. Does not touch prompt logic, identity logic, executor
  contract, or publishing.
- **Structured QA verdict: FAIL.** Reviewed against the actual rendered image, not
  metadata. Root cause isolated to Batch 3's compaction step, which had no
  scene/environment keyword-priority category -- Scene/Environment/Lighting language
  present in the source prompt was dropped under budget pressure, producing a
  plain-background bust crop instead of the specified coffee-shop scene, which in
  turn made most of the wardrobe and body-shape checklist items unverifiable.
- What the render did confirm: identity resolution correctly used the live approved
  element (no manual override reachable), `element_list`-only payload held, and the
  specific 07-03 bra-top-drift failure class was not reproduced in what was visible.
- Per §5.2/§13: this pivot's Phase 1 checkpoint is **not yet met**. The folder-native
  migration (§9 Phase 2) remains paused. Per doctrine, the fix belongs in the same
  narrow function that caused it (add a scene/environment category to
  `_SAFETY_KEYWORD_PRIORITY`), not a broader rewrite.

**2026-07-06 — Batches 5a-5e: two reserved compaction floors, then a re-proof render (still FAIL, meaningfully improved)**

- Fixed the isolated root cause above via a small series of narrow, individually
  validated repairs to the same compaction function
  (`pipeline/kling_apilena_api_executor.py::_build_compact_prompt`), each caught and
  corrected by functional testing before being reported as done:
  a priority reorder alone was insufficient; a 600-char Scene:+Environment: floor
  fixed framing but starved wardrobe continuity; narrowing the floor to `Scene:` only
  (200 chars) restored continuity's normal-priority chance, which then exposed a
  pre-existing false-positive keyword (`"crop"` matching an unrelated camera-framing
  sentence); fixing that keyword revealed continuity was genuinely absent; a second,
  separate small reserved floor for the single essential continuity-lock sentence
  (110 chars) restored it, confirmed by direct substring inspection, not booleans.
  Full detail in the technical changelog (Batch 5a-5e).
- Re-ran the proof render on the same regression slot (`2026-07-06-03-photo`).
  **Structured QA verdict: FAIL**, but with the two originally-targeted defects
  (scene/environment absence, continuity-sentence absence) now confirmed fixed in the
  actual rendered image, not just the receipt -- the frame now shows a genuine cafe
  environment, and the visible tank top reads as real clothing, not a bra/lingerie
  substitution. Remaining fail reasons are separate and pre-existing: recurring
  freckle-density concern, most of the specified wardrobe outside the frame and
  unverifiable, and a missing coffee-cup prop.
- Practical read: **proof-worthy but not production-ready**, not "still failing" in
  the same way as before. Per §5.2: this pivot's Phase 1 checkpoint is still not met.
  The folder-native migration (§9 Phase 2) remains paused.

**2026-07-06 — Canonical reference comparison (non-coding); hair-color concern downgraded, identity fidelity assessed**

- Downloaded (read-only, no credits) the 4 resource images from the live "APILENA"
  Kling element itself and compared directly against the render.
- `skin_realism_no_invented_marks` corrected from FAIL to PASS: all 4 references show
  comparable authentic freckling; the earlier fail verdict was appropriately cautious
  without a reference, but didn't hold up once one was available.
- `identity_fidelity` newly assessed as FAIL: hair color/highlight pattern (missing
  the reference set's warm caramel balayage) was a real, consistent mismatch across
  all 4 comparison points. Assessed as generation-model variance, not a pipeline
  defect (the "match hair color exactly" instruction was confirmed present and intact
  in the submitted prompt) -- decision made to track, not code against, on one data
  point.

**2026-07-06 — Batch 6: reserved framing-directive floor**

- New-slot proof render (`2026-07-05-02-photo`, same outfit wc_p082, `full_body`
  reference mode instead of `upper_body`) showed the model still cropped to a bust
  shot, failing to test full garment continuity. Root cause isolated: the source
  prompt's framing directive ("Framing should clearly show her full silhouette...")
  matched only the lowest-priority `body_shape` group (via "waist") and lost the
  budget competition -- same structural pattern as the earlier scene/continuity gaps.
- Fixed with a third reserved floor (`_FRAMING_FLOOR_KEYWORDS`,
  `FRAMING_FLOOR_CHARS = 160`), reusing the existing `_apply_reserved_floor` helper.
  Deliberately keyed on `"framing should"`, not the broad `"waist"` keyword.
  Functional test confirmed Scene:/continuity/framing all survive together (2494/2499
  chars). Not rendered yet at this point -- validated only.

**2026-07-06 — Post-Batch-6 re-proof renders: two consecutive wrong-garment substitutions, classified as recurring model non-compliance**

- Ran the approved re-proof render on `2026-07-05-02-photo`. Framing opened up as
  designed (wider shot achieved), but the model rendered a beige trench coat + dark
  scarf instead of the specified white tank top + black mini skirt.
- Full artifact-chain inspection (workorder slot, source `image_prompt`, compacted
  `submit_payload.json`, `negativePrompt`) confirmed the submitted prompt was correct
  and verbatim -- zero trench/coat/scarf language anywhere in the pipeline. Classified
  as generation-model non-compliance, not a code/routing defect. QA verdict replaced
  (not left stale) to reflect this render's actual, different failure reason.
- Per the decision rule (same-slot rerender to test one-off vs. recurring): re-ran the
  identical slot again. Second render substituted a different wrong garment (light
  turtleneck sweater) -- again with a verified-correct submitted prompt. **Reclassified
  from one-off variance to recurring garment-substitution noncompliance.** QA verdict
  replaced again, explicitly noting the superseded prior verdict both times so no
  stale QA record was left behind.
- Diagnosis: the existing negative-prompt protections guard only against
  under-dressing drift (bra/bikini/underwear substitution); there was zero protection
  against over-dressing/covering substitution (sweater/coat/scarf/jacket). This is a
  content gap in `pipeline/prompting/lena_prompt_brain.py`, not an executor bug.

**2026-07-06 — Batch 7: wardrobe-obedience lock designed and coded (validation incomplete, interrupted)**

- Approved narrow fix: a silhouette-class-scoped positive "Garment-obedience lock"
  sentence plus matching anti-substitution negative terms, added to
  `pipeline/prompting/lena_prompt_brain.py` (new
  `catalog_outfit_is_sleeveless_top_skirt_set()` helper; extended the existing
  `public_wardrobe_continuity_lock()` Skirt-set branch and
  `build_public_lane_negative_prompt()`'s skirt block). Deliberately scoped to
  sleeveless/tank-top + skirt outfits only, not blanket-applied, and not
  outfit-specific to `wc_p082`.
- Added a fourth reserved compaction floor in
  `pipeline/kling_apilena_api_executor.py` (`_GARMENT_OBEDIENCE_FLOOR_KEYWORDS`,
  `GARMENT_OBEDIENCE_FLOOR_CHARS = 300`), reusing the existing `_apply_reserved_floor`
  helper -- no new mechanism.
  Corresponding receipt fields added, mirroring the existing scene/continuity/framing
  pattern.
- `py_compile` clean on both files. Re-ran workorder prep for 2026-07-05; confirmed
  the new "Garment-obedience lock" language and anti-substitution negative terms are
  present in the regenerated source `image_prompt`/`negative_prompt` for the
  reassigned `wc_p082` slot. **The full functional test proving this content survives
  `_build_compact_prompt`'s compaction step was started but not completed** -- the
  session was redirected before that check finished. This is the open item blocking
  Batch 7 closure (see §0).

**2026-07-06 — Repo-knowledge-layer proposed (not yet approved); master-file update discipline made a hard rule**

- Proposed a minimal repo-knowledge layer for the whole `content_bot` repo (not just
  the Lena pivot): `REPO_MAP.md`, `LIVE_SURFACES.md` (replacing the two files already
  proven stale this session -- `tools/LEGACY_PROVIDER_SURFACES.md` and
  `pipeline/config/lena_live_path_manifest_v1.json`), `QUARANTINED_SURFACES.md`,
  `OWNERSHIP_MAP.md`, `PROOF_STATUS.md`, `GLOSSARY.md`, proposed to live in a new
  top-level `repo_knowledge/` folder. Nothing created -- proposal only, awaiting
  approval.
- Established as a hard, standing rule (§11.3): this master file's §0 Current State
  and §14 changelog must be updated for every meaningful step, before that step is
  reported as complete. This entry itself, plus the §0 rewrite and §11.3 addition
  earlier in this same update, are the first application of that rule.

**2026-07-06 — Session continuity protocol adopted: read-first at session start, update-before-close at session end**

- New standing rule: every new session must start by reading this file and
  `pipeline/change_notes/lena_agentic_pivot_changelog.md` -- not chat memory -- and
  ground its opening summary (current state, last completed step, blockers, live
  path, next approved step) in those files before beginning any work.
- Reaffirms and formalizes §11.3: no meaningful step (code batch, proof render, QA
  verdict, confidence-changing diagnosis, blocker discovery, next-step decision,
  live-path correction, source-of-truth change) is closed until both this file and
  the changelog are updated.

**2026-07-06 — Batch 7 validated (positive lock); Batch 7b: negative-term reorder failed, deeper root cause found**

- Full functional test completed for Batch 7 against `2026-07-05-03-photo` (wc_p082,
  reassigned there by prep rotation). **Positive side: genuine, verbatim, confirmed
  by direct substring inspection** -- scene, continuity, framing, and the new
  "Garment-obedience lock:" sentence all present together, prompt at 2471/2499 chars.
  **Negative side: zero of 11 anti-substitution terms survived** -- checked directly,
  not inferred from the receipt. Batch 7 not closed on this finding. Full detail in
  the technical changelog (Batch 7).
- Attempted the approved narrowest fix (Batch 7b): reordered the 11 terms to the
  front of `build_public_lane_negative_prompt()`'s `extra_bits`, no new floor
  mechanism, per scope. **Did not work** -- re-tested against `2026-07-05-02-photo`
  after prep rotation moved wc_p082 back there; still zero survived.
- Root cause found to be bigger than assumed: the base `NEGATIVE_PROMPT` constant in
  `lena_prompt_brain.py` is 2734 characters by itself, already exceeding the
  2499-char negative-prompt budget before `extra_bits` is ever added. Confirmed this
  isn't specific to the new terms -- checked whether *pre-existing* extra_bits
  protections ("mirror selfie", "bra top", "bikini-like bodice") survive compaction;
  they don't either. The entire `build_public_lane_negative_prompt()` mechanism has
  apparently never reached the actual submitted negative prompt, for any outfit, not
  just this silhouette class. Flagged, not acted on -- larger than this batch's scope.
- Stopped per instruction rather than implementing a negative-prompt floor
  mechanism. Batch 7 remains **not closed**. See §0 for current blockers and open
  decisions.

**2026-07-06 — Batch 7c: negative-prompt reserved floor implemented; Batch 7 closed**

- Approved narrow fix: a reserved floor inside `_build_compact_negative_prompt()`
  (`pipeline/kling_apilena_api_executor.py`), scoped only to the 11
  garment-obedience anti-substitution terms (`NEGATIVE_GARMENT_OBEDIENCE_FLOOR_CHARS
  = 380`). Trims the lowest-priority tail of the base negative list if needed, rather
  than reordering (already tried and shown insufficient in Batch 7b).
- Functional test against `2026-07-05-02-photo` (wc_p082): **all 11 anti-substitution
  terms present verbatim** in the compact negative prompt, confirmed by direct
  substring inspection, not receipt inference. Positive lock, scene, and continuity
  all remain genuine and intact. Compact prompt 2498/2499 chars, compact negative
  2497/2499 chars -- both within the existing cap.
- **Batch 7 is now closed.** Full detail in the technical changelog (Batch 7c).
- Per explicit decision, the repo-wide negative-prompt budget/truthfulness gap found
  in Batch 7b (base `NEGATIVE_PROMPT` alone exceeds budget; other public-lane
  protections likely never reaching submitted payloads for any outfit) is recorded
  as a **separate, tracked technical-debt issue**, not folded into Batch 7 and not
  fixed now. A later dedicated batch must redesign negative-prompt
  prioritization/truthfulness repo-wide.
- Repo-knowledge-layer work remains explicitly deferred until after one post-Batch-7
  rerender is judged, per instruction. Not started.

**2026-07-06 — Post-Batch-7 rerender: HARD FAIL, proof lane paused, model-compliance ceiling declared**

- Ran the approved post-Batch-7 rerender on `2026-07-05-02-photo` (wc_p082). Confirmed
  via `prompt_receipt.json`, before viewing the image, that the submitted prompt and
  negative prompt both correctly carried the full closed Batch 7 fix. Result: third
  consecutive wrong-outfit render (sweater + scarf again), and this time also a
  severe drift into cartoon/illustrated rendering style -- explicitly what the
  negative prompt protects against. Replaced the stale QA verdict with an honest
  review.
- **Explicitly declared a hard fail, not a near miss.** Wrong outfit, wrong visual
  style, not a usable Lena proof.
- **Final classification: recurring model-level noncompliance.** Not a routing bug,
  not a compaction bug, not a stale-ref bug, not one-off variance -- ruled out across
  three renders, each with an independently verified-correct pipeline.
- **Pipeline path validated:** identity resolution, element_list-only submission,
  and scene/continuity/framing/garment-obedience compaction survival (positive and
  negative) are all confirmed correct and consistent, every render this session.
- **Remaining failure is model-compliance, not pipeline:** the generation model does
  not reliably obey wardrobe and style-realism instructions on this specific
  slot/outfit/lane combination, even when the delivered instruction is verified
  correct.
- **Further rerenders on this exact proof lane are paused.** No executor patch
  follows from this finding right now.
- Two viable next branches identified, decision pending: (1) move into the
  repo-knowledge layer + first folder-native implementation slice, since the
  pipeline itself is validated; or (2) test a different generation
  path/provider/conditioning strategy specifically for image obedience, since the
  remaining failure is model-level, not something this repo's prompt/compaction code
  can fix further.

**2026-07-06 — Direction: Branch 1. First filesystem-native slice created: `pipeline/agents/lena/40_identity_continuity/`**

- Approved: Branch 1 (repo-knowledge layer + first folder-native slice). Branch 2
  (alternate generation provider/conditioning investigation) remains a tracked,
  separate, not-yet-started follow-up.
- Created exactly five files, no more, wrapping the existing real owner
  `pipeline/identity/lena_identity.py` -- no code moved, no other folders created,
  no `state/`/`inbox/`/`outbox/` subdirectories (not in scope for this minimal
  slice):
  - `pipeline/agents/lena/40_identity_continuity/AGENT.md`
  - `pipeline/agents/lena/40_identity_continuity/RULES.md`
  - `pipeline/agents/lena/40_identity_continuity/INPUTS.md`
  - `pipeline/agents/lena/40_identity_continuity/OUTPUTS.md`
  - `pipeline/agents/lena/40_identity_continuity/CURRENT_STATE.md`
- Grounded in a fresh re-read of `pipeline/identity/lena_identity.py` (not memory)
  and a fresh grep confirming its three real callers
  (`pipeline/kling_apilena_api_executor.py`, `tools/lena_preflight.py`,
  `pipeline/lena_production_job.py`).
- Explicitly documented a gap against the original doctrine target (§7.5): this
  module does not write an `identity_lock.json` artifact; it's a pure in-process
  resolve/raise library today. Recorded as an open question, not a hidden
  capability -- per the standing rule not to claim knowledge of files that don't
  exist.
- Next recommended folder: `70_visual_qa/`, wrapping `pipeline/qa/lena_photo_qa.py`
  + `tools/lena_review_proof_render_v1.py` -- the other piece with real, proven code
  behind it (per the original repo-knowledge-layer proposal's ownership map).
  Repo-knowledge files (REPO_MAP/LIVE_SURFACES/QUARANTINED_SURFACES/OWNERSHIP_MAP/
  PROOF_STATUS/GLOSSARY) still queued after that, not started.

**2026-07-06 — Direction correction: repo-knowledge/session-recovery layer built instead of `70_visual_qa/`**

- User explicitly redirected: build the repo-knowledge/session-recovery layer next,
  not `70_visual_qa/`. Reason given: session continuity, not the count of
  folder-native slices, is the biggest operational risk -- every new Claude
  instance needs a reliable starting point before more agent folders get built.
- Explicit constraints honored: no rendering, no publishing, no code moved, no new
  folder-native slice created (`70_visual_qa/` still does not exist).
- Rewrote `pipeline/change_notes/NEXT_SESSION_START.md` to point a new session at
  the knowledge layer immediately after itself, before the master file's §0.
- Created five new files under `pipeline/knowledge/content_bot/`, each grounded in
  a fresh direct read this session (not the prior session's memory of these
  surfaces):
  - `REPO_MAP.md` -- built from a direct `ls` of the repo root and `pipeline/`.
  - `LIVE_PATHS.md` -- built from `pipeline/config/lena_live_path_manifest_v1.json`
    and `tools/LEGACY_PROVIDER_SURFACES.md`, read directly, not paraphrased from
    memory of earlier sessions.
  - `AUTHORITATIVE_SURFACES.md` -- built from direct header/docstring reads of
    `lena_identity.py`, `lena_photo_qa.py`, `lena_review_proof_render_v1.py`, and
    `kling_apilena_api_executor.py`.
  - `QUARANTINED_SURFACES.md` -- summarizes `tools/LEGACY_PROVIDER_SURFACES.md`
    (named as the detailed source of truth it points back to, not duplicated in
    full).
  - `CURRENT_PROOF_STATUS.md` -- built from a direct read of the actual QA verdict
    artifact, `pipeline/asset_review/lena/2026-07-05/2026-07-05-02-photo_qa.json`,
    not from this master file's prose summary of it.
- No new folder-native slice created. `70_visual_qa/` remains not-yet-built and
  not yet approved -- this batch was documentation/orientation only.
- Next step still not decided between `70_visual_qa/` and starting the Branch 2
  provider/conditioning investigation. See updated §0 and
  `pipeline/change_notes/NEXT_SESSION_START.md`.

**2026-07-06 — Repo-knowledge layer accepted; second folder-native slice created: `pipeline/agents/lena/70_visual_qa/`**

- User accepted the repo-knowledge/session-recovery layer as complete, then
  approved building the second folder-native slice: `70_visual_qa/`, wrapping
  `pipeline/qa/lena_photo_qa.py`, `tools/lena_review_proof_render_v1.py`, and
  `pipeline/asset_review/lena/`.
- Created exactly five files, no more, no code moved:
  - `pipeline/agents/lena/70_visual_qa/AGENT.md`
  - `pipeline/agents/lena/70_visual_qa/RULES.md`
  - `pipeline/agents/lena/70_visual_qa/INPUTS.md`
  - `pipeline/agents/lena/70_visual_qa/OUTPUTS.md`
  - `pipeline/agents/lena/70_visual_qa/CURRENT_STATE.md`
- Grounded in a fresh, full re-read of both real modules (not memory), plus a
  fresh read of the real QA verdict artifact for the paused proof slot
  (`pipeline/asset_review/lena/2026-07-05/2026-07-05-02-photo_qa.json`) and a
  targeted grep of the changelog for prior "stale QA verdict" incidents.
- Documented the stale-QA-file mechanism precisely in `RULES.md`: `slot_id` is
  stable across rerenders, `save_qa_template()` defaults to `force=False`, and
  `tools/lena_review_proof_render_v1.py`'s CLI exposes no force flag -- so a
  rerender on a previously-used slot surfaces the **old** QA verdict via
  `build_review_bundle()`'s `qa_overall_status` field until a human/Claude
  explicitly writes a fresh one after viewing the new image. Cited two real prior
  instances of this being caught and fixed by hand (the pre-Batch-5 scaffold and
  the previous-turtleneck-render verdict, both referenced in the changelog).
- Documented false-green hard-fail conditions beyond what `validate_qa_result()`
  already checks in code: trusting a receipt-level "prompt was correct" as proof
  the image is correct, and carrying a `pass` over from a prior render without
  re-viewing the new image.
- Documented the canonical-reference-image procedure for identity/skin/hair
  review, grounded in the real 2026-07-06 non-coding verification entry: fetch the
  4 resource images from the render's own `live_apilena_lookup_response.json`
  (already fetched, no extra cost) rather than re-fetching or judging from memory.
- No code moved, no render run, nothing published. `70_visual_qa/RULES.md` flags
  one open, not-yet-decided question: whether the review helper should gain an
  explicit force-replace flag -- not authorized to build.
- Next step still not decided: no specific next folder-native slice is
  recommended (both previously-flagged high-value candidates are now built), vs.
  starting the Branch 2 provider/conditioning investigation. See updated §0 and
  `pipeline/change_notes/NEXT_SESSION_START.md`.

**2026-07-06 — Branch 2 provider/conditioning investigation: read-only phase complete, major finding**

- User approved starting Branch 2. Explicit constraints: no render, no code, no
  publish, no `.env` change. Read-only artifact and repo investigation only.
- Traced the live executor's exact endpoint/model/payload by reading
  `pipeline/kling_apilena_api_executor.py` in full: submission endpoint
  `POST https://api.klingai.com/v1/images/generations` (hardcoded default,
  confirmed no `KLING_IMAGE_API_URL`/`KLING_BASE_API_URL` override in `.env`); no
  `model_name` sent in any of the 3 recent `submit_payload.json` files (confirmed
  by direct read of each) because `KLING_IMAGE_MODEL_NAME` is absent from `.env`
  and the code only adds the field `if IMAGE_MODEL_NAME:`; payload is
  `element_list` only, no `image_list`, no `resolution`, no style/mode field.
- Downloaded (read-only, zero credits, same method as the project's own prior
  2026-07-06 canonical-reference-comparison) and viewed all 4 of the live
  APILENA element's resource images directly. **Confirmed clean, photoreal,
  consistent (brunette + caramel balayage, authentic freckling) -- ruling out
  "bad/stylized element contents" as a root-cause category.**
- Viewed the actual generated images (not just metadata) for all 3 recent
  renders by resizing and reading them directly:
  - `2026-07-04-01-photo` (pre-Batch-1, `payload_no_image_list: false` --
    element_list + image_list of the 4 live element images): photoreal, but
    wrong eye color (green, contract specifies deep dark brown) and wardrobe
    substituted (black crop/bandeau top + denim shorts, not the specified black
    bodysuit + jeans, despite an explicit continuity-lock sentence and negative
    terms against exactly this substitution).
  - `2026-07-05-02-photo` (3rd render, current live path, element-list only):
    the known cartoon/illustrated-style failure, confirmed directly -- Pixar/
    3D-illustration rendering, oversized eyes, doll-like proportions, plus the
    known wrong-outfit failure (sweater+scarf, not tank+skirt).
  - `2026-07-06-03-photo` (current live path, element-list only): photoreal,
    good face/skin, but hair color mismatch (flat dark brunette vs. the
    reference set's consistent caramel/honey balayage) -- matches the QA
    verdict already on file exactly, confirming that verdict was not stale.
- Found and read (via `git show HEAD:<path>`, since the deletion is uncommitted)
  `pipeline/workorders/lena/README_BODYLOCK_PRODUCTION_RULES_2026-06-24.md` and
  both of its Python runners (`tools/generation/lena_apply_bodylock_to_daily_batch_v1.py`,
  `tools/generation/lena_run_daily_bodylock_live_v1.py`) -- all three are
  currently deleted from the working tree but were git-committed at `f5908ac6`
  ("Harden Lena publish gates and BodyLock production path") and are still fully
  recoverable from git history.
- **Major finding:** the BodyLock doc names a real, tested, different recipe as
  the approved production path: endpoint `POST https://api.klingai.com/v1/images/
  omni-image` (not `/v1/images/generations`), model `kling-v3-omni` (explicitly
  set, not omitted), `element_list` + `image_list` together (both required,
  validated in code -- `validate_payload()` hard-fails if `image_list` is
  missing), resolution `2k`, and a ~400-char scene-only prompt. The same doc
  explicitly names element-only submission and a 2,172-char appearance-heavy
  prompt as **tested and rejected** causes of "identity drift and pasted-face
  failures." The current live path's compacted prompts run up to 2,498 chars --
  already longer than the length BodyLock's own doc says already failed.
- Found real evidence the BodyLock recipe worked in production at least once:
  `pipeline/publishing/lena/dispatch_outbox/2026-06-24/manual_bodylock_20260624_ig_Instagram_Feed_payload.json`
  references a real generated asset that reached the publish-dispatch stage
  (asset file itself no longer on disk, but the dispatch record is real and
  git-tracked... note: this specific file is untracked/working-tree only per
  git status, treat as a real artifact, not proof of a merged/published post).
- Flagged, for the user's review and not acted on: the "element_list-only"
  photo contract now encoded in `pipeline/identity/lena_identity.py`
  (`REQUIRED_REFERENCE_BINDING_MODE = "kling_omni_element_only_photo"`) was
  itself written this session (Batch 2, 2026-07-05), formalizing a same-day
  Batch 1 diagnosis that treated `image_list` in the submitted payload as a
  contract violation. That diagnosis may have conflated two different things:
  the genuinely dangerous manual-URL-override env-var mechanism (arbitrary,
  unvetted, no expiry -- correctly banned) versus `image_list` as a payload
  field sourced from the live element's own vetted resources (which the
  2026-07-04 payload actually did, and which BodyLock's doc explicitly
  requires). Not reversed or edited -- flagged as a decision for the user.
- No code changed. No render run. No `.env` touched. Nothing published. Reference
  images downloaded to the session scratchpad directory only, not saved into the
  repo.
- Full decision memo (endpoint/model/payload, element/source images, style
  assessment, endpoint-reliability evidence, comparison to the BodyLock path,
  failure category, smallest next diagnostic, recommended next spend) delivered
  to the user in-conversation; not duplicated verbatim here -- see this entry for
  the technical trace, and this file's updated §0 for the current-state summary.
- Next step: not yet decided. Recommended (not yet approved): one controlled,
  paid diagnostic render retesting the BodyLock recipe on the same slot/outfit/
  environment already tested 3x, isolating provider/endpoint/model/payload-shape
  as the changed variable. Requires the user's explicit approval, a decision on
  the image_list anchor image, and re-adding the missing env vars
  (`KLING_LENA_ELEMENT_ASSET_ID`, an anchor image URL) -- both absent from `.env`
  today. No render authorized until then.

**2026-07-06 — BodyLock diagnostic: pre-spend memo, corrected approach, tooling built (dry-run only)**

### Direction and correction
User rejected the previously-proposed "re-add missing env vars to `.env`" path
outright, for two separate reasons: (1) Option 1 (endpoint+model swap only, no
`image_list`) was rejected as still ambiguous -- it wouldn't test the actual
committed BodyLock recipe. (2) The safety framing was corrected: no permanent
`.env` edit, no restoring manual-URL-override behavior as a normal path, no
weakening the containment guard, no publish, no render without a further,
separate approval of the exact anchor and exact command.

### A/B/C -- recipe, comparison, contradicted assumptions
Delivered in-conversation as a pre-spend memo (not duplicated verbatim here):
the exact committed BodyLock payload shape from `README_BODYLOCK_PRODUCTION_
RULES_2026-06-24.md` and `lena_run_daily_bodylock_live_v1.py`'s `build_payload()`
(confirmed: BodyLock sends **no `negativePrompt` field at all** -- a comparison
point not previously surfaced); a full side-by-side table against the current
live path (endpoint, model, element_list, image_list, prompt length, negative
prompt length, resolution, reference source); and the specific current
assumptions the committed recipe contradicts (element-only sufficiency, long
appearance-heavy prompts, `/v1/images/generations` as a validated
character-conditioning endpoint, negative-prompt necessity).

### D -- implementation
Built `tools/lena_bodylock_diagnostic_v1.py`: a new, standalone script, zero
modification to `pipeline/kling_apilena_api_executor.py` or any of its
containment guards. Design choices, each directly answering a user-stated
safety rule:
- Inert unless `CONTENT_BOT_BODYLOCK_DIAGNOSTIC=1/true/yes` is explicitly set
  (checked first, before anything else runs).
- Reuses `pipeline.identity.lena_identity.assert_no_manual_reference_override()`
  -- the same containment guard the live executor uses -- so this diagnostic
  cannot be tricked into honoring `KLING_LENA_ELEMENT_IMAGE_URLS_JSON` /
  `KLING_LENA_ELEMENT_IMAGE_URLS` either. Guard not weakened, not bypassed,
  reused as-is.
- New anchor env var `CONTENT_BOT_BODYLOCK_ANCHOR_URL`, read fresh from the
  process environment each invocation -- never written to `.env`, no default,
  no fallback. Must be `https://` or the build hard-fails.
- Hardcoded (not env-overridable) `REQUIRED_ENDPOINT` (`/v1/images/omni-image`)
  and `REQUIRED_MODEL` (`kling-v3-omni`) -- re-checked against the actual
  payload dict just built, not just the constants, so the two can't silently
  drift apart.
- Hard-fails if: the diagnostic flag is unset; the anchor URL is unset or not
  `https://`; the prompt is empty or exceeds 400 chars; `image_list` doesn't
  contain exactly one entry; `n` isn't exactly 1; a negative-prompt key is
  present at all.
- Default mode is dry-run (`--execute` omitted): validates and prints the exact
  payload, zero network calls, zero credits, no debug folder written. Only
  `--execute` reaches `requests.post`.
- When it does execute, artifacts write to a freshly timestamped, fixed-prefix
  folder (`pipeline/kling_debug/bodylock_diagnostic/bodylock_diagnostic_<UTC
  timestamp>/`, not caller-nameable) containing a `DIAGNOSTIC_NOT_PRODUCTION.md`
  marker file plus the submit/poll/result JSON -- structurally impossible to
  collide with or be mistaken for a production-dated workorder folder.

### Verification performed (no spend)
Ran `py_compile` (clean). Ran the script three times to prove the hard-fails
actually fire: flag unset -> correct `RuntimeError`; flag set, anchor unset ->
correct `RuntimeError`; flag+anchor set, 499-char prompt -> correct `RuntimeError`
citing the 400-char cap. Ran a valid dry-run (flag + a real anchor URL from the
live element's own resources + a 286-char scene-only prompt for the same city-
bench/coffee/wc_p082 scenario) and confirmed the exact expected payload shape:
`model_name: kling-v3-omni`, `element_list` resolving to the real live element
(`315187972322559`), one `image_list` entry, `resolution: 2k`, `n: 1`, no negative
prompt. Confirmed via `git status` that `.env` is untouched and that dry-run mode
created no diagnostic debug folder (none exists on disk).

### What was explicitly not done
No network call reached Kling. No credits spent. No `.env` edit. No change to
`kling_apilena_api_executor.py` or its containment guards. No render.

### Anchor decision -- not made, presented for the user
Three candidates presented: (1) the live APILENA element's own cover image
(recommended -- already verified clean/photoreal this session), (2) a specific
named canonical Lena proof image (none named yet), (3) the original "Goodtest1"
anchor (not confirmed to still exist). Not decided.

### Next step
Waiting on the user's explicit approval of the exact anchor URL and the exact
`--execute` command (including final prompt text) before any real submission.

**2026-07-06 — BodyLock diagnostic executed once: rejected at submission, new sub-problem found**

### Direction
User approved exactly one real diagnostic run: anchor = the live APILENA
element's own cover image, exact command as previously reviewed, plus `--execute`.
Explicit constraints repeated: no `.env` edit, no publish, no more than one
image, do not run the normal production executor.

### What happened
Confirmed the anchor URL was still current (re-read the freshest
`live_apilena_lookup_response.json`, 2026-07-06, matched the cover URL used in
the earlier dry-run) and that Kling credentials were present in `.env`
(presence-only check, no values printed) before running. Ran exactly:
```
CONTENT_BOT_BODYLOCK_DIAGNOSTIC=1 CONTENT_BOT_BODYLOCK_ANCHOR_URL="<live element cover URL>" python tools/lena_bodylock_diagnostic_v1.py --prompt "<286-char scene-only prompt>" --execute
```
The script built and validated the payload correctly (same shape verified in the
prior dry-run), then called `POST https://api.klingai.com/v1/images/omni-image`.
**Kling rejected the submission: `HTTP 400 {"code": 1201, "message": "Element id
not found: 315187972322559", "request_id": "85814f13-15a6-4450-9759-34eb59963085"}`.**
No `task_id` was ever issued -- the flow never reached polling or image
generation. Zero credits spent. Artifacts (`submit_payload.json`,
`submit_response.json` only -- no poll/result files, since none were reached)
written to
`pipeline/kling_debug/bodylock_diagnostic/bodylock_diagnostic_20260706T200037Z/`.

### Interpretation
This is a real, informative result, just not the one the diagnostic was designed
to produce (a rendered image to judge for realism/outfit/style). The exact same
element id (`315187972322559`, "APILENA") that resolves and generates
successfully on `/v1/images/generations` (the current live path, looked up via a
web-session-scraped internal endpoint, cookie/web-token auth) is **not found** by
the AK/SK-authenticated official API that `/v1/images/omni-image` requires. This
points to a probable structural cause distinct from anything found in the
original Branch 2 investigation: the element may exist only in Kling's web-UI
element registry, not in whatever registry the AK/SK-authenticated official API
checks against. This also reconciles with an old, previously-shelved finding in
this repo: `tools/generation/kling_lena_element_endpoint_research_v1.py`
(2026-06-14, static codebase research, no API call) found `GET /v1/elements`
returned 404 and explicitly stated "no confirmed path found in codebase or prior
requests" for how the official API lists or creates elements. That unresolved gap
from three weeks ago is now directly implicated in why this diagnostic could not
proceed to generation.

### What was explicitly not done
No image was generated (none to judge for realism/outfit/style -- the report to
the user says this directly, not implied). No retry attempted with a different
element id, auth method, or endpoint. No code changed beyond running the
already-approved script as designed. `.env` untouched. The normal production
executor (`kling_apilena_api_executor.py`) was not invoked. Nothing published.

### Next step
Not yet decided. This is a new, distinct sub-problem (element-registry/auth
mismatch on the official API) separate from the original wrong-outfit/style
question, which remains unresolved and untouched by this result. Candidates,
none approved: read-only research into the official API's element list/create
mechanism; asking Kling support/docs directly; or setting the BodyLock-recipe
angle aside and returning to the original question via a different diagnostic.
Do not retry on your own judgment -- ask first.

**2026-07-06 — Element-registry investigation (no-spend): no confirmed-working omni-image element found in repo history**

### Direction
User classified the diagnostic rejection precisely: not a prompt/outfit/anchor/
image_list problem, but the current APILENA element ID not being visible to the
omni-image endpoint -- meaning it likely exists in the web/UI registry but not
the official AK/SK Omni API registry. Directed a no-spend investigation only:
find whether this repo has any older element ID actually proven to work with
omni-image + kling-v3-omni + AK/SK + element_list/image_list. No render, no
`.env` edit, no Kling call, no code change.

### Method
Git history search (via `git show <commit>:<path>` and `git log --all -S
"<term>"` pickaxe across all commits, not just HEAD -- covers deleted/
uncommitted files too, since the relevant deletions were never committed) plus
a check of every `.env.bak_*` snapshot currently on disk (11 files, spanning
2026-06-17 through 2026-06-25).

### A. Any official-API-visible Lena element ID in repo history?
One candidate, **unconfirmed**: `u_313006264506046`, introduced in
`tools/strategy/lena_build_kling_payload_dryrun_v1.py` and
`tools/strategy/lena_submit_kling_payload_v1.py` (commits `25055603`/`7f4fec51`,
2026-06-25 23:33 / 2026-06-26 00:46 -- the day *after* BodyLock's hardening
commit `f5908ac6`, 2026-06-25 10:50). Uses a different payload schema entirely:
`fromElementId` (top-level string) + `arguments: [{"name": "elementVersion",
"value": "[...]"}]` + `image_list` (3 hardcoded CDN URLs) + `negative_prompt` --
not BodyLock's `element_list` shape. This later tooling's own `BLOCKED_TERMS`
explicitly reject `"element_list"`, `"Goodtest1"`, and `"/v1/images/
generations"` as wrong/superseded approaches, and `BLOCKED_IDS` blocks four
other element IDs including `313794609092321` and the known-retired
`313524913093322` -- meaning this repo's own history shows BodyLock's `element_
list` approach was already considered superseded within about a day of being
committed. `u_313006264506046` itself appears in exactly these two commits and
nowhere else -- no result manifest, no `pipeline/strategy/lena/kling_results/`
artifact exists anywhere (that directory was added to `.gitignore` the same day
it was introduced, and doesn't exist on disk today). **No evidence it was ever
run live.**

### B. Does Goodtest1 (or another BodyLock anchor) still exist?
No. "Goodtest1" appears only as a name (BodyLock's README) and as a
`BLOCKED_TERM` in the later scripts -- its actual URL was never hardcoded or
committed anywhere findable in this repo. Unrecoverable. (The *later* script's
own anchor -- 3 real CDN URLs tied to `u_313006264506046` -- is recoverable,
but ties to the unconfirmed element above, not to BodyLock.)

### C. Did the old BodyLock recipe ever actually succeed under AK/SK auth?
Weaker than previously described. `tools/generation/
lena_run_daily_bodylock_live_v1.py` strictly requires `KLING_AK`/`KLING_SK` and
strictly aborts if `KLING_LENA_ELEMENT_ASSET_ID` is unset or equals the
hardcoded retired ID `313524913093322`. Checked all 11 `.env.bak_*` snapshots
on disk: `KLING_LENA_ELEMENT_ASSET_ID` appears in exactly two, both dated
2026-06-22, both set to `313524913093322` -- the exact ID this script rejects.
It is **absent** from the 2026-06-25 08:22 backup (same day as the BodyLock
hardening commit) and every other snapshot including today's `.env`. This means
at the one `.env` snapshot closest to BodyLock's own creation date, running its
live runner would have aborted, not succeeded. The one previously-cited
positive signal -- the 2026-06-24 publish-dispatch record
(`pipeline/publishing/lena/dispatch_outbox/2026-06-24/manual_bodylock_
20260624_ig_Instagram_Feed_payload.json`) -- references a filename
(`lena_bodylock_omni_2026-06-24-01-photo.jpg`) matching this project's *normal*
daily-workorder naming convention, not the standalone live-runner's own output
naming (`bodylock_daily_{label}_{suffix}.jpg`). This suggests the dispatched
image more likely came from the normal daily pipeline with BodyLock settings
patched in (via the *other* BodyLock script,
`lena_apply_bodylock_to_daily_batch_v1.py`), not a proven standalone AK/SK +
omni-image success under the exact recipe described in the README.
**Conclusion: cannot confirm.**

### D. Can APILENA realistically be used with omni-image, based on repo evidence?
No supporting evidence anywhere, and one direct data point against it (today's
diagnostic rejection). APILENA only ever appears in the web-session-scraped
`kling.ai/api/elements` lookup path in this repo's history -- never in any
omni-image or AK/SK context.

### E. Recommendation given to the user
Framed as a real choice, not a single answer: option 1 (recreate as an
official-API-visible element) is the only path toward the documented recipe,
but is **unproven groundwork, not a restoration** -- no element has ever been
confirmed to work this way in this account's history, per (A)-(D) above.
Suggested pairing option 4 (ask Kling support/docs directly) with option 1 if
pursuing it, since two guesses (APILENA, then `u_313006264506046`) have already
gone unconfirmed or failed. Option 2 (accept `/v1/images/generations` and its
limitations) is the only path with any real, current-session evidence of
working, imperfectly. Option 3 (different provider) has no repo evidence either
way. Not decided by the user yet.

### What was explicitly not done
No render. No code changed. No `.env` edit. No Kling API call. No publishing.
Purely git/file archaeology (`git show`, `git log -S` pickaxe, reading
`.env.bak_*` files already on disk).

### Next step
Not yet decided among the four options presented (recreate element / accept
current path's limitations / switch provider / ask Kling support), plus the
separate read-only-research and abandon-omni-image candidates already on the
table from the prior entry. Ask before proceeding on any of these.

**Addendum (same day):** a background search surfaced two pre-existing `.har`
browser-capture files in the repo (`scratch/kling_elements_page.har`,
`scratch/herby_kling_elements_page.har`, not created this session). Domain-only
inspection (no cookies/tokens read) confirmed neither capture -- both real
browser sessions actively using the Kling web UI's element/omni-image feature --
ever contacts `api.klingai.com`; the entire flow lives under the `kling.ai`
domain (`/api/elements*`, `/api/omni/submit-config-template`, `/api/omni/
intent-recognition`). This corroborates and sharpens (D): the web UI's element
system and the public `api.klingai.com` API appear to be structurally separate
products on separate hosts. Strengthens the case for trying option 4 (ask Kling
support/docs) before option 1 (recreate element), but does not change the
recommendation itself -- still the user's decision.

**2026-07-06 — Decision: Kling Omni/BodyLock diagnostic path PAUSED; support packet prepared**

### Direction
User decided the HAR evidence was sufficient to stop further Kling diagnostic
testing. Explicit framing: the working web-UI element flow uses `kling.ai`
endpoints; the official AK/SK API uses `api.klingai.com` and cannot see
APILENA; no more guessing at payload shapes or old element IDs. Directed
preparation of a concise support packet for Kling/APILENA support covering:
current element ID and where it works/fails, the exact error, the HAR
evidence, and four specific questions (registry visibility, how to obtain a
working element, correct payload schema, whether `kling-v3-omni` supports
character-element conditioning via the official API at all). Explicit
constraints: no code, no render, no `.env` edit, no Kling call, no publish.

### What was done
Wrote `pipeline/change_notes/lena_kling_omni_support_packet_2026-07-06.md` --
a standalone, ready-to-send document (not a continuity file, a support
communication) covering all 9 points requested: element ID
(`315187972322559`), works on `/v1/images/generations`, fails on
`/v1/images/omni-image`, exact error (`code 1201, "Element id not found"`,
with `request_id`), the HAR-based domain evidence, and four questions (web-UI/
official-API registry visibility; how to create/obtain a working element;
which payload schema is correct -- `element_list` / `fromElementId` /
`arguments.elementVersion` / other; whether `kling-v3-omni` supports
character-element conditioning via the official API at all). Written for an
external, non-technical-doctrine audience -- no internal jargon, no repo file
paths in the main body (kept to an "internal note" footer only).

### Continuity updates
Updated all three continuity files to state plainly:
- The Kling Omni/API BodyLock path is paused pending Kling/APILENA support
  clarification -- not paused for a single retry, paused as a category (no
  more element IDs, payload schemas, endpoints, or auth methods to be tried
  on our own judgment).
- `/v1/images/generations` remains the only currently working Kling image
  path, quality-limited (wrong outfit / occasional style drift / hair-color
  mismatches, as documented throughout this session) but functional, and is
  explicitly unaffected by this pause -- the pause is scoped to the omni-image/
  BodyLock diagnostic thread only.
- No more Kling spend of any kind on the omni-image thread until the support
  packet gets a response.

### What was explicitly not done
No code written or changed. No render run. No `.env` edit. No Kling API call.
No publishing. The support packet was not sent to Kling by us -- that's the
user's action.

### Next step
Waiting on Kling/APILENA support's response to the packet. The original wrong-
outfit/style question on the current live path remains open and could be
pursued in parallel via a different diagnostic, if the user chooses -- not
started, not decided.

**2026-07-06 — Kling Omni/BodyLock PARKED (clean stop); third folder-native slice created: `pipeline/agents/lena/60_executor/`**

### Direction
User gave a final, explicit close-out on the Kling Omni/BodyLock thread:
park it exactly where it is, no more Kling tests, no more element IDs, no
more payload schemas, no element recreation without support/docs confirming
the correct method, no `.env` edits, no render. Standing prohibitions until
an external trigger (a response to the support packet). Added an unmissable
PARKED banner to the top of `NEXT_SESSION_START.md` and this file's §0, plus
a closing entry in the changelog, so a future session can't mistake this for
an active investigation. Confirmed `.env` untouched via `git status` before
closing.

Next: user approved building the third folder-native slice,
`pipeline/agents/lena/60_executor/`, wrapping the real execution surfaces:
`pipeline/kling_apilena_api_executor.py` (live), `tools/lena_bodylock_
diagnostic_v1.py` (parked), `pipeline/lena_production_job.py`
(orchestrator), and `tools/LEGACY_PROVIDER_SURFACES.md` (legacy context).
`tools/process_queue.py` considered and excluded from ownership (it's a
downstream publishing surface, not a generation executor) but mentioned in
`AGENT.md`/`INPUTS.md` to mark the boundary explicitly.

### What was created
Exactly five files, no code moved:
- `pipeline/agents/lena/60_executor/AGENT.md`
- `pipeline/agents/lena/60_executor/RULES.md`
- `pipeline/agents/lena/60_executor/INPUTS.md`
- `pipeline/agents/lena/60_executor/OUTPUTS.md`
- `pipeline/agents/lena/60_executor/CURRENT_STATE.md`

Grounded in a fresh re-read of `pipeline/kling_apilena_api_executor.py`,
`tools/lena_bodylock_diagnostic_v1.py` (both already read in full earlier
this session), and a fresh read of `pipeline/lena_production_job.py` and
`tools/process_queue.py` (both read for the first time this session) --
confirmed the exact call chain (`lena_production_job.py` gates and imports
`kling_apilena_api_executor.run_executor()` behind `CONTENT_BOT_KLING_
EXECUTE`), not assumed from memory.

Covers, per explicit instruction: (1) current working Kling path (endpoint,
model, payload shape, element); (2) paused Kling Omni/BodyLock path, stated
as parked, not mid-investigation; (3) diagnostic-only paths (the standalone
script's dry-run-by-default design, and the live executor's own no-spend
mode); (4) dead/legacy executor names (`kling_ui_executor.py`,
`kling_direct_executor.py`, both generations of deleted BodyLock/transport
scripts, old strategy-era orchestration, blocked OpenArt/Seedance surfaces);
(5) what must never be invoked casually; (6) what requires explicit human
approval; (7) where payload artifacts are written (`pipeline/kling_debug/
apilena_api/` and `pipeline/kling_debug/bodylock_diagnostic/`); (8) what a
new session should inspect before touching execution, in order.

### What was explicitly not done
No code moved. No `.env` edit. No render. No Kling call. No publish. The
parked Kling Omni/BodyLock thread was not reopened or advanced -- this
folder documents that it's parked, consistent with the standing rule in its
own `RULES.md` not to treat re-reading these docs as authorization to resume.

### Next step
Not yet decided between a further folder-native slice or returning to the
original wrong-outfit/style question via a different diagnostic. The Kling
Omni/BodyLock thread remains separately parked, waiting on an external
response.

**2026-07-06 — Fourth folder-native slice created: `pipeline/agents/lena/50_prompt_builder/`**

### Direction
User approved `60_executor/` and directed the next branch: build the
folder-native prompt-builder slice, `pipeline/agents/lena/
50_prompt_builder/`, wrapping `pipeline/prompting/lena_prompt_brain.py`, the
prompt receipt fields used by the executor, the wardrobe/scene/framing/
garment-obedience locks, and the known negative-prompt budget issue.
Explicit constraints: minimum five files, no code moved, no `.env` edit, no
render, no Kling call, no publish, no fixing the negative-prompt budget yet,
and do not reopen the parked Kling Omni/BodyLock thread.

### What was created
Exactly five files, no code moved:
- `pipeline/agents/lena/50_prompt_builder/AGENT.md`
- `pipeline/agents/lena/50_prompt_builder/RULES.md`
- `pipeline/agents/lena/50_prompt_builder/INPUTS.md`
- `pipeline/agents/lena/50_prompt_builder/OUTPUTS.md`
- `pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md`

### Grounding
Read `pipeline/prompting/lena_prompt_brain.py` directly this session (2834
lines total; read the header/constants, `build_negative_prompt_for_catalog()`
/ `build_public_lane_negative_prompt()`, `public_wardrobe_continuity_lock()`
(the garment-obedience/continuity lock generator, confirmed silhouette-
class-scoped via `catalog_outfit_is_sleeveless_top_skirt_set()`),
`framing_policy_for_mode()`, the main assembly function
`generate_prompt_package()`, and `apply_prompt_package_to_slot()`).
Confirmed via direct grep that the real, live caller is `tools/
lena_prepare_daily_workorders_brain.py` (other callers found in the repo are
legacy/patch scripts). Measured `len(NEGATIVE_PROMPT)` directly: **2734
chars**, confirming the previously-cited figure exactly. Cross-referenced
against `_build_prompt_receipt()` in `pipeline/kling_apilena_api_executor.py`
(read in full in an earlier session turn) to document the source-prompt/
compact-prompt boundary accurately.

### What this folder documents, per explicit instruction
1. What the Prompt Builder owns: full source prompt + negative prompt
   construction, wardrobe/scene/framing/garment-obedience locks.
2. Authoritative files/functions: `generate_prompt_package()`,
   `apply_prompt_package_to_slot()`, `public_wardrobe_continuity_lock()`,
   `framing_policy_for_mode()`, the `NEGATIVE_PROMPT` constant and its
   conditional additions.
3. Source vs. compact prompts: source is unbounded (observed up to 10,668
   chars this session), built at workorder-prep time; compact is capped at
   2499 chars each, built at submission time by the executor (owned by
   `60_executor/`, not here -- explicit boundary stated in `AGENT.md`).
4. How wardrobe/scene/framing/garment-obedience locks are created: per-
   outfit, keyed off catalog text (dress / bodysuit / skirt-set / shorts-set
   / outerwear / generic top), with the sleeveless-top-and-skirt case adding
   the garment-obedience lock as a single self-contained sentence by design
   (so the executor's reserved-floor mechanism can key on one marker).
5/6. What prompt receipt fields prove (exactly which safety sentences/terms
   reached the compact strings submitted to Kling, independently
   re-verifiable) and do not prove (that the generated image is correct --
   restated with the real 11/11-terms-present-yet-wrong-outfit evidence from
   this session).
7. The negative-prompt overflow: exact numbers (2734 vs. 2499, a 235-char
   overflow before any outfit-specific term), one reserved floor covering
   only the garment-obedience terms, no floor for anything else. Documented,
   explicitly not fixed.
8. Why prompt correctness does not equal image correctness: stated as this
   folder's core rule, grounded in the same real render evidence used
   throughout this session (garment-obedience terms confirmed present on
   three consecutive wrong-outfit renders; a confirmed-correct negative
   prompt including "cartoon"/"doll-like" that still drifted into cartoon
   style once).
9. What to inspect before changing prompt logic: `RULES.md`'s real incident
   (a `"crop"` keyword false positive from a prior batch, caused by a wording
   change interacting with executor floor-matching) as the concrete reason
   to check compaction-keyword coupling before editing locked sentences.

### What was explicitly not done
No code moved. No `.env` edit. No render. No Kling call. No publish. The
negative-prompt budget was measured and documented, not fixed. The parked
Kling Omni/BodyLock thread was not touched, reopened, or referenced as
something to resume.

### Next step
Not yet decided between a further folder-native slice, fixing the negative-
prompt budget overflow (its own dedicated decision), or returning to the
original wrong-outfit/style question via a different diagnostic. The Kling
Omni/BodyLock thread remains separately parked, waiting on an external
response.

**2026-07-06 — Negative-prompt budget repair implemented (no render)**

### Direction
User approved implementing the smallest safe fix from the 2026-07-06 design
memo. Explicit constraints: no render, no Kling call, no publish, no `.env`
edit, no reopening Kling Omni/BodyLock, no positive-prompt change, no change
to identity/wardrobe/scene/framing/positive-garment-obedience locks. Exact
scope specified: tiered constants in `lena_prompt_brain.py`, reserved floors
+ receipt fields in `kling_apilena_api_executor.py`, validated by
`py_compile` + no-network dry-run across 6 outfit classes x public/non-public
lanes, preserving garment-obedience 11/11.

### A. Files changed
- `pipeline/prompting/lena_prompt_brain.py`
- `pipeline/kling_apilena_api_executor.py`
- `pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md` (doc update)

### B. Before/after negative prompt lengths
Base `NEGATIVE_PROMPT`: **2734 -> 2696 chars** (139 -> 137 terms). Only two
confirmed exact-duplicate terms removed (`"navel piercing"` / `"belly button
jewelry"`, paraphrases of `"belly button piercing"` / `"navel jewelry"`
already present) -- verified via direct set-difference against the full
original 139-term list that nothing else was dropped, reworded, or added.
Compact negative-prompt length across all 12 tested cases: **2488-2499
chars** (always at or under the 2499 cap).

### C. Per-floor survival (12 cases: 6 outfit classes x public/non-public lane)
- Core, style-realism, body-anatomy: **survived in all 12/12 cases.**
- Public-safety: **survived in all 12/12 cases** (base 4 terms always in
  source regardless of lane; 6 lane-specific clothing terms additionally
  present and protected on public-lane cases).
- Garment-obedience (pre-existing, unchanged): **11/11 re-confirmed** on its
  real test case (`sleeveless_top_skirt`/public) -- identical to
  pre-repair behavior.
- Outfit-specific-substitution: survived (non-zero) on every public-lane
  case where its terms were actually present in source (lane-gated, same as
  garment-obedience -- expected zero on non-public lanes and outfit classes
  that add none of these terms).
- One partial case: `sleeveless_top_skirt`/public (the single render
  simultaneously needing core + style + public-safety + garment-obedience +
  outfit-specific + body-anatomy) trimmed body-anatomy to 32/37 terms under
  real budget contention -- `survived_via_reserved_floor` remained `true`
  throughout; expected graceful degradation on the highest-pressure case, not
  a bug.

### D. Implementation detail
`lena_prompt_brain.py`: `NEGATIVE_PROMPT` restructured into `CORE_NEGATIVE_
TERMS` (21), `STYLE_REALISM_NEGATIVE_TERMS` (29), `PUBLIC_SAFETY_NEGATIVE_
TERMS` (11), `BODY_ANATOMY_NEGATIVE_TERMS` (37), `OPTIONAL_FILL_NEGATIVE_
TERMS` (39), reconstructed via `", ".join(...)` of all five in original
order -- byte-compatible with every existing consumer (confirmed via grep
that no other file imports this constant's value; only two other files
define their own unrelated local `NEGATIVE_PROMPT` fallbacks). Two more
constants added purely for the executor's floor-matching, without touching
`build_public_lane_negative_prompt()`'s own inline assembly logic at all:
`OUTFIT_SPECIFIC_SUBSTITUTION_TERMS` (29, union of the dress/crop-top/
bodysuit/skirt/shorts/outerwear substitution terms) and `PUBLIC_LANE_SAFETY_
TERMS` (6, the clothing-safety subset of the lane-conditional extras --
selfie-framing terms deliberately excluded as a composition preference, not
a clothing-safety protection).

`kling_apilena_api_executor.py`: imported the five tiers plus the two
matching-only constants; added five floor-budget constants (core=350,
style-realism=550, public-safety=450, outfit-specific=400, body-anatomy=750,
sized against real measured tier content with headroom, confirmed via direct
calculation that the four always-on tiers' real combined content, 1953
chars, safely fits under the 2499 cap alongside either the existing
garment-obedience floor or the new outfit-specific floor, which are mutually
exclusive in practice); added a generic `_apply_negative_floor()` helper
mirroring the existing garment-obedience mechanism exactly (narrow, additive,
never forces consumption -- a floor with no matching source terms simply
uses zero of its budget); applied the five new floors strictly *after* the
pre-existing garment-obedience floor, unchanged in position and behavior;
extended `_build_prompt_receipt()` with ~40 new fields (matched/survived-
count/total/present/reserved-chars/chars-used/survived-boolean per floor,
plus an optional-fill transparency block).

**Bug found and fixed during testing:** the first version of the optional-
fill "reserved chars" receipt field computed a naive `cap - sum(all floor
caps)` subtraction, which went negative (-381) because the floor caps
deliberately sum to more than 2499 (garment-obedience and outfit-specific are
mutually exclusive in practice, so their caps overlap by design). Fixed to
compute from actual per-render floor *consumption* instead of nominal caps
-- always non-negative, re-verified across all 12 cases after the fix.

### Validation performed
`python -m py_compile` on both files (twice -- once per edit round, including
after the bug fix). No-network dry-run calls against slot dicts built from
the real `lena_prompt_brain.py` functions (`build_negative_prompt_for_
catalog()`, `build_public_lane_negative_prompt()`), covering plain top,
sleeveless-top+skirt, dress, bodysuit, shorts-set, and outerwear, each on
both a real public lane and a synthetic non-public lane -- 12 cases total.
Confirmed via `git status --short .env` (empty output) that `.env` was never
touched at any point. Confirmed via `find pipeline/kling_debug -newer
pipeline/prompting/lena_prompt_brain.py` (empty output) that no render/debug
artifacts were created -- the dry-run calls only exercised in-memory
functions, no network, no Kling call, no publish.

### E. Unresolved risks
- Whether this repair changes real image output on Kling is completely
  untested -- no render has been run. The repair guarantees more negative-
  prompt content reaches the submitted payload; it cannot, from a no-render
  validation alone, prove Kling honors that content any better than before.
- The highest-pressure case (`sleeveless_top_skirt`/public) shows real,
  measured contention between floors (body-anatomy trimmed to 32/37) --
  worth watching if a future outfit class needs even more simultaneous
  protection than today's six classes.
- `OUTFIT_SPECIFIC_SUBSTITUTION_TERMS` and `PUBLIC_LANE_SAFETY_TERMS`
  duplicate content that also lives inline in `build_public_lane_negative_
  prompt()` -- an intentional, documented tradeoff (keeps that function's
  own logic byte-for-byte unchanged) but a real drift risk if those inline
  lists are ever edited without updating the matching constants.
- Whether the always-on tier assignments (which terms are "core" vs. "style"
  vs. "optional fill") are the *right* long-term categorization is a design
  judgment from the memo, not an empirically-validated one.

### F. Recommendation on a future one-image proof render
**Recommended, not run.** A single, controlled proof render on a previously-
tested slot (e.g. `2026-07-05-02-photo`/wc_p082, the slot with three
documented wrong-outfit/style-drift failures this session) would let a
direct before/after comparison of the exact same outfit/scene under the
repaired negative-prompt path. This is the logical next diagnostic step, but
requires the user's separate, explicit approval before running -- not
authorized by this implementation step.

### What was explicitly not done
No code moved between unrelated files (only the two files above were
touched). No `.env` edit of any kind. No render. No Kling API call. No
publishing. No change to positive-prompt content, wardrobe/scene/framing
locks, or the positive-side garment-obedience lock sentence. The parked
Kling Omni/BodyLock thread was not touched, reopened, or referenced as
something to resume.

### Next step
Waiting on the user's decision on the recommended one-image proof render (F
above), a further folder-native slice, or returning to the original
wrong-outfit/style question via a different diagnostic. The Kling Omni/
BodyLock thread remains separately parked.

**2026-07-06 — Negative-prompt repair proof render: RUN, result FAIL (4th consecutive wrong-outfit miss)**

### Direction
User approved the recommended proof render: exactly one controlled image on
`2026-07-05-02-photo`/wc_p082, current `/v1/images/generations` path only.
Explicit constraints: exactly one image, current path only, no Omni/BodyLock,
no `.env` edit, no publish, no batch, no alternate endpoint, no alternate
element ID, save all artifacts normally, run visual QA honestly. Explicit
pre-flight checklist required before rendering: floors survived, compact
negative <=2499, correct slot, correct element, no `image_list`, no Omni/
BodyLock path.

### Method -- keeping this a true single-variable comparison
The real slot in `pipeline/kling_workorders/2026-07-05/daily_workorders.json`
still held its original, pre-repair `negative_prompt` (4189 chars, written
2026-07-05). Tested whether re-running `generate_prompt_package()` fresh for
this exact `date_str`/`slot_id`/`media_type` would reproduce the same
outfit/scene -- it did **not** (`wc_p084`/`env_e004`/"car moment" instead of
`wc_p082`/`env_s006`/"city bench"), because the wardrobe catalog and scene
bank pools have changed since 2026-07-05, changing what a deterministic seed
lands on even though the seed itself is stable. Regenerating the full
package would have silently changed the outfit under test, invalidating the
comparison against the 3 prior failures. Instead: looked up the `wc_p082`
catalog entry directly (`load_wardrobe_catalog()`), rebuilt only its
`negative_prompt` via `build_negative_prompt_for_catalog()` +
`build_public_lane_negative_prompt()` (confirmed lane `"city bench"` is in
`PUBLIC_SOCIAL_LANES`), and patched only the `negative_prompt` field (and its
metadata duplicate) into the real slot JSON via a small Python script (not
Edit/Write on the JSON directly, per this repo's established JSON-safety
practice) -- `image_prompt`, wardrobe, scene, environment, and every other
field left byte-identical to the 3 prior failed attempts.

### Pre-flight verification (before rendering)
Ran the real patched slot through `_build_compact_prompt()` /
`_build_compact_negative_prompt()` / `_build_prompt_receipt()` directly
(no-network) before rendering. Confirmed: compact negative 2496/2499 chars;
core 21/21, style-realism 29/29, public-safety 17/17, outfit-specific 7/29,
body-anatomy 32/37, garment-obedience 11/11 all survived; positive-side
floors (scene/wardrobe-continuity/framing/garment-obedience-lock) all still
present, confirming the positive prompt was genuinely untouched; endpoint
resolved to `/v1/images/generations` (not omni-image). Confirmed
`KLING_LENA_ELEMENT_IMAGE_URLS_JSON`/`KLING_LENA_ELEMENT_IMAGE_URLS` absent
from `.env` (presence-only check).

### The render
`CONTENT_BOT_KLING_TARGET_SLOT_ID=2026-07-05-02-photo
CONTENT_BOT_KLING_MAX_SLOTS=1 CONTENT_BOT_KLING_EXECUTE=1 python
pipeline/kling_apilena_api_executor.py 2026-07-05` -- exactly one slot
processed, task `903248497381220361` succeeded. `result_manifest.json`
confirmed: `element_id: "315187972322559"`, `element_name: "APILENA"`,
`provider_endpoint: "https://api.klingai.com/v1/images/generations"`,
`payload_no_image_list: true`. `prompt_receipt.json` confirmed every
pre-flight prediction exactly, matching the dry-run to the character.

### Visual QA (honest, image viewed directly)
Downloaded/resized/viewed the actual generated image. Wrote a fresh QA
verdict to `pipeline/asset_review/lena/2026-07-05/2026-07-05-02-photo_qa.json`,
explicitly superseding the stale 3rd-failure verdict (per the stale-QA-file
lesson), validated via `lena_photo_qa.validate_qa_result()` (passed, no
false-green inconsistency). **Overall: FAIL.**
- `wardrobe_class_fidelity`: FAIL -- **4th consecutive miss on this exact
  slot.** Specified white ribbed tank top + black leather mini skirt;
  rendered a mustard/yellow coat + scarf over a gray top -- an outerwear
  substitution, the same structural failure category (unspecified outerwear
  replacing the named top) as the two prior wrong-outfit misses (previously
  a trench coat, then a turtleneck sweater).
- `identity_fidelity`: FAIL -- hair drifted reddish-auburn/copper, eyes read
  lighter amber-brown, both off the canonical APILENA reference set
  confirmed earlier this session.
- `face_realism_anti_generic_drift`: FAIL but **improved** -- not a full
  cartoon/3D-illustration failure this time (unlike the 3rd pre-repair
  render), though still glossy/airbrushed/idealized, inconsistent with clean
  photoreal camera realism.
- `skin_realism_no_invented_marks`, `public_scene_clothing_continuity`,
  `outerwear_underlayer_correctness`, `hands_anatomy_sanity`,
  `environment_realism_scene_coherence`, `caption_scene_coherence`: all
  passed. `body_shape_continuity`: not applicable (obscured by the coat).

### Conclusion
**The negative-prompt budget repair measurably improved style/cartoon-drift
but did not fix the wardrobe-substitution failure.** With negative-prompt
protection now near-maximal and explicitly confirmed present in the
submitted payload (11/11 garment-obedience terms, 21/21 core, 29/29 style-
realism), the model still substituted an unspecified outerwear garment for
the named top -- the same failure category as before the repair, a 4th
consecutive occurrence on this exact slot. This is strong further evidence
the wrong-outfit failure is model/provider-level, not something more prompt
engineering on this path will fix.

### What was explicitly not done
No `.env` edit (confirmed via `git status --short .env`, empty, both before
and after). No batch (`CONTENT_BOT_KLING_MAX_SLOTS=1` plus the target-slot
filter guaranteed exactly one image; `processed_slots: 1` confirmed in the
executor's own output). No alternate endpoint or element ID -- both
confirmed via the receipt to be the current live path and the current live
element. No Omni/BodyLock path touched or reopened. No publishing.

### Next step
Not yet decided: whether to treat the wrong-outfit failure as a provider-
level limit and stop further prompt-side iteration on it, pick a further
folder-native slice, or wait on the parked Kling Omni/BodyLock thread's
external response as the more promising path to actually fixing wardrobe
fidelity. Ask before proceeding on any of these.

**2026-07-06 — Final classification accepted: negative-prompt repair retained; wardrobe-obedience prompt iteration stopped**

### Direction
User accepted the proof-render result and gave a final, explicit
classification, closing this thread: (1) negative-prompt repair retained,
(2) it improved style-realism protection, (3) it did not solve wardrobe
obedience, (4) the current `/v1/images/generations` path is usable only as
quality-limited/proof-limited, not trusted for wardrobe-exact production,
(5) the next meaningful fix, if pursued, is a provider/conditioning
strategy change, not more prompt tweaking. Explicit standing prohibitions
restated: no rerender of this slot, no further wardrobe-obedience prompt
patch, no reopening Kling Omni/BodyLock, no `.env` edit, no publish.

### What was updated
- `pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md` -- fully
  rewritten (was stale, still describing "three consecutive renders" and
  "Branch 2... has not started"). Now states the 4-render history, the
  negative-prompt repair as resolved/retained, and the 5-point final
  classification verbatim.
- `pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md` -- added a
  "Proof-render result -- FINAL CLASSIFICATION, repair retained" section,
  replacing the now-answered "what is not currently proven" framing from
  before the render.
- `pipeline/change_notes/NEXT_SESSION_START.md` -- added a FINAL, ACCEPTED
  CLASSIFICATION bullet stating all 5 points plainly at the top of the
  session-state list; updated "Exact next approved action" to state the
  thread is settled and closed, not an open decision.
- This file's §0 (Current blocker, Current proof status, Next approved
  step, What must NOT be done next) -- updated throughout to state the
  classification as final and accepted rather than a pending recommendation.

### What was explicitly not done
No code changed (this was a documentation-only turn). No render. No `.env`
edit. No Kling call. No publish. The negative-prompt repair's code was not
touched -- it remains exactly as implemented and proof-tested. Kling Omni/
BodyLock was not reopened or referenced as something to resume.

### Next step
Not yet decided: what to work on next, now that the wrong-outfit/negative-
prompt thread is closed and Kling Omni/BodyLock remains separately parked.
Ask before proceeding.

**2026-07-06 — Production QA standard corrected: exact wardrobe obedience demoted to diagnostic-only**

### Direction
User issued an important correction: exact wardrobe obedience had been
over-weighted all session as an automatic production failure. It was useful
as a *diagnostic* (does the model literally follow the catalog outfit
text?), but it is not the production goal. New corrected standard, given in
full: production goal is varied outfits over time, sexy/high-hook/viewer-
grabbing, somewhat-to-moderately revealing, platform-safe, realistic enough,
coherent scene, close-enough identity continuity, no obvious AI/cartoon/
anatomy failure. A wardrobe substitution is acceptable if the result is
still stylish, sexy/hooky, platform-safe, not frumpy, not boring, not
repetitive, coherent with the scene, and not identity-breaking. Hard
rejects: cartoon/illustration/obvious-AI look; broken anatomy/bad hands/
extra limbs; face identity badly off; boring/frumpy/non-hook outfit; outfit
too covered or not visually compelling; too explicit/unsafe; scene makes no
sense; same outfit/pose/location formula repeating across posts; caption/
image totally mismatched; low-quality/fake-looking output. New priority
order: (1) hook strength, (2) outfit variety, (3) sexy but platform-safe
styling, (4) realism, (5) identity continuity, (6) scene variety, (7)
caption/image coherence, (8) exact wardrobe obedience -- diagnostic only.
Explicit constraints: no render, no Kling call, no `.env` edit, no publish,
no prompt-code change yet -- documentation only this turn.

### Files updated
1. `pipeline/agents/lena/70_visual_qa/RULES.md` -- added a full "Production
   QA standard correction" section (the corrected standard, priority order,
   and hard-reject list verbatim) immediately after the stale-QA-file
   lesson, since it's now equally foundational. Removed `wardrobe_class_
   fidelity` from the "what counts as false-green" hard-gating list (it
   named three fields that must be a deliberately-confirmed pass for any
   overall pass; now only `identity_fidelity` and `public_scene_clothing_
   continuity` remain hard-gating). Added an explicit note that `pipeline/
   qa/lena_photo_qa.py`'s actual checklist code (`QA_CHECKLIST_FIELDS`,
   `validate_qa_result()`) has **not** been updated to match -- this is a
   documentation correction, not a code change, and the gap between doc and
   code is named plainly, not papered over. Added the schema-update
   question to "Not yet decided / not yet built."
2. `pipeline/agents/lena/70_visual_qa/CURRENT_STATE.md` -- added a
   "Production QA standard corrected" section at the top stating the
   correction and its scope (historical QA JSON files are not being
   retroactively rewritten -- they remain accurate records of what was
   concluded under the standard in force at the time; this is documented
   *reinterpretation*, not a rewrite of history). Reinterpreted the most
   recent real verdict (`2026-07-05-02-photo`, 4th render) inline: the
   `wardrobe_class_fidelity: fail` is not itself disqualifying under the
   corrected standard; the real concern is that the coat+scarf substitution
   reads as too covered/low-hook (a corrected-standard hard reject in its
   own right), plus the independently-real identity drift. Added two items
   to "what is not currently proven": whether any render would pass the
   corrected standard in full (never formally scored), and whether the QA
   schema will be updated to match (not decided).
3. `pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md` -- added a
   "Production standard correction" section narrowing (not reversing) the
   negative-prompt repair's final classification: the repair's style-
   realism improvement stands on its own regardless of this correction; the
   4th render's wardrobe-obedience conclusion is reframed as a diagnostic
   result, with the real corrected-standard concern being coverage/hook
   level, not catalog-string mismatch.
4. `pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md` -- added a
   prominent "Production standard correction" section immediately after the
   file's purpose statement (before "What was validated"), so it's the
   first substantive thing read. States plainly that everything below it
   was written under the prior, corrected standard, and is left as
   historical record rather than rewritten. Added a same-day addendum to the
   "Classification" section clarifying that "not trusted for wardrobe-exact
   production" should not be read as "not usable for production" --
   production-worthiness under the *corrected* standard has not been
   assessed yet.
5. `pipeline/change_notes/NEXT_SESSION_START.md` -- added a new, second
   standing banner (STANDARD CORRECTION) at the very top, above the
   existing PARKED banner, stating the full corrected standard so no future
   session can miss it. Updated the FINAL, ACCEPTED CLASSIFICATION bullet to
   cross-reference the correction and narrow points 3-4. Updated "Exact next
   approved action" to add the QA-schema-update candidate. Fixed a stale
   "three consecutive fails" reference to "four." Added explicit prohibitions
   against judging future renders by exact wardrobe match.
6. This file's §0 -- added the STANDARD CORRECTION callout under "Last
   updated," narrowed the "Current proof status" bullets, updated "Next
   approved step" with the QA-schema-update candidate, and added two new
   "What must NOT be done next" items (don't claim proof-limited path is
   validated for corrected-standard production either; don't judge future
   renders against exact wardrobe match). Appended this §14 entry.

### What was explicitly not done
No code changed (`pipeline/qa/lena_photo_qa.py`'s checklist schema, `lena_
prompt_brain.py`, `kling_apilena_api_executor.py` all untouched -- the
schema-update candidate is flagged, not built). No render. No `.env` edit.
No Kling call. No publish. No historical QA JSON rewritten -- correction is
additive commentary, not retroactive editing.

### Next step
Not yet decided: whether to update `pipeline/qa/lena_photo_qa.py`'s
checklist schema to match the corrected standard (a real code change,
requires separate approval), pick a further folder-native slice, or
something else. Ask before proceeding.

---

**2026-07-06 -- Two session-continuity skills created (convenience wrappers, not new doctrine)**

- Created two Claude Code project skills, at the user's request, purely to
  make the existing session-start and session-checkpoint procedures
  one-command instead of manually re-derived from these files each time:
  - `.claude/skills/lena-session-start/SKILL.md` -- runs
    `NEXT_SESSION_START.md`'s "Read these first, in order" list plus this
    file's §0 and the changelog's latest entry, then produces the same
    5-part grounded summary (current state / last completed step /
    blockers-parked branches / next approved step / hard prohibitions)
    before any work begins.
  - `.claude/skills/lena-session-checkpoint/SKILL.md` -- runs the
    close-out procedure: stop new work, update `NEXT_SESSION_START.md`,
    this master file, the changelog, and any touched `CURRENT_STATE.md`,
    recording what changed / files changed / validations run / decisions
    made / blockers / next step / prohibitions, then report back.
- Both skills are explicitly pointer-only: they carry no repo doctrine of
  their own, name this file, `NEXT_SESSION_START.md`, and the changelog as
  the sources of truth, and state that if the skill and the repo files
  ever disagree, the repo files win.
- No code changed. No render. No Kling/OpenArt/Seedance call. No `.env`
  edit. No publish. No production routing changed. No other skills
  created.

### Next step
Unchanged from above -- not yet decided whether to update the QA checklist
schema, pick a further folder-native slice, or something else. Ask before
proceeding.

---

**2026-07-06 -- Visual QA code updated: wardrobe-catalog mismatch no longer auto-fails (approved, implemented)**

- Per an audit-first approval flow (read-only audit, then explicit sign-off),
  made the smallest code change to `pipeline/qa/lena_photo_qa.py` to stop
  treating exact wardrobe-catalog mismatch as an automatic production
  failure, matching the corrected production standard above.
- Added `DIAGNOSTIC_ONLY_CHECKLIST_KEYS = ("wardrobe_class_fidelity",)` and
  `HARD_GATING_CHECKLIST_KEYS` (every other existing checklist key,
  unchanged). Changed `validate_qa_result()`'s false-green `any_failed`
  check to iterate only `HARD_GATING_CHECKLIST_KEYS` instead of the full
  `QA_CHECKLIST_KEYS`. `QA_CHECKLIST_FIELDS`/`QA_CHECKLIST_KEYS` themselves
  are unchanged in count, order, and keys -- only `wardrobe_class_
  fidelity`'s human label was reworded to say it's diagnostic/non-gating.
- Net effect: a QA result can now record `wardrobe_class_fidelity: fail`
  with `overall: pass` without tripping the false-green guard, as long as no
  other (hard-gating) field is `fail`. Every other field --
  `identity_fidelity`, `public_scene_clothing_continuity`, `outerwear_
  underlayer_correctness`, `body_shape_continuity`, `hands_anatomy_sanity`,
  `face_realism_anti_generic_drift`, `skin_realism_no_invented_marks`,
  `environment_realism_scene_coherence`, `caption_scene_coherence` -- still
  forces `overall: fail` on any `fail`, exactly as before.
- Validated (no render, no provider call, no `.env` edit, no publish, no
  prompt/executor/routing change): `py_compile` clean; the real on-disk
  `2026-07-05-02-photo_qa.json` (wc_p082, `overall: fail` for reasons beyond
  wardrobe) still validates cleanly, unchanged; a standalone script proved
  (A) a wardrobe-only `fail` now validates with `overall: pass`, and (B) all
  9 `HARD_GATING_CHECKLIST_KEYS` still force `overall: fail` when any one of
  them is `fail`, with a legitimate matching `fail`+reasons verdict still
  accepted for each.
- Explicitly deferred, not built: dedicated checklist fields for `hook_
  strength`, `outfit_variety`, `sexy_safe_styling`, `scene_variety` --
  flagged in `70_visual_qa/RULES.md` as a separate, larger, future change
  requiring its own approval.
- Files updated to record this: `pipeline/agents/lena/70_visual_qa/
  CURRENT_STATE.md` (new "QA code updated" section, updated "what is not
  currently proven"), `pipeline/agents/lena/70_visual_qa/RULES.md` (closed
  the "known gap" note, updated the false-green section and the "not yet
  decided" list), `pipeline/change_notes/NEXT_SESSION_START.md` (new bullet
  in "Current state," resolved the "New candidate next step" into a "done"
  note), this §14 entry, and the separate technical changelog.

### Next step
Not yet decided: whether to add the four deferred checklist dimensions
(hook/variety/sexy-safe/scene-variety), pick a further folder-native slice,
or something else. Ask before proceeding.

---

**2026-07-06 -- Hook/variety QA schema v2 built (approved design memo, then implemented)**

- Per an audit-first flow (no-code design memo covering: new fields vs. a
  separate block, gating vs. advisory per field, scoring method, pass/fail
  criteria, interaction with existing hard-gating fields, over-rejection
  avoidance, future formula-repetition detection, files needing updates,
  no-render validation), the user approved the design and its exact
  parameters, then approved implementing it.
- `pipeline/qa/lena_photo_qa.py`: `SCHEMA_VERSION` bumped `"1"` -> `"2"`;
  added `LEGACY_SCHEMA_VERSIONS_WITHOUT_PRODUCTION_SCORING = {"1"}` so
  existing on-disk QA files (both still `"1"`) are exempt from the new
  requirement and validate unchanged, no migration. Added a new sibling
  block, `production_scoring` (`PRODUCTION_SCORING_FIELDS`), separate from
  `QA_CHECKLIST_FIELDS` (different kind of judgment; two of the four fields
  aren't even single-render properties):
  - `hook_strength` (`weak`/`moderate`/`strong`/`unreviewed`) -- `weak`
    forces `overall: fail`; `moderate`/`strong` both pass, deliberately not
    a strict bar.
  - `styling_sexy_platform_safe` (`pass`/`fail`/`not_applicable`/
    `unreviewed`) -- `fail` forces `overall: fail`. Covers both named
    hard-reject extremes (too covered/frumpy, or too explicit/unsafe) on
    the actual produced outfit.
  - `outfit_variety_vs_recent_posts` / `scene_variety_vs_recent_posts`
    (`pass`/`fail`/`not_yet_measured`/`unreviewed`) -- **advisory only**,
    cannot affect `overall` under any value. No history-comparison tracker
    exists yet to measure these honestly -- gating on an unmeasured signal
    was explicitly rejected in the design memo as an over-rejection risk.
  `validate_qa_result()` extended additively: existing checklist logic is
  untouched; new checks require/validate `production_scoring` only when
  `schema_version` isn't a legacy version, and only `hook_strength`/
  `styling_sexy_platform_safe` can force the false-green rule.
  `wardrobe_class_fidelity` is unaffected -- still diagnostic-only.
- Validated (no render, no provider call, no `.env` edit, no publish, no
  prompt/executor/routing change): `py_compile` clean; reloaded both real
  on-disk QA files (`2026-07-05-02-photo_qa.json`,
  `2026-07-06-03-photo_qa.json`, both `schema_version: "1"`) -- both still
  validate with zero errors; a freshly built v2 template validates cleanly
  in its all-unreviewed state; a standalone script proved all 6 requested
  checks (A: hook=weak+pass rejected, matching fail+reasons accepted;
  B: hook=moderate/strong+pass accepted; C: styling=fail+pass rejected,
  matching fail+reasons accepted; D: both variety fields at fail/not_yet_
  measured/pass all accepted regardless, 6 combinations; E: wardrobe=fail+
  pass still accepted, regression check; F: all 9 `HARD_GATING_CHECKLIST_
  KEYS` individually still force fail, zero regressions).
- Explicitly deferred, not built: the history-comparison tracker itself
  (working name `pipeline/qa/lena_variety_tracker.py`) that would let the
  two variety fields become more than advisory -- out of scope for this
  change, needs its own future approval. `tools/lena_review_proof_render_
  v1.py` left unchanged (optional surfacing update, not required -- it only
  reads `qa_result.get("overall")`).
- Files updated to record this: `pipeline/agents/lena/70_visual_qa/
  CURRENT_STATE.md` (new "Hook/variety schema v2" section, updated "what is
  not currently proven"), `pipeline/agents/lena/70_visual_qa/RULES.md`
  (closed the gap note fully, documented the new block/gating rules, updated
  "human approval required" and "not yet decided/not yet built"),
  `pipeline/change_notes/NEXT_SESSION_START.md` (two new bullets), this §14
  entry, and the separate technical changelog.

### Next step
Not yet decided: whether to build the variety-history tracker, score a real
render against the new v2 schema for the first time, pick a further
folder-native slice, or something else. Ask before proceeding.

---

**2026-07-06 -- Fifth folder-native slice built: `80_repair/` (documentation only, no code)**

- Per §7.9's original target ("Convert QA failures into minimal, scoped
  fixes... must not do broad rewrites for narrow failures... human approval
  for any code change... hard-fail if repair scope expands beyond the
  smallest responsible layer without justification"), built
  `pipeline/agents/lena/80_repair/` with the minimum 5 files
  (`AGENT.md`, `RULES.md`, `INPUTS.md`, `OUTPUTS.md`, `CURRENT_STATE.md`).
  No repair code exists anywhere in the repo -- this slice is pure decision
  doctrine, grounded in this project's real QA/render history, not
  hypothetical failure modes.
- **Rule zero (the load-bearing rule):** exact wardrobe-catalog mismatch
  alone is never a repair trigger. It only matters to a repair decision if it
  also produces low hook, frumpy/unsafe styling, an incoherent scene, or
  (once measurable) repetition -- each independently checkable from the same
  QA verdict, never inferred from `wardrobe_class_fidelity` alone.
- **Master hard-stop-vs-retryable table**, keyed by failure category, not by
  `overall: fail` alone:
  - **Hard stop, no auto-retry:** unsafe/too-explicit styling (platform-
    safety boundary); identity drift or cartoon/style drift *repeated*
    despite confirmed-intact protections; broken anatomy/hands repeated;
    incoherent scene/caption mismatch with unknown root cause.
  - **Retryable, capped at 1-2 attempts with a stated hypothesis:** weak
    hook (content-level pose/framing choice); frumpy/too-covered styling
    (content-level wardrobe-catalog choice); identity drift or cartoon/style
    drift on *first* occurrence (only after confirming via reference images
    or `prompt_receipt.json` that the failure is real and the relevant floor
    was actually intact); anatomy/hands on first occurrence (one clean
    re-roll, nothing else changed).
  - **No action:** exact wardrobe mismatch alone; either variety field,
    regardless of value (advisory only, no tracker exists).
- **Schema v2 interaction, stated explicitly:** only `HARD_GATING_
  CHECKLIST_KEYS` plus `production_scoring.hook_strength == "weak"` and
  `production_scoring.styling_sexy_platform_safe == "fail"` can trigger a
  repair conversation. `wardrobe_class_fidelity` and both variety fields
  structurally cannot, by design.
- **Endless-loop guardrails:** hard numeric caps per category (never
  unlimited), every retry requires a stated hypothesis, `wardrobe_class_
  fidelity` and `not_yet_measured` can never be the counted reason for a
  retry, and a repeated failure in the same category is itself the signal to
  stop guessing and escalate -- grounded directly in this project's own
  wc_p082 precedent (four renders, then an explicit, user-approved stop).
- Each specific failure type named in the approval (weak hook, too-covered/
  frumpy styling, unsafe/too-explicit styling, identity drift, cartoon/style
  drift, anatomy/hands, incoherent scene/caption mismatch) has its own
  dedicated `RULES.md` section with a concrete default action.
- **Explicitly not done:** no repair code written, no render, no provider
  call, no `.env` edit, no publish, no prompt/executor/routing change. This
  folder cannot authorize a code change on its own -- any actual repair
  implementation still requires its own separate, explicit approval, exactly
  like every prior code change this session.
- Files updated to record this: this §14 entry,
  `pipeline/change_notes/NEXT_SESSION_START.md` (new bullet, updated
  "not yet decided," updated folder count and hard-prohibitions list to
  five slices), and the separate technical changelog.

### Next step
Not yet decided: whether to build the variety-history tracker, score a real
render (or a real `fail` verdict) against the new v2 schema/`80_repair/`
doctrine for the first time, pick a further folder-native slice, or
something else. Ask before proceeding.

---

**2026-07-07 -- Schema v2 + `80_repair` doctrine applied for the first time, to the existing `wc_p082` image (no new render)**

- User asked to apply the new schema and doctrine to the already-existing
  `2026-07-05-02-photo`/`wc_p082` image, explicitly without rerendering:
  `pipeline/kling_library/lena/2026-07-05/2026-07-05-02-photo_seed.png`
  (Kling task `903248497381220361`), viewed directly (not judged from
  metadata/receipts alone, per `70_visual_qa/RULES.md`'s "must never do"
  rule).
- Replaced the QA verdict at `pipeline/asset_review/lena/2026-07-05/
  2026-07-05-02-photo_qa.json` with a new `schema_version: "2"` record
  (validated via `lena_photo_qa.validate_qa_result()` before and after
  writing, and after reloading from disk -- all clean). This is a
  deliberate, explicit replacement of the prior `schema_version: "1"`
  verdict for the same render, not a silent overwrite -- the record itself
  states this and references the superseded verdict.
- **production_scoring result:** `hook_strength: "moderate"` (genuine warm
  expression, direct eye contact, engaged posture -- not weak/static, but a
  standard seated portrait, not dynamic enough for "strong"). `styling_
  sexy_platform_safe: "fail"` -- the mustard coat + scarf covers the torso
  and arms almost completely, the named hard-reject "outfit too covered or
  not visually compelling," independent of the catalog string. Both variety
  fields `"not_yet_measured"` (advisory, no tracker, as designed).
- **Checklist result, unchanged from the prior schema v1 review of this same
  image** (not re-derived from scratch -- this is a re-score of one existing
  image, not a fresh independent judgment): `identity_fidelity: fail`
  (hair/eye color drift, already confirmed against canonical references in
  the original review), `face_realism_anti_generic_drift: fail` (residual
  glossy/idealized quality, not cartoon), `wardrobe_class_fidelity: fail`
  (diagnostic only, correctly contributes nothing to the gate), all other
  fields `pass`/`not_applicable`.
- **`overall: fail`** -- for three legitimate corrected-standard reasons
  (identity drift, too-covered styling, residual unrealism), explicitly
  **not** because of the wardrobe substitution, which is exactly what the
  schema v2 design was built to demonstrate: wardrobe mismatch is visible in
  the record but never the stated reason for failure.
- **`80_repair` classification: HARD STOP**, for two converging reasons: (1)
  this slot already carries a separate, standing prohibition against
  rerendering (`NEXT_SESSION_START.md`'s "Hard prohibitions" -- four prior
  renders, explicit user-approved stop already in force), and (2) even
  judged fresh on `80_repair/RULES.md`'s per-dimension table, three
  independent hard-gating dimensions failed simultaneously (identity,
  styling, realism) -- not one isolated, cleanly-attributable defect a
  scoped retry could target, per master §7.9's own "smallest responsible
  layer" hard-fail condition. No repair action was taken or recommended for
  execution; the hypothetical action (re-pick a less coverage-prone
  wardrobe/scene combination, re-verify identity resolution) was recorded
  for reference only, explicitly not authorized.
- **What this teaches about the current Kling path:** under the old standard
  this render failed for wardrobe-mismatch reasons; under the corrected
  standard + schema v2, it still fails, but for identity/styling/realism
  reasons instead. This is real evidence the path's actual ceiling is
  provider-level output quality, not exact-wardrobe-obedience as previously
  overweighted -- consistent with (not a reversal of) the standing
  conclusion that further fixes here are a provider/conditioning question,
  not a prompt-content one. Does not reopen Kling Omni/BodyLock.
- Files updated: `pipeline/asset_review/lena/2026-07-05/
  2026-07-05-02-photo_qa.json` (the QA record itself -- data, not code),
  `pipeline/agents/lena/70_visual_qa/CURRENT_STATE.md` (new section on this
  first real v2 scoring, updated "what is not currently proven"),
  `pipeline/agents/lena/80_repair/CURRENT_STATE.md` (new section on this
  first real doctrine application, updated "what is not currently proven"
  to note the retryable branch remains untested), this §14 entry,
  `pipeline/change_notes/NEXT_SESSION_START.md` (new bullet, resolved the
  prior open question), and the separate technical changelog.
- Explicitly not done: no render, no Kling/OpenArt/Seedance call, no `.env`
  edit, no publish, no prompt/executor/routing change, no rerender of
  `wc_p082` (the image reviewed was the existing one, viewed directly).

### Next step
Not yet decided: whether to build the variety-history tracker, score a
*different* render to test `80_repair`'s untested retryable branch, pick a
further folder-native slice, or something else. Ask before proceeding.

---

**2026-07-07 -- Production-style proof batch, cartoon failure, and ROOT CAUSE identified via HAR analysis**

- Built and approved a 3-candidate production-style proof plan (optimized for
  hook/variety/sexy-safe/realism/identity, NOT exact wardrobe), all on new
  non-wc_p082 slots: `wc_p030`/flower-shop, `wc_p034`/brunch, `wc_p062`/
  rooftop, written to `pipeline/kling_workorders/2026-07-07/
  daily_workorders.json` via the real prompt-brain functions (forced wardrobe/
  scene selection, no re-randomization).
- No-spend dry-run of all 3: passed (correct APILENA element `315187972322559`,
  `/v1/images/generations` only, no `image_list`, all negative floors survive,
  compact prompt/negative ≤2499 chars).
- Rendered exactly 1 real image (`2026-07-07-01-photo`, `wc_p030`, task
  `903293121000898623`). **Result: fully cartoon/3D-illustrated -- the #1 hard
  reject** -- despite all 29 anti-cartoon style-realism negative terms
  surviving compaction. Candidates 2 and 3 were deliberately NOT rendered.
- **User (correctly) challenged the whole approach**, asking where the
  reference images come from and what's actually needed. This triggered a
  read-only diagnostic that found the root cause:
  1. Downloaded and viewed APILENA's 4 stored reference images directly:
     **photoreal and correct** (warm brunette/caramel hair, dark brown eyes,
     freckles, curvy realistic body). The element is not the problem.
  2. Traced the executor payload: `_submit_photo()` fetches those reference
     image URLs, verifies presence, then **discards them**. The actual
     payload is `element_list:[{element_id}]` + prompt + negative + aspect
     ratio -- **no reference image, no model pin.**
  3. Read-only HAR analysis (approved, sanitized -- no tokens/cookies/signed
     URLs printed) of the Kling **web app's** own element generation
     (`scratch/kling_elements_page.har`, `scratch/herby_kling_elements_page.har`):
     the web app's `POST kling.ai/api/omni/submit-config-template`
     (`type: mmu_omni_image`) sends `fromElementId` + `resourceType:"ELEMENT"`
     + the **actual reference image URL** (`url`/`cover`) + a pinned model
     (`kolors_version:"3.0-omni"`), preceded by an `intent-recognition` call.
     It never touches `api.klingai.com`.
  - **Conclusion:** the current path's failures are conditioning-level. The
    realism/identity lever (pass the reference image + pin the omni model) is
    absent from the current payload; no prompt change can reach it. This
    supersedes the earlier "provider/model-level noncompliance" framing with
    a specific, actionable mechanism.
- **Actions taken (approved):** (1) added `scratch/*.har` + `*.har` to
  `.gitignore` -- the HARs hold session-scoped tokens/signed URLs (confirmed:
  23 + 146 signed/token URLs across the two files) and were previously
  untracked-but-not-ignored; now ignored, confirmed via `git check-ignore`.
  (2) Recorded this finding across the continuity files and sharpened the
  support packet with a new **Question 5**: can the *official* `api.klingai.com`
  image API accept a raw reference/character image directly (URL or base64),
  independent of the web element registry, and if so what endpoint/model-id/
  fields replicate the web app's `kolors_version 3.0-omni` + reference-image
  behavior?
- **Explicitly not done:** no web-app request replayed, no `kling.ai/api/omni/*`
  automation, no endpoint called, no executor code changed, no `.env` edit, no
  publish, no provider switch, no further renders. HAR analysis scripts live
  in the session scratchpad (outside the repo), not in `scratch/` -- nothing
  committable was created.
- Files updated: `pipeline/change_notes/lena_kling_omni_support_packet_
  2026-07-06.md` (§5b + Question 5), `pipeline/knowledge/content_bot/
  CURRENT_PROOF_STATUS.md` (ROOT CAUSE IDENTIFIED section),
  `pipeline/agents/lena/60_executor/CURRENT_STATE.md` (§1a),
  `pipeline/change_notes/NEXT_SESSION_START.md` (banner update + current-state
  bullet + new hard prohibitions), this §14 entry, `.gitignore`, and the
  changelog.

### Next step
Blocked on external input for the real fix (support answer to Question 5).
Do not keep rendering on the current path expecting different results. Other
non-blocked options remain: variety-history tracker, a further folder-native
slice, or something else. Ask before proceeding.

---

**2026-07-07 -- Session checkpoint: RENDER FREEZE on the current path, next action external**

- **User issued an explicit standing directive:** stop all Kling rendering on
  the current `/v1/images/generations` path until the support/API question
  (support packet Question 5) is answered OR the user explicitly approves a
  different test. Recorded as a 🛑 RENDER FREEZE banner at the very top of
  `pipeline/change_notes/NEXT_SESSION_START.md`.
- **Next action is external and user-owned:** the user will send the support
  packet / Question 5 to Kling or APILENA. Nothing on the Claude side advances
  this thread until that response arrives.
- **Standing prohibitions reaffirmed (do not, until support clarifies):**
  render more images, replay web-UI requests, automate against `kling.ai` web
  endpoints, change executor code, touch `.env`, publish, switch providers, or
  reopen Omni/BodyLock.
- No code, render, provider call, `.env` edit, or publish in this checkpoint
  turn -- documentation-only close-out. The prior turn's root-cause finding
  and the `.gitignore`/HAR handling are already fully recorded (see the
  2026-07-07 root-cause §14 entry above and the changelog).

### Next step
External (user sends support packet). On resume: read this file's §0 banners
first, then `NEXT_SESSION_START.md`. Non-blocked work options if the user
wants to proceed without waiting: variety-history tracker, a further
folder-native slice. Ask before proceeding.

---

**2026-07-07 -- Local visual-reference set + preflight reference guard (no render, freeze intact)**

- User unfroze ONLY local visual-reference work. Created
  `pipeline/reference_images/lena/apilena_current/` with the 4 confirmed-correct
  APILENA reference images (`lena_ref_01_face.jpg`, `_02_body_front.jpg`,
  `_03_body_angle.jpg`, `_04_style_anchor.jpg` -- copied from local copies, no
  Kling call; images git-ignored/local-only), a `manifest.json` (element ids,
  per-image roles, sha256, date_captured 2026-07-07, note "canonical Lena
  visual references"), and a standalone preflight guard
  `pipeline/reference_images/lena/apilena_reference_guard.py`.
- The guard blocks any Lena generation payload lacking actual visual reference
  image data with `"BLOCKED: Lena visual references are not included in the
  generation payload."` -- `element_list` alone is explicitly insufficient.
  Dry-run proof confirmed: element_list-only → BLOCKED; reference-bearing
  payloads → pass. `py_compile` clean.
- **Guard is standalone, NOT wired into the executor** (that would be a
  production-routing change, which is frozen). No render, no Kling call, no
  `.env` edit, no publish, no provider switch. Full detail in the changelog's
  2026-07-07 "Local visual-reference set" entry.

### Next step
Unchanged: external (user sends support packet, now including Question 5). The
local reference set + guard are ready for the day a reference-conditioned
official path is confirmed -- but no render happens until the freeze lifts.

---

**2026-07-07 -- Strategic pivot recorded: content_bot reframed as horizontal media infrastructure**

- User approved a strategic pivot: `content_bot` is no longer described as an
  AI-influencer-only system. New framing: horizontal media production
  infrastructure, capable of running multiple independent "media node" types.
- **Lena's role changes in framing only, not in substance.** She is now the
  **R&D/demo/stress-test node** -- the hardest node to get right (identity
  continuity across arbitrary generative content), and everything proven this
  session (QA-schema pattern, folder-native agent docs, repair doctrine,
  continuity discipline) is exactly why the next node can be built lightweight
  and fast. **Not abandoned, not deleted, not downgraded** -- this entire
  master file, every folder-native slice, the render freeze, and the support-
  packet thread remain exactly as they were, on their own timeline.
- **New Revenue Lane, first node: `podcast_repurpose`.** Turns a business's
  existing raw media (podcast episodes, YouTube videos, Zoom/webinar
  recordings, raw clips, testimonials) into a month of short-form content
  (clip ideas, hooks, captions, titles, thumbnail text, posting calendar, CTA
  variants, a content packet, an approval packet, light analytics notes).
  External pitch: "I turn your existing videos, podcasts, calls, and business
  knowledge into a month of short-form social content."
- **Created, docs only:**
  - `pipeline/change_notes/business_media_node_pivot_plan.md` -- the full
    strategic memo (positioning, Revenue Lane vs. Lena R&D Lane, first
    offer, target customers, exact proposed monthly deliverables, MVP
    workflow, folder/node structure, what carries over from Lena vs. what
    stays Lena-specific, 7-day build plan, what not to build yet, how to
    sell the first 3 clients manually).
  - `pipeline/nodes/business_media/podcast_repurpose/` -- 6 lightweight docs
    (`README.md`, `INPUTS.md`, `OUTPUTS.md`, `WORKFLOW.md`, `OFFER.md`,
    `CURRENT_STATE.md`). Deliberately NOT the full Lena-style numbered
    agent-slice pattern (`40_identity_continuity/` .. `80_repair/`) -- that
    structure is proven and available to adopt later, once this node has
    real code and real failure modes worth that level of structure.
- **What carries over from Lena (patterns, not code):** the folder-native
  Markdown documentation convention, the continuity-file discipline, the
  structured QA-verdict pattern (schema-versioned checklist + hard-gating vs.
  advisory + false-green validation), the repair-doctrine pattern (capped
  retries, stated hypotheses), the session-continuity skill pattern, the
  scored hook-bank pattern (`strong_hook_bank_v1.json`'s shape, not its
  Lena-voiced content), and the already-infrastructure-wide repo-knowledge
  layer (`pipeline/knowledge/content_bot/*.md`, not yet updated to reflect
  the new node -- flagged, not done this turn).
- **What stays Lena-specific, explicitly not diluted into the new node:**
  `lena_identity.py`, `lena_prompt_brain.py`, `kling_apilena_api_executor.py`,
  the wardrobe/environment/scene catalogs, `lena_photo_qa.py` and its schema
  v2 `production_scoring` block, all five Lena folder-native agent slices,
  the Kling reference-image investigation/render freeze, and Lena's
  Instagram-specific publishing path.
- **Explicitly not done:** no code beyond Markdown scaffolding, no Kling call,
  no render, no `.env` edit, no publish, no production-routing change, no
  Lena executor patch, no Blotato work, no pricing commitment, no pilot run.
- Files updated to record this: `pipeline/change_notes/NEXT_SESSION_START.md`
  (new STRATEGIC PIVOT banner, reading-list update, current-state bullet, two
  new hard-prohibition items), this file's §0 (pivot-context banner) and this
  §14 entry, and the changelog.

### Next step
Per the pivot memo's 7-day plan: run the MVP workflow by hand on one real or
sample piece of client media before writing any code (highest-value next
step), in parallel with manual outreach toward the first pilot prospects. No
code, no Kling, no render, no Blotato until that manual validation happens.
Lena's own next step is unchanged (external, blocked on the support answer).

---

**2026-07-07 -- Kling reference-by-URL (Variant B) local no-call payload diagnostic built**

- On the Lena visual-reference thread (research: capability matrix + test plan,
  both 2026-07-07), built a standalone no-network diagnostic:
  `tools/diagnostics/lena_kling_reference_url_payload_dryrun.py`. It imports
  only the existing reference guard (`pipeline/reference_images/lena/
  apilena_reference_guard.py`), never the executor or any HTTP-submitting code.
- It builds the **Variant B** Kling omni-image payload -- `model_name:
  "kling-v3-omni"`, `image_list: [{"image": "<APILENA reference URL>"}]`, **no
  `element_list`** -- pulling a real APILENA `cover` resource URL from the
  newest existing local lookup artifact, and runs the guard against it plus the
  current element_list-only shape.
- Result (py_compile clean, run once, no network): **Variant B PASSES** the
  guard (image reference present); the **element_list-only shape is BLOCKED**
  with `BLOCKED: Lena visual references are not included in the generation
  payload.` Prints only sanitized payload shape (no full/signed URLs).
- **APILENA hosted resource URLs are locally available** (6 lookup artifacts,
  2026-07-04..07) and **do not appear to carry `Expires`/`Signature`/
  `Key-Pair-Id`/token** params (only `x-kcdn-pid`) -- they look persistent,
  unlike the time-signed generated-image result URLs; true public
  accessibility unverified without a fetch (out of scope).
- **Proves only that the payload CAN carry the reference URL** and that the
  guard distinguishes it from the blocked element-only shape. **Does NOT prove
  Kling accepts/honors it** -- dropping `element_list` from omni-image is still
  unverified live; needs one later `n=1` test (test plan §7) or support
  Question 5.
- No Kling call, no render, no credit spend, no `.env` edit, no executor
  patch, no production-routing change. RENDER FREEZE intact.

### Next step
Unchanged: real fix blocked on support Question 5 or an explicitly-approved
single `n=1` reference-by-URL live test (Variant B first). The local payload
path is proven ready up to the API call.

---

**2026-07-07 -- BREAKTHROUGH: Variant B live test SUCCEEDED (reference-by-URL fixes the cartoon collapse)**

- Ran the approved single `n=1` live test
  (`tools/diagnostics/lena_kling_reference_url_live_test.py --execute`, double-
  gated). **Pure Variant B: `model_name:"kling-v3-omni"`, `image_list:
  [{"image":"<APILENA cover resource URL>"}]`, NO `element_list`, NO
  `negative_prompt`.**
- **Result: HTTP 200 / code 0 / SUCCEED**, task `903333900062163005`, image
  returned + downloaded. **The official AK/SK endpoint accepted a pure
  image_list-only payload** -- the `1201 element id not found` error is
  bypassed entirely (no element to look up).
- **Output is photoreal** (real skin texture/pores/freckles, natural hair,
  believable sunlight, real depth of field -- the opposite of the earlier
  fully-cartoon element-only render), and **Lena identity is meaningfully
  conditioned** (matches the APILENA reference: hair, dark brown eyes, freckle
  pattern, face structure, gold hoops, curvy build). **The cartoon collapse is
  resolved by sending the actual reference URL**, confirming the root-cause
  diagnosis directly.
- **Remaining issues are normal production steering, not the blocker:** crop
  (upper-body vs. prompted full-body), wardrobe adherence (a white sports-bra-
  style crop top, which would trip Lena's own no-bra-as-outfit publish-safety
  line), and framing. The reference/identity/realism blocker itself is solved.
- Exactly one call; no retries, no second variant, no executor patch, no
  `.env` edit, no web-UI replay, no publish. 5 diagnostic artifacts under
  `pipeline/kling_debug/reference_url_test/ref_url_test_20260707T045501Z/`.
- **Render-freeze status changes in kind:** the freeze existed because the
  cartoon/identity failure was unsolved. It's now solved in principle. The old
  element-list-only path stays frozen (confirmed bad), but the thread is no
  longer "blocked, waiting on support" -- it's "solved, pending an approved
  executor patch + a small reliability check."
- Drafted (proposal only, no code):
  `pipeline/change_notes/lena_kling_reference_url_executor_patch_proposal.md`.

### Next step
Review the executor-patch proposal. No executor change, render, or Kling call
until it's explicitly approved. A small reliability check (a few more n=1
reference-by-URL renders) is worth doing before trusting consistency, under
explicit approval only.

---

**2026-07-07 -- Executor PATCHED for reference-by-URL mode (code change, dry-run validated, no render)**

- Approved and implemented the executor-patch proposal.
  `pipeline/kling_apilena_api_executor.py` now builds the proven Variant B
  payload through a new single-source-of-truth function
  **`build_reference_url_photo_payload()`**: `model_name="kling-v3-omni"`,
  `image_list:[{"image":"<APILENA reference URL>"}]`, **element_list absent,
  negative_prompt absent**, n=1, 9:16. Submits + polls the omni-image endpoint.
- Safety: `apilena_reference_guard.assert_lena_visual_references_present()` is
  enforced twice (inside the builder and again in `_submit_photo` before
  submit) -- an element_list-only Lena payload is blocked (fail-closed). Only
  https reference URLs are accepted (never a local C:\ path). Reference and
  output URLs are sanitized everywhere they're logged/returned (never full
  CDN/signed URLs). The compact negative prompt is still computed for the
  telemetry receipt but is NOT placed in the payload.
- Validation (no network): `py_compile` clean; a dry-run proof monkeypatched
  all three network functions to raise, built the payload via the REAL
  executor function from saved-artifact URLs + a real workorder slot, and
  proved model_name/image_list-present/element_list-absent/negative_prompt-
  absent/n=1/9:16/guard-passes/old-shape-blocked and **0 network calls**.
- No Kling call, no render, no publish, no scheduler, no batch, no second
  variant, no negative-prompt A/B, no `.env` edit, no R2 hosting.
  `tools/lena_preflight.py` unchanged.

### Next step
Exactly one n=1 patched-path live test (real executor wiring, not final
creative quality), then QA -- under explicit approval only ("RUN PATCHED PATH
TEST").

---

**2026-07-07 -- Patched-path live test SUCCEEDED end-to-end + first schema-v2 QA PASS**

- Ran the one approved n=1 patched-path test (slot `2026-07-07-02-photo`,
  `wc_p034`/brunch, never-rendered). **The patched production executor
  succeeded end-to-end:** `ok: true`, `status: downloaded`, task
  `903345804994285660`, `/v1/images/omni-image`. Submitted payload verified:
  `model_name="kling-v3-omni"`, image_list reference-by-URL present,
  **element_list absent, negative_prompt absent**, n=1, 9:16. Output downloaded
  to the production library path
  (`pipeline/kling_library/lena/2026-07-07/2026-07-07-02-photo_seed.png`).
- **Photoreal, Lena identity strongly conditioned, no cartoon collapse.**
  Wardrobe/framing acceptable enough for the API proof and notably better than
  the element-only cartoon path (black ribbed crop + white mini ≈ wc_p034,
  sunglasses in hair matching the pose spec).
- **First schema-v2 QA PASS this session:**
  `pipeline/asset_review/lena/2026-07-07/2026-07-07-02-photo_qa.json`
  (validated). All checklist fields pass/na; `hook_strength=strong`,
  `styling_sexy_platform_safe=pass`. **`overall: pass` is a QA verdict, NOT a
  publish authorization** -- the record sets `publish_ready: false` (needs
  operator sign-off on image+caption; path is only n=2).
- **Reliability is n=2 total** on reference-by-URL -- wiring confirmed,
  consistency not yet proven; not unattended-production ready.
- Exactly one render; no retries, batch, second variant, negative_prompt,
  element_list, `.env` edit, publish, or scheduler.

### Next step
A small reliability check (2-3 more n=1 patched-path renders on fresh slots)
before trusting the path for unattended production -- explicit approval only.
No publish without separate operator approval of image+caption.

---

**2026-07-07 -- Reliability check: 2 more patched-path renders, BOTH PASS**

- Ran the approved 2-render reliability check, one at a time, both through the
  patched executor (verified pure Variant B each: kling-v3-omni, image_list, no
  element_list, no negative_prompt):
  - `2026-07-07-03-photo` (wc_p062 metallic halter midi dress, rooftop, task
    `903349357289414713`) -- **PASS** (photoreal, strong identity, no cartoon,
    real platform-safe dress, hook strong).
  - `2026-07-05-03-photo` (wc_p086 red tank + cargo, flower shop, task
    `903349874073796628`, MAX_SLOTS=1 so frozen wc_p082 untouched) -- **PASS**
    (photoreal, strong identity, no cartoon, platform-safe; bottom rendered as
    cargo pants vs. the specified maxi skirt -- diagnostic-only substitution).
  - Both `overall: pass` schema-v2 QA, `publish_ready: false`.
- **Reference-by-URL is now 4-for-4** photoreal + identity-matched + no cartoon
  across distinct outfits/scenes. **The patched Kling reference-by-URL path is
  reliability-proven enough for controlled production** -- but publishing
  remains **operator-approved only** (explicit image+caption sign-off; nothing
  authorized yet). Exactly 2 renders; no batch/retries/negative_prompt/
  element_list/`.env`/publish/scheduler/patching.

### Next step
No render/publish without explicit approval. Natural next gate: operator
approval of a specific image+caption for a first controlled publish, or
continued controlled production under approval.

---

**2026-07-07 -- First controlled publish packet created (DRAFT, operator-review-required)**

- Prepared one controlled publish packet for the strongest reliability-check
  candidate. **Image:** `pipeline/kling_library/lena/2026-07-07/
  2026-07-07-03-photo_seed.png` (wc_p062 metallic midi dress, rooftop sunset).
  **Packet:** `pipeline/publish_packets/lena/2026-07-07/
  LENA_PUBLISH_PACKET_2026-07-07-03-photo.md`.
- Contents: image path, QA summary (**overall PASS**, `publish_ready: false`),
  5 caption options (≤3 hashtags each), one soft CTA, one Story poll, one
  pinned-comment idea, IG/FB/TikTok platform notes, final operator approval
  checklist. **Recommended caption:** "the sunset showed up. so did I."
- **DRAFT / operator-review-required.** Nothing posted, scheduled, queued, or
  auto-approved. No publish, scheduler, render, Kling call, `.env` edit, or
  batch. Publishing needs Nicolas's explicit sign-off on image + caption +
  platform.

### Next step
Operator review of the packet. Nothing publishes automatically.

---

**2026-07-07 -- Live publish attempt failed safely (no network reached) + publish-path metadata bug found and fixed**

- Per explicit operator approval, attempted the first live publish of
  `2026-07-07-03-photo`. **It failed safely at local contract validation --
  before any network call.** `success_count: 0`, moved to `pipeline/queue/
  failed/`. **Confirmed: no R2 upload, no Meta Graph call, no Instagram post
  occurred.**
- **Root cause (pre-existing, not specific to this post):**
  `PostingManager.validate_post()` in `pipeline/posting_manager.py` discarded
  the queue JSON's original `metadata` (dropping `avatar_nickname`,
  `image_engine`, `image_prompt`) and replaced it with only
  `media_size_bytes`/`media_sha256` before handing it to the publisher module
  -- breaking `instagram_queue_bridge`'s contract validation for any queue
  entry going through the live module-backed path, not just this one.
- **Fix (approved, minimal, one method):** `validate_post()` now copies the
  original queue metadata and merges in the two derived fields instead of
  discarding it.
- **Validated, no network:** `py_compile` clean; a monkeypatched-network
  diagnostic proved `avatar_nickname`/`image_engine`/`image_prompt` all
  survive `validate_post()`, `media_size_bytes`/`media_sha256` are correctly
  added, and the real `instagram_queue_bridge` contract validator now passes
  on the reconstructed payload -- zero network calls made.
- **Queue file restored:** `pipeline/queue/failed/2026-07-07-03-photo.json`
  moved back to `pipeline/queue/2026-07-07-03-photo.json` (failure bookkeeping
  stripped). **Dry-run re-run and passing** (`ok:true`, queue file untouched).
- No publish, no R2 upload, no Meta Graph call, no Instagram post, no
  scheduler, no `.env` edit, no render/Kling call, no caption/image/platform
  change. **Live retry is ready, pending explicit approval** -- no automatic
  retry.

### Next step
Wait for explicit "APPROVED TO PUBLISH..." before running `--live` again. No
automatic action.

---

**2026-07-07 -- Live publish retry: metadata fix confirmed working, Meta/Instagram auth failed (no post created)**

- Per explicit approval, retried the live publish. **The metadata preservation
  fix worked** -- the entry passed contract validation and reached the real
  adapter this time. `resolve_public_media_url()` had no supplied public URL,
  so it **auto-uploaded the image to R2 (succeeded)**; `create_media_container()`
  then called the real Meta Graph API 3 times, and **Meta rejected all 3 with
  `OAuthException` code 190** ("log in to www.instagram.com...") -- a genuine
  Meta-issued error (real `fbtrace_id`s).
- **No Instagram post was created.** Queue file moved to `pipeline/queue/
  failed/2026-07-07-03-photo.json`.
- **Root cause is an external Meta/Instagram auth/account challenge -- NOT the
  queue metadata bug**, which is confirmed fixed and working correctly.
- **Possible cleanup note:** a real R2 object may now exist from this failed
  attempt (`lena/queue-media/2026-07-07/2026-07-07-03-photo.png` or similar)
  -- not deleted this turn; clean up or reuse intentionally later.
- No retry, no `.env` edit, no R2 deletion, no token regeneration, no further
  Meta calls, no render/Kling/scheduler/other publish.

### Next step
**Do not retry live publish until the Meta/Instagram token or account issue is
fixed externally.** Once fixed, a fresh explicit "APPROVED TO PUBLISH..." is
required before any retry.

---

**2026-07-07 -- Token fixed externally, FIRST LIVE INSTAGRAM PUBLISH SUCCEEDED, provenance patch built (commit blocked on unrelated pre-existing hook issue)**

- Nicolas fixed the Meta/Instagram access token externally (outside this
  session) and saved it in the existing `.env` (not edited by Claude).
- **Token/account check PASSED** (env names `META_INSTAGRAM_ACCESS_TOKEN`/
  `META_IG_USER_ID` confirmed present, no values printed; real adapter API
  path returned username `lenadelapineapple.official` -- matches intended
  account).
- Queue file restored (failure bookkeeping cleared), dry-run passed, and
  under explicit "APPROVED TO PUBLISH..." approval, **the live publish
  succeeded**: Instagram media id `18154201054431808`, permalink
  `https://www.instagram.com/p/Daf8-NgFDSu/` (confirmed via a read-only
  follow-up GET). Queue file moved to `pipeline/queue/published/
  2026-07-07-03-photo.json`.
- **Read-only provenance audit**, then an **approved additive patch**:
  `pipeline/publisher/instagram_graph_adapter.py::publish_post()` gained one
  extra non-fatal read-only GET against the **published media id** (per
  explicit correction, not the creation/container id) for `permalink`/
  `instagram_media_type`/`instagram_timestamp`; `pipeline/posting_manager.py`
  now flattens those plus `instagram_media_id`/`caption_variant` into the
  receipt, and `_move_post()` records `published_post_path`. `py_compile`
  clean; isolated no-network validation passed (synthetic payloads + a
  temp-dir `_move_post()` test). **The already-published item's existing
  receipt was deliberately left untouched, not backfilled**, per explicit
  instruction.
- **Git commit blocker RESOLVED.** Root cause confirmed pre-existing and
  unrelated: `.git/hooks/pre-commit` hardcoded `--config=.pre-commit-config.yaml`,
  which is absent from the repo (and `.venv`, so the hook fell through to a
  system-wide `pre-commit` that failed on the missing config before examining
  any file). User's explicit choice was to **remove the stale hook**
  (`.git/hooks/pre-commit` deleted -- it's a local, untracked file, not part of
  the repo). Both patched files then committed cleanly as `8870a82b` "feat:
  add Instagram Graph publisher and posting manager" -- no `--no-verify`
  used, nothing else staged/committed. No `.pre-commit-config.yaml` exists to
  restore; re-adding hook-based checks later needs a fresh explicit decision.
- No render, no Kling call, no `.env` edit, no R2 upload beyond what the
  approved live publish itself required, no other publish, no scheduler, no
  unrelated files staged/committed, no repo clutter cleaned beyond two
  session-generated `.pyc` files.

### Next step
None pending on the publisher/commit thread -- it's closed. Lena render/publish
threads remain in their last recorded state (render freeze narrowed but in
force; no further publish without explicit approval).

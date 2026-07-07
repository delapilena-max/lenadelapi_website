# Start Here — Next Session

**Do not begin work until you've read the files below. Do not rely on chat memory.**

> ## 🔄 STRATEGIC PIVOT (2026-07-07): content_bot is now horizontal media infrastructure
> **`content_bot` is no longer Lena-only.** It is reframed as horizontal media
> production infrastructure capable of running multiple independent "media
> node" types. **Lena is now the R&D/demo/stress-test node** — her generation
> stays **frozen** (see the RENDER FREEZE banner below), but she is **not
> abandoned, deleted, or downgraded**; nothing about her code or docs changed.
> **The new Revenue Lane's first node is `podcast_repurpose`**
> (`pipeline/nodes/business_media/podcast_repurpose/`): turning a business's
> existing raw media (podcasts, YouTube videos, Zoom/webinar recordings, raw
> clips, testimonials) into a month of short-form content (clip ideas, hooks,
> captions, titles, thumbnail text, posting calendar, CTA variants, a content
> packet, an approval packet, light analytics notes). **Docs only so far — no
> code, no clients, no pilot run.** Full plan:
> `pipeline/change_notes/business_media_node_pivot_plan.md`. Explicitly not
> started yet: any processing code, Blotato/posting integration, pricing
> commitment. Read the memo before assuming this node's shape is more decided
> than it is — it's a docs-only MVP plan, one manual pilot pass away from its
> first real validation.
>
> **Day 2 of the 7-day plan done and committed (2026-07-07, commit `fe1c5ce4`,
> docs-only):** `pipeline/nodes/business_media/podcast_repurpose/OFFER.md` now
> carries a pricing hypothesis (anchor $997/month, explicitly unvalidated —
> "pricing commitment" above still means no *validated/final* price, not that
> a number hasn't been written down as a starting guess), and a new
> `PITCH_SCRIPT.md` in the same folder drafts the outbound warm-outreach
> message. Neither has been shown to a real prospect or sent to anyone. Next:
> Days 3–4, manual outreach (outside this repo) — see that folder's
> `CURRENT_STATE.md` for exact status.
>
> ## 🛑 RENDER FREEZE (2026-07-07) — narrowed after the reference-by-URL breakthrough
> **UPDATE 2026-07-07:** the cartoon/identity blocker is **SOLVED IN PRINCIPLE.**
> An approved single `n=1` live test with a pure `image_list`-only payload
> (`model_name:"kling-v3-omni"`, `image_list:[{"image":"<APILENA reference
> URL>"}]`, no `element_list`) returned **HTTP 200 / SUCCEED** and produced a
> **photoreal, identity-matched** Lena. The fix is confirmed working.
>
> The freeze now means: **the OLD `element_list`-only `/v1/images/generations`
> path stays frozen (confirmed to produce cartoons), AND no render / Kling call
> happens without explicit approval.** **EXECUTOR PATCHED + PATCHED-PATH TEST
> PASSED 2026-07-07:** `_submit_photo()` builds the reference-by-URL payload
> (`build_reference_url_photo_payload()`, guard-enforced); one approved n=1
> patched-path render (slot `2026-07-07-02-photo`, task `903345804994285660`)
> **succeeded end-to-end** — photoreal, identity-matched, no cartoon, first
> schema-v2 QA PASS (`overall: pass`, `publish_ready: false`). **RELIABILITY
> CHECK PASSED** — 2 more approved patched-path renders (rooftop wc_p062, task
> `903349357289414713`; flower-shop wc_p086, task `903349874073796628`) both
> PASS, making reference-by-URL **4-for-4** photoreal + identity-matched + no
> cartoon. **The patched path is reliability-proven enough for CONTROLLED
> production; publishing remains operator-approved only** (explicit
> image+caption sign-off — nothing authorized yet).
> **Still do not:** render or call Kling without explicit approval; publish
> without operator image+caption sign-off; replay
> web-UI requests; automate against `kling.ai` web endpoints; touch `.env`;
> publish; switch providers. Support Question 5 is answered empirically for the
> omni-image image_list-only case; sending it remains optional (field-doc /
> multi-image / URL-sourcing clarity only).

> ## ✅ LENA LIVE CHAIN NOW GIT-DURABLE + INFO-HIERARCHY CORRECTED (2026-07-07)
> **The proven Lena photo path is now durable in git — it previously existed
> only on local disk.** Four checkpoint commits, in order: `3bf932ab` (tracked
> the live execution core: `pipeline/kling_apilena_api_executor.py`,
> `pipeline/identity/lena_identity.py`, `pipeline/qa/lena_photo_qa.py`,
> `pipeline/lena_production_job.py`, `tools/lena_preflight.py`), `2c49b348`
> (tracked the queue/scheduling glue: `pipeline/scheduler.py`,
> `pipeline/scheduler_jobs.py`, `pipeline/env_loader.py`,
> `tools/process_queue.py`), `81056cb3` (committed the already-implemented
> negative-prompt tiering repair in `pipeline/prompting/lena_prompt_brain.py`
> plus the photo-first `pipeline/config/lena_kling_contract.json`), and
> `a0407bc2` (corrected a stale source-of-truth conflict in
> `information_hierarchy/Projects/Lena Influencer Node/Instructions/
> Instructions.md`, which previously named the retired `hcr_001`/`wc_p045`/
> BODYLOCK-era scripts as "official"). Combined with the already-committed
> `posting_manager.py` + `instagram_graph_adapter.py` (`8870a82b`), **every
> file in the live chain
> `lena_prompt_brain.py -> kling_apilena_api_executor.py -> lena_photo_qa.py
> -> publish packet/queue -> posting_manager.py -> instagram_graph_adapter.py`
> is now tracked in git with zero working-tree drift from HEAD.**
>
> **Video remains disabled; photo lane first, unchanged.** `lena_kling_
> contract.json`'s video-count fields (`videos_per_day`, `videos_per_day_max`,
> `video_generation_target_per_day`, `max_posts_video_day`) are all `0`; a
> studio Kling element exists for a later, separate video/studio lane but is
> out of scope until that lane is explicitly started.
>
> **`tools/strategy/lena_build_content_packet_dryrun_v1.py` is ideation/
> planning only, not the live publish-packet builder.** It doesn't read
> rendered images, QA schema v2, reference-by-URL render artifacts, queue
> files, or publish receipts, and writes to a different location using a
> different prompt schema than the live chain. Corrected in the
> information-hierarchy doc above; the script itself was not touched.
>
> **Next build target, if pursued: `90_content_packet/`, not
> `95_publish_gate/` yet** — a real, owned tool that builds a publish packet
> from an actual QA-passed render (the way the one successful 2026-07-07
> packet was built by hand). `95_publish_gate/` (a formal approval-gate
> artifact) comes *after* a real packet artifact exists to gate — building it
> first would have nothing real to gate. Neither is built yet; building
> either needs its own separate approval, one slice at a time, per this
> file's existing folder-native-slice discipline.
>
> **Do not work on `business_media`/`podcast_repurpose`, sales, or outreach
> from this thread** — that lane is explicitly paused; Lena is the current
> priority. No code was changed by this checkpoint — all four commits above
> either tracked existing on-disk files as-is or corrected documentation;
> nothing was patched, no render/Kling call/publish/R2 upload/`.env` edit
> occurred.

> ## ✅ `90_content_packet/` SLICE CREATED, DOCS-ONLY (2026-07-07, commit `61ae69b3`)
> **`pipeline/agents/lena/90_content_packet/` now exists**, following the
> established five-file Lena agent-slice pattern (`AGENT.md`, `RULES.md`,
> `INPUTS.md`, `OUTPUTS.md`, `CURRENT_STATE.md`) already used by
> `40_identity_continuity/` through `80_repair/`. **Docs/design only — no
> packet-builder code exists yet.** It owns the *intended* real publish-
> packet artifact built from an actual QA-passed render (the target shape is
> grounded in the one real hand-built precedent,
> `pipeline/publish_packets/lena/2026-07-07/
> LENA_PUBLISH_PACKET_2026-07-07-03-photo.md`) — not a claim that any tool
> produces this automatically today. Per its own `RULES.md`: it does not
> call Kling, render, publish, upload to R2, edit `.env`, auto-approve a
> post, or ever set `approved_for_live_publish: true`.
> `tools/strategy/lena_build_content_packet_dryrun_v1.py` **remains ideation/
> planning only** — untouched, not repurposed, not treated as this slice's
> input.
>
> **Next safe task, either:** (1) a read-only scoping pass for what real
> `90_content_packet` packet-builder code would need (still no code written
> without separate explicit approval), or (2) a further, explicitly-approved
> Kling reliability check on the reference-by-URL photo path. **Do not start
> `95_publish_gate/` yet** — it comes only after a real packet
> artifact/tool exists to gate. **Do not start video API work or use the
> studio element yet. Do not work on `business_media`/sales/outreach.** No
> code, Kling call, render, publish, R2 upload, or `.env` edit occurred in
> this checkpoint.

> ## ✅ `90_content_packet/` FIRST REAL TOOL BUILT, TWO BATCHES (2026-07-07, commits `346d0006` + `ea139e69`)
> **`90_content_packet/` now has its first real tool:
> `tools/lena_build_publish_packet_v1.py`.** Resolves a named `--date`/`--slot`,
> requires the rendered image to exist on disk, requires an existing QA
> verdict, runs `lena_photo_qa.validate_qa_result()`, and hard-fails unless
> `overall == "pass"` — no packet is ever built ahead of a real QA pass
> (`90_content_packet/RULES.md` Rule zero).
>
> **Batch 1 (`346d0006`): read-only resolver.** Wrote nothing. Deliberately
> does not reuse `tools/lena_review_proof_render_v1.py`'s
> `build_review_bundle()`, because that function calls
> `lena_photo_qa.save_qa_template()`, which **does write** an unreviewed QA
> scaffold the first time a slot has no QA file — a correct side effect for a
> review helper, wrong for a resolver that must hard-fail with zero writes.
>
> **Batch 2 (`ea139e69`): Markdown packet writing only.** Writes to
> `pipeline/publish_packets/lena/<date>/LENA_PUBLISH_PACKET_<slot_id>.md`.
> **Non-clobber default** — aborts unless `--force` is passed; `--force`
> overwrites only that exact resolved file, never a directory. **Still does
> not write a queue draft, still does not write to `pipeline/queue/`, still
> has no `--live`, `--approve`, or `--queue` flag** — no code path in the
> tool can call Kling, render, publish, upload to R2, or read/edit `.env`; no
> imports of `posting_manager`, `process_queue`, the Kling executor, any
> publisher/API module, `requests`, or `urllib`. Validated against the real
> QA-passed `2026-07-07-03-photo` slot (positive case), two real
> missing/failing-QA slots (clean aborts, zero writes), a real non-clobber
> abort against the existing hand-built packet (untouched), and a temporary
> `--out-dir scratch/` write that was inspected then deleted.
>
> `pipeline/publish_packets/lena/` and `pipeline/queue/` remain untracked,
> pre-existing artifact directories — not staged, not committed, not touched
> by either batch.
>
> **Batch 3 (`--queue-draft` JSON emission) remains optional/deferred,
> needs separate explicit approval.** `95_publish_gate/` remains deferred
> until the packet/queue-draft behavior is settled. Video API work, the
> studio element, and `business_media`/sales/outreach remain out of scope.

> ## ✅ `90_content_packet/` BATCH 3 COMMITTED -- ALL THREE BATCHES NOW COMPLETE (2026-07-07, commit `e9edb3d9`)
> **Batch 3 is committed.** `tools/lena_build_publish_packet_v1.py` now
> supports an optional `--queue-draft` flag. When passed, it writes a
> queue-shaped draft JSON to
> `<out-dir>/<date>/<slot_id>_queue_draft.json` alongside the Markdown
> packet — **default location is under `pipeline/publish_packets/lena/`,
> never `pipeline/queue/`.**
>
> **Hard guard, checked before any write this run when `--queue-draft` is
> passed:** `_assert_not_inside_live_queue()` resolves the intended
> queue-draft path and aborts the entire run — including the Markdown
> packet, zero files written — if that path is inside or equal to
> `pipeline/queue/`. Confirmed to reject both `--out-dir pipeline/queue`
> and `--out-dir pipeline/queue/something`.
>
> **Queue draft fields are intentionally safe:**
> `approved_for_live_publish: false` (hardcoded), `operator_review_required:
> true` (hardcoded), `metadata.queue_draft_only: true` (hardcoded), caption
> is a placeholder string only (never auto-selected), and
> `metadata.publish_packet_path` points back to the Markdown packet.
>
> **Still true of the whole tool, all three batches:** no `--live`,
> `--approve`, or any publish flag exists; no import of `posting_manager`,
> `process_queue`, any publisher/API module, the Kling executor, `requests`,
> `urllib`, or `pipeline.env_loader`; no code path can call Kling, render,
> publish, upload to R2, or read/edit `.env`.
> `pipeline/publish_packets/lena/` and `pipeline/queue/` remain untracked,
> pre-existing artifact directories — not staged, not committed.
>
> **`95_publish_gate/` is now the next reasonable docs-only design
> target** — the packet/queue-draft behavior this slice depends on is
> settled (all three batches committed). Video API work, the studio
> element, and `business_media`/sales/outreach remain out of scope.

> ## ✅ `95_publish_gate/` DOCS-ONLY SLICE CREATED (2026-07-07, commit `3a4c1412`)
> **`pipeline/agents/lena/95_publish_gate/` now exists**, following the
> standard five-file slice pattern (`AGENT.md`, `RULES.md`, `INPUTS.md`,
> `OUTPUTS.md`, `CURRENT_STATE.md`). **Docs-only — no code/tool exists
> yet.** It owns the *future* durable human approval decision record,
> sitting between `90_content_packet/` and the live publish flow. It does
> not build packets, does not build queue drafts, does not QA images, does
> not move/copy files into `pipeline/queue/`, does not run
> `tools/process_queue.py`, does not call `posting_manager.py`, does not
> publish, and does not auto-approve.
>
> **Preserves the safety doctrine as hard blocks (once any code exists):**
> a placeholder caption, more than 3 hashtags, QA not `pass`, a missing
> packet, a missing expected queue draft, or a missing/false
> `metadata.queue_draft_only` all block recording approval; so does unclear
> operator approval. **Queue-draft fields stay untouched forever** —
> `approved_for_live_publish: false`, `operator_review_required: true`, and
> `metadata.queue_draft_only: true` are never mutated by this slice; any
> future approval decision would be recorded as a *separate* artifact, not
> an edit to the draft.
>
> **Next safe task: read-only scoping for a future approval-record
> checker/builder** — still no code without separate explicit approval. A
> further Kling reliability check remains a separate, unrelated track
> needing its own explicit approval. Video API work, the studio element,
> and `business_media`/sales/outreach remain out of scope.

> ## ✅ FIRST LIVE INSTAGRAM PUBLISH SUCCEEDED (2026-07-07) — read this before assuming publish is still blocked
> Nicolas manually fixed the Meta/Instagram access token (external, outside
> this session). Token/account check then passed (username
> `lenadelapineapple.official`). Under explicit "APPROVED TO PUBLISH..."
> approval, `python tools/process_queue.py --live --media-type photo --date
> 2026-07-07` **succeeded**: Instagram media id `18154201054431808`, permalink
> `https://www.instagram.com/p/Daf8-NgFDSu/`. Queue file moved to
> `pipeline/queue/published/2026-07-07-03-photo.json` (+ sibling
> `.receipt.json`) — **left untouched/not backfilled, per explicit
> instruction.**
>
> **Provenance patch implemented, validated, and COMMITTED (2026-07-07):**
> `pipeline/publisher/instagram_graph_adapter.py::publish_post()` now does one
> extra non-fatal read-only GET (against the **published media id**, not the
> creation id) to capture `permalink`/`instagram_media_type`/
> `instagram_timestamp`; `pipeline/posting_manager.py`'s receipt dict now
> flattens `instagram_media_id`/`permalink`/`instagram_media_type`/
> `instagram_timestamp`/`caption_variant`, and `_move_post()` now records
> `published_post_path`. `py_compile` clean on both; isolated no-network
> validation passed. The already-published item's existing receipt was
> deliberately **not** backfilled.
>
> **✅ COMMIT BLOCKER RESOLVED, patch committed as `8870a82b` (2026-07-07):**
> the broken `.git/hooks/pre-commit` (a `pre-commit`-framework hook with no
> matching `.pre-commit-config.yaml` anywhere in the repo — pre-existing,
> unrelated to any of this session's file content) was **deleted** per
> explicit operator choice ("Remove the stale hook"), not bypassed with
> `--no-verify`. Both patched files were then committed cleanly: `8870a82b`
> "feat: add Instagram Graph publisher and posting manager"
> (`pipeline/posting_manager.py`, `pipeline/publisher/
> instagram_graph_adapter.py`). Nothing else was staged or committed in that
> commit — the other modified/deleted files seen in `git status` remain
> untouched, out of scope. No `.pre-commit-config.yaml` exists to re-add; if
> hook-based checks are wanted again later, that needs a fresh explicit
> decision, not an assumption. **No commit blocker remains for this patch.**
> These three checkpoint continuity docs (this file,
> `lena_agentic_pivot_changelog.md`, `lena_filesystem_native_agent_pivot_master.md`)
> were themselves reviewed and the latter two committed as `77e6adf6` "Track
> Lena agentic pivot checkpoint docs"; this file was intentionally excluded
> from that commit pending this accuracy fix.

> ## ⚠️ STANDARD CORRECTION (2026-07-06): exact wardrobe obedience is NOT the production goal
> Earlier this session, "wrong outfit" was treated as an automatic production
> failure. **That was wrong and has been corrected.** Exact wardrobe match is
> a *diagnostic* signal only (does the model literally follow the catalog
> outfit text?) — it is not the production bar.
>
> **The actual production goal:** varied Lena photos, different outfits over
> time, sexy/high-hook/viewer-grabbing, somewhat-to-moderately revealing,
> platform-safe, realistic enough, coherent scene, close-enough identity
> continuity, no obvious AI/cartoon/anatomy failure. A wardrobe substitution
> is fine if the result is still stylish, sexy/hooky, platform-safe, not
> frumpy, not boring, not repetitive, coherent with the scene, and not
> identity-breaking.
>
> **Priority order:** (1) hook strength, (2) outfit variety, (3) sexy but
> platform-safe styling, (4) realism, (5) identity continuity, (6) scene
> variety, (7) caption/image coherence, (8) exact wardrobe obedience —
> diagnostic only.
>
> **Hard rejects (the real production blockers):** cartoon/illustration/
> obvious-AI look; broken anatomy/bad hands/extra limbs; face identity badly
> off; boring/frumpy/non-hook outfit; outfit too covered or not visually
> compelling; too explicit/unsafe; scene makes no sense; same outfit/pose/
> location formula repeating across posts; caption/image totally mismatched;
> low-quality/fake-looking output.
>
> Full detail: `pipeline/agents/lena/70_visual_qa/RULES.md`'s "Production QA
> standard correction" section. This reframes (does not reverse) the 4th
> render's classification below and the negative-prompt repair's conclusion —
> see those sections for the corrected reasoning. **The QA code
> (`pipeline/qa/lena_photo_qa.py`) has NOT been updated to match yet** —
> apply this standard manually when reading any checklist that still labels
> a wardrobe mismatch as `fail`.

> ## 🔒 PARKED: Kling Omni/BodyLock investigation (2026-07-06)
> User-approved, clean stop. **Do not run more Kling tests. Do not try more
> element IDs. Do not try more payload schemas. Do not recreate Lena as an
> API-visible element unless support/docs confirm the correct method. Do not
> touch `.env`. Do not render.** The only next action on this thread is
> external: send/read the response to
> `pipeline/change_notes/lena_kling_omni_support_packet_2026-07-06.md`. This
> is not a "figure out what to try next" state — it's fully closed until that
> external input arrives. See "Current branch / thread" below for full detail.
>
> **2026-07-07 update:** the root cause of the image-quality failures is now
> identified (current executor sends `element_list` only — no reference image,
> no model pin; the web app sends the reference image + `kolors_version
> 3.0-omni`). The support packet now carries a sharpened **Question 5**: can
> the *official* `api.klingai.com` API accept a raw reference image directly
> (image URL or base64), independent of the web element registry? This is the
> highest-value thing to get answered. Still external-only — **do not replay
> the web-app `kling.ai/api/omni/*` endpoints, do not automate against the web
> session, do not change executor code, do not switch providers** until the
> answer arrives.

## Read these first, in order

1. This file (note the STRATEGIC PIVOT banner above — `content_bot` is no longer
   Lena-only).
2. `pipeline/change_notes/business_media_node_pivot_plan.md` — the new Revenue
   Lane framing, if this is your first read of it. Not yet reflected in
   `pipeline/knowledge/content_bot/REPO_MAP.md` (unedited this pass — still
   Lena-only in its own text; the pivot memo is the current source of truth
   for the new framing until that file is updated).
3. `pipeline/knowledge/content_bot/REPO_MAP.md` — what the repo's major folders own
   (Lena-focused; see note above).
4. `pipeline/knowledge/content_bot/LIVE_PATHS.md` — what's actually live vs paused right now.
5. `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` — read §0
   "Current State" at the top in full.
6. `pipeline/change_notes/lena_agentic_pivot_changelog.md` — read at least the most
   recent dated entry at the bottom.

Then summarize back to the user: where we are, what was just finished, what's
blocked, current live path, and next approved step — grounded in those files, before
doing anything else.

## Session skills (convenience wrappers, not source of truth)

Two Claude Code skills exist to run the two procedures above:
`.claude/skills/lena-session-start/SKILL.md` (runs the "read these first" +
summarize steps) and `.claude/skills/lena-session-checkpoint/SKILL.md` (runs
the checkpoint/close-out steps from "Hard prohibitions" below). They are
pointer-only — they contain no doctrine of their own and defer to this file
and the other continuity files if anything ever disagrees. Added 2026-07-06.

## Current state (as of the last session, 2026-07-06; strategic pivot added 2026-07-07)

- **STRATEGIC PIVOT (2026-07-07): `content_bot` reframed as horizontal media
  infrastructure.** New Revenue Lane, first node `podcast_repurpose`
  (`pipeline/nodes/business_media/podcast_repurpose/README.md` +
  `INPUTS.md`/`OUTPUTS.md`/`WORKFLOW.md`/`OFFER.md`/`CURRENT_STATE.md`), docs
  only, no code, no clients, no pilot run yet. Lena reframed as the R&D/demo/
  stress-test node — not abandoned, not downgraded; her generation stays
  frozen per the RENDER FREEZE banner above, on its own separate timeline.
  Full plan: `pipeline/change_notes/business_media_node_pivot_plan.md`. No
  code, no Kling call, no render, no `.env` edit, no publish, no Lena executor
  patch, no Blotato work, no production-routing change.
- **Pipeline/code path: validated.** Batches 1-7 done. Identity resolution,
  `element_list`-only submission, and scene/continuity/framing/garment-obedience
  compaction survival (positive and negative) are all confirmed correct across every
  render this session.
- **Kling image generation on the tested proof slot: failing.** Three consecutive
  renders on `2026-07-05-02-photo` (wc_p082) produced the wrong outfit despite a
  verified-correct pipeline each time; the third also drifted into a cartoon/
  illustrated style. Classified as recurring model-level noncompliance, not a
  pipeline defect. **This proof lane is paused, not resolved.** See
  `pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md` for the exact detail.
- **Repo-knowledge/session-recovery layer built and accepted** (this file plus
  `pipeline/knowledge/content_bot/*.md`), built 2026-07-06, because session
  continuity — not more agent folders — was the biggest operational risk.
- **Second folder-native slice built:**
  `pipeline/agents/lena/70_visual_qa/` (2026-07-06), wrapping
  `pipeline/qa/lena_photo_qa.py` + `tools/lena_review_proof_render_v1.py` +
  `pipeline/asset_review/lena/`. Documentation only — no code moved.
- **Third folder-native slice built:** `pipeline/agents/lena/60_executor/`
  (2026-07-06), wrapping `pipeline/kling_apilena_api_executor.py` (live path),
  `tools/lena_bodylock_diagnostic_v1.py` (parked path), `pipeline/
  lena_production_job.py` (orchestrator), and `tools/LEGACY_PROVIDER_
  SURFACES.md` as legacy context. Documentation only — no code moved.
- **Fourth folder-native slice built:** `pipeline/agents/lena/
  50_prompt_builder/` (2026-07-06), wrapping `pipeline/prompting/
  lena_prompt_brain.py` (source prompt/negative-prompt construction,
  wardrobe/scene/framing/garment-obedience locks) and documenting what the
  executor's prompt receipt does/does not prove. Confirmed the negative-
  prompt budget overflow directly: base `NEGATIVE_PROMPT` constant measures
  **2734 chars** against a **2499-char** cap — a 235-char overflow before any
  outfit-specific term is added. Documented, not fixed (explicit instruction).
  Documentation only — no code moved. Four slices now exist:
  `40_identity_continuity/`, `50_prompt_builder/`, `60_executor/`,
  `70_visual_qa/`.
- **Negative-prompt budget: REPAIRED (2026-07-06), code change, no render.**
  Approved implementation of the design memo. In `pipeline/prompting/
  lena_prompt_brain.py`: `NEGATIVE_PROMPT` restructured from one flat 2734-
  char/139-term string into five tiered constants (core / style-realism /
  public-safety / body-anatomy / optional-fill); 2 confirmed exact-duplicate
  terms removed (2734 → 2696 chars, 139 → 137 terms); all other terms
  preserved unchanged. In `pipeline/kling_apilena_api_executor.py`:
  `_build_compact_negative_prompt()` now applies 6 reserved floors (the
  pre-existing garment-obedience floor, unchanged and first, plus 5 new
  ones), and `_build_prompt_receipt()` reports reserved/used/survived for
  each. Validated via `py_compile` + no-network dry-run calls only across 6
  outfit classes × 2 lane types (12 cases): compact negative prompt always
  ≤2499 chars (measured 2488–2499); every always-on floor survived in all 12
  cases; garment-obedience 11/11 re-confirmed unchanged. No render, no
  Kling call, no `.env` edit, no positive-prompt change at implementation
  time. Full detail: changelog's "Negative-prompt budget repair implemented"
  entry.
- **FINAL, ACCEPTED CLASSIFICATION (2026-07-06, user-confirmed) -- read
  alongside the STANDARD CORRECTION banner at the top of this file, which
  narrows point 3/4 below:**
  1. The negative-prompt budget repair is **retained** -- not reverted,
     not provisional.
  2. It **improved style-realism protection** (no more cartoon/3D-
     illustration drift on the one render tested).
  3. It **did not solve exact wardrobe obedience** -- 4th consecutive
     outfit-class miss on `wc_p082`. **Per the standard correction, this is
     not itself a production failure** -- the real concern with that
     specific render is that the substituted coat+scarf reads as too
     covered/low-hook, not that it missed the catalog string.
  4. The current Kling `/v1/images/generations` path is **usable only as
     quality-limited / proof-limited for the exact-wardrobe diagnostic** --
     whether it's usable for actual production (under the corrected
     standard) has not been formally assessed.
  5. **The next meaningful fix, if pursued, is a provider/conditioning
     strategy change, not more prompt-content tweaking.** Ties to the
     parked Kling Omni/BodyLock thread, not to further edits here. (This
     point is about conditioning fidelity generally, not specifically about
     exact wardrobe match, which is no longer the goal.)
  Standing, settled prohibitions from this classification: do not rerender
  `2026-07-05-02-photo`; do not patch `lena_prompt_brain.py`/
  `kling_apilena_api_executor.py` again on the wardrobe-obedience theory;
  do not reopen Kling Omni/BodyLock; no `.env` edit; no publish.
- **Negative-prompt repair proof render: RUN, RESULT FAIL (2026-07-06).**
  One controlled render on the same previously-failed comparison slot
  (`2026-07-05-02-photo`/wc_p082, current `/v1/images/generations` path
  only) using the repaired negative prompt (only the negative_prompt field
  was refreshed via `build_negative_prompt_for_catalog()`/
  `build_public_lane_negative_prompt()` against the live wc_p082 catalog
  entry; positive prompt/wardrobe/scene left byte-identical to the 3 prior
  failed attempts for a true single-variable comparison). Pre-flight
  confirmed: all negative floors would survive, compact negative 2496/2499
  chars, correct slot/element, no `image_list`, current path only, no
  Omni/BodyLock. Render succeeded technically (task `903248497381220361`,
  element `315187972322559`/APILENA, `/v1/images/generations`,
  `payload_no_image_list: true`) and the receipt confirmed every predicted
  floor exactly (garment-obedience 11/11, core 21/21, style-realism 29/29,
  public-safety 17/17, body-anatomy 32/37, outfit-specific 7/29). **Visual
  QA verdict: FAIL -- 4th consecutive wrong-outfit miss on this exact slot**
  (rendered a mustard coat + scarf outerwear substitution instead of the
  specified white tank + black mini skirt), plus identity drift (hair/eye
  color) and a residual glossy/beauty-filter quality. **Style/cartoon-drift
  did measurably improve** -- not a full cartoon/3D-illustration failure
  this time, unlike the 3rd pre-repair render. **Conclusion: the negative-
  prompt repair improved style-realism but did not fix the wardrobe-
  substitution failure, even with near-maximal negative-prompt protection
  now guaranteed present** -- strong further evidence the wrong-outfit
  failure is model/provider-level, not prompt-content-level. Full QA:
  `pipeline/asset_review/lena/2026-07-05/2026-07-05-02-photo_qa.json`
  (superseded the stale 3rd-failure verdict). `.env` untouched throughout;
  exactly one image generated; no publish.
- **Branch 2 (provider/conditioning) investigation: started, read-only, major
  finding (later partially revised -- see below).** Traced the exact endpoint/
  model/payload used by `kling_apilena_api_executor.py` (`POST https://
  api.klingai.com/v1/images/generations`, no `model_name` sent, `element_list`
  only, no `image_list`) and compared it against a git-committed recipe
  (`README_BODYLOCK_PRODUCTION_RULES_2026-06-24.md`, commit `f5908ac6`,
  currently deleted from the working tree) that documented a different endpoint
  (`/v1/images/omni-image`), model `kling-v3-omni`, `element_list` +
  `image_list` together, and a ~400-char prompt as the approved production path.
  **Caution:** a later investigation (below) found this recipe's real-world
  success is less certain than first described -- see the 2026-07-06 "element
  registry" investigation entry. The current live path has still never tested
  the omni-image endpoint. Full memo in the 2026-07-06 changelog entries.
  Read-only -- no code changed, no render run, no `.env` touched, nothing
  published.
- **Branch 2 diagnostic tooling built and run once (2026-07-06).** Standalone,
  opt-in-only script `tools/lena_bodylock_diagnostic_v1.py` (does not touch the
  live executor, `.env`, or containment guards) was built, dry-run-verified, then
  run exactly once with `--execute` (user-approved anchor: live APILENA element's
  own cover image). **Result: submission rejected before any generation task was
  created.** `POST https://api.klingai.com/v1/images/omni-image` returned
  `HTTP 400 {"code": 1201, "message": "Element id not found: 315187972322559"}`.
  Zero credits spent (no `task_id` issued, no image produced). This is a new,
  significant finding: the AK/SK-authenticated official API (used by
  `/v1/images/omni-image`) cannot see an element ID that works fine on
  `/v1/images/generations` (the current live path, resolved via a web-session-
  scraped endpoint, different auth). Likely means this element only exists in
  Kling's web-UI element registry, not the AK/SK-visible one -- see
  `pipeline/kling_debug/bodylock_diagnostic/bodylock_diagnostic_20260706T200037Z/`
  for the full request/response. **No BodyLock-recipe image has been produced or
  judged yet.**
- **Element-registry no-spend investigation (2026-07-06): no confirmed working
  element for omni-image + AK/SK exists anywhere in this repo's history.**
  Searched git history (`git show`/pickaxe across all commits, including
  deleted/uncommitted files) and every `.env.bak_*` snapshot on disk (11 total,
  2026-06-17 through 2026-06-25). Findings:
  - A second, later element ID (`u_313006264506046`, using a different
    `fromElementId`/`elementVersion` payload schema, committed 2026-06-25/26 --
    one day after BodyLock) exists in two commits, but has **zero evidence** of
    ever being run live anywhere in the repo (its result directory was never
    created; it was gitignored the same day it was introduced). That same
    later script explicitly lists BodyLock's own approach (`element_list`,
    `Goodtest1`) as a blocked/wrong pattern -- meaning this repo's own history
    shows BodyLock's recipe was already considered superseded within a day of
    being committed.
  - "Goodtest1" is only ever a *name*, never a stored URL, anywhere in this
    repo -- unrecoverable.
  - `KLING_LENA_ELEMENT_ASSET_ID` (BodyLock's required env var) appears in
    exactly 2 of 11 `.env` backups (both 2026-06-22), set to `313524913093322`
    -- the exact ID BodyLock's own script hard-rejects as retired. It is
    **absent** from the 2026-06-25 backup (same day as the BodyLock hardening
    commit) and every other snapshot, including today's `.env`. This means
    BodyLock's live runner would have aborted, not succeeded, at the one
    `.env` snapshot closest to its own creation date.
  - The one positive-looking signal (the 2026-06-24 publish-dispatch record)
    references a filename matching this project's *normal* daily-workorder
    naming, not BodyLock's own live-runner output naming -- suggesting it more
    likely came from the normal pipeline with BodyLock settings patched in,
    not a proven standalone AK/SK + omni-image success.
  - **Conclusion: no element ID has ever been confirmed, with real evidence in
    this repo, to work on the AK/SK-authenticated omni-image endpoint** --
    not APILENA, not BodyLock's own (ID never captured), not
    `u_313006264506046` (never run). Full detail in the 2026-07-06 changelog
    entry ("Element-registry investigation").
- No retry attempted, no code changed, no `.env` touched, nothing called,
  nothing published for either of the above -- both were read-only.
- **Two pre-existing `.har` browser captures** already in the repo
  (`scratch/kling_elements_page.har`, `scratch/herby_kling_elements_page.har`)
  were found and domain-inspected: neither ever contacts `api.klingai.com` --
  the web UI's element/omni-image flow lives entirely under `kling.ai`.
  Corroborates the registry-separation theory.
- **Decision: Kling Omni/BodyLock diagnostic path is now PAUSED.** The user
  judged the HAR evidence sufficient to stop further guessing. A support
  packet was written:
  `pipeline/change_notes/lena_kling_omni_support_packet_2026-07-06.md`. No
  more Kling spend, element-ID guessing, or payload-schema guessing on this
  thread until Kling/APILENA support responds. The current
  `/v1/images/generations` path remains the only working Kling path, quality
  limitations and all.
- **Visual QA code updated to match the corrected production standard
  (2026-07-06, approved and implemented).** `pipeline/qa/lena_photo_qa.py`
  no longer forces `overall: fail` when only `wardrobe_class_fidelity`
  fails -- new `DIAGNOSTIC_ONLY_CHECKLIST_KEYS` / `HARD_GATING_CHECKLIST_
  KEYS` constants, and `validate_qa_result()`'s false-green check now only
  iterates the hard-gating set. No field added/removed/renamed; existing QA
  JSON files unaffected. Validated via `py_compile`, reload of the real
  on-disk `wc_p082` QA file, and two standalone checks (wardrobe-only fail
  now validates with `overall: pass`; every other field still forces
  `overall: fail`). Dedicated fields for hook strength/outfit variety/
  sexy-safe styling/scene variety remain deferred, not built. No render, no
  provider call, no `.env` edit, no publish, no prompt/executor/routing
  change. Full detail: `70_visual_qa/CURRENT_STATE.md` and the two
  continuity files below.
- **Hook/variety QA schema v2 built on top of the above (2026-07-06,
  approved and implemented).** `pipeline/qa/lena_photo_qa.py`'s
  `SCHEMA_VERSION` bumped to `"2"`; new `production_scoring` sibling block
  with `hook_strength` and `styling_sexy_platform_safe` as new hard-gating
  dimensions, plus `outfit_variety_vs_recent_posts` /
  `scene_variety_vs_recent_posts` as advisory-only (no history tracker
  built yet). Both existing on-disk QA files stay `schema_version: "1"` and
  validate unchanged -- no migration. Validated via `py_compile`, reload of
  both existing QA files, a fresh v2 template, and 6 synthetic checks (A-F)
  all passing. No render, no provider call, no `.env` edit, no publish, no
  prompt/executor/routing change. Full detail:
  `70_visual_qa/CURRENT_STATE.md`'s "Hook/variety schema v2" section.
- **Fifth folder-native slice built: `pipeline/agents/lena/80_repair/`
  (2026-07-06).** Documentation only -- no repair code exists anywhere in
  the repo. Defines hard-stop-vs-retryable doctrine for QA failures, grounded
  in real history (wc_p082's four-render stop precedent, the negative-prompt
  repair, the Batch 5 compaction bug, and schema v2). Key rule: exact
  wardrobe mismatch alone is never a repair trigger -- only production-
  scoring-gating or hard-gating-checklist failures are. Full doctrine:
  `pipeline/agents/lena/80_repair/RULES.md`.
- **Schema v2 + `80_repair` doctrine applied for the first time (2026-07-07),
  to the existing `wc_p082` image -- no new render.** Re-scored
  `pipeline/kling_library/lena/2026-07-05/2026-07-05-02-photo_seed.png`
  (Kling task `903248497381220361`) under `schema_version: "2"`, viewing the
  actual image directly. Result: `hook_strength: "moderate"`,
  `styling_sexy_platform_safe: "fail"` (too-covered end -- the mustard
  coat+scarf covers the body almost completely), both variety fields
  `not_yet_measured`. `identity_fidelity` and `face_realism_anti_generic_
  drift` still `fail` (unchanged from the prior review of this same image).
  `wardrobe_class_fidelity: fail` recorded but correctly non-gating.
  **`overall: fail`** -- for identity/styling/realism reasons, explicitly not
  because of the wardrobe substitution. `80_repair` classification:
  **HARD STOP** (this slot already has a standing no-rerender prohibition,
  and three hard-gating dimensions failed at once -- not a clean single-
  variable retry candidate). No repair action taken or recommended. This
  confirms the current Kling path's real ceiling is identity/styling/realism
  quality, not exact-wardrobe-obedience. Full detail:
  `70_visual_qa/CURRENT_STATE.md` and `80_repair/CURRENT_STATE.md`. No
  render, no provider call, no `.env` edit, no publish, no
  prompt/executor/routing change, no rerender of `wc_p082`.
- **ROOT CAUSE of the image-quality failures IDENTIFIED (2026-07-07).** A
  fresh production-style proof render on a new, non-wc_p082 slot
  (`2026-07-07-01-photo`, outfit `wc_p030`, flower shop) came out **fully
  cartoon/3D-illustrated** despite all 29 anti-cartoon negative terms
  surviving. Direct viewing of APILENA's stored reference images confirmed
  they are **photoreal and correct** -- the element is fine. A read-only HAR
  analysis of the Kling **web app** then isolated the cause: the current
  executor **fetches APILENA's reference image URLs, verifies them, then
  discards them** -- its payload sends only `element_list:[{element_id}]`,
  with **no reference image and no model pin**. The web app instead sends
  `fromElementId` + `resourceType:"ELEMENT"` + the **actual reference image
  URL** + a pinned model (`kolors_version:"3.0-omni"`). So the realism/
  identity conditioning lever is simply absent from the current payload --
  the failures are conditioning-level, not prompt-content-level, and no
  prompt change can reach them. Full detail:
  `pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md`'s "ROOT CAUSE
  IDENTIFIED" section, `60_executor/CURRENT_STATE.md` §1a, and the support
  packet's sharpened Question 5. **The HAR captures (`scratch/*.har`) contain
  session tokens/signed URLs and are now git-ignored -- never commit them.**
  No web-app request was replayed, no endpoint called, no executor code
  changed, no `.env` edit, no publish, no provider switch.
- **Visual-reference fix researched + a no-call payload diagnostic built
  (2026-07-07).** Three artifacts now stand ready up to the API boundary,
  no executor change yet: (1) capability matrix
  (`lena_visual_reference_api_capability_matrix.md`, Kling + Higgsfield);
  (2) test plan (`lena_kling_reference_by_url_test_plan.md`, Variant A
  kolors-style vs. Variant B omni-image image_list-only; B recommended
  first as more repo-grounded); (3)
  `tools/diagnostics/lena_kling_reference_url_payload_dryrun.py`, which builds
  the **Variant B** payload (`model_name:"kling-v3-omni"`,
  `image_list:[{"image":"<APILENA reference URL>"}]`, **no `element_list`**)
  from a real APILENA `cover` URL in an existing local lookup artifact and
  proves via the reference guard that **Variant B PASSES** while
  **element_list-only is BLOCKED** (`BLOCKED: Lena visual references are not
  included in the generation payload.`). APILENA resource URLs are locally
  available with **no `Expires`/`Signature`/`Key-Pair-Id`/token** params
  (look persistent). **This proves only that the payload can carry the
  reference URL -- NOT that Kling accepts it** (dropping `element_list` from
  omni-image is unverified live). The exact later-patch target is
  `pipeline/kling_apilena_api_executor.py` `_submit_photo()` -- frozen, not
  touched. No Kling call, no render, no credit spend, no `.env` edit, no
  executor patch. Full detail: `60_executor/CURRENT_STATE.md` §1b and the
  changelog's 2026-07-07 Variant B diagnostic entry.
- **BREAKTHROUGH (2026-07-07): Variant B live test SUCCEEDED — reference-by-URL
  fixes the cartoon collapse.** The approved single `n=1` live test ran with a
  pure `image_list`-only payload (`model_name:"kling-v3-omni"`,
  `image_list:[{"image":"<APILENA cover resource URL>"}]`, no `element_list`,
  no `negative_prompt`) and returned **HTTP 200 / code 0 / SUCCEED**, task
  `903333900062163005`, image downloaded. **The official AK/SK endpoint
  accepted a pure image_list-only payload** (bypassing the `1201` element
  error), and the output is **photoreal + Lena-identity-matched** — the
  opposite of the element-only cartoon render. Remaining issues are normal
  production steering (crop/wardrobe/framing/publish-safety), not the
  reference/identity/realism blocker, which is now solved. Exactly one call;
  no retries, no second variant, no executor patch, no `.env`, no publish. 5
  diagnostic artifacts under
  `pipeline/kling_debug/reference_url_test/ref_url_test_20260707T045501Z/`.
  Executor-patch proposal drafted (no code):
  `pipeline/change_notes/lena_kling_reference_url_executor_patch_proposal.md`.
  Full detail: `CURRENT_PROOF_STATUS.md` "SOLVED IN PRINCIPLE" section,
  `60_executor/CURRENT_STATE.md` §1c, and the changelog's 2026-07-07
  BREAKTHROUGH entry.
- **EXECUTOR PATCHED for reference-by-URL (2026-07-07, dry-run validated, no
  render).** `pipeline/kling_apilena_api_executor.py` `_submit_photo()` now
  builds the payload via `build_reference_url_photo_payload()`:
  `model_name="kling-v3-omni"`, `image_list` with the APILENA reference URL,
  **element_list absent, negative_prompt absent**, n=1, 9:16, submits/polls the
  omni-image endpoint. `apilena_reference_guard` enforced before submit
  (fail-closed on element_list-only); https-only refs (no C:\ paths); URLs
  sanitized in logs. Validated: `py_compile` clean + a dry-run proving the
  exact shape, guard pass, old-shape blocked, and **0 network calls**. No
  render/Kling call/publish/scheduler/`.env` edit. Full detail:
  `60_executor/CURRENT_STATE.md` §1d and the changelog's 2026-07-07 executor-
  patch entry.
- **PATCHED-PATH LIVE TEST PASSED (2026-07-07).** One approved n=1 render
  through the real patched executor (slot `2026-07-07-02-photo`, `wc_p034`/
  brunch, task `903345804994285660`) **succeeded end-to-end**:
  `status:downloaded`, `/v1/images/omni-image`, submitted payload verified
  (`model_name="kling-v3-omni"`, image_list reference-by-URL, no element_list,
  no negative_prompt). Output at
  `pipeline/kling_library/lena/2026-07-07/2026-07-07-02-photo_seed.png` is
  **photoreal, identity-matched, no cartoon**. Earned the **first schema-v2 QA
  PASS** this session (`pipeline/asset_review/lena/2026-07-07/
  2026-07-07-02-photo_qa.json`, `overall:pass`, `hook_strength:strong`,
  `styling_sexy_platform_safe:pass`, `publish_ready:false`). **Reliability is
  n=2 total on reference-by-URL — wiring confirmed, consistency not yet
  proven, not unattended-production ready; publish needs operator sign-off.**
  Exactly one render; no retries/batch/second-variant/publish/scheduler/`.env`.
  Full detail: `60_executor/CURRENT_STATE.md` §1e, `CURRENT_PROOF_STATUS.md`,
  and the changelog's 2026-07-07 patched-path-success entry.
- **RELIABILITY CHECK PASSED (2026-07-07): 2 more patched-path renders, both
  PASS.** `2026-07-07-03-photo` (wc_p062 metallic midi dress, rooftop, task
  `903349357289414713`) and `2026-07-05-03-photo` (wc_p086 red tank + cargo,
  flower shop, task `903349874073796628`, MAX_SLOTS=1 so frozen wc_p082
  untouched) -- both photoreal, strong identity, no cartoon, platform-safe,
  `overall: pass` schema-v2 QA, `publish_ready: false`. **Reference-by-URL is
  now 4-for-4** across distinct outfits/scenes. **Path is reliability-proven
  for CONTROLLED production; publish is operator-approved only.** Exactly 2
  renders; no batch/retries/negative_prompt/element_list/publish/scheduler/
  `.env`/patching. Full detail: `60_executor/CURRENT_STATE.md` §1f,
  `CURRENT_PROOF_STATUS.md`, and the changelog's reliability-check entry.
- **FIRST CONTROLLED PUBLISH PACKET created (2026-07-07, DRAFT).** For the
  rooftop metallic-dress image
  (`pipeline/kling_library/lena/2026-07-07/2026-07-07-03-photo_seed.png`):
  packet at `pipeline/publish_packets/lena/2026-07-07/
  LENA_PUBLISH_PACKET_2026-07-07-03-photo.md` — QA overall PASS, 5 caption
  options (≤3 hashtags), soft CTA, Story poll, pinned comment, IG/FB/TikTok
  notes, operator approval checklist. Recommended caption: "the sunset showed
  up. so did I." **DRAFT / operator-review-required — nothing posted,
  scheduled, queued, or auto-approved.** Publishing needs Nicolas's explicit
  sign-off on image + caption + platform. No publishing has ever occurred in
  this project.
- **Live publish attempted + failed safely + publish-path bug fixed
  (2026-07-07).** With explicit approval, a live publish of
  `2026-07-07-03-photo` was attempted and **failed safely at local contract
  validation, before any network call — no R2 upload, no Meta Graph call, no
  Instagram post occurred.** Root cause: `PostingManager.validate_post()`
  (`pipeline/posting_manager.py`) discarded the queue JSON's original
  `metadata` (dropping `avatar_nickname`/`image_engine`/`image_prompt`) before
  it reached `instagram_queue_bridge`'s contract validator — a pre-existing
  bug affecting any queue entry on the live path, not specific to this post.
  **Fixed** (minimal, one method): metadata now preserved + merged with
  `media_size_bytes`/`media_sha256`. Validated no-network (monkeypatched
  network calls to raise): `avatar_nickname`/`image_engine`/`image_prompt`
  survive; contract validation now passes. Queue file restored to
  `pipeline/queue/2026-07-07-03-photo.json`; dry-run re-run and passing.
  **Live retry is ready, pending explicit approval — no publish authorized
  yet.** Full detail: `CURRENT_PROOF_STATUS.md` and the changelog's
  2026-07-07 publish-path-bug entry.
- **Live publish RETRIED + metadata fix confirmed + Meta/Instagram auth
  FAILED (2026-07-07).** Per explicit approval, retried the live publish.
  **The metadata fix worked** — the entry passed contract validation and
  reached the real adapter. `resolve_public_media_url()` auto-uploaded the
  image to R2 (**succeeded**); `create_media_container()` called the real
  Meta Graph API 3 times, and **Meta rejected all 3 with `OAuthException`
  code 190** ("log in to www.instagram.com..."). **No Instagram post was
  created.** Queue file moved to `pipeline/queue/failed/
  2026-07-07-03-photo.json`. **Root cause is an external Meta/Instagram
  auth/account challenge — NOT the queue metadata bug**, which is confirmed
  fixed. **Possible cleanup note:** a real R2 object may now exist from this
  attempt — not deleted, flagged for later cleanup or intentional reuse.
  **Do not retry live publish until the token/account issue is fixed
  externally.** No `.env` edit, no R2 deletion, no token regeneration, no
  further Meta calls, no render/schedule/other publish. Full detail:
  `CURRENT_PROOF_STATUS.md` and the changelog's 2026-07-07 Meta-auth-failure
  entry.
- **Meta token fixed externally by Nicolas → token/account check PASSED →
  FIRST LIVE INSTAGRAM PUBLISH SUCCEEDED (2026-07-07).** Env names confirmed
  present (`META_INSTAGRAM_ACCESS_TOKEN`, `META_IG_USER_ID`; no values
  printed). Token/account check via the real adapter API path
  (`graph.instagram.com`) returned username `lenadelapineapple.official` —
  matches the intended account. Queue file restored, dry-run passed. Under
  explicit "APPROVED TO PUBLISH..." approval, the live run succeeded:
  Instagram media id `18154201054431808`, permalink confirmed via a
  read-only follow-up GET: `https://www.instagram.com/p/Daf8-NgFDSu/`. Queue
  file moved to `pipeline/queue/published/2026-07-07-03-photo.json`.
- **Provenance patch implemented and COMMITTED as `8870a82b`.** Read-only
  audit found the receipt mechanism already existed (`<published_file>.
  receipt.json` via `_move_post()`) but was missing `permalink` entirely and
  had `instagram_media_id` buried in nested JSON. Patched
  `pipeline/publisher/instagram_graph_adapter.py::publish_post()` (one extra
  non-fatal read-only GET against the **published media id**, per explicit
  correction, for `permalink`/`instagram_media_type`/`instagram_timestamp`)
  and `pipeline/posting_manager.py` (flattened receipt fields +
  `caption_variant` + `published_post_path` in `_move_post()`). `py_compile`
  clean; isolated no-network validation passed (synthetic response shapes +
  a temp-dir `_move_post()` test — the real published item/receipt was
  deliberately left untouched, not backfilled). Two disposable `.pyc` files
  from this session's compile checks were removed; nothing else cleaned.
- **Git commit blocker RESOLVED — no blocker remains.** Both patched files
  were untracked in git (never committed — pre-dates this session, from an
  earlier out-of-band publisher-patch install). `git commit` had failed
  because `.git/hooks/pre-commit` hardcoded `--config=.pre-commit-config.yaml`,
  which does not exist anywhere in the repo (confirmed via search + git
  history — it existed in the past, per two historical commit messages, but
  was gone without the hook being removed/regenerated); `.venv` was also
  absent, so the hook fell through to a system-wide `pre-commit` install
  that failed on the missing config before touching any file. **Confirmed
  unrelated to file content.** User's explicit choice was to remove the
  stale hook (`.git/hooks/pre-commit` deleted, untracked/local-only, not
  `--no-verify`); both files then committed cleanly as `8870a82b`.

## Current branch / thread

**As of the most recent work (2026-07-06), two things are true at once —
read both:**

1. **Kling Omni/API BodyLock diagnostic path is PAUSED**, pending Kling/
   APILENA support clarification. The user decided the HAR evidence (web UI
   element flow uses `kling.ai` domain; official API uses `api.klingai.com`
   and cannot see APILENA) was sufficient to stop further diagnostic
   guessing. A support packet was prepared:
   `pipeline/change_notes/lena_kling_omni_support_packet_2026-07-06.md` --
   ready to send, asking (1) whether web-UI-created elements are visible to
   the official AK/SK API at all, (2) how to create/obtain an element that
   is, (3) which payload schema is correct, and (4) whether `kling-v3-omni`
   supports character-element conditioning through the official API at all.
   **No further Kling diagnostic testing, no more element-ID guessing, no
   more payload-shape guessing until that packet gets a response.**

2. **Since that pause, four more things happened on the current
   `/v1/images/generations` path, in order:** (a) four folder-native slices
   were built (`40_identity_continuity/`, `50_prompt_builder/`,
   `60_executor/`, `70_visual_qa/`); (b) the negative-prompt budget was
   repaired in code (tiered constants + 6 reserved floors) and proof-render-
   tested (one image, result: style-realism improved, wardrobe still wrong);
   (c) the user accepted that outcome as final and closed the wardrobe-
   obedience/negative-prompt thread; (d) **the production standard itself
   was then corrected** -- exact wardrobe obedience was demoted from
   "automatic production failure" to "diagnostic only." **This last item is
   the single most recent, most important thing to internalize** -- see the
   STANDARD CORRECTION banner at the top of this file for the full
   corrected standard before evaluating any past or future render.

Nothing above reopens Kling Omni/BodyLock -- that thread remains separately
parked, waiting on the external response, untouched by (2).

## Exact next approved action

**The wrong-outfit/negative-prompt thread is settled and closed (user-
confirmed 2026-07-06) -- see the FINAL, ACCEPTED CLASSIFICATION bullet
above, read alongside the STANDARD CORRECTION banner at the top of this
file.** Prompt-content iteration aimed at exact wardrobe obedience is
stopped, not paused -- and separately, exact wardrobe obedience is no
longer even the production goal, so there's less reason to chase it going
forward regardless. The Kling Omni/BodyLock thread remains separately
parked (waiting on an external support response -- see the banner at the
top of this file).

**QA-schema gating fix: DONE (2026-07-06, approved and implemented).**
`pipeline/qa/lena_photo_qa.py` no longer treats `wardrobe_class_fidelity:
fail` as an automatic `overall: fail` -- new `DIAGNOSTIC_ONLY_CHECKLIST_KEYS`
/ `HARD_GATING_CHECKLIST_KEYS` constants, and `validate_qa_result()`'s
false-green check now only iterates the hard-gating set. No field added,
removed, or renamed; every other checklist field still hard-gates exactly as
before. Validated via `py_compile`, reloading the real on-disk `wc_p082` QA
file (still validates unchanged), and two standalone checks (wardrobe-only
fail now validates with `overall: pass`; every other field still forces
`overall: fail`). No render, no provider call, no `.env` edit, no publish,
no prompt/executor/routing change. Full detail:
`pipeline/agents/lena/70_visual_qa/CURRENT_STATE.md`'s "QA code updated to
match the corrected standard" section.

**Hook/variety schema v2: DONE (2026-07-06, approved and implemented).**
`pipeline/qa/lena_photo_qa.py`'s `SCHEMA_VERSION` bumped `"1"` -> `"2"`; a
new sibling block `production_scoring` added with 4 fields:
`hook_strength` (weak/moderate/strong -- `weak` gates `overall: fail`),
`styling_sexy_platform_safe` (pass/fail -- `fail` gates `overall: fail`),
and `outfit_variety_vs_recent_posts` / `scene_variety_vs_recent_posts`
(pass/fail/not_yet_measured -- **advisory only, never gates**, since no
history-comparison tracker exists yet). `LEGACY_SCHEMA_VERSIONS_WITHOUT_
PRODUCTION_SCORING = {"1"}` means both real on-disk QA files (still
`schema_version: "1"`) are exempt and validate unchanged -- no migration.
Validated via `py_compile`, reloading both existing on-disk QA files
(unchanged, still valid), a fresh v2 template (valid in its unreviewed
state), and 6 lettered synthetic checks (A-F) covering every gating and
non-gating combination, all passing as designed. No render, no provider
call, no `.env` edit, no publish, no prompt/executor/routing change.
`tools/lena_review_proof_render_v1.py` left unchanged (not required). Full
detail: `pipeline/agents/lena/70_visual_qa/CURRENT_STATE.md`'s "Hook/variety
schema v2" section.

**Still not built:** the history-comparison tracker (working name
`pipeline/qa/lena_variety_tracker.py`) that would let the two variety fields
become more than advisory -- explicitly out of scope for this change, needs
its own approval.

**Fifth folder-native slice built (2026-07-06): `80_repair/`**, documentation
only, no code -- see the "Current state" bullet above and `pipeline/agents/
lena/80_repair/RULES.md` for the full hard-stop-vs-retryable doctrine.

**Schema v2 scored against a real image, and `80_repair` doctrine applied,
both for the first time (2026-07-07): DONE.** See the "Current state" bullet
above -- `wc_p082`'s existing image, re-scored (no new render), result
`overall: fail` for identity/styling/realism reasons (not wardrobe),
classified HARD STOP by `80_repair`. The retryable branch of `80_repair`'s
table remains untested against a real case (this was a hard stop).

**Production-style proof batch started (2026-07-07):** a 3-candidate,
non-wc_p082 batch was built (`pipeline/kling_workorders/2026-07-07/
daily_workorders.json`: `wc_p030`/flower-shop, `wc_p034`/brunch,
`wc_p062`/rooftop). All 3 passed the no-spend dry-run (correct APILENA
element, `/v1/images/generations` only, no `image_list`, all negative floors
survive, ≤2499 chars). Exactly 1 was rendered (`2026-07-07-01-photo`,
`wc_p030`) -- **result: fully cartoon/3D, hard reject.** Candidates 2 and 3
were NOT rendered (they would fail the same way -- see root-cause bullet
above). QA verdict for candidate 1 was **not** written up (the diagnostic
pivoted to root cause instead); write it if this thread resumes.

**Not yet decided / blocked on external input:** the image-quality problem is
now root-caused (conditioning-level, not prompt-level) and the fix is blocked
on the support packet's sharpened Question 5. Do NOT keep rendering candidates
on the current path expecting a different result. Other open (non-blocked)
options: build the variety-history tracker, pick a further folder-native slice
(five exist now: `40_identity_continuity/`, `50_prompt_builder/`,
`60_executor/`, `70_visual_qa/`, `80_repair/`), or something else. Ask, or
wait for the user to specify.

## Exact commands/files to inspect first if resuming technical work

- `pipeline/knowledge/content_bot/AUTHORITATIVE_SURFACES.md` — the source-of-truth
  index; read this before trusting any specific file as canonical.
- `pipeline/knowledge/content_bot/QUARANTINED_SURFACES.md` — what NOT to treat as
  live, so you don't re-discover dead surfaces from scratch.
- `pipeline/agents/lena/40_identity_continuity/AGENT.md`,
  `pipeline/agents/lena/50_prompt_builder/AGENT.md`,
  `pipeline/agents/lena/60_executor/AGENT.md`,
  `pipeline/agents/lena/70_visual_qa/AGENT.md`, and
  `pipeline/agents/lena/80_repair/AGENT.md` — the pattern already
  established for any new folder slice. `60_executor/RULES.md` is the
  clearest statement of what must never be invoked casually across the whole
  execution surface — read it before considering any render.
  `50_prompt_builder/RULES.md`'s core rule ("prompt correctness does not
  equal image correctness") applies to any prompt-wording change.
  `80_repair/RULES.md` is doctrine only (no code) — read its Rule zero
  (exact wardrobe mismatch alone is never a repair trigger) before treating
  any QA `fail` as something to act on.
- `pipeline/identity/lena_identity.py`, `pipeline/qa/lena_photo_qa.py`,
  `tools/lena_review_proof_render_v1.py`, `pipeline/kling_apilena_api_
  executor.py`, `tools/lena_bodylock_diagnostic_v1.py`,
  `pipeline/lena_production_job.py`, `pipeline/prompting/
  lena_prompt_brain.py` — the real, proven modules already folder-wrapped.
- `pipeline/kling_workorders/2026-07-05/daily_workorders.json` and
  `pipeline/kling_debug/apilena_api/2026-07-05/2026-07-05-02-photo/` — the paused
  proof lane's data, if that thread is revisited.
- `README_BODYLOCK_PRODUCTION_RULES_2026-06-24.md` (retrieve via
  `git show HEAD:pipeline/workorders/lena/README_BODYLOCK_PRODUCTION_RULES_2026-06-24.md`
  — deleted from the working tree, still in git history at commit `f5908ac6`) — the
  documented, previously-working generation recipe Branch 2 found and compared
  against the current live path. Read this before proposing any Branch 2 diagnostic.
- `tools/lena_bodylock_diagnostic_v1.py` — the standalone diagnostic runner built
  this session. Read its module docstring and hard-fail checks before proposing
  to run it again. Default (no `--execute`) is always safe -- dry-run only.
  Already run once (user-approved) on 2026-07-06 -- rejected by Kling with
  `HTTP 400 code 1201 "Element id not found: 315187972322559"` before any image
  was generated. See
  `pipeline/kling_debug/bodylock_diagnostic/bodylock_diagnostic_20260706T200037Z/`
  for the exact request/response. Read this before proposing another run --
  the open question now is an element-registry/auth mismatch on the
  official API, not the original wrong-outfit/style question.
- Masked env check before any render: confirm `KLING_LENA_ELEMENT_IMAGE_URLS_JSON`
  and `KLING_LENA_ELEMENT_IMAGE_URLS` are absent from `.env` (presence-only check,
  never print values).

## Hard prohibitions

- **Business media pivot (`podcast_repurpose`) is docs-only.** Do not write
  processing/automation code for it without explicit approval — the plan says
  to validate the workflow by hand (one manual pass) before automating any of
  it. Do not start Blotato or any posting-automation work. Do not treat the
  pivot memo's proposed package/pricing as committed — it is a hypothesis
  pending real pilot conversations.
- **Lena is not abandoned by the pivot.** Do not delete, downgrade, or
  deprioritize any Lena code/docs because of the new Revenue Lane framing —
  she remains the R&D/demo node, frozen only on the Kling render-freeze
  timeline described above, unrelated to the pivot's pace.
- **Kling Omni/BodyLock diagnostic path is paused pending Kling/APILENA support
  clarification.** Do not run `tools/lena_bodylock_diagnostic_v1.py` with
  `--execute` again, do not try another element ID, do not try another payload
  schema (`fromElementId`, `arguments.elementVersion`, or anything else), and
  do not try another endpoint or auth method — all further guessing is
  explicitly stopped until a response comes back on
  `pipeline/change_notes/lena_kling_omni_support_packet_2026-07-06.md`.
- Do not rerender on `2026-07-05-02-photo` / wc_p082 on the *current* path without
  a specific, approved reason — four consecutive fails already fully diagnosed
  under the exact-wardrobe-match diagnostic (now known to be the wrong
  production bar, per the standard correction banner above — that doesn't
  authorize a rerender, it just changes why past renders were judged).
- The current `/v1/images/generations` path remains the only working Kling
  image path and is not affected by the pause above — it may still be used for
  its existing purpose, quality limitations and all; the pause is specifically
  about the omni-image/BodyLock diagnostic thread, not all Kling usage.
- **Do not replay or automate against the Kling web-app endpoints**
  (`kling.ai/api/omni/submit-config-template`, `.../intent-recognition`,
  `kling.ai/api/elements*`) discovered in the HAR analysis. They use
  web-session auth and internal fields; replaying them is out of bounds
  (fragile, session-token-dependent, ToS-adjacent). The safe fix path is the
  *official* API pending the support answer, not mimicking the web session.
- **Do not commit the HAR captures** (`scratch/*.har`) — they contain
  session-scoped tokens and signed URLs. They are now git-ignored
  (`scratch/*.har` + `*.har` in `.gitignore`); keep them local-only.
- Do not judge any future render's production-worthiness by exact catalog-
  wardrobe match — apply the corrected standard (hook/variety/sexy-safe/
  realism/identity/scene/caption, in that priority order) instead. See the
  banner at the top of this file.
- Do not add a `.env`-backed default for `CONTENT_BOT_BODYLOCK_ANCHOR_URL` or any
  mechanism that makes the diagnostic path runnable without explicitly passing
  both env vars inline on the command each time.
- Do not patch `kling_apilena_api_executor.py` or `lena_prompt_brain.py` again on the
  basis of the wrong-outfit renders — ruled out as code-fixable three times over.
  (This does not apply to the negative-prompt budget repair below, which is a
  separate, already-approved, already-implemented, non-render-related fix.)
- The negative-prompt budget overflow is **fixed in code as of 2026-07-06**
  (tiered constants + 6 reserved floors) and **proof-render-tested** (one
  image, `2026-07-05-02-photo`, result: FAIL on wardrobe/identity, improved
  but not clean on style-realism -- see above). Do not re-litigate or
  re-patch the floor mechanism without a concrete new finding — see
  `pipeline/agents/lena/50_prompt_builder/CURRENT_STATE.md` and the
  changelog's repair + proof-render entries for exact validated numbers.
- Do not run another render on `2026-07-05-02-photo` or any other slot
  without a specific, separately-approved reason — this slot now has 4
  consecutive documented wrong-outfit failures; do not treat this file as
  authorization for a 5th attempt.
- Do not unilaterally change `pipeline/identity/lena_identity.py`'s "element_list-
  only" doctrine based on the BodyLock finding — flagged as a load-bearing
  assumption worth the user's review, not something to reverse without their
  explicit decision.
- Do not build out any folder-native slice beyond what's explicitly approved next.
- Do not create all remaining agent folders at once — one slice at a time, each
  requiring explicit approval. Five exist now (`40_identity_continuity/`,
  `50_prompt_builder/`, `60_executor/`, `70_visual_qa/`, `80_repair/`); do not
  build out the remaining ones (`10_strategy/`, `20_life_context/`,
  `30_creative_direction/`, `90_content_packet/`, `95_publish_gate/` — per
  master file §6) without approval.
- `80_repair/` is documentation only — do not treat it as authorization to
  write actual repair code, retry logic, or a `repair_patch.json` writer.
  Any real repair implementation still needs its own separate approval, per
  master §7.9 and `80_repair/RULES.md`'s own "human approval required" list.
- Do not touch `.env`. Do not publish. Do not run live generation without an
  explicit, current-session confirmation that manual override env vars are absent.
- Do not skip this file, the knowledge layer, or the master file's §0 at the start
  of a session, even if chat memory seems to have context — these files are the
  source of truth, not memory.
- Every meaningful step (code batch, proof render, QA verdict, confidence-changing
  diagnosis, blocker discovery, next-step decision, live-path correction,
  source-of-truth change) must update both continuity files (master + changelog)
  before being reported as closed. If they weren't updated, the step isn't done.

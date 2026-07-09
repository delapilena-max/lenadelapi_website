# Legacy Provider Surfaces

This document is the routing legend for the `tools/` directory.

## Current canonical Lena live path

These are the active saved surfaces for the current Lena autonomy path:

| Entry point | Purpose |
|---|---|
| `run_lena_autonomous.ps1` | Windows wrapper for the current autonomous run |
| `lena_autonomous_run.py` | Top-level live runner: production, preflight, and queue publishing |
| `../pipeline/lena_production_job.py` | Daily production orchestrator |
| `lena_prepare_daily_workorders_brain.py` | Builds the daily Lena workorders |
| `../pipeline/prompting/lena_prompt_brain.py` | Prompt construction brain used by the workorder flow |
| `../pipeline/kling_apilena_api_executor.py` | Real current executor: APILENA-only Kling image submission (verified 2026-07-05 by tracing the actual `import` in `pipeline/lena_production_job.py`, not by this doc) |
| `lena_preflight.py` | Contract and queue readiness gate |
| `process_queue.py` | Current live publish surface |

**Correction, 2026-07-05:** this doc previously named `../pipeline/kling_ui_executor.py` as canonical. That file is untracked, has no callers anywhere in the repo, and is not the executor that runs. See `pipeline/change_notes/lena_agentic_pivot_changelog.md` for the containment findings.

Machine-readable source of truth:

- `pipeline/config/lena_live_path_manifest_v1.json`
- `tools/lena_live_path_status_v1.py`

## Older strategy-era Lena surfaces (not canonical live path)

These files are still in the repo, but they are no longer the source of truth for the live Lena path:

| File | Status |
|---|---|
| `lena_strategy_autonomy_run_v1.py` | Legacy strategy-era runner |
| `lena_daily_orchestrator_v1.py` | Legacy orchestration surface |
| `strategy/lena_run_strategy_autonomy_prep_v1.py` | Legacy prep surface |
| `strategy/lena_submit_kling_payload_v1.py` | Legacy strategy submit surface |
| `run_lena_strategy_autonomy.ps1` | Legacy wrapper surface |

## Legacy surfaces — blocked (require `--allow-legacy-openart-seedance`)

These files route work to OpenArt or Seedance, which are no longer the active Lena path.
They will refuse to run without an explicit override flag and should not be used for new work.

| File | Was used for |
|---|---|
| `lena_route_provider_v1_5.py` | Routed workorders to OpenArt/Seedance |
| `run_lena_provider_only_daily_v1_5_2.py` | Ran the full legacy OpenArt/Seedance daily pipeline |
| `wire_lena_v1_5_openart_seedance_provider.py` | Patched `run_lena_generate_daily.ps1` to insert the legacy provider steps |
| `generation/lena_generation_adapter_interface_v1.py` | Planned OpenArt/Seedance multi-scene keyframe pipeline |

## Doc-only / uncalled surfaces

| File | Status |
|---|---|
| `../pipeline/kling_ui_executor.py` | Untracked, no callers anywhere in the repo. Was mistakenly documented as canonical above; not currently invoked. Quarantined pending decision, not deleted. |
| `../pipeline/kling_direct_executor.py` | Absent from disk and from git history entirely. Older handoffs (2026-07-02/03) describe safety fixes living in this file; those fixes are not confirmed present in the real live executor. Do not assume they carried over. |

## Legacy surfaces — named but not blocked

These files have OpenArt or Seedance in their names or logic but do not route live work.
They are preserved as historical context. Do not treat them as active architecture.

| File | Notes |
|---|---|
| `lena_prepare_openart_seedance_workorders_v1_5.py` | Built manual workorder exports for OpenArt/Seedance |
| `lena_enhance_openart_workorders_v1_5_2.py` | Enhanced those workorders |
| `lena_cleanup_openart_seedance_workorders_v1_5_3.py` | Cleaned up old workorder files |
| `lena_import_openart_seedance_outputs_v1_5_1.py` | Imported outputs from OpenArt/Seedance |
| `lena_validate_openart_anchor_v1_5_2.py` | Validated OpenArt anchor config |
| `lena_openart_anchor_status_v1_5_2.py` | Reported anchor status |
| `lena_openart_prompt_cleanup_status_v1_5_3.py` | Reported prompt cleanup status |
| `lena_provider_status_v1_5.py` | Legacy provider status report |
| `lena_validate_provider_layer_v1_5.py` | Validated the OpenArt/Seedance provider layer |
| `lena_validate_provider_import_v1_5_1.py` | Validated asset imports from legacy providers |
| `lena_init_provider_import_v1_5_1.py` | Initialized legacy provider import flow |
| `lena_control_panel_v1_5_4.py` | Legacy control panel for OpenArt/Seedance ops |
| `lena_validate_control_panel_v1_5_4.py` | Validated that control panel |
| `lena_autonomous_asset_generation_controller_v1.py` | Controller preview for OpenArt/Seedance generation jobs |
| `generation/lena_provider_adapter_shell_v1.py` | Provider adapter shell for legacy stack |
| `generation/lena_kling_pipeline_readiness_v1.py` | Early Kling readiness checker (pre-strategy era) |
| `generation/lena_kling_request_payload_preview_v1.py` | Early Kling payload preview (pre-strategy era) |

## Pipeline data — historical only

`pipeline/provider_workorders/openart_seedance/` and related subdirectories contain
archived workorder JSON from the OpenArt/Seedance era. These are read-only historical
artifacts. The active production and publish path is defined by
`pipeline/config/lena_live_path_manifest_v1.json`.

## Provider transition in progress: Higgsfield (2026-07-08, docs-only, not yet integrated)

**Nicolas is committing to Higgsfield as the likely main generation provider path
going forward.** Kling (`../pipeline/kling_apilena_api_executor.py`) remains the
only live, working provider today — nothing above in this document changes.
This section records the transition decision and the read-only audit findings
so future work starts from verified facts, not fresh guessing. **No Higgsfield
code exists in this repo yet. No install, login, API call, or render has
occurred.**

**First integration route: CLI, not MCP.** Verified from official Higgsfield
sources (`higgsfield.ai/cli`, `higgsfield.ai/mcp`, `github.com/higgsfield-ai/cli`,
`github.com/higgsfield-ai/higgsfield-client`) — no browser automation or
unofficial scraping was used to gather this:
- Higgsfield's own MCP page explicitly recommends the **CLI**, not MCP, for
  Claude Code, OpenClaw, and Hermes -- MCP is framed for hosted/chat-style
  agents (Claude web, Cowork), not a local terminal coding agent like this one.
- The CLI has real machine-readable output (`--json` on every command) and
  real job/history primitives (`generate create/list/get/wait/cost`,
  `soul-id create/wait`) that map cleanly onto this repo's existing
  debug-manifest pattern (`result_manifest.json` + `task_id`).
- MCP's auth model (account-linked via agent-settings connector) does not fit
  this repo's non-interactive, scripted, credit-tracked execution pattern
  (`python pipeline/kling_apilena_api_executor.py <date>`-style invocation)
  as well as a CLI subprocess call would.
- MCP remains useful context (documents Higgsfield's full model catalog and
  capabilities) but is **not** the first repo executor path.

**Known unresolved blockers before any code is written** (all confirmed
unresolved via the official CLI README and Python SDK README -- not found,
not silently assumed):
- Prompt-length limit: undocumented anywhere official.
- Negative-prompt support: undocumented anywhere official.
- No native dry-run / `--no-op` / validate-only mode exists in the CLI or SDK.
- Output download-to-file path: the CLI/SDK return URLs, not files; how a
  downloaded file would be saved locally (to mirror
  `expected_assets.seed_image_path`) is unconfirmed.
- Soul character identity requirements differ materially from Kling's
  element mechanism: Soul training wants 20+ reference photos in a
  consistent style, reportedly without faces in some guidance -- not a
  single hosted-element-URL swap like `KLING_LENA_ELEMENT_UI_ID`.
- Auth token refresh/storage: CLI docs state tokens are "short-lived" but do
  not document storage location or refresh mechanics.
- Per-model pricing/credit cost: a `generate cost <model>` command exists
  but actual cost figures were not found in the docs reviewed.
- Moderation/NSFW risk: each Higgsfield model applies its own NSFW filtering;
  Higgsfield's own Soul model specifically blocks NSFW prompts; the SDK's
  job-status enum includes a terminal `NSFW` state (a job can complete and
  still come back flagged, not just be pre-blocked at submit time). Lena's
  content strategy is deliberately "sexy but platform-safe, allure, IT-girl"
  -- not explicit, but more revealing than generic lifestyle content -- so
  the actual moderation threshold across Higgsfield's 30+ models is a real,
  untested risk, not a solved problem.
- Image vs. video contract differences: Higgsfield separates image and video
  generation into different model families and CLI flags (`--start-image`,
  `--duration`, `--mode`, `--sound` for video) -- maps reasonably well onto
  this repo's existing `final_photo_path`/`final_video_path` split, but
  needs explicit handling, not an assumed 1:1 mapping.

**Future implementation sequence (each step needs its own separate
approval; none of steps 2-7 are authorized by this docs-only entry):**
1. Docs note -- this entry.
2. No-live-call dry-run command/contract builder (construct and print the
   intended CLI invocation or SDK call args from a real slot's
   `image_prompt`/metadata; zero subprocess calls, zero network calls).
3. Higgsfield executor skeleton (`pipeline/higgsfield_lena_api_executor.py`
   or similar), writing to the same `expected_assets.seed_image_path` /
   `result_manifest.json`-shaped contract the Kling executor uses today.
4. CLI install/login -- only with explicit separate approval.
5. One approved `n=1` live Higgsfield generation -- same discipline as every
   Kling render this session (dry-run reviewed first, exactly one live
   call, full debug-artifact capture).
6. QA schema-v3 review of that render (`pipeline/qa/lena_photo_qa.py`,
   including the Visual Hook / Allure Gate fields) before anything else.
7. Only after a QA pass: consider R2/queue/publish for a Higgsfield-sourced
   render -- these paths are already provider-agnostic (confirmed in the
   prior read-only audit) and should need no changes, but that itself
   should be verified with a real artifact before being assumed.

Full detail: the 2026-07-08 read-only Higgsfield provider-integration audit
and Higgsfield docs/CLI/MCP verification (session record; not yet copied
into a dedicated change-notes file).

## Higgsfield provider-configuration doctrine (2026-07-09, docs-only)

These are **provider/UI/API settings, not prompt text** -- never write any
of the following into `image_prompt`/`prompt` strings. This section is the
source of truth for how the eventual Higgsfield executor (step 3 in the
sequence above, still unbuilt) must configure each generation call, and for
what a manual UI test should set today.

- **Prompt Enhancer: ON**, for all Lena manual Higgsfield tests and future
  production, unless Nicolas explicitly says otherwise. Nicolas ran a real
  side-by-side manual comparison directly in the Higgsfield UI (outside
  this repo -- no executor exists yet) and found Prompt Enhancer OFF
  produced measurably weaker Lena results: less premium fashion finish,
  flatter image quality, a weaker hip/body read, and less natural
  creator/influencer polish, versus the earlier Prompt-Enhancer-ON velvet
  rooftop outputs. No code path exists today that could set this flag --
  recorded now so the future executor skeleton builds it in from the
  start rather than needing a later correction.
- **Negative prompt: disabled by default** (unchanged) --
  `generate_higgsfield_prompt_package()` in `pipeline/prompting/
  lena_prompt_brain.py` sets `negative_prompt_enabled: False`; Soul 2.0
  is expected to own identity/body directly without a negative-prompt
  fight, unlike Kling's reference-image conditioning.
- **Lena Soul: selected in provider/UI config, never written into prompt
  text** (unchanged) -- already implemented as
  `soul_selection_mode: "provider_config_not_prompt_text"` package
  metadata; Prompt Enhancer follows the same pattern.
- **Motorcycle lanes: paused/opt-in, not default production** (unchanged)
  -- all 7 moto lanes are in `production_blocked_lanes` in
  `pipeline/prompt_banks/lena/lena_photo_scene_bank_v1.json` as of commit
  `1a01add9`; still present in code/scene bank for manual opt-in, not
  deleted.
- **Body silhouette anchor: top production priority over props/scenes**
  (unchanged) -- `HIGGSFIELD_BODY_SILHOUETTE_ANCHOR` in
  `pipeline/prompting/lena_prompt_brain.py`, always inserted into every
  Higgsfield prompt (commits `1a01add9`, `7ad7ac6a`). Current wording
  separates body shape from pose: hips must read structurally wider than
  the waist even in a neutral standing pose, not only via a hip-pushed
  pose.

**Current creative benchmark (updated 2026-07-09, further updated later
same session — NARROWED, NOT A CLOSED PASS):**

The rooftop black-dress render below was the first single image where
identity, body, outfit, realism, and framing all passed together at
once, and was locked as "complete production benchmark" earlier this
session. **That verdict has since been narrowed by real evidence**: 3 of
3 follow-up production-readiness renders (rooftop copper-bronze dress,
coffee-shop white mini skirt, brunch plum skirt) failed body continuity
against it, under the same byte-identical body anchor and framing text.
Body continuity is not currently production-ready across varied content
-- see the changelog's "Expression/gaze wiring fixed... then real
production-readiness renders reopened the body-consistency question"
entry for the full diagnostic chain. This earlier variance evidence is
not erased by the entry below.

**Nicolas-approved preferred body benchmark (2026-07-09, later in
session):** Nicolas reviewed two controlled 9:16 Version-B black-bodycon
rooftop renders (part of the diagnostic chain above) and explicitly
selected the first over the second as his preferred Lena body benchmark
-- "Her body is like perfect." / "I'd say this one is my favorite." --
superseding the rooftop black-dress render above for body-target
purposes specifically. **This verdict is recorded as authoritative on
Nicolas's judgment, not as an independently re-derived body-shape
assessment.**

Nicolas-approved preferred Lena body benchmark: narrow waist, clear
waist-to-hip contrast, naturally broad hip line, fit-curvy medium frame,
proportional full bust, realistic toned legs, and an overall silhouette
Nicolas considers the ideal Lena body.

Exact successful configuration: Lena Soul selected; Prompt Enhancer OFF;
negative prompt OFF; Higgsfield UI aspect ratio explicitly 9:16; Version
B black-bodycon rooftop control prompt (repeated final framing line
included); current committed body anchor and framing wording both
unchanged. At 3:4, the same Version B test failed full-head framing 2/2;
after switching to 9:16, both follow-up outputs preserved the full head,
and Nicolas selected the first as preferred. **Not claimed**: that 9:16
alone fixes all variance, that Enhancer OFF alone guarantees the body,
or that prior failures share one cause -- this is recorded as the
strongest successful configuration observed so far and Nicolas's
explicit preferred visual benchmark, not a closed root cause.

**LOCKED as of this checkpoint -- do not re-tune without new evidence:**
- `HIGGSFIELD_BODY_SILHOUETTE_ANCHOR` -- unchanged through this new
  evidence; do not rewrite or re-tune.
- The framing reinforcement (commit `9c787c17`) -- unchanged; do not
  reword.
- Do not replace this benchmark without Nicolas's explicit approval. Do
  not resume blind prompt-wording experiments.

**Current next-work status:** the provider-side aspect-ratio lookup was
completed, the UI setting was confirmed at 3:4, and a controlled switch
to explicit 9:16 produced two strong full-head/full-body outputs under
Enhancer OFF. Nicolas selected the first of those two as his preferred
Lena body benchmark. This narrows but does not universally close the
broader body-consistency question. The next production-oriented step is
not pre-approved; do not resume blind prompt rewrites or change the body
anchor.

Prior benchmark (rooftop black-dress, complete-image reference; kept,
not deleted -- see nuance above): full head-to-shoes framing, face/
identity, hips reading clearly, waist-to-hip curve, fit-curvy medium
frame, not runway-skinny. Superseded for body-target purposes by the new
9:16 image above; still the best available complete-image (identity +
body + outfit + realism + framing all together) reference.

Prior benchmark (kept for reference only): the black fitted mini/bodycon,
neutral-stance output produced under the `1d7cf3c9` anchor -- wide-set
pelvis, hips clearly wider than the waist, fuller upper thighs, fit-curvy
medium frame, not skinny/runway-thin, not plus-size, not cartoonish,
shape reads even in neutral stance with no hip-pop pose doing the work.
Not publishable (head cropped) -- silhouette reference only.

Earlier benchmark (kept for reference only): the Prompt-Enhancer-ON
rooftop velvet midi dress outputs -- narrow waist, hips clearly wider
than the waist, visible outward hip flare, fitted wardrobe tracing the
waist-to-hip curve, realistic but curvy, no prop blocking the hips.

Full detail: `pipeline/change_notes/lena_agentic_pivot_changelog.md`'s
2026-07-09 (later in session) entries -- "body test succeeded, framing
crop found", "complete production benchmark locked", "Expression/gaze
wiring fixed... reopened the body-consistency question", and "Nicolas-
approved preferred body benchmark chosen".

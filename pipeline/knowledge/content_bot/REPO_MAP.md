# Repo Map - content_bot

**Purpose:** High-level orientation to the repo's major folders and what they own.
Not a file-by-file index - see `AUTHORITATIVE_SURFACES.md` for specific
source-of-truth files, and `QUARANTINED_SURFACES.md` for what's dead/legacy.

Grounded in a direct `ls` of the repo root and `pipeline/` on 2026-07-06.

## Repo root

- `pipeline/` - almost all real production code, config, and data. See below.
- `tools/` - CLI entry points, one-off scripts, and control panels that call into
  `pipeline/`. Large and messy: many versioned filenames (`_v1_5_2`, `_v2_6_1`) and
  `.bak_*` files from iterative hand-patching. `tools/LEGACY_PROVIDER_SURFACES.md` is
  the routing legend for this directory - read it before trusting any script here.
- Root-level `RUN_LENA_*.bat` files - Windows launchers for individual `tools/`
  scripts. Named after the script they run; not independently meaningful.
- `.claude/` - Claude Code project config (this session's harness settings).
- Assorted loose root files (`README*.md`, `RESTORE.md`, diagnostic `.txt` snapshots,
  a stray `$dest/` and `Control Panels/` directory) - not part of the pipeline;
  operator scratch/notes, not source of truth for anything.

## `pipeline/` - major subfolders

**Core production code (top-level `.py` files directly under `pipeline/`):**
- `kling_apilena_api_executor.py` - the real, live Kling image-submission executor
  (see `LIVE_PATHS.md`).
- `lena_production_job.py` - daily production orchestrator (prepare -> generate ->
  package -> preflight).
- `lena_generation_signature.py`, `lena_contract_workflow.py`,
  `lena_publish_quality_gate.py`, `env_loader.py`, `scheduler_jobs.py`,
  `scheduler.py`, `posting_manager.py`, `caption_generator.py` - supporting
  production/publishing logic.
- `kling_ui_executor.py` - untracked, no callers anywhere in the repo. Quarantined,
  not deleted. Do not treat as live.

**Newer, consolidated ownership modules (2026-07-05 pivot):**
- `identity/` - `lena_identity.py`, the single source of truth for Lena photo
  identity resolution (element-id cleaning, expected/forbidden elements, the
  manual-override fail-closed guard).
- `qa/` - `lena_photo_qa.py`, the structured visual-QA schema for photo proofs
  (checklist-based, machine-readable; does not itself run a vision model).
- `agents/lena/` - filesystem-native agent folders. Currently only
  `40_identity_continuity/` exists (docs-only front door to `identity/`). This is
  the target layout described in `lena_filesystem_native_agent_pivot_master.md` Sec. 6;
  most of the 11 planned folders don't exist yet.
- `knowledge/content_bot/` - this repo-orientation layer (this file and its
  siblings).

**Prompting / creative:**
- `prompting/` - `lena_prompt_brain.py`, the prompt-construction brain used by the
  daily workorder flow (positive + negative prompt assembly, garment-obedience
  lock, compaction).
- `prompt_banks/`, `prompt_director/`, `prompt_rotator.py`, `prompt_state.json` -
  wardrobe/scene/prompt content banks and rotation state consumed by the prompt
  brain and workorder builders.

**Config and contracts:**
- `config/` - JSON contracts and policy files, including
  `lena_live_path_manifest_v1.json` (machine-readable live-path source of truth),
  `lena_kling_contract.json`, `lena_generation_policy.json`,
  `lena_autonomy_rules.json`.

**Workorders, generation data, and debug artifacts:**
- `kling_workorders/` - daily workorder JSON (what was asked for, per slot/date).
- `kling_debug/apilena_api/` - per-render raw artifacts (submit payload, submit
  response, poll response, prompt receipt, result manifest) - the ground truth for
  "what was actually sent and returned" for any given render.
- `kling_library/`, `lena_api_seed_current/` - reference/seed data for the Kling
  identity element.
- `asset_review/lena/<date>/` - QA verdict artifacts (`*_qa.json`), one per
  reviewed slot, produced by `pipeline/qa/lena_photo_qa.py` and consumed by
  `tools/lena_review_proof_render_v1.py`.

**Publishing / queue lifecycle:**
- `queue/`, `workorders/`, `publish_packets/`, `publish_readiness/`,
  `provider_review_queue/`, `provider_publish_staging/`, `published/`,
  `publish_logs/`, `outbox/`, `output/` - the stages a piece of content moves
  through from workorder to published post. Multiple folders exist because the
  pipeline evolved through several eras; not all are equally live (see
  `LIVE_PATHS.md`).
- `publisher/`, `publishing/` - publishing-surface code (naming overlap is
  historical, not a duplication bug to "fix" casually).

**Legacy / other-era surfaces (present, not canonical):**
- `provider_workorders/`, `provider_outputs/`, `provider_library/` - OpenArt/
  Seedance-era data, read-only historical artifacts per
  `tools/LEGACY_PROVIDER_SURFACES.md`.
- `strategy/` - older strategy-era planning code, superseded.

**Everything else (present, lower relevance to the current Lena photo work):**
- `analytics/`, `autonomy/`, `bond_funnel/`, `compositor/`, `content_library/`,
  `debug/`, `dialogue/`, `feedback/`, `global_character_anchor/`, `health_logs/`,
  `influencer_nodes/`, `input/`, `life_generator/`, `media_host/`, `monetization/`,
  `quality_reports/`, `renderer/`, `schedule/`, `series_campaigns/`, `state/`,
  `tests/`, `tts/`, `workorder_seed_repair/` - each owns a narrower feature area.
  Not covered in more depth here since none were touched in the pivot; grep or ask
  before assuming what's live inside any of these.
- `change_notes/` - the continuity system: `NEXT_SESSION_START.md`,
  `lena_filesystem_native_agent_pivot_master.md`,
  `lena_agentic_pivot_changelog.md`. Read `NEXT_SESSION_START.md` first, always.
- `change_notes/CHAT_SESSION_BOOT_PROMPT.md` and
  `knowledge/content_bot/SESSION_BOOT_PROTOCOL.md` - the reusable new-session
  boot surfaces; pointer-based on purpose so chats orient on live source files
  instead of copied history.

## What this map deliberately leaves out

Every `.bak_*` file, every versioned duplicate script in `tools/`, and every
per-date data file under workorder/debug/review folders. Those are instances, not
structure - go to `AUTHORITATIVE_SURFACES.md` or the relevant folder directly when
you need one.

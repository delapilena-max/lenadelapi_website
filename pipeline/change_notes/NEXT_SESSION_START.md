# Next Session Start - Lena Reference-Guided Higgsfield Integration

Updated: 2026-07-23
Repo: `C:\projects\ai\content_bot\lenadelapi_website_full_photo_autonomy`

## Current Git State

- HEAD: `1fbd796b184f01faac0882926e59dbc97c822e8e`
- Branch: detached HEAD
- Worktree: intentionally dirty with the uncommitted Soul Cinema Studio integration.
- The provider-retirement cleanup is already committed at HEAD.

## Primary Objective

Replace Lena's rejected unrestricted Higgsfield `text2image_soul_v2` route with a fail-closed, reference-guided Higgsfield workflow that can still generate photos.

The selected replacement is `soul_cinema_studio`. Marketing Studio is not used.

## Replacement Contract

- Provider: Higgsfield only
- Model/workflow: `soul_cinema_studio`
- Lena Soul ID: `e45ec580-a6db-4063-a9b2-f9163856daae`
- Source-image parameter: `image_references`
- Exactly one source image is required.
- Source image: `pipeline/higgsfield_library/lena/2026-07-09/prompt_isolation_tests/readypack0709-pack004-08-wardrobe-test-c_seed.png`
- Source image SHA-256: `7649a7ab360832390eac0e5f06ed7bb4f21d941f31e57201ef6721c00a313ffb`
- Source authority: `pipeline/identity/lena_visual_reference_authority_v1.json`
- Aspect ratio: `9:16`
- Quality: `2k`
- Prompt enhancement: explicitly disabled

The source authority is identity continuity only. It is not treated as scene or style authority.

## Implemented Offline

- Added a canonical Soul Cinema contract that validates the authority artifact, source path, source bytes, SHA-256, model, and Lena Soul ID.
- Updated handoff, manual approval, standing-autonomy approval, cycle authorization, claim, receipt, executor, manifest, and retry lineage to carry the exact reference binding.
- The provider argv now requires the full approved prompt, exact Lena Soul ID, exact source image, `9:16`, `2k`, and `enhance_prompt=false`.
- Missing, substituted, stale, malformed, or SHA-mismatched reference evidence fails before provider submission.
- New provider-command evidence binds the exact Soul/reference argv to the returned job UUID.
- New identity manifests use `soul_cinema_studio`; historical `text2image_soul_v2` evidence remains recognized as historical and is not rewritten.
- Kling Omni, OpenArt/Seedance, Marketing Studio, and video are not active.

## Operational State

- No paid Soul Cinema generation has been performed.
- The replacement is offline-integrated but not yet provider-proven with a new image.
- Do not queue or publish the previously rejected image.
- No Anthropic call, queue mutation, publishing, scheduler activation, or `.env` access occurred during this integration.

## Verification

- Executor contract: `65 passed`
- Canonical generation approval: `115 passed`
- Retry handoff and retry approval: `53 passed`
- Provider policy/config: `12 passed`
- Handoff builder excluding one unrelated pre-existing negative-test failure: `16 passed, 1 deselected`
- Focused cross-boundary integration ring: `14 passed`
- Controlled success-path proof: `1 passed`
- `git diff --check`: clean, with line-ending warnings only

Unrelated failures observed during broader focused files:

- `test_missing_selected_candidate_fails_closed` receives a raw `FileNotFoundError` instead of its expected normalized exit.
- `test_authorization_bound_photo_qa_context_allows_historical_expired_authorization` has a stale monkeypatch lambda signature.
- The real offline controlled harness stopped during candidate selection for its synthetic test day; no provider call occurred.

Do not broaden this replacement patch to fix those unrelated tests.

## Runtime Artifacts

Existing untracked runtime artifacts remain under:

- `pipeline/approvals/lena/generation/2026-07-23/`
- `pipeline/higgsfield_debug/2026-07-23/`
- `pipeline/state/lena_engagement_demand_state_v1.json`
- `pipeline/state/lena_world_state_v1.json`
- `pipeline/strategy/`

Do not stage or modify them unless Nicolas explicitly names an artifact.

## Next Safe Action

1. Review the uncommitted replacement integration.
2. Commit only the intended source, tests, policy, and continuity notes.
3. Only after explicit paid-test approval, create fresh paperwork and run one executor-only Soul Cinema generation.
4. Stop after download for human review. Do not queue or publish automatically.

## Hard Prohibitions

- Do not restore unrestricted `text2image_soul_v2` for new Lena generation.
- Do not use Marketing Studio.
- Do not restore Kling Omni, OpenArt, Seedance, BodyLock, or video generation.
- Do not run paid generation without explicit authorization.
- Do not call Anthropic, queue, publish, or activate the scheduler as part of the first proof.
- Do not print or edit `.env`.
- Do not stage untracked runtime evidence by accident.

## Addendum (Claude, later same day 2026-07-23) - Soul ID rotation

Action 3 above ran: job `64084207-2b32-4ed4-bcfa-c32fa66eeedd` under Soul id `e45ec580-a6db-4063-a9b2-f9163856daae`, slot `lenagate2026072382b626ca-pack000-00-photo`, completed and downloaded. Nicolas reviewed it and it did not look like Lena. Free, read-only `higgsfield` CLI checks (no spend) showed `e45ec580` was itself a fresh Soul (created 2026-07-20) that had never produced an accepted Lena image -- every prior accepted image, including the pinned reference photo, was generated under an older id, `90a293d7-f3af-4377-8751-3304a27b6f31`, which by 2026-07-23 no longer existed on the account (`soul-id get` returned "Soul not found").

Nicolas erased the account's Souls and retrained a fresh Lena Soul 2.0: `79119c27-64fc-47f8-9ff3-c174d12932aa` (`type: soul_2`, `status: completed`, confirmed via `higgsfield soul-id list --json`). Claude updated the current-id constant (`pipeline/identity/lena_higgsfield_soul_cinema_contract_v1.py::CUSTOM_REFERENCE_ID`), the historical-evidence set (`pipeline/identity/lena_higgsfield_identity.py::APPROVED_CUSTOM_REFERENCE_IDS`, which now retains `e45ec580` only as historical fact), the executor's doc comment, and the pinned test literals in `tests/test_lena_build_next_live_image_handoff_v1.py`, `tests/test_lena_higgsfield_executor_handoff_contract_v1.py`, and `tests/test_lena_prepare_higgsfield_retry_handoff_v1.py`.

Next safe action: this new Soul id has NOT yet been proven with any live generation. Do not assume it visually matches Lena until a fresh paid, executor-only test is explicitly authorized, run, and reviewed by Nicolas -- same process as before (fresh handoff/approval, stop after download, no queue/publish/second job).

## Addendum (Codex, 2026-07-31) - single canonical publisher secret source

A. What changed

- Removed the per-worktree `.env` requirement for Lena photo publishing in this deployment checkout.
- The shared config resolver, go-live readiness surface, and scheduler driver launcher now all resolve governed publisher secrets from the single canonical machine-local secret source `C:\projects\ai\content_bot\.env`.
- The tracked env-key map is now translation-only and no longer declares repo-local dotenv discovery.
- `.env.example` and tracked publisher config notes now instruct operators to keep secrets only in `C:\projects\ai\content_bot\.env`.

B. Files changed

- `.env.example`
- `pipeline/influencer_nodes/lena/meta_env_key_map_v2_9_1.json`
- `pipeline/influencer_nodes/lena/meta_publisher_config_v2_9.local.json`
- `pipeline/change_notes/NEXT_SESSION_START.md`
- `tests/test_lena_autopublish_go_live_readiness_v1.py`
- `tests/test_lena_scheduler_registration_source_v1.py`
- `tools/lena_autonomy_scheduler_driver_run_v1.ps1`
- `tools/lena_autopublish_go_live_readiness_v1.py`
- `tools/lena_meta_refresh_page_token_v1.py`
- `tools/publishers/lena_meta_publish_common_v2_9.py`

C. Validations run

- `C:\Python314\python.exe -m py_compile tools\publishers\lena_meta_publish_common_v2_9.py tools\lena_autopublish_go_live_readiness_v1.py tools\lena_meta_refresh_page_token_v1.py tests\test_lena_autopublish_go_live_readiness_v1.py tests\test_lena_scheduler_registration_source_v1.py tests\test_lena_autonomy_scheduler_driver_v1.py tests\test_lena_autopublish_approved_queue_v2_8.py tests\test_lena_autopublish_approved_queue_v2_8_new.py tests\test_lena_run_autonomous_publish_cycle_v1.py tests\test_lena_build_publish_packet_v1.py`
- `C:\Python314\python.exe -m pytest -p no:cacheprovider tests/test_lena_autopublish_go_live_readiness_v1.py tests/test_lena_build_publish_packet_v1.py tests/test_lena_autonomy_scheduler_driver_v1.py tests/test_lena_scheduler_registration_source_v1.py tests/test_lena_autopublish_approved_queue_v2_8.py tests/test_lena_autopublish_approved_queue_v2_8_new.py tests/test_lena_run_autonomous_publish_cycle_v1.py`
- PowerShell parser checks passed for `tools/lena_autonomy_scheduler_driver_run_v1.ps1`, `tools/register_lena_autonomy_scheduler_task_v1.ps1`, and `setup_lena_3photo_scheduler_v1.ps1`.
- `git diff --check` passed with line-ending warnings only.
- Read-only readiness from `C:\projects\ai\content_bot_photo_production_main_v1` resolved `META_PAGE_ACCESS_TOKEN` and the other governed secret keys from `C:\projects\ai\content_bot\.env` without requiring a deployment-local `.env`.

D. Decisions made

- Git worktree cleanliness is not allowed to govern secret-source authority.
- Secret-source authority is now fixed to `C:\projects\ai\content_bot\.env`, while non-secret publisher values continue to come from `pipeline/influencer_nodes/lena/meta_publisher_config_v2_9.local.json`.
- The scheduler wrapper now imports the same Python resolver used by readiness and publisher runtime rather than re-implementing secret loading in PowerShell.

E. Blockers / parked branches

- Readiness no longer reports `publisher_config_not_ready` or `environment_visibility_issue` for this checkout.
- The remaining readiness blocker is still `repository_dirty` because `tests/test_lena_scheduler_migration_plan_v1.py` and `tools/migrate_lena_legacy_scheduler_tasks_to_canonical_driver_v1.ps1` remain untracked in this worktree.
- The canonical driver task is still not registered, and the four disabled legacy tasks still point at `C:\projects\ai\lenadelapi_website_autopublish_fix`; that scheduler replacement remains parked pending explicit approval.

F. Next approved step

1. Decide whether to land or remove the two unrelated local migration files so the deployment checkout can become clean.
2. After the worktree is clean and with explicit approval, run the disabled-task replacement step for the scheduler.

G. What must not be done

- Do not create or require `C:\projects\ai\content_bot_photo_production_main_v1\.env`.
- Do not copy, print, or rewrite any secret from `C:\projects\ai\content_bot\.env`.
- Do not modify Task Scheduler in this step.
- Do not publish, generate media, create queues, invoke Anthropic, or touch video in this step.

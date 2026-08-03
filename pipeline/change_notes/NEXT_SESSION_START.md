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

## Addendum (Codex, 2026-07-31) - canonical disabled scheduler deployed; bounded one-photo proof staged

A. What changed

- Verified the live scheduler migration outcome in the canonical deployment checkout after the elevated governed `-Apply`.
- Confirmed `Lena Autonomy Scheduler Driver` is installed, disabled, bound to the canonical launcher and working directory, and the four obsolete Lena tasks are retired.
- Re-verified the preserved migration evidence outside Git: migration receipt, rollback instructions, canonical post-export, and all four legacy XML backups with matching recorded hashes.
- Re-ran read-only publisher/scheduler readiness from `C:\projects\ai\content_bot_photo_production_main_v1` and confirmed publisher configuration, environment visibility, credential visibility, media-host readiness, canonical secret-source binding, and canonical disabled-task deployment state.
- Prepared the bounded one-photo autonomy proof package in this status record only. No proof was executed.

B. Files changed

- `pipeline/change_notes/NEXT_SESSION_START.md`

C. Validations run

- Read-only `Get-ScheduledTask` / `Export-ScheduledTask` verification for:
  - `Lena Autonomy Scheduler Driver`
  - `Lena Daily Orchestrator`
  - `Lena Publish Morning Slot`
  - `Lena Publish Afternoon Slot`
  - `Lena Publish Evening Slot`
- `C:\Python314\python.exe -m tools.lena_autopublish_go_live_readiness_v1 --production-root C:\projects\ai\content_bot_photo_production_main_v1 --python-exe C:\Python314\python.exe --validate-only`
- Re-read preserved evidence under:
  - `C:\Users\Nicolas\AppData\Local\Temp\lena_scheduler_apply_20260731\apply_live_20260731_124953`

D. Decisions made

- Treat `StopAtDurationEnd=true` together with an omitted repetition `Duration` element as `non_blocking_serialization_deviation`; do not reinstall or mutate the task solely for that inert serialized field.
- Treat the scheduler deployment as successful and disabled-by-default, with rollback evidence preserved.
- Keep continuous autonomy inactive. The next gate is one bounded photo proof only, with Phase A generation/local evaluation and Phase B live publication requiring separate explicit Nicolas authorizations.
- Use the deterministic controlled photo route:
  - strategy prep dry-run
  - controlled selected-candidate artifact
  - generation reconciliation artifact
  - next-live-image handoff artifact
  - single-use Higgsfield generation approval artifact
  - one live executor run
  - local deterministic QA
  - privacy-clean derivative
  - publish packet
  - one approved queue row
  - one manual live publish invocation

E. Blockers / parked branches

- Live readiness facts are green, but the current readiness script still reports the older top-level classification:
  - actual `overall_result`: `ready_for_disabled_scheduler_replacement`
  - expected operational classification now that the canonical disabled task is deployed: `ready_for_bounded_photo_autonomy_proof`
- This is now a source-classification mismatch, not an environment, credential, scheduler-installation, or task-state blocker.
- The canonical scheduler must remain disabled. No recurring autonomy proof is authorized.

F. Next approved step

1. If Nicolas explicitly authorizes Phase A, run the bounded one-photo generation route only:
   - `C:\Python314\python.exe tools\strategy\lena_run_strategy_autonomy_prep_v1.py --date <UTC_DATE> --recipes hcr_012 --controlled-photo-autonomy`
   - `C:\Python314\python.exe tools\lena_record_higgsfield_generation_approval_v1.py --handoff-artifact <handoff_json> --operator-id nicolas --confirm "<required confirmation phrase>"`
   - `C:\Python314\python.exe pipeline\higgsfield_lena_api_executor.py --handoff-artifact <handoff_json> --approval-artifact <generation_approval_json> --live`
  - `C:\Python314\python.exe -m tools.lena_photo_qa_disposition_v1 --decision-artifact <handoff_json> --manifest <result_manifest_json> --image <generated_image_path> --expected-image-sha256 <generated_image_sha256> --identity-evidence <identity_verification_json> --identity-reference-authority-artifact C:\projects\ai\content_bot_photo_production_main_v1\pipeline\identity\lena_visual_reference_authority_v1.json --identity-reference-authority-sha256 080ea6edafb02aa73f412e9d60e2315019f3a905f17f8ef84d900150a037041c --identity-reference C:\projects\ai\content_bot_photo_production_main_v1\pipeline\higgsfield_library\lena\2026-07-09\prompt_isolation_tests\readypack0709-pack004-08-wardrobe-test-c_seed.png::7649a7ab360832390eac0e5f06ed7bb4f21d941f31e57201ef6721c00a313ffb --qa-mode autonomous_local --write-artifact`
   - Stop after local QA, privacy-clean derivative creation, and human review of the generated image plus caption.
2. Only after separate explicit Nicolas approval of the specific generated photo and caption, run Phase B:
   - `C:\Python314\python.exe tools\lena_build_publish_packet_v1.py --date <UTC_DATE>`
   - `C:\Python314\python.exe tools\lena_build_approved_publish_queue_v2_8.py --date <UTC_DATE> --platforms "Instagram Feed"`
   - `C:\Python314\python.exe tools\lena_autopublish_approved_queue_v2_8.py --date <UTC_DATE> --platforms "Instagram Feed" --live --i-understand-this-can-publish --limit 1`

Bounded one-photo proof package

- Route: `tools/strategy/lena_run_strategy_autonomy_prep_v1.py --controlled-photo-autonomy` forces `--recipes hcr_012`, selects one controlled candidate, builds one reconciliation artifact, then builds one `lena_next_live_image_handoff` artifact.
- Soul binding: the live executor enforces the current Lena Soul `79119c27-64fc-47f8-9ff3-c174d12932aa`; provider submission fails closed unless `--soul-id` is present and exactly matches the verified Lena Soul binding.
- HPE / prompt provenance: the handoff must bind the selected candidate SHA, prompt SHA, candidate-selection binding, provider-execution binding, and binding-linkage authority blocks. Phase A uses the canonical executor only through `--handoff-artifact ... --approval-artifact ... --live`.
- Wardrobe / scene authority: the controlled policy binds recipe `hcr_012`, wardrobe `wc_p050`, and the committed identity reference authority at `pipeline/identity/lena_visual_reference_authority_v1.json`.
- Provider / model route: Higgsfield only, model `text2image_soul_v2`, through `pipeline/higgsfield_lena_api_executor.py`; no video provider, no Anthropic requirement.
- Maximum paid cost: `3 provider_credits` daily ceiling from `pipeline/config/lena_standing_autonomy_policy_v1.json`; this package still caps generation count at exactly `1`.
- Generation count limit: `1`; no second candidate, no batch, no retry, no fallback.
- Framing: aspect ratio `9:16`; output extensions limited to the approved still-image set; platform-safe feed-photo composition only.
- Local deterministic QA gates: provenance binding, identity verification, Lena photo QA disposition, no-provider/no-publish QA package, and privacy-clean derivative preparation.
- Identity / Soul lineage checks: handoff, approval artifact, executor provider-command binding, manifest, and local identity evidence must all bind the same Soul/reference/prompt/candidate lineage.
- Clean derivative / metadata scrubbing: required before any Phase B queue construction for the controlled photo route; clean export must bind source SHA and lineage in its report.
- Caption path: the content packet `caption_draft` is the deterministic caption seed; any Phase B live publication remains separately review-gated against the exact generated image.
- Target platform: `Instagram Feed`
- Queue construction: build accepted publish packet, then one queue row only, then one manual live publish invocation with explicit flags.
- Publish authorization boundary: Phase A approval does not authorize queue creation or publication. Phase B requires separate explicit Nicolas approval of the specific photo and exact caption.
- Stop conditions:
  - any provenance / Soul / prompt / SHA mismatch
  - any QA non-accept result
  - any duplicate-content rejection
  - any missing clean-export binding
  - any missing sidecar or caption/photo approval mismatch
  - any attempt to exceed one generation, one queue row, or one publish action
- Rollback / reconciliation:
  - Phase A stop leaves no queue or publish mutation
  - Phase B queue/publish stays bounded to one row and one platform with receipt-based duplicate prevention
  - preserved scheduler rollback instructions remain at `C:\Users\Nicolas\AppData\Local\Temp\lena_scheduler_apply_20260731\apply_live_20260731_124953\migration_output\scheduler_task_migration_20260731_125425\rollback_instructions.json`
- Evidence / receipt roots:
  - scheduler migration evidence: `C:\Users\Nicolas\AppData\Local\Temp\lena_scheduler_apply_20260731\apply_live_20260731_124953`
  - handoff: `pipeline/strategy/lena/next_actions/<UTC_DATE>/`
  - generation approval / claim / receipt: `pipeline/approvals/lena/generation/<UTC_DATE>/`
  - generated source image: `pipeline/higgsfield_library/lena/<UTC_DATE>/`
  - provider manifest / debug evidence: `pipeline/higgsfield_debug/<UTC_DATE>/<slot_id>/`
  - QA artifacts: `pipeline/asset_review/lena/<UTC_DATE>/`
  - publish packets: `pipeline/publish_packets/lena/<UTC_DATE>/`
  - approved queue / claims / receipts: `pipeline/publishing/lena/approved_queue/<UTC_DATE>/`, `pipeline/publishing/lena/approved_queue_claims/<UTC_DATE>/`, `pipeline/publishing/lena/approved_queue_receipts/<UTC_DATE>/`

G. What must not be done

- Do not enable or start `Lena Autonomy Scheduler Driver`.
- Do not reinstall, mutate, or roll back the successful scheduler migration to chase the inert `StopAtDurationEnd` serialization field.
- Do not treat the current disabled scheduler deployment as active continuous autonomy.
- Do not run any paid generation without explicit Nicolas authorization for Phase A.
- Do not create a queue row or publish anything under Phase A authority.
- Do not publish anything under queue-construction authority alone; Phase B requires separate explicit approval of the exact photo and caption.
- Do not call Anthropic, touch video, invoke TikTok, or use any non-Higgsfield generation provider in this proof lane.

## Addendum (Codex, 2026-07-31) - automatic governed receipt after confirmed Lena manual publish

A. What changed

- Finished the narrow manual-publish receipt fix in the canonical deployment checkout.
- `tools/lena_autopublish_approved_queue_v2_8.py` now routes confirmed manual publish success through the same governed receipt path already used by scheduled autonomous mode.
- Manual success now writes the governed receipt before final queue-row completion.
- Existing matching receipts are recovered idempotently; conflicting receipts fail closed before any connector invocation.
- If receipt writing fails after a confirmed remote success, the row is preserved as remotely posted with local reconciliation required, and a later local-only rerun rebuilds the missing receipt from the preserved dispatch report without republishing.
- The existing successful Instagram publication, queue row, dispatch report, and reconciled receipt were re-verified and not modified or retried.

B. Files changed

- `tools/lena_autopublish_approved_queue_v2_8.py`
- `tests/test_lena_autopublish_approved_queue_v2_8.py`
- `pipeline/change_notes/NEXT_SESSION_START.md`

C. Validations run

- `C:\Python314\python.exe -B -m pytest -p no:cacheprovider tests/test_lena_autopublish_approved_queue_v2_8.py tests/test_lena_autopublish_approved_queue_v2_8_new.py tests/test_lena_run_autonomous_publish_cycle_v1.py tests/test_lena_build_publish_packet_v1.py tests/test_lena_build_generation_reconciliation_v1.py tests/test_lena_record_generation_reconciliation_decision_v1.py tests/test_lena_reconciliation_integration_v1.py tests/test_lena_standing_autonomy_policy_v1.py tests/test_lena_instagram_media_host_custom_domain_v1.py tests/test_lena_autopublish_go_live_readiness_v1.py tests/test_lena_autonomy_scheduler_driver_v1.py tests/test_lena_scheduler_registration_source_v1.py -q`
- Result: `146 passed`
- Focused receipt file result: `21 passed`
- `C:\Python314\python.exe -m py_compile tools\lena_autopublish_approved_queue_v2_8.py tools\lena_build_publish_packet_v1.py tools\lena_autopublish_go_live_readiness_v1.py tools\lena_run_autonomous_publish_cycle_v1.py tools\lena_validate_approved_queue_autopublisher_v2_8.py tools\lena_standing_autonomy_policy_v1.py tools\strategy\lena_build_generation_reconciliation_v1.py tools\strategy\lena_record_generation_reconciliation_decision_v1.py tools\strategy\lena_reconciliation_contract_v1.py tools\publishers\lena_meta_publish_common_v2_9.py tests\test_lena_autopublish_approved_queue_v2_8.py tests\test_lena_autopublish_approved_queue_v2_8_new.py tests\test_lena_run_autonomous_publish_cycle_v1.py tests\test_lena_build_publish_packet_v1.py tests\test_lena_build_generation_reconciliation_v1.py tests\test_lena_record_generation_reconciliation_decision_v1.py tests\test_lena_reconciliation_integration_v1.py tests\test_lena_standing_autonomy_policy_v1.py tests\test_lena_instagram_media_host_custom_domain_v1.py tests\test_lena_autopublish_go_live_readiness_v1.py tests\test_lena_autonomy_scheduler_driver_v1.py tests\test_lena_scheduler_registration_source_v1.py`
- `C:\Python314\python.exe tools\lena_validate_approved_queue_autopublisher_v2_8.py`
- Real read-only dry run after the existing July 31 publication:
  - `C:\Python314\python.exe tools\lena_autopublish_approved_queue_v2_8.py --date 2026-07-31 --platforms "Instagram Feed" --dry-run`
  - Result: `processed=0`, `publish_calls_performed=0`, `queue_mutated=false`
- Read-only readiness:
  - `C:\Python314\python.exe -m tools.lena_autopublish_go_live_readiness_v1 --production-root C:\projects\ai\content_bot_photo_production_main_v1 --python-exe C:\Python314\python.exe --validate-only`
  - Result: read-only only; `provider_calls_performed=0`, `publish_calls_performed=0`, `anthropic_calls_performed=0`
- `git diff --check`

D. Decisions made

- Keep the governed receipt schema unchanged; the defect was in manual-mode control flow, not in the receipt artifact contract.
- Treat the preserved dispatch report as the only allowed local reconciliation source when a confirmed publish succeeded but receipt writing failed.
- Preserve duplicate-publication prevention by treating `publish_state=posted` plus `failure_reason=receipt_reconciliation_required` as remotely published, never as publish retry authority.
- Keep the existing successful July 31 Instagram publication and all of its runtime artifacts immutable.
- Keep the canonical scheduler disabled. Continuous autonomy remains inactive.

E. Blockers / parked branches

- The narrow source fix is ready locally, but merge is still pending.
- Read-only readiness still reports `repository_dirty` until this fix is committed and pushed.
- Continuous autonomy is still not authorized; scheduler enablement remains a separate explicit gate after this fix is merged.

F. Next approved step

1. Commit only the receipt-fix source, focused tests, and this status-note update.
2. Push the fix on a new branch and open a PR into `main`.
3. Wait for terminal CI.
4. Only after merge and separate explicit authorization may any scheduler enablement or further bounded autonomy proof proceed.

G. What must not be done

- Do not republish or otherwise touch the existing July 31 Instagram publication.
- Do not modify queue runtime artifacts, receipts, media, or dispatch evidence as source.
- Do not enable or start `Lena Autonomy Scheduler Driver`.
- Do not publish, generate media, invoke Anthropic, or touch video in this fix step.

## Addendum (Codex, 2026-07-31) - governed runtime evidence no longer self-blocks readiness

A. What changed

- Narrowed the readiness `repository_dirty` gate so it no longer blocks on the exact governed July 31 runtime evidence written by the approved photo lane.
- Readiness now excludes only validated runtime artifacts under the approved Lena photo roots for analytics, bounded-live authorization, publish packets, approved queue rows, approved queue receipts, dispatch outbox payloads, and dispatch reports.
- The exclusion is fail-closed: tracked source changes still block, unexpected untracked files still block, fake source/config/secret-like files under those roots still block, and traversal or resolved-path escape does not qualify for exclusion.
- Read-only readiness now reports the excluded runtime paths, count, and approved roots separately so the deployment can remain physically evidence-bearing without appearing operationally unsafe.

B. Files changed

- `tools/lena_autopublish_go_live_readiness_v1.py`
- `tests/test_lena_autopublish_go_live_readiness_v1.py`
- `pipeline/change_notes/NEXT_SESSION_START.md`

C. Validations run

- `C:\Python314\python.exe -B -m pytest -p no:cacheprovider tests/test_lena_autopublish_go_live_readiness_v1.py tests/test_lena_autopublish_approved_queue_v2_8.py tests/test_lena_autopublish_approved_queue_v2_8_new.py tests/test_lena_run_autonomous_publish_cycle_v1.py tests/test_lena_build_generation_reconciliation_v1.py tests/test_lena_record_generation_reconciliation_decision_v1.py tests/test_lena_reconciliation_integration_v1.py tests/test_lena_autonomy_scheduler_driver_v1.py tests/test_lena_scheduler_registration_source_v1.py tests/test_lena_build_publish_packet_v1.py tests/test_lena_standing_autonomy_policy_v1.py tests/test_lena_instagram_media_host_custom_domain_v1.py -q`
- Result: `158 passed`
- Focused readiness file result: `33 passed`
- `C:\Python314\python.exe -m py_compile tools\lena_autopublish_go_live_readiness_v1.py tools\lena_autopublish_approved_queue_v2_8.py tools\lena_build_publish_packet_v1.py tools\lena_run_autonomous_publish_cycle_v1.py tools\lena_validate_approved_queue_autopublisher_v2_8.py tools\lena_standing_autonomy_policy_v1.py tools\strategy\lena_build_generation_reconciliation_v1.py tools\strategy\lena_record_generation_reconciliation_decision_v1.py tools\strategy\lena_reconciliation_contract_v1.py tools\publishers\lena_meta_publish_common_v2_9.py tests\test_lena_autopublish_go_live_readiness_v1.py tests\test_lena_autopublish_approved_queue_v2_8.py tests\test_lena_autopublish_approved_queue_v2_8_new.py tests\test_lena_run_autonomous_publish_cycle_v1.py tests\test_lena_build_publish_packet_v1.py tests\test_lena_build_generation_reconciliation_v1.py tests\test_lena_record_generation_reconciliation_decision_v1.py tests\test_lena_reconciliation_integration_v1.py tests\test_lena_standing_autonomy_policy_v1.py tests\test_lena_instagram_media_host_custom_domain_v1.py tests\test_lena_autonomy_scheduler_driver_v1.py tests\test_lena_scheduler_registration_source_v1.py`
- `C:\Python314\python.exe tools\lena_validate_approved_queue_autopublisher_v2_8.py`
- `git diff --check`
- Real read-only post-publication dry run:
  - `C:\Python314\python.exe tools\lena_autopublish_approved_queue_v2_8.py --date 2026-07-31 --platforms "Instagram Feed" --dry-run`
  - Result: `processed=0`, `publish_calls_performed=0`, `queue_mutated=false`

D. Decisions made

- Treat governed runtime evidence as operationally expected, not as implicit source dirt, but only when each path matches an exact approved runtime root plus artifact-shape contract.
- Keep the approved runtime exclusion roots exact:
  - `pipeline/analytics/`
  - `pipeline/approvals/lena/bounded_live_cycles/`
  - `pipeline/publish_packets/`
  - `pipeline/publishing/lena/approved_queue/`
  - `pipeline/publishing/lena/approved_queue_receipts/`
  - `pipeline/publishing/lena/dispatch_outbox/`
  - `pipeline/publishing/lena/dispatch_reports/`
- Preserve the July 31 queue row, receipt, dispatch payload/report, approval evidence, and analytics files as immutable runtime evidence; do not delete them to make readiness pass.
- Keep the canonical scheduler disabled and continuous autonomy inactive.

E. Blockers / parked branches

- During implementation, read-only readiness still truthfully reported `repository_dirty` while these tracked source/test edits were uncommitted.
- After commit, the only expected remaining gate is the existing pre-activation state with the canonical scheduler still disabled; no provider, publisher, queue, or task mutation blocker remains in this fix lane.

F. Next approved step

1. Commit only this readiness/runtime-output correction, its focused tests, and this status-note update.
2. Re-run read-only readiness from the committed checkout to confirm the preserved July 31 governed runtime evidence no longer blocks readiness.
3. Push the fix on a new branch, open a PR into `main`, and wait for CI.
4. Do not enable the scheduler in this step.

G. What must not be done

- Do not delete or rewrite the July 31 governed runtime evidence to fake a clean repository.
- Do not broaden the exclusion to the entire `pipeline/` tree or to arbitrary untracked files.
- Do not allow `.py`, `.ps1`, config-like JSON, dotenv/secret-like files, or escape paths under runtime roots to bypass `repository_dirty`.
- Do not enable or start `Lena Autonomy Scheduler Driver`.
- Do not publish, generate media, invoke Meta/Higgsfield/Anthropic, or touch video in this fix step.

## Addendum (Codex, 2026-07-31) - canonical scheduler automatic poll failure fixed

A. What changed

- Diagnosed the real automatic-poll failure for `Lena Autonomy Scheduler Driver` from the preserved July 31 scheduler log and exact task action.
- The scheduled wrapper was invoking `C:\Python314\python.exe - <RepoRoot>`, then running `tools.lena_autonomy_scheduler_driver_v1` under `runpy` without clearing that bootstrap argument.
- On every automatic poll, the Python driver reached `argparse` with the stray positional repository-root argument still present and failed immediately with:
  - `usage: - [-h] [--inspect-only] [--now NOW]`
  - `error: unrecognized arguments: C:\projects\ai\content_bot_photo_production_main_v1`
- The fix is narrow: the wrapper now preserves the canonical secret-source bootstrap but resets `sys.argv` to the driver module name before entering `runpy`, so scheduled polls no longer inherit the wrapper bootstrap argument as a fake CLI operand.
- This failure occurred after Python started but before any slot decision, generation, queue, publish, Anthropic, scheduler mutation, or video action was reached.

B. Files changed

- `tools/lena_autonomy_scheduler_driver_run_v1.ps1`
- `tests/test_lena_autonomy_scheduler_driver_v1.py`
- `tests/test_lena_scheduler_registration_source_v1.py`
- `pipeline/change_notes/NEXT_SESSION_START.md`

C. Validations run

- Preserved failure evidence outside Git:
  - `C:\Users\Nicolas\AppData\Local\Temp\lena_scheduler_failure_20260731_181428`
- Exact task action repro from the canonical working directory:
  - wrapper exit code `1`
  - deepest reproduced failure:
    - file: `tools/lena_autonomy_scheduler_driver_v1.py`
    - stage: CLI parse
    - error: unrecognized repository-root positional argument
- `C:\Python314\python.exe -B -m pytest -p no:cacheprovider tests/test_lena_autonomy_scheduler_driver_v1.py tests/test_lena_scheduler_registration_source_v1.py tests/test_lena_autopublish_go_live_readiness_v1.py tests/test_lena_autopublish_approved_queue_v2_8.py tests/test_lena_autopublish_approved_queue_v2_8_new.py tests/test_lena_run_autonomous_publish_cycle_v1.py tests/test_lena_build_publish_packet_v1.py tests/test_lena_build_generation_reconciliation_v1.py tests/test_lena_record_generation_reconciliation_decision_v1.py tests/test_lena_reconciliation_integration_v1.py tests/test_lena_standing_autonomy_policy_v1.py tests/test_lena_instagram_media_host_custom_domain_v1.py tests/test_lena_photo_qa_disposition_v1.py -q`
- Result: `315 passed, 1 skipped`
- `C:\Python314\python.exe -m py_compile tools\lena_autonomy_scheduler_driver_v1.py tools\lena_autopublish_go_live_readiness_v1.py tools\lena_autopublish_approved_queue_v2_8.py tools\lena_build_publish_packet_v1.py tools\lena_run_autonomous_publish_cycle_v1.py tools\lena_validate_approved_queue_autopublisher_v2_8.py tools\lena_standing_autonomy_policy_v1.py tools\strategy\lena_build_generation_reconciliation_v1.py tools\strategy\lena_record_generation_reconciliation_decision_v1.py tools\strategy\lena_reconciliation_contract_v1.py tools\publishers\lena_meta_publish_common_v2_9.py tests\test_lena_autonomy_scheduler_driver_v1.py tests\test_lena_scheduler_registration_source_v1.py tests\test_lena_autopublish_go_live_readiness_v1.py tests\test_lena_autopublish_approved_queue_v2_8.py tests\test_lena_autopublish_approved_queue_v2_8_new.py tests\test_lena_run_autonomous_publish_cycle_v1.py tests\test_lena_build_publish_packet_v1.py tests\test_lena_build_generation_reconciliation_v1.py tests\test_lena_record_generation_reconciliation_decision_v1.py tests\test_lena_reconciliation_integration_v1.py tests\test_lena_standing_autonomy_policy_v1.py tests\test_lena_instagram_media_host_custom_domain_v1.py tests\test_lena_photo_qa_disposition_v1.py`
- PowerShell parser checks passed for:
  - `tools/lena_autonomy_scheduler_driver_run_v1.ps1`
  - `tools/register_lena_autonomy_scheduler_task_v1.ps1`

D. Decisions made

- Treat the proven scheduler failure as a wrapper-to-driver argv hygiene defect, not as a slot-policy, readiness, queue, provider, or runtime-evidence failure.
- Keep the central secret source unchanged at `C:\projects\ai\content_bot\.env`.
- Keep the canonical task definition, trigger, principal, working directory, media host, duplicate prevention, automatic receipts, HPE, autonomous-local QA, Soul binding, and photo-only scope unchanged.
- Do not broaden this fix into a scheduler redesign or alternate orchestrator audit.

E. Blockers / parked branches

- The automatic poll failure itself is fixed in source and covered by regression tests.
- Remaining live activation steps require elevated local Administrator PowerShell to enable the Windows scheduled task; this Codex session must not mutate Task Scheduler directly.
- The preserved July 31 governed runtime evidence remains authoritative and untouched.

F. Next approved step

1. Commit only the scheduler wrapper fix, direct tests, and this status-note update.
2. Push a focused PR into `main`, wait for CI, and merge with a merge commit if green.
3. Fast-forward the deployment checkout to the merged `main`.
4. Hand off the exact elevated enable/verification commands for the operator to run locally, then inspect the resulting automatic polls.

G. What must not be done

- Do not rerun Phase A.
- Do not generate another proof photo or republish queue `q_488721d95be927`.
- Do not touch the video lane.
- Do not call Anthropic.
- Do not reset or clean away governed runtime evidence.

## Addendum (Codex, 2026-07-31) - scheduler runtime log no longer self-blocks activation readiness

A. What changed

- Verified on merged `main` that the preserved July 31 governed queue, receipt, dispatch, approval, packet, and analytics evidence was already excluded correctly by readiness.
- Found one exact remaining activation-path blocker: the canonical scheduler wrapper writes `logs/scheduler/lena_autonomy_scheduler_<YYYY-MM-DD>.log`, and readiness was still treating that exact runtime log family as unexpected untracked source dirt.
- Narrowed the readiness runtime-path classifier so only canonical scheduler log filenames under `logs/scheduler/` are treated as governed runtime evidence.
- The exclusion remains fail-closed: arbitrary files under `logs/`, source/config/secret-like files, and any path outside the exact scheduler log root still block `repository_dirty`.

B. Files changed

- `tools/lena_autopublish_go_live_readiness_v1.py`
- `tests/test_lena_autopublish_go_live_readiness_v1.py`
- `pipeline/change_notes/NEXT_SESSION_START.md`

C. Validations run

- `C:\Python314\python.exe -B -m pytest -p no:cacheprovider tests/test_lena_autopublish_go_live_readiness_v1.py tests/test_lena_autonomy_scheduler_driver_v1.py tests/test_lena_scheduler_registration_source_v1.py tests/test_lena_autopublish_approved_queue_v2_8.py tests/test_lena_autopublish_approved_queue_v2_8_new.py tests/test_lena_run_autonomous_publish_cycle_v1.py tests/test_lena_build_publish_packet_v1.py tests/test_lena_build_generation_reconciliation_v1.py tests/test_lena_record_generation_reconciliation_decision_v1.py tests/test_lena_reconciliation_integration_v1.py tests/test_lena_standing_autonomy_policy_v1.py tests/test_lena_instagram_media_host_custom_domain_v1.py tests/test_lena_photo_qa_disposition_v1.py -q`
- Result: `316 passed, 1 skipped`
- `C:\Python314\python.exe -m py_compile tools\lena_autopublish_go_live_readiness_v1.py tests\test_lena_autopublish_go_live_readiness_v1.py tools\lena_autonomy_scheduler_driver_v1.py tools\lena_autopublish_approved_queue_v2_8.py tools\lena_build_publish_packet_v1.py tools\lena_run_autonomous_publish_cycle_v1.py tools\lena_validate_approved_queue_autopublisher_v2_8.py tools\lena_standing_autonomy_policy_v1.py tools\strategy\lena_build_generation_reconciliation_v1.py tools\strategy\lena_record_generation_reconciliation_decision_v1.py tools\strategy\lena_reconciliation_contract_v1.py tools\publishers\lena_meta_publish_common_v2_9.py tests\test_lena_autonomy_scheduler_driver_v1.py tests\test_lena_scheduler_registration_source_v1.py tests\test_lena_autopublish_approved_queue_v2_8.py tests\test_lena_autopublish_approved_queue_v2_8_new.py tests\test_lena_run_autonomous_publish_cycle_v1.py tests\test_lena_build_publish_packet_v1.py tests\test_lena_build_generation_reconciliation_v1.py tests\test_lena_record_generation_reconciliation_decision_v1.py tests\test_lena_reconciliation_integration_v1.py tests\test_lena_standing_autonomy_policy_v1.py tests\test_lena_instagram_media_host_custom_domain_v1.py tests\test_lena_photo_qa_disposition_v1.py`
- `C:\Python314\python.exe tools\lena_validate_approved_queue_autopublisher_v2_8.py`
- `git diff --check`
- Real read-only checks from the canonical deployment checkout:
  - `C:\Python314\python.exe -m tools.lena_autopublish_go_live_readiness_v1 --production-root C:\projects\ai\content_bot_photo_production_main_v1 --python-exe C:\Python314\python.exe --validate-only`
  - `C:\Python314\python.exe tools\lena_autopublish_approved_queue_v2_8.py --date 2026-07-31 --platforms "Instagram Feed" --dry-run`
- Observed result before committing this source fix:
  - scheduler log path excluded correctly
  - zero unexpected untracked paths remained
  - the only reported blocker was the tracked source/test edit itself, as intended
  - dry run stayed `processed=0`, `publish_calls_performed=0`, `queue_mutated=false`

D. Decisions made

- Treat the scheduler wrapper's daily log as governed runtime evidence because the canonical task itself writes it on every automatic poll and its presence should not make the deployment appear unsafe.
- Keep the exclusion exact to the canonical file contract:
  - root: `logs/scheduler/`
  - filename pattern: `lena_autonomy_scheduler_<YYYY-MM-DD>.log`
- Do not broaden the exclusion to arbitrary `logs/` content.

E. Blockers / parked branches

- Before commit, read-only readiness still truthfully reports `repository_dirty` because this source/test change is tracked and uncommitted.
- After commit and merge, the remaining operational gate is expected to be local Administrator enablement of the already-registered canonical task; Codex must not mutate Task Scheduler directly.

F. Next approved step

1. Commit only this narrow readiness classifier correction, its focused tests, and this status-note update.
2. Push a focused PR into `main`, wait for CI, and merge with a merge commit if green.
3. Re-run read-only readiness from the clean merged checkout.
4. Hand off the exact elevated enable/verification commands for the operator to run locally.

G. What must not be done

- Do not exclude arbitrary `logs/` content from readiness.
- Do not delete or rewrite the preserved July 31 runtime evidence.
- Do not enable or start `Lena Autonomy Scheduler Driver` from Codex.
- Do not generate, publish, invoke Anthropic, or touch video in this fix step.

## Addendum (Codex, 2026-07-31) - scheduler autonomy evidence no longer self-blocks activation readiness

A. What changed

- Found the remaining exact activation-path blocker after the clean-export and scheduler-log fixes: readiness excluded governed queue, receipt, dispatch, approval, packet, analytics, and scheduler-log outputs, but not the canonical scheduler's own Lena autonomy evidence under `pipeline/autonomy/lena/`.
- The live deployment was tracked-source clean at merged `main`, scheduler disabled, publisher/environment/credentials/media host ready, and blocked only because untracked July 31 scheduler evidence was classified as unexpected source dirt.
- Added a shared autonomy runtime evidence contract used by readiness and the scheduler driver.
- Readiness now excludes only exact governed Lena autonomy artifact shapes beneath:
  - `pipeline/autonomy/lena/daily_schedule/<YYYY-MM-DD>/lena_autonomy_daily_schedule_<YYYY-MM-DD>.json`
  - `pipeline/autonomy/lena/scheduler_driver/<YYYY-MM-DD>/<slot>_state.json`
  - `pipeline/autonomy/lena/scheduler_driver/<YYYY-MM-DD>/<slot>_<kind>_<HHMMSS>_<microseconds>.json`
- The scheduler-driver date directory must be a real ISO date, slot must be `morning`, `afternoon`, or `evening`, and receipt kind must be one of the governed scheduler lifecycle families: `generation`, `generation_success`, `generation_failure`, `publish`, `publish_failure`, `skip`, `poll`, or `poll_result`.

B. Files changed

- `tools/lena_autonomy_runtime_evidence_v1.py`
- `tools/lena_autopublish_go_live_readiness_v1.py`
- `tools/lena_autonomy_scheduler_driver_v1.py`
- `tests/test_lena_autonomy_runtime_evidence_v1.py`
- `tests/test_lena_autopublish_go_live_readiness_v1.py`
- `tests/test_lena_autonomy_scheduler_driver_v1.py`
- `pipeline/change_notes/NEXT_SESSION_START.md`

C. Validation intent

- Prove current real July 31 scheduler-driver JSON evidence is governed runtime evidence, not source dirt.
- Prove generation, generation-success, generation-failure, skip, and poll evidence shapes are accepted only when they match the exact scheduler contract.
- Prove arbitrary JSON, source scripts, executables, env/secret-like files, config-like files, traversal, symlink escape, and files outside exact approved Lena autonomy roots still fail closed.
- Prove tracked source changes still block readiness.

D. Decisions made

- Keep the exclusion exact to Lena's governed autonomy runtime roots; do not exclude `pipeline/autonomy/` broadly.
- Treat normal scheduler evidence as allowed runtime dirt for readiness, but continue reporting every excluded path, count, and root transparently.
- Do not enable, disable, or start the scheduler from Codex.
- Do not generate, queue, publish, reconcile, invoke Anthropic, or touch video.

## Addendum (Codex, 2026-08-03) - fresh Lena video creative authority prevents Pilot prompt reuse

A. What changed

- Added an offline Lena video creative-generation layer inside the canonical namespace `pipeline/media_properties/lena/video/`, so every new video content unit can receive fresh canonical A-N source artifacts before deterministic prompt compilation.
- Removed the provisional parallel `pipeline/video/` namespace during merge-gate review because it duplicated schema, provider-compiler, prompt-hash, request-hash, and example-package authority.
- Added the LLM instruction authority for structured JSON only; it cannot define schemas, compile provider requests, calculate final request hashes or fingerprints, authorize execution, reuse a prior prompt, silently change locked input, mutate learning, call providers, queue, or publish.
- The fresh helper now delegates source validation to `validate_source_for_compilation()` and plan/request compilation to the existing canonical `compile_video()` path.
- Added prompt-reuse rules that allow exact reuse only for same-job recovery, same ambiguous-submission reconciliation, same-result download/validation, or deterministic recompilation of the same immutable attempt.
- Added attempt-versioning rules so a QA-rejected attempt cannot be rerun under the old compiled prompt as a new provider create call.
- Fresh examples are generated as temporary fixtures in tests/CLI output roots only; they do not consume a governed daily production slot.

B. Files changed

- `pipeline/media_properties/lena/video/fresh_creative_generation.py`
- deleted `pipeline/video/**`
- `tools/lena_build_fresh_video_package_v1.py`
- `tests/test_lena_video_fresh_creative_generation_v1.py`
- `pipeline/change_notes/NEXT_SESSION_START.md`
- `pipeline/change_notes/lena_video_json_production_system_v1.md`

C. Validations run

- `python -B -m pytest -p no:cacheprovider tests/test_lena_video_fresh_creative_generation_v1.py -q`
  - Result: `15 passed`
- `python -B -m pytest -p no:cacheprovider tests/test_lena_video_json_schemas_v1.py tests/test_lena_video_json_validation_v1.py -q`
  - Result: `50 passed, 2 skipped`
- `python -B -m pytest -p no:cacheprovider tests/test_lena_video_json_compiler_v1.py tests/test_lena_video_json_cli_architecture_v1.py -q`
  - Result: `23 passed`
- `python -B -m pytest -p no:cacheprovider tests/test_lena_higgsfield_retry_generation_approval_v1.py tests/test_lena_record_human_rejection_v1.py tests/test_lena_higgsfield_generation_approval_v1.py -q`
  - Result: `141 passed`
- `python -B -m compileall pipeline\media_properties\lena\video\fresh_creative_generation.py tools\lena_build_fresh_video_package_v1.py tests\test_lena_video_fresh_creative_generation_v1.py`
  - Result: passed
- `git diff --check`
  - Result: passed

D. Decisions made

- Root cause: the SpaceX Pilot dataset was a single immutable example episode with validators and deterministic compilers, but no upstream governed creative-generation layer that minted fresh per-video JSON authority before each new provider create call.
- The SpaceX Pilot prompt remains valid only as an immutable example or for same-attempt recovery/reconciliation/validation/recompile; it must not become a reusable production prompt.
- The canonical namespace is `pipeline/media_properties/lena/video/`; `pipeline/video/` must not become a competing Lena video authority surface.
- Canonical source schemas, source validation, plan compilation, compiled request shape, prompt transport, request hashes, and fingerprints remain owned by the existing Lena video stack.
- Keep this as an offline source/authority slice; no live executor, queue, publication, learning mutation, or photo-lane routing changed.
- Use PR `#139` as the clean review target; conflicting PR `#138` was closed.

E. Blockers / parked branches

- No provider execution is authorized by this checkpoint.
- No automatic live-video engine integration is completed here; this is the creative authority and guard layer only.
- Legacy checkpoint-skill files `lena_filesystem_native_agent_pivot_master.md` and `lena_agentic_pivot_changelog.md` are absent from current `origin/main`; this checkpoint updates the current `NEXT_SESSION_START.md` plus the current video JSON production change note instead.

F. Next approved step

- Review and merge PR `#139` if the implementation and CI remain acceptable.
- After merge, wire future daily video planning through this fresh creative authority before any provider-bound request is considered.

G. What must not be done

- Do not reuse the SpaceX Pilot compiled prompt for a new provider create call.
- Do not rerun a QA-rejected attempt under the old prompt as a new create call.
- Do not generate media, spend credits, create queue entries, publish, invoke Anthropic, edit `.env`, or mutate the live photo lane from this slice.

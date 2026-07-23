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

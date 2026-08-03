# Lena Video JSON Production System V1 Change Note

**Date:** 2026-08-02
**Scope:** Source-only Lena video authority; no live photo deployment, provider,
media, scheduler, publishing, credential, runtime, or historical evidence change.

## What Changed

Added Lena's first complete structured-JSON video production authority: fourteen
strict schemas plus common definitions, canonical JSON/SHA-256 binding, safe
artifact loading, cross-file and semantic validation, two deterministic compiler
stages, two structured offline CLIs, premium QA reject conditions, architecture
documentation, and the complete SpaceX launch pilot chain.

The genuinely neutral JSON primitives were extracted to
`pipeline/media_properties/json_authority_v1.py`. ITB and Lena both consume that
module; neither property imports the other's canon, identity, data, policy, or
continuity. No framework, provider adapter, abstract class, database, service
container, plugin system, migration system, or workflow engine was introduced.

## Policy

The source policy now records three photo products plus exactly one final Lena
video product per governed date. Video authority is exactly 8 seconds, 720p,
720 by 1280, 9:16, and a 36-credit aggregate ceiling. Direct binding to Character
Element `6a842337-ef20-4cb9-a0ff-04fa5eb8f8d3` is mandatory. Seedance 2.0 is the
preferred initial route only inside the execution-disabled video artifact
authority and only when direct binding is supported; the active central
`video_engine` remains `null`. Voice remains optional, temporal HPE is mandatory,
and video execution still requires separate request-bound authorization. The
exact prompt is authored to the existing 4,096-character Higgsfield repository
execution policy; truncation and automatic shortening remain forbidden.

V1 authorizes zero attempts and zero retries. The provider-neutral plan and
compiled request both keep execution disabled. The photo-only standing-autonomy
policy and live deployment checkout were not modified.

## Pilot

`pipeline/media_properties/lena/video/pilots/spacex_launch_001/` contains the
complete A-through-N chain for **Lena Excitedly Watches a SpaceX Rocket Launch**.
It specifies a lawful public viewing area, distant believable launch scale,
companion-held rear smartphone camera, non-selfie framing, extra headroom, exact
continuous wardrobe, four executable HPE beats, no dialogue, no restricted
access, no SpaceX affiliation, and no execution authority.

- Generation-plan SHA-256:
  `a219ca9f40b2210542a2ba67828b50dd830c46b59e3813e6018eec420f794970`
- Compiled-request SHA-256:
  `6f80fc07960ddf4a15e62157ae9b3f75e4baf9166c25ef2fdd8985a0f45fcc36`
- Deterministic compilation fingerprint:
  `92e8887fb3c65ec7886a99f5ba7b33927d79f7086f0cd59103ad4fec8a988c0d`
- Exact prompt length/budget/headroom: `3997 / 4096 / 99` characters.
- Execution authorized: `false`
- Authorized attempts: `0`
- Actual spend: `0`

## Local Validation

All commands used `C:\Python314\python.exe` with bytecode/cache writes disabled.

- New Lena video JSON ring: `73 passed, 2 skipped`. Both skips are real-symlink
  creation cases unavailable to this non-elevated Windows process; traversal,
  local-reference confinement, root safety, and fail-closed escape tests passed.
- Directly affected shared ring: `85 passed`, covering all ITB tests after the
  neutral extraction, the Lena strategy-policy and active-provider contracts,
  and the full existing Higgsfield prompt-budget authority audit.
- Consolidated affected verification ring: `158 passed, 2 skipped`.
- File-aware source compilation: 19 changed Python files passed.
- Import smoke: 11 neutral, ITB, Lena, and CLI modules passed.
- Complete pilot validation: 14 artifacts, zero errors.
- Validator and compiler validate-only smokes returned structured JSON and zero
  activity counters.
- Repeated generation-plan and request compilation was byte-equivalent and
  matched the checked-in outputs and fingerprints.
- `git diff --check` passed.

No provider, network, generation, publishing, scheduler, video execution,
Anthropic, credential, or live photo-lane action occurred.

## Final Adversarial Review Correction

The merge review added exact A-N upstream-edge enforcement, exact four-by-two-
second HPE windows, provider-name rejection inside provider-neutral requirement
text, source-mapping-order-independent compilation, and an exact outgoing UTF-8
prompt-byte proof. The governed Pilot plan SHA, request SHA, fingerprint, prompt,
and all A-N JSON artifacts remain unchanged. The outgoing prompt is exactly
3,997 ASCII characters and UTF-8 bytes with LF separators, no repository
wrapper, and 99 characters/bytes of headroom against the 4,096-character
repository execution policy.

## Next Authorized Step

Review this source-only pull request and merge only after green CI and explicit
authorization. Provider integration, paid generation, voice, music, editing,
caption selection, scheduling, publishing, and learning ingestion remain
separate future tasks.

## 2026-08-03 Fresh Creative Authority Addendum

The SpaceX Pilot chain remains one immutable example episode, not a reusable
production prompt. A follow-up offline source slice adds the missing governed
creative-generation layer under the canonical namespace
`pipeline/media_properties/lena/video/` so future Lena video production can mint
fresh canonical A-N source artifacts for each new content unit before any
provider-bound authorization is considered.

Root cause corrected at architecture level:

- The V1 Pilot proved schema validation, cross-artifact validation, deterministic
  compilation, and prompt/request hashing.
- It did not yet provide a governed layer that creates a new per-video creative
  authority for each daily unit.
- Without that layer, an immutable compiled Pilot prompt could be mistaken for a
  production template.

The merge-gate review removed the provisional parallel `pipeline/video/` tree.
That tree duplicated schema constants, canonical JSON/hash helpers, provider
request compilation, final request hashes, prompt hashes, fingerprints, and
example packages. Those responsibilities now remain solely with the existing
canonical Lena video stack:

- schemas: `pipeline/media_properties/lena/video/schemas/`;
- source validation: `validate_source_for_compilation()`;
- canonical compilation: `compile_video()`;
- generation-plan and compiled-request shapes: canonical A-N schemas;
- prompt transport, request hash, plan hash, and fingerprint: canonical compiler
  outputs only.

The repaired offline layer records:

- structured-JSON-only LLM instruction authority;
- canonical A-N source artifact authoring;
- canonical source validation before compilation;
- deterministic prompt/request compilation only through `compile_video()`;
- daily novelty checks across recent concept, environment, wardrobe, gesture,
  emotional arc, camera grammar, hook, CTA, audio, and ending-pose fields;
- prompt-reuse blocking for new provider create calls;
- offline attempt-record construction with superseded-attempt, prior-job,
  previous-QA, creative-change, compiled request, source plan, authorization,
  and retry fields. The attempt record cannot authorize provider creation.

Prompt reuse is allowed only for same-provider-job recovery, reconciliation of
the same ambiguous submission, downloading or validating the same result, or
deterministic recompilation of the same immutable attempt. A QA-rejected attempt
may not be rerun under the old prompt as a new provider create call.

Offline examples are now generated as test/CLI fixtures under explicit output
roots. They do not live under a governed production date tree and do not consume
a real daily slot. The tests prove three example concepts compile through the
canonical compiler to three distinct prompts, and each compiled prompt begins
with the static Lena Character Element token.

Validation:

- fresh-video suite: `15 passed`;
- canonical video schema/validation ring: `50 passed, 2 skipped`;
- canonical video compiler/CLI architecture ring: `23 passed`;
- adjacent generation-approval/human-rejection ring: `141 passed`;
- compileall for canonical fresh video module, CLI, and tests: passed;
- `git diff --check`: passed.

No provider call, media generation, queue action, publication, scheduler,
credential, `.env`, Anthropic, live photo-lane, or historical evidence mutation
occurred.

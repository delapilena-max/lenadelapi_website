# Lena Video JSON Production System V1

## Production Authority

Validated JSON is Lena video production authority because prose alone cannot
prove which identity, performance, wardrobe, environment, camera, sound, cost,
attempt, commercial, or quality decisions reached a compiled request. Every
artifact has a stable ID, Lena property ID, video ID, governed date, creation
timestamp, producer version, and canonical SHA-256 bindings to upstream
authority. A missing reference, stale hash, mismatched identity, cycle, or
silent user-lock change blocks compilation.

Compiled plans and requests are disposable downstream outputs. They cannot
rewrite source authority and never authorize provider execution. V1 stops at a
validated provider-neutral plan, an exact execution-disabled Higgsfield request,
pre-generation evidence shapes, and documentation.

## Current Operating Policy

- Exactly one final governed Lena video product is allowed per governed date.
- The target is exactly 8,000 milliseconds at 720 by 1,280 pixels, 720p, 9:16.
- The standard aggregate provider ceiling is 36 credits per final video.
- The exact compiled Higgsfield prompt must fit the active 4,096-character
  repository execution policy without truncation or automatic shortening.
- The verified Character Element UUID is
  `6a842337-ef20-4cb9-a0ff-04fa5eb8f8d3`.
- Direct Character Element binding is mandatory.
- Seedance 2.0 is the preferred initial route only where direct Element binding
  is supported.
- Temporal, executable HPE is mandatory. Voice is optional by concept.
- One final product per day is not an attempt policy. Attempts, retries,
  execution timezone, and spend require separate explicit authority.
- V1 authorizes zero attempts and zero retries. Every compiled request has
  `execution_authorized=false` and provider `execution_mode=disabled`.
- The live photo lane remains separately governed at three photos per day. This
  package does not import or mutate its scheduler, queues, publishers,
  credentials, runtime evidence, media, or publications.

The repository-level references are
`pipeline/config/lena_generation_policy.json`,
`pipeline/influencer_nodes/lena/daily_cadence.json`, and
`tools/PROVIDER_SURFACES.md`. The photo-only standing-autonomy policy is not a
video execution authority.

## Authority Order

```text
A. Character authority ---+
B. Video policy ---------- +--> D. Complete video specification
C. Business intent --------+             |
                                           +--> E. Temporal HPE
                                           +--> F. Environment
                                           +--> G. Wardrobe
                                           +--> H. Camera
                                           +--> I. Audio
                                                    |
                                                    v
                                      J. Provider-neutral generation plan
                                                    |
                                                    v
                                      K. Higgsfield compiled request
                                                    |
                                                    v
                                      L. Manifest -> M. QA -> N. Learning
```

No arrow points upward. A, B, and C are roots. D binds them. E through I bind D.
J binds all nine source artifacts. K binds J and preserves all source hashes. L
binds K. M binds J, K, and L. N binds L and M. The graph is acyclic and every
edge is checked against the current upstream canonical hash.

## Schema Map

| Order | Schema | Authority |
|---|---|---|
| A | `lena_video_character_authority_v1.schema.json` | Adult Lena identity, exact Character Element, face/body/hair/skin, wardrobe separation, drift rejection |
| B | `lena_video_policy_v1.schema.json` | Daily final-product cap, duration, format, credit ceiling, attempts, authorization, photo isolation |
| C | `lena_video_business_intent_v1.schema.json` | Audience and commercial intent, rights, disclosures, prohibited claims, CTA |
| D | `lena_video_spec_v1.schema.json` | Complete creative unit, user locks, authority IDs, hook/setup/payoff, QA and provider-neutral requirements |
| E | `lena_video_hpe_v1.schema.json` | Four executable temporal performance beats and final settled state |
| F | `lena_video_environment_v1.schema.json` | Exact location, materials, objects, light, weather, motion, people, geometry, access, scale |
| G | `lena_video_wardrobe_v1.schema.json` | Garments, fit, material, fastenings, continuity, motion, exclusions, safety, brand declarations |
| H | `lena_video_camera_v1.schema.json` | Camera holder/device, framing, headroom, optics, motion, focus, exposure, scale, safe areas |
| I | `lena_video_audio_plan_v1.schema.json` | Optional dialogue/voice, timing, lip sync, music, diegetic sound, ambience, hierarchy, mix |
| J | `lena_video_generation_plan_v1.schema.json` | Validated provider-neutral production plan with no execution authority |
| K | `lena_higgsfield_compiled_request_v1.schema.json` | Exact prompt, negative prompt, prompt count/budget, model arguments, source hashes, fingerprint, disabled execution |
| L | `lena_video_manifest_v1.schema.json` | Future job, spend, attempts, output hashes, dimensions, identity/audio/edit/export evidence |
| M | `lena_video_qa_v1.schema.json` | Deterministic checks, semantic visual checks, optional human review, premium disposition |
| N | `lena_video_learning_v1.schema.json` | Creative descriptors, governed metrics, bounded conclusions, confidence, anti-overfitting |

`common_defs_v1.schema.json` is the local fragment authority for IDs,
timestamps, hashes, upstream references, attempts, user locks, HPE segments,
garments, and QA checks. Every object schema rejects unknown fields. `$ref`
resolution is local-only and cannot traverse or resolve outside the schema root.

## Canonical JSON And Hashes

`pipeline/media_properties/json_authority_v1.py` is the shared domain-neutral
authority primitive used by both Lena and ITB. Canonical serialization uses
UTF-8, sorted keys, compact separators, exact integers, and no insignificant
formatting. Floats are forbidden; exact durations use milliseconds and exact
ratios use integer basis points where needed.

Artifact SHA-256 covers the complete canonical object. A changed source field
invalidates every downstream edge that binds its previous hash. Full validation
also recomputes J and K from current sources and requires exact object equality,
so manually refreshing hashes cannot legitimize a stale or hand-edited compiled
output.

The K fingerprint excludes only `compilation_timestamp` and its own
`deterministic_compilation_fingerprint`. Full validation still requires the
entire checked-in request, including the timestamp, to equal deterministic
compiler output.

## Executable HPE Contract

HPE is an exact 0-8 second performance contract, not a mood adjective:

1. `0-2s`: anticipation releases as the distant rocket appears; gaze, breath,
   eyebrows, torso inclination, hand initiation, and recovery are specified.
2. `2-4s`: delight develops through one measurable half-step, weight transfer,
   shoulder turn, shared glance, and a rising forearm.
3. `4-6s`: awe develops while the pointing gesture initiates, reaches a readable
   completion, and begins recovery without obscuring Lena's face.
4. `6-8s`: hand, shoulders, stance, breath, gaze, and expression settle naturally
   instead of freezing on a repeated gesture.

Every beat has start/end milliseconds, observable action, body mechanics,
meaningful displacement, gaze, normalized expression, blink count, breathing,
weight transfer, gesture initiation, gesture completion, recovery, and camera
relationship. Validation rejects gaps, overlaps, non-positive segments,
incomplete duration, less than meaningful total movement, frozen expression,
and absent gesture completion.

## Validation Stages

1. The loader checks safe root and artifact paths, UTF-8 JSON syntax, strict
   schemas, governed filenames, traversal, symlink/junction escape, and local
   schema references.
2. Cross-authority validation checks property/video/date identity, duplicate
   IDs, upstream presence, canonical hashes, timestamp order, and graph cycles.
3. Source validation checks exact Character Element binding; one-day, 8-second,
   720p, 9:16, 36-credit and zero-attempt policy; business disclosures; HPE;
   dialogue fit; wardrobe; environment; camera feasibility; authority IDs; and
   user locks. Concise compilation cues must remain provider-neutral.
4. Compilation-readiness validation recomputes the neutral plan and compiled
   request exactly, checks plan neutrality, prompt argument equality, request
   fingerprint, source-plan binding, the 4,096-character execution policy, and
   disabled execution.
5. Lifecycle validation checks request/manifest binding, spend, attempts, output
   hash counts, final clean export, daily duplicate finals, pre-generation QA,
   and zero-confidence learning.

Errors are structured with stable code, stage, message, severity, and applicable
artifact ID, field path, expected/actual value, source file, and correction.
Both CLIs emit structured JSON and meaningful exit codes: 0 for success, 2 for
contract failure, and 3 for filesystem failure.

## Deterministic Compilation

`compilation.py` contains two pure ordered builders with no validation, provider,
network, clock, random, environment, or filesystem behavior:

1. `compile_generation_plan` builds J from validated A through I and stamps it
   with `lena_video_plan_compiler_v1`.
2. `compile_higgsfield_request` builds K from J and A through I, starts the exact
   prompt with `@[Lena](6a842337-ef20-4cb9-a0ff-04fa5eb8f8d3)`, compiles all four
   HPE beats and production constraints, creates the negative prompt and fixed
   arguments, and stamps it with `lena_video_higgsfield_compiler_v1`.

The detailed artifacts remain full production authority. Their explicit
provider-neutral prompt cues are concise authored authority, not compiler-made
summaries or truncation. Concept-specific hard and negative constraints live in
D, so the compiler is generic across future Lena videos and does not hard-code
the SpaceX pilot. Compilation fails before writing if the exact prompt exceeds
the shared 4,096-character policy.

`compiler.py` is the narrow orchestration boundary: load sources, validate them,
call both pure builders, and schema-check outputs. `validation.py` independently
uses the same builders to reject downstream drift. This direction avoids a
circular import while giving the pure compilation contract two real consumers.

## Quality And QA

Deterministic validity is necessary but not a premium-quality claim. The pilot
QA artifact separates checks that source data can prove from identity, anatomy,
hair, skin, hands, garment, environment, motion, camera, lighting, audio,
platform-safety, commercial, and overall-quality checks that need real output.
All media-dependent checks are `not_assessable` before generation, overall
quality is `not_assessable_pre_generation`, and publication is `not_authorized`.

Explicit reject conditions block identity drift, malformed anatomy, static
posing, incomplete motion, generic environments, impossible rocket scale,
unsafe or failed launch implications, selfie or impossible camera behavior,
wardrobe leakage, accidental sexualized emphasis, false SpaceX affiliation,
poor audio, and technically valid but mediocre provider-demo output.

## SpaceX Launch Pilot

`pilots/spacex_launch_001/` contains the complete A-through-N chain for **Lena
Excitedly Watches a SpaceX Rocket Launch**. It governs Lena as an adult public
spectator at a lawful coastal viewing lawn outside restricted property. A
companion holds a rear smartphone camera; it is not a selfie. Lena wears fully
fastened jean shorts, a fitted long-sleeve surfing rash guard, and low-profile
shoes. The launch is safe, distant, physically plausible, and free of employment,
sponsorship, endorsement, or special-access implications.

The manifest remains `pre_generation`: provider job ID and clean export are
null; spend and attempts are zero; output, identity, audio, edit, and derivative
evidence arrays are empty. The learning record has null metrics, no conclusions,
and zero confidence.

The checked-in exact prompt is 3,997 characters against the 4,096-character
policy, leaving 99 characters of governed headroom. Its generation-plan SHA-256
is `a219ca9f40b2210542a2ba67828b50dd830c46b59e3813e6018eec420f794970`,
compiled-request SHA-256 is
`6f80fc07960ddf4a15e62157ae9b3f75e4baf9166c25ef2fdd8985a0f45fcc36`,
and deterministic fingerprint is
`92e8887fb3c65ec7886a99f5ba7b33927d79f7086f0cd59103ad4fec8a988c0d`.

## Folder Structure

```text
lena/video/
  contracts.py       Lena IDs, errors, fingerprints, zero-activity counters
  artifacts.py       artifact registry, safe loading, schemas, authority graph
  compilation.py     two pure deterministic builders
  validation.py      source, compilation, lifecycle, cadence and QA rules
  compiler.py        validated in-memory orchestration
  schemas/           fourteen strict artifact schemas plus common definitions
  pilots/            complete generic-pipeline examples
  documentation/     authoritative architecture
```

Thin commands live in `tools/lena_video_*_v1.py`; business logic does not.

## Creating A Future Video

1. Create A, B, and C for one governed video/date without copying pilot creative
   content.
2. Bind D to their current canonical hashes and lock every explicit user choice.
3. Create E through I from D, using an exact executable timeline and production
   details rather than generic adjectives.
4. Validate sources and compile J/K in memory with `--validate-only`.
5. Use an explicit output directory only when the deterministic plan/request
   should be materialized; existing different files fail closed on collision.
6. Create L, M, and N in truthful pre-generation states and validate all fourteen
   artifacts.
7. Stop. Request authorization, provider capability proof, attempt/spend
   authority, execution adapter, output QA, clean export, publishing, and learning
   ingestion are separate future stages.

## Future Provider Path

A future executable adapter may consume only a currently validated K artifact
whose source chain, request hash, capability proof, attempt authority, aggregate
spend ceiling, and separate authorization all match. It must never reinterpret
creative source authority, infer retries, use photo credentials or queues, or
turn compilation success into generation or publication authority. Provider job
polling, receipts, media hosting, editing, semantic QA, captions, scheduling, and
publishing are intentionally absent from V1.

## Deliberately Deferred

V1 has no provider SDK/CLI adapter, credentials, `.env` access, provider setup,
media generation, voice generation, music generation, edit engine, scheduler,
publisher, metrics ingestion, database, plugin system, service container,
abstract provider framework, migration framework, or generic workflow engine.
Those layers require a real authorized consumer and separate tests before they
exist.

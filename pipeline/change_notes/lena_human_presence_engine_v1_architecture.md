# Human Presence Engine v1 — Architecture (PR1: Schema/Contract Only)

**Status:** Authority/contract layer only. Zero generation-behavior change. Not consumed by any
prompt-construction, ranking, QA, or publishing code in this PR.

## Purpose

Define a reusable, character-agnostic contract for what makes an AI-generated performance read as
an inhabited human presence rather than a sequence of attractive poses — and a narrowly-scoped Lena
binding on top of it, without hard-coding the engine to any one character.

## Evidence Basis

This design was built from a detailed written behavioral specification supplied by the product
owner, not from direct analysis of image or video reference material — no visual reference files
were available in the environment this was implemented in. The specification described qualities
observed in reference performance work by a named third-party creator, with an explicit instruction
to extract behavioral *qualities* (internal life, viewer awareness, gaze arcs, microexpression
transitions, motivated movement, weight transfer, speech rhythm, warmth, playfulness, confidence,
adult sensual presence structurally separate from safety, and temporal performance arcs) while
copying neither that creator's identity, face, exact content, nor individual choreography. This
document and the accompanying code describe only generic performance mechanics — no reference
creator is named anywhere in the implementation, and no specific choreography, dialogue, or visual
content is reproduced.

## Two-Layer Architecture

**Generic platform layer** — `pipeline/presence/human_presence_contract_v1.py`. Defines every enum
vocabulary, every section schema, and the single validation entry point
(`validate_presence_contract`). Contains no reference to any specific character. A second,
hypothetical character with an entirely different body archetype and a fully desexualized
performance profile validates through this same module with zero code changes — proven directly in
the test suite.

**Character adapter layer** — `tools/strategy/lena_human_presence_profile_v1.py`. Supplies Lena's
specific values along the engine's generic axes (most importantly, her body-presentation silhouette:
pronounced bust emphasis, pronounced waist-hip contrast, pronounced hip/glute emphasis, required
realistic proportions, `hourglass_voluptuous` shape class) and Lena's default performance template.
It calls the generic validator; it does not re-implement any rule.

This mirrors the existing repository pattern of the character doctrine itself: one canonical,
machine-validated authority, consumed (later, in a future PR) rather than duplicated.

## Contract Sections

`viewer_relationship`, `gaze_arc`, `expression_arc`, `performance_actions`, `movement_dynamics`,
`speech_behavior`, `sensual_presence`, `body_presentation`, `temporal_beats`,
`character_doctrine_provenance` — each a structured, individually-addressable set of fields, not one
vague aggregate score. Every field is a closed enum (or boolean), so an unknown value fails closed
with a specific `unknown_enum_value` error rather than silently passing through.

## Sensuality Is Structurally Separate From Safety

`sensual_presence.sources` may only be drawn from performance qualities — `gaze`, `anticipation`,
`movement`, `confidence`, `voice`, `framing`, `timing`. The words "exposure" and "sexual_keywords" are
not members of this vocabulary at all — this is a structural guarantee, not a runtime deny-list.
`sensual_presence.exposure_dependency` has no "high" option in its own vocabulary, for the same
reason: a caller cannot construct a contract that claims exposure-driven sensuality even if it wanted
to.

The only interaction between `sensual_presence` and safety is a single one-way gate: a sensual tier
other than `"none"` requires `body_presentation.adult_character_required` to already be `true`.
Sensuality can never satisfy that requirement — it can only be blocked by its absence. Nothing in
`sensual_presence` can relax `body_presentation.anatomy_continuity_required`, which the validator
pins to `true` unconditionally, regardless of sensual tier.

## Body Presentation Is Character-Specific, the Engine Is Not

The engine defines generic axes (`bust_emphasis`, `waist_hip_contrast`, `hip_glute_emphasis`,
`proportion_realism`, `silhouette_shape_class`) with multiple valid values each — it never defines
what any specific character's body actually is. Lena's adapter supplies her established voluptuous
silhouette along those axes; a hypothetical second character with a slim-athletic silhouette and a
fully non-sensual performance profile validates through the identical, unmodified engine code. The
engine module's own source contains no character names and no body-type-specific language.

## Provenance Binding

`character_doctrine_provenance` mirrors the path+sha256+version binding pattern already used for
recommendation/candidate/reconciliation artifacts elsewhere in this pipeline. The generic validator
re-reads the referenced doctrine file from disk and re-computes its sha256 at validation time — it
never trusts a cached value. A stale or mismatched binding fails closed with `doctrine_provenance_stale`.
A path that would escape the repository root fails closed with `doctrine_provenance_path_outside_repository`.

## What This PR Does Not Do

No change to prompt construction, recipe families, candidate ranking, QA schemas, executor behavior,
provider calls, Level A reconciliation logic, or publishing behavior. The contract and the Lena
adapter are built, validated, and tested, but nothing in the existing pipeline reads them yet.

## Open Decisions for HPE PR2

- Exact prompt-construction integration point and whether presence weighting is additive-only (bias
  weighted-choice pools) or introduces new required fields.
- Whether `presence_failure_indicators()` becomes a QA hard-gate list, an advisory list, or both,
  split by indicator.
- Whether candidate ranking gains new presence-derived dimensions and, if so, their exact position
  in the existing ranking tuple.
- Whether a second, real (non-hypothetical) character profile is built in a later phase, and what
  process governs authoring a new character's `silhouette_profile` and default template.

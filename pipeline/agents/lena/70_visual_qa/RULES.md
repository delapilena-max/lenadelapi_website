# Rules -- 70_visual_qa

Grounded in `pipeline/qa/lena_photo_qa.py` and
`tools/lena_review_proof_render_v1.py` as they actually exist, and in real
session history where this exact failure mode occurred (2026-07-05/06 renders on
`2026-07-05-02-photo`).

## Production QA standard correction (2026-07-06) -- read this before judging wardrobe

Exact wardrobe obedience was over-weighted earlier this session. It was a
useful *diagnostic* (does the model literally follow the catalog outfit
text?), but it is **not the production goal** and must not be treated as an
automatic production failure.

**The actual production goal:** varied Lena photos, different outfits over
time, sexy/high-hook/viewer-grabbing, somewhat-to-moderately revealing,
platform-safe, realistic enough, coherent scene, close-enough identity
continuity, no obvious AI/cartoon/anatomy failure.

**A wardrobe substitution is acceptable** if the result is still stylish,
sexy/hooky, platform-safe, not frumpy, not boring, not repetitive, coherent
with the scene, and not identity-breaking. Do not fail a render solely
because "the catalog said tank-top-and-skirt and the image shows something
else" -- judge the *actual outfit produced* against the criteria above, not
against the literal catalog string.

**Production priority order (highest to lowest):**
1. Hook strength
2. Outfit variety
3. Sexy but platform-safe styling
4. Realism
5. Identity continuity
6. Scene variety
7. Caption/image coherence
8. Exact wardrobe obedience -- **diagnostic only, not a normal production gate**

**Hard rejects (these, not "wrong specific garment," are the real
production-blocking failures):**
- Cartoon/illustration/obvious AI look
- Broken anatomy/bad hands/extra limbs
- Face identity badly off
- Boring/frumpy/non-hook outfit
- Outfit too covered or not visually compelling
- Too explicit/unsafe
- Scene makes no sense
- Same outfit/pose/location formula repeating across posts (not the same
  thing as retesting one diagnostic slot multiple times)
- Caption and image totally mismatched
- Low-quality/fake-looking output

**Gap closed (2026-07-06, implemented in two stages):**
1. `pipeline/qa/lena_photo_qa.py` has `DIAGNOSTIC_ONLY_CHECKLIST_KEYS =
   ("wardrobe_class_fidelity",)` and `HARD_GATING_CHECKLIST_KEYS` (every
   other original checklist key), and `validate_qa_result()`'s false-green
   check only iterates the latter -- `wardrobe_class_fidelity: fail` no
   longer forces `overall: fail`.
2. A new sibling block, `production_scoring`, was added under **schema
   v2** (`SCHEMA_VERSION = "2"`), scoring the corrected standard directly:
   `hook_strength` (weak/moderate/strong; `weak` forces `overall: fail`),
   `styling_sexy_platform_safe` (pass/fail/not_applicable/unreviewed;
   `fail` forces `overall: fail`), and `outfit_variety_vs_recent_posts` /
   `scene_variety_vs_recent_posts` (pass/fail/not_yet_measured/unreviewed;
   **advisory only, never gates `overall`** -- no history-comparison
   tracker exists yet to measure these reliably).

No original field was added, removed, or renamed; existing `schema_version:
"1"` QA JSON files are exempt from the `production_scoring` requirement and
still validate unchanged (`LEGACY_SCHEMA_VERSIONS_WITHOUT_PRODUCTION_
SCORING = {"1"}`). See `CURRENT_STATE.md`'s "QA code updated to match the
corrected standard" section for the full validated detail on both stages.

## Visual Hook / Allure hard gate (2026-07-08) -- read this before passing anything "technically fine"

**A technically coherent image must still fail if it is boring, generic, not
alluring, not IT-girl, or not Lena-feed-worthy.** This is not a restatement of
the 2026-07-06 correction above -- it closes a real gap that correction left
open: `hook_strength`/`styling_sexy_platform_safe` alone were shown (real
session history, 2026-07-07 flower-shop render) to let a render pass that had
correct identity, correct frame logic, correct wardrobe-class-adjacent
substitution, working pose/expression layers, and zero hard checklist
failures -- and was still, in Nicolas's words, "not a sexy fucking picture."
Being technically coherent is necessary. It is not sufficient.

**Lena's standing feed standard:**
- Sexy but platform-safe. Allure / IT-girl / main-character energy.
- Confident body language; fitted or silhouette-visible wardrobe.
- Visible bust/waist/hips/thighs unless the slot is explicitly portrait/story.
- Scroll-stopping feed value -- would a real viewer stop scrolling on this?

**Cute-but-generic lifestyle content is a fail**, even with a technically
correct outfit, coherent scene, and no anatomy problems. "Nothing is broken"
is not the bar. See `feedback_qa_body_sexiness_calibration.md` (Claude's
cross-session memory) for the concrete two-miss history behind this rule.

**Nightlife is allowed and is not the audit's concern.** Rooftop patios, wine
bars, restaurants, lounges, parties, date-night energy, and going-out looks
are all fully permitted settings -- do not treat a nightlife/social lane as
inherently risky, and do not phrase a review as "no alcohol/nightlife issue"
(that implies the setting itself is a problem, which it is not). **Only flag
alcohol** if the actual rendered image clearly makes alcohol the hero/focal/
promotional element, shows intoxication, or centers drinking in a way that
was not explicitly approved. See `feedback_nightlife_alcohol_not_prohibited.md`.

**Schema v3 (`pipeline/qa/lena_photo_qa.py`) adds six more `production_scoring`
fields to enforce this mechanically, not just as prose doctrine:**
- `allure_level` (none/mild/strong) -- **`none` forces `overall: fail`.**
- `it_girl_energy` (pass/fail) -- **`fail` forces `overall: fail`.**
- `body_visibility_score` (low/medium/high) -- **advisory only** for this
  first patch (forces structured attention, does not gate alone yet).
- `outfit_hook_score` (weak/moderate/strong) -- **advisory only.**
- `pose_attitude_score` (weak/moderate/strong) -- **advisory only.**
- `feed_worthy_reason` (free text) -- **required non-empty** once a record is
  finalized (`overall` is `pass` or `fail`, not `unreviewed`), regardless of
  verdict. Forces the reviewer to answer, explicitly, in words: *would this
  stop someone scrolling, and why or why not?*

`hook_strength` remains the canonical visual-hook score and was **not**
renamed or duplicated -- `allure_level`/`it_girl_energy` are new, separate
dimensions (allure and "does this feel like Lena" are not the same axis as
raw attention-grabbing strength; a render can be attention-grabbing without
being alluring, or vice versa).

Existing `schema_version: "1"` and `"2"` QA JSON files are exempt from all six
new fields and still validate unchanged (`LEGACY_SCHEMA_VERSIONS_WITHOUT_
ALLURE_GATE = {"1", "2"}`) -- confirmed against the real on-disk `2026-07-05-
01-photo_qa.json`, `2026-07-07-01-photo_qa.json`, and `2026-07-07-03-photo_
qa.json` files, none of which were modified or migrated by this change.

## The stale-QA-file lesson (read this first)

This is the reason this folder exists, not an abstract warning.

- `slot_id` is stable across rerenders on the same slot (e.g. `2026-07-05-02-photo`
  was rendered three times). The QA artifact path
  (`pipeline/asset_review/lena/<date>/<slot_id>_qa.json`) is the **same file** every
  time.
- `save_qa_template()` defaults to `force=False` -- it will **not** overwrite an
  existing QA file. `tools/lena_review_proof_render_v1.py`'s CLI does not expose a
  force flag at all.
- Consequence: after a rerender, `build_review_bundle()`'s `qa_overall_status`
  field will report whatever verdict is already on disk -- which may describe a
  **previous** render's image, not the current one. This has actually happened in
  this project (2026-07-06: a "stale fail-verdict scaffold from the pre-Batch-5
  render" was overwritten by hand; 2026-07-06 again: "replaced the stale QA verdict
  from the previous turtleneck render").
- **The reviewer, not the tooling, is responsible for catching this.** Before
  trusting any `qa_overall_status` value: check whether the QA file's
  `reviewed_at_utc` / `created_at_utc` timestamp is consistent with the render you
  actually just ran, not an earlier one. If in doubt, open the QA json directly and
  read it.
- **Every new render on a previously-used slot requires an explicit QA
  replacement/update for that render.** Do not treat an old `pass` (or `fail`) as
  still describing a new image. Write a fresh QA result over the old one
  (deliberately, after viewing the new image) every time a slot is rerendered.

## Hairstyle silhouette diversity (2026-07-17)

Repeated hairstyle silhouettes reduce realism and make outputs look templated.
Higgsfield Soul 2.0 has a documented tendency to reproduce the same elevated
front curl / lifted crown crest from the identity element across generations.

**What to compare:** before passing an image, compare its crown/front-hair
silhouette against recent Lena outputs. Flag when the elevated front curl,
pompadour-like crest, or rooster-comb shape repeats substantially.

**Rejection threshold:** reject an image when its hairstyle silhouette is
substantially identical to a recent output, unless the recipe explicitly
requires continuity across a set.

**What is NOT a reject reason:** hairstyle variation itself. Center part,
side part, tucked ears, loose ponytail, bun, brushed back, tousled, damp --
these are all valid Lena hairstyles. A different hairstyle from the last image
is not drift and must not be flagged as identity failure.

**Identity continuity for hair depends only on:** brunette color, long to
medium-long length, thick volume, naturally wavy base texture. A different
silhouette with those four traits intact is a pass on identity.

**Implementation status:** this remains human-QA-only for now. There is no
structured recent-output comparison tracker in code yet, so reviewers compare
recent Lena outputs by eye. Do not invent a machine similarity score here.

## Must never do

- Never treat `qa_overall_status` (or any field) from `build_review_bundle()` as
  current truth without confirming which render it corresponds to.
- Never accept a QA verdict, pass or fail, that was produced without a human or
  Claude actually viewing the rendered image. Metadata, receipts, and boolean
  flags (`payload_no_image_list`, `garment_obedience_lock_present`, etc.) describe
  what was *submitted*, never what was *produced*.
- Never leave a stale QA verdict in place after a rerender "because it's close
  enough" -- always explicitly replace it.
- Never redefine `QA_CHECKLIST_FIELDS`, `PRODUCTION_SCORING_FIELDS`,
  `ALLOWED_STATUS_VALUES`, `ALLOWED_HOOK_STRENGTH_VALUES`,
  `ALLOWED_VARIETY_STATUS_VALUES`, `ALLOWED_OVERALL_VALUES`,
  `ALLOWED_ALLURE_LEVEL_VALUES`, `ALLOWED_BODY_VISIBILITY_SCORE_VALUES`, or
  `LEGACY_SCHEMA_VERSIONS_WITHOUT_ALLURE_GATE` anywhere else.
  `pipeline/qa/lena_photo_qa.py` is the one definition.
- Never pass a render on `hook_strength`/`styling_sexy_platform_safe`/
  `allure_level`/`it_girl_energy` alone because "nothing is technically
  broken." Boring/generic/non-alluring is a real, separate failure mode --
  see the "Visual Hook / Allure hard gate" section above.
- Never gate `overall` on `outfit_variety_vs_recent_posts` or
  `scene_variety_vs_recent_posts` without first building and approving a real
  history-comparison tracker (see "Not yet decided / not yet built") -- until
  then these two fields are structurally incapable of an honest verdict and
  must stay advisory.

## Adult style is not unsafe by itself

For clearly adult fictional Lena images, the following are allowed on their
own and must not fail safety merely for showing skin or sexual suggestiveness:

- scantily clad
- bikini
- lingerie
- underwear
- deep cleavage
- visible midriff
- exposed thighs and hips
- tight or sheer clothing
- sensual or provocative posing
- bedroom or dressing-room context
- emphasized curves
- implied nudity while nipples and genitals remain covered

These still fail safety:

- visible genitals
- explicit nipple exposure
- depicted sexual acts
- masturbation
- coercive sexual content
- sexual violence
- age ambiguity

## What counts as false-green and must hard-fail

`validate_qa_result()` already encodes part of this mechanically:
- `overall == "pass"` while any hard-gating checklist item is `"fail"` -- rejected.
- Any hard-gating checklist item `"fail"` while `overall != "fail"` -- rejected.
- `overall == "pass"` while `production_scoring.hook_strength == "weak"` or
  `production_scoring.styling_sexy_platform_safe == "fail"` -- rejected (schema
  v2+ records only).
- `overall == "pass"` while `production_scoring.allure_level == "none"` or
  `production_scoring.it_girl_energy == "fail"` -- rejected (schema v3+
  records only; see "Visual Hook / Allure hard gate" above).
- A finalized (`pass`/`fail`) schema v3+ record with an empty or missing
  `production_scoring.feed_worthy_reason` -- rejected.
- `overall == "fail"` with empty `failure_reasons` -- rejected.
- `production_scoring.outfit_variety_vs_recent_posts` and `scene_variety_
  vs_recent_posts` are validated for shape only -- their value, whatever it
  is, never triggers a rejection or forces `overall`. This is deliberate, not
  a gap: see the "advisory only" note above. The same is true (for now) of
  `body_visibility_score`, `outfit_hook_score`, and `pose_attitude_score`.

Beyond what the validator checks in code, these are also false-green and must be
treated as hard-fail conditions by the reviewer, not soft judgment calls:
- Reporting `overall: pass` based on the submitted prompt/negative-prompt being
  correct (receipt-level truth) without having looked at the actual image.
- Reporting `overall: pass` while `identity_fidelity` or `public_scene_clothing_
  continuity` is anything other than a deliberately confirmed `pass` -- these two
  are directly tied to the Non-Negotiable Lena Photo Contract (master doctrine
  file §4) and to the platform-safety no-underwear/lingerie line.
  **`wardrobe_class_fidelity` is no longer in this hard-gating list** -- corrected
  2026-07-06 as doctrine, and as of 2026-07-06 also code-enforced:
  `validate_qa_result()` no longer lets a `wardrobe_class_fidelity: fail`
  force `overall: fail`. A `fail` on the literal catalog-outfit match is not,
  by itself, grounds to fail the render. Judge the produced outfit against the
  production standard above (hook/variety/sexy-safe/not-frumpy/coherent)
  instead of the catalog string.
- A `pass` carried over from a prior render of the same slot without re-viewing the
  new image (the stale-QA-file lesson above).
- A style-level categorical failure (e.g. the 2026-07-06 cartoon/illustrated-style
  drift) marked anything but `fail` on `face_realism_anti_generic_drift`, even if
  wardrobe or other fields happen to look fine.

## Must hard-fail (code-level)

- `validate_qa_result()` returns `(False, errors)` for any of the internal
  inconsistencies above -- a QA result that fails validation must not be treated as
  a usable verdict.

## How canonical reference images should be used during identity/skin/hair review

Before judging `identity_fidelity` or `skin_realism_no_invented_marks`, view the
approved Lena identity references bound to the Higgsfield Soul approval and the
actual rendered image. Do not judge from memory of what Lena "should" look like.

1. Use the exact identity evidence and command binding stored under
   `pipeline/higgsfield_debug/<date>/<slot_id>/`; do not re-fetch provider data
   merely to perform a routine visual review.
2. View the approved references and rendered image side by side, not from a
   written description of them.
3. Use them to settle exactly the kind of question that goes wrong without a
   reference: is a given skin mark authentic (present in the references) or
   invented drift? Is hair color/pattern a genuine match (base color +
   highlighting pattern) or a flattened/generic substitute? This project has
   already reversed a verdict both ways this way (freckles: FAIL to PASS once a
   reference was viewed; hair: previously unreviewed to FAIL once a reference was
   viewed and a genuine highlighting mismatch was found).
4. A verdict on `identity_fidelity` or `skin_realism_no_invented_marks` written
   without having viewed the canonical references for that render is incomplete,
   not just cautious -- get the references before finalizing, not after.

## Human approval required

- Adding, removing, or redefining a checklist field in `QA_CHECKLIST_FIELDS`
  or `PRODUCTION_SCORING_FIELDS`.
- Changing the false-green validation rules in `validate_qa_result()`
  (checklist or `production_scoring`).
- Making `outfit_variety_vs_recent_posts`, `scene_variety_vs_recent_posts`,
  `body_visibility_score`, `outfit_hook_score`, or `pose_attitude_score`
  gating instead of advisory.
- Bumping `SCHEMA_VERSION` again or changing what
  `LEGACY_SCHEMA_VERSIONS_WITHOUT_PRODUCTION_SCORING` or
  `LEGACY_SCHEMA_VERSIONS_WITHOUT_ALLURE_GATE` covers.
- Wiring in an automated vision-model judge (would change "no automated QA yet"
  from a documented gap to an actual capability -- a real architectural change).

## Not yet decided / not yet built

- Whether `tools/lena_review_proof_render_v1.py` should gain an explicit
  `--force-requery` or similar flag so replacing a stale verdict is a tooling
  action instead of a manual file write. Not decided -- flagged in OUTPUTS.md.
- Removing `wardrobe_class_fidelity` from automatic overall-fail gating is
  **done** (2026-07-06). Adding `hook_strength` and `styling_sexy_platform_
  safe` as real, gating dimensions is **also done** (2026-07-06, schema v2 --
  see `CURRENT_STATE.md`).
- **Not built:** the history-comparison tracker that would let
  `outfit_variety_vs_recent_posts` / `scene_variety_vs_recent_posts` become
  more than advisory metadata -- needs a small, separate module (sketched but
  not built, working name `pipeline/qa/lena_variety_tracker.py`) that reads
  recent published slots' wardrobe/environment/pose metadata and computes a
  repeat-count. Explicitly out of scope for the 2026-07-06 schema v2 change;
  requires its own approval.

# Rules -- 40_identity_continuity

Grounded in `pipeline/identity/lena_identity.py` as it actually exists, and in the
Non-Negotiable Lena Photo Contract (master doctrine file, §4).

## Must never do

- Never invent a fallback reference when `KLING_LENA_ELEMENT_UI_ID` is unset or
  unresolvable. `require_expected_photo_element()` raises in that case -- callers
  must not catch that and substitute something else.
- Never allow `KLING_STUDIO_ELEMENT_ASSET_ID` / `KLING_STUDIO_ELEMENT_UI_ID` /
  `KLING_PODCAST_STUDIO_ELEMENT_ASSET_ID` / `KLING_PODCAST_STUDIO_ELEMENT_UI_ID` to
  resolve as the photo lane's identity. `forbidden_photo_element_ids()` exists
  specifically so callers can reject these.
- Never silently accept `KLING_LENA_ELEMENT_IMAGE_URLS_JSON` or
  `KLING_LENA_ELEMENT_IMAGE_URLS` as a valid reference source. This was the exact
  containment finding from 2026-07-05: a manual override path that let stale/manual
  URLs silently outrank the live element lookup.
- Never redefine the allowed photo reference-mode contract (`ALLOWED_PHOTO_IDENTITY_BINDINGS`,
  `REQUIRED_REFERENCE_BINDING_MODE`, `REQUIRED_REFERENCE_SOURCE_POLICY`,
  `REQUIRED_SEED_SOURCE`) anywhere else. `tools/lena_preflight.py` enforces these
  against generated output -- there must be exactly one definition.

## Must hard-fail

- `assert_no_manual_reference_override()` raises `RuntimeError` if either forbidden
  override env var is set. This is the enforcement mechanism, not a warning.
- `require_expected_photo_element()` raises `RuntimeError` if
  `KLING_LENA_ELEMENT_UI_ID` is unset or not a digit string.
- Any photo item whose metadata doesn't match the allowed reference-mode contract
  should fail preflight (`tools/lena_preflight.py` is the actual enforcement point;
  this module supplies the contract it checks against).

## Human approval required

- Changing which env var is authoritative for photo identity
  (`EXPECTED_PHOTO_ELEMENT_ENV_VAR`, currently `KLING_LENA_ELEMENT_UI_ID`).
- Changing the canonical live Lena element itself (a business/identity decision, not
  a code change).
- Adding a new forbidden-element category or a new allowed reference-mode value.

## Hairstyle variation is not identity drift (2026-07-17)

Lena's hair identity is: brunette, long to medium-long, thick, naturally wavy.
These four traits are fixed and must be preserved across generations.
The active prompt brain now reinforces that in both Lena image-generation
paths with one shared hairstyle-variation directive; that directive is a
prompting cue, not a new identity trait.

The following are NOT fixed identity traits and must not be treated as drift:
- Exact crown silhouette or height
- Exact front-curl shape or presence
- Part location (center, side, uneven, none)
- Specific wave pattern or volume distribution
- Face-framing strand placement

Failing an image or flagging identity drift solely because the hairstyle
silhouette differs from a previous output is incorrect. The model regularly
reproduces the same elevated front curl from the identity element; breaking
that pattern is the goal, not a defect.

When evaluating identity continuity, weight: facial structure, eye color,
skin tone, body morphology, and broad hair color + wave character.
Do not weight: specific hairstyle shape, crown height, or curl pattern.

## Not yet decided / not yet built

- Whether a real `identity_lock.json` artifact will be written (per the original
  doctrine target, §7.5) or whether the current in-process resolve/raise pattern is
  sufficient going forward. Not decided -- flagged in OUTPUTS.md.

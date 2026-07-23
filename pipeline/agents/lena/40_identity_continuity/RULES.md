# Rules -- 40_identity_continuity

Grounded in `pipeline/identity/lena_higgsfield_identity.py`,
`pipeline/higgsfield_lena_api_executor.py`, and the Non-Negotiable Lena Photo
Contract.

## Must never do

- Never submit a Lena photo without the exact current Lena Soul binding defined
  by `DEFAULT_LENA_CUSTOM_REFERENCE_ID`.
- Never substitute a historical Soul id, arbitrary custom reference, or local
  filename when the current Lena Soul binding is missing or disagrees with the
  handoff and approval.
- Never infer Soul attachment from a completed provider record when that record
  does not expose the submitted Soul id. Bind the exact local command, including
  `--soul-id`, to the returned job UUID instead.
- Never let prompt, handoff, approval, command-binding, manifest, and downloaded
  image lineage disagree.

## Must hard-fail

- The executor must stop before provider submission if the handoff or approval
  omits the verified Lena Soul id or supplies a different id.
- The executor must stop before provider submission if the constructed command
  does not contain the exact verified Lena Soul id.
- The executor must stop if the approved prompt bytes and the prompt bytes at
  the subprocess boundary differ.
- Local identity evidence must match the exact provider job, prompt hash, image
  path, image hash, and approved dimensions.

## Human approval required

- Changing the current Lena Soul id.
- Approving a new identity/reference mechanism.
- Accepting an image whose identity or presentation does not visibly match Lena,
  even when the mechanical lineage checks pass.

## Hairstyle variation is not identity drift

Lena's hair identity is brunette, long to medium-long, thick, and naturally
wavy. Exact crown silhouette, part location, curl placement, and wave
distribution may vary. Identity review should weight facial structure, eye
color, skin tone, body morphology, and broad hair color and texture rather than
one exact hairstyle.

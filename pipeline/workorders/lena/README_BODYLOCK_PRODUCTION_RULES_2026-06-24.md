# Lena BodyLock Production Rules — 2026-06-24

## Approved generation path for Lena production Omni images

- **Model:** `kling-v3-omni`
- **Endpoint:** `POST https://api.klingai.com/v1/images/omni-image`
- **n:** `1` — never more than 1 for production
- **Reference payload:** `element_list + image_list` — both required
- **Image anchor:** Goodtest1.jpg or an explicitly Nicolas-approved current anchor
- **Prompt style:** Short scene-only prompt (~400 chars max) — no dense appearance descriptors

## Rejected paths — do not use for production

- **`lena_kling_omni_image_public_api_live_test_v1.py`** — element-only, no image_list anchor.
  Produced identity drift and pasted-face failures on 2026-06-24 and 2026-06-25. Do not use.
- **Element-only payload** (`element_list` without `image_list`) — rejected for Lena production.
- **n=2 or higher** — produces identity-divergent variants. Rejected.
- **2,172-char appearance-heavy prompt** — overrides element identity. Rejected.

## Publish approval rules

- "Huge improvement" does not equal publish approval.
- Visual candidate status does not equal publish approval.
- Publish requires **explicit Nicolas approval of both**:
  1. The generated image (identity, outfit, scene, quality)
  2. The caption-to-image match
- No publish, R2 upload, or queue entry until both approvals are explicit and in-session.
- Every generated image gets a `.status.json` sidecar with `publish_approved: false` until approved.

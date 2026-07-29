# lenadelapi-website

This repository hosts the public Terms of Service and Privacy Policy pages for **lenadelapi_uploader**, the web/desktop integration used to create, preview, and publish ai_lady content to TikTok via OAuth and the Content Posting API.

## Purpose
These static pages are provided to satisfy app review requirements on the TikTok Developer Portal and to give users a clear, public record of our terms and privacy practices.

## Contents
- `tos.html` — Terms of Service (effective 2026-05-11)
- `privacy.html` — Privacy Policy (effective 2026-05-11)
- `login.html` — static GitHub Pages entry point that sends users to the server-side TikTok OAuth start route
- `auth/tiktok/callback.html` — static success/error result page after the server-side callback completes

## Deployment
This site is intended to be published via GitHub Pages. After pushing to `main`, enable Pages in the repository settings and use the generated URLs for the TikTok app submission.

## TikTok Login Kit backend

GitHub Pages must not contain the TikTok client secret, OAuth authorization code,
access token, or refresh token. TikTok Login Kit is handled by the Cloudflare
Worker in `worker/`.

Routes:

- `GET /auth/tiktok/start` — creates a random OAuth state value, stores it in KV,
  and redirects to `https://www.tiktok.com/v2/auth/authorize/` with scopes
  `user.info.basic,video.upload,video.publish`.
- `GET /auth/tiktok/callback` — validates the state and exact configured
  redirect URI, exchanges the code server-side at
  `https://open.tiktokapis.com/v2/oauth/token/`, stores tokens in KV, and
  redirects back to the static result page without exposing secrets.
- `POST /auth/tiktok/refresh` — server-side refresh-token support protected by
  the `INTERNAL_REFRESH_BEARER` secret.

Required Cloudflare bindings/configuration:

- KV namespace `OAUTH_STATE_KV` for short-lived OAuth state records.
- KV namespace `TIKTOK_TOKEN_KV` for server-side TikTok token records.
- Worker vars:
  - `TIKTOK_CLIENT_KEY`
  - `TIKTOK_REDIRECT_URI`
  - `PUBLIC_SUCCESS_REDIRECT`
  - `PUBLIC_ERROR_REDIRECT`
- Worker secrets:
  - `TIKTOK_CLIENT_SECRET`
  - `INTERNAL_REFRESH_BEARER`

Set secrets with Wrangler; do not commit them:

```sh
wrangler secret put TIKTOK_CLIENT_SECRET
wrangler secret put INTERNAL_REFRESH_BEARER
```

The TikTok Developer Portal redirect URI must be the deployed Worker callback,
exactly:

```text
https://lenadelapi-tiktok-oauth.delapilena.workers.dev/auth/tiktok/callback
```

The redirect URI must be absolute HTTPS, static, and contain no query string or
fragment.

## Contact
For privacy or legal inquiries: privacy@lenadelapi.example




import assert from 'node:assert/strict';
import test from 'node:test';

import {
  handleRequest,
  internalsForTests,
  redactTikTokPayload,
} from '../src/tiktok-oauth-worker.js';

class FakeKV {
  constructor() {
    this.map = new Map();
  }

  async put(key, value, options = undefined) {
    this.map.set(key, { value, options });
  }

  async get(key, type = undefined) {
    const item = this.map.get(key);
    if (!item) return null;
    return type === 'json' ? JSON.parse(item.value) : item.value;
  }

  async delete(key) {
    this.map.delete(key);
  }

  keys() {
    return Array.from(this.map.keys());
  }
}

function parseSetCookies(response) {
  if (typeof response.headers.getSetCookie === 'function') {
    return response.headers.getSetCookie();
  }
  return response.headers.get('set-cookie').split(/,(?=__Host-)/);
}

function baseEnv(overrides = {}) {
  return {
    TIKTOK_CLIENT_KEY: 'test-client-key',
    TIKTOK_CLIENT_SECRET: 'test-client-secret',
    TIKTOK_REDIRECT_URI: 'https://auth.example.test/auth/tiktok/callback',
    PUBLIC_SUCCESS_REDIRECT: 'https://pages.example.test/auth/tiktok/callback.html',
    PUBLIC_ERROR_REDIRECT: 'https://pages.example.test/auth/tiktok/callback.html',
    INTERNAL_REFRESH_BEARER: 'refresh-admin-secret',
    OAUTH_STATE_KV: new FakeKV(),
    TIKTOK_TOKEN_KV: new FakeKV(),
    ...overrides,
  };
}

function fixedCrypto() {
  return {
    getRandomValues(bytes) {
      for (let index = 0; index < bytes.length; index += 1) {
        bytes[index] = index + 1;
      }
      return bytes;
    },
  };
}

function cookieFromStart(response) {
  return response.headers.get('set-cookie').split(';')[0];
}

test('start route redirects to TikTok v2 with random stored state and required scopes', async () => {
  const env = baseEnv();
  const response = await handleRequest(
    new Request('https://auth.example.test/auth/tiktok/start'),
    env,
    { cryptoImpl: fixedCrypto(), now: () => Date.parse('2026-07-29T00:00:00Z') },
  );

  assert.equal(response.status, 302);
  const location = new URL(response.headers.get('location'));
  assert.equal(location.origin + location.pathname, internalsForTests.TIKTOK_AUTHORIZATION_URL);
  assert.equal(location.searchParams.get('client_key'), 'test-client-key');
  assert.equal(location.searchParams.get('response_type'), 'code');
  assert.equal(location.searchParams.get('scope'), 'user.info.basic,video.upload,video.publish');
  assert.equal(location.searchParams.get('redirect_uri'), env.TIKTOK_REDIRECT_URI);
  assert.notEqual(location.searchParams.get('state'), 'login');
  assert.match(response.headers.get('set-cookie'), /HttpOnly; Secure; SameSite=Lax/);

  const state = location.searchParams.get('state');
  const stored = await env.OAUTH_STATE_KV.get(`tiktok:oauth:state:${state}`, 'json');
  assert.equal(stored.state, state);
  assert.equal(stored.redirect_uri, env.TIKTOK_REDIRECT_URI);
  assert.equal(stored.scope, 'user.info.basic,video.upload,video.publish');
});

test('state mismatch fails closed before token exchange', async () => {
  const env = baseEnv();
  await env.OAUTH_STATE_KV.put(
    'tiktok:oauth:state:good-state',
    JSON.stringify({ state: 'good-state', redirect_uri: env.TIKTOK_REDIRECT_URI }),
  );
  let fetchCalls = 0;
  const response = await handleRequest(
    new Request('https://auth.example.test/auth/tiktok/callback?code=oauth-code&state=bad-state', {
      headers: { Cookie: `${internalsForTests.STATE_COOKIE}=good-state` },
    }),
    env,
    { fetcher: async () => { fetchCalls += 1; throw new Error('must not call provider'); } },
  );

  assert.equal(response.status, 303);
  assert.equal(fetchCalls, 0);
  const location = new URL(response.headers.get('location'));
  assert.equal(location.searchParams.get('status'), 'error');
  assert.equal(location.searchParams.get('error'), 'state_mismatch');
});

test('TikTok callback error is surfaced without token exchange', async () => {
  const env = baseEnv();
  let fetchCalls = 0;
  const response = await handleRequest(
    new Request('https://auth.example.test/auth/tiktok/callback?error=access_denied&error_description=Denied'),
    env,
    { fetcher: async () => { fetchCalls += 1; throw new Error('must not call provider'); } },
  );

  assert.equal(response.status, 303);
  assert.equal(fetchCalls, 0);
  const location = new URL(response.headers.get('location'));
  assert.equal(location.searchParams.get('status'), 'error');
  assert.equal(location.searchParams.get('error'), 'access_denied');
});

test('redirect URI mismatch is rejected before token exchange', async () => {
  const env = baseEnv();
  await env.OAUTH_STATE_KV.put(
    'tiktok:oauth:state:state-1',
    JSON.stringify({ state: 'state-1', redirect_uri: env.TIKTOK_REDIRECT_URI }),
  );
  let fetchCalls = 0;
  const response = await handleRequest(
    new Request('https://wrong.example.test/auth/tiktok/callback?code=oauth-code&state=state-1', {
      headers: { Cookie: `${internalsForTests.STATE_COOKIE}=state-1` },
    }),
    env,
    { fetcher: async () => { fetchCalls += 1; throw new Error('must not call provider'); } },
  );

  assert.equal(response.status, 400);
  assert.equal(fetchCalls, 0);
  assert.deepEqual(await response.json(), {
    ok: false,
    error: 'redirect_uri_mismatch',
    message: 'Request URL did not match the configured TikTok redirect URI.',
  });
});

test('successful callback stores tokens server-side and redacts public output', async () => {
  const env = baseEnv();
  await env.OAUTH_STATE_KV.put(
    'tiktok:oauth:state:state-2',
    JSON.stringify({ state: 'state-2', redirect_uri: env.TIKTOK_REDIRECT_URI }),
  );
  let providerBody = '';
  const response = await handleRequest(
    new Request('https://auth.example.test/auth/tiktok/callback?code=oauth-code-secret&state=state-2', {
      headers: { Cookie: `${internalsForTests.STATE_COOKIE}=state-2` },
    }),
    env,
    {
      now: () => Date.parse('2026-07-29T00:00:00Z'),
      cryptoImpl: fixedCrypto(),
      fetcher: async (url, options) => {
        providerBody = String(options.body);
        return new Response(JSON.stringify({
          open_id: 'open-id-123',
          scope: 'user.info.basic,video.upload,video.publish',
          token_type: 'Bearer',
          access_token: 'access-token-secret',
          refresh_token: 'refresh-token-secret',
          expires_in: 86400,
          refresh_expires_in: 31536000,
        }), { status: 200 });
      },
    },
  );

  assert.equal(response.status, 303);
  assert.match(providerBody, /grant_type=authorization_code/);
  assert.match(providerBody, /redirect_uri=https%3A%2F%2Fauth.example.test%2Fauth%2Ftiktok%2Fcallback/);
  const location = response.headers.get('location');
  assert.doesNotMatch(location, /access-token-secret|refresh-token-secret|oauth-code-secret/);
  assert.match(location, /status=success/);
  assert.match(location, /open_id=open-id-123/);
  assert.match(parseSetCookies(response).join('\n'), /__Host-lena_tiktok_session=.*HttpOnly; Secure; SameSite=None/);

  const stored = await env.TIKTOK_TOKEN_KV.get('tiktok:user:open-id-123', 'json');
  assert.equal(stored.access_token, 'access-token-secret');
  assert.equal(stored.refresh_token, 'refresh-token-secret');
  assert.equal(stored.expires_at, '2026-07-30T00:00:00.000Z');
  assert.equal(env.TIKTOK_TOKEN_KV.keys().some((key) => key.startsWith('tiktok:session:')), true);
  assert.equal(await env.OAUTH_STATE_KV.get('tiktok:oauth:state:state-2'), null);

  assert.deepEqual(
    redactTikTokPayload({ access_token: 'a', refresh_token: 'r', nested: { client_secret: 's', ok: true } }),
    { access_token: '[REDACTED]', refresh_token: '[REDACTED]', nested: { client_secret: '[REDACTED]', ok: true } },
  );
});

test('session route returns connected account without exposing tokens', async () => {
  const env = baseEnv();
  await env.TIKTOK_TOKEN_KV.put('tiktok:session:session-123', JSON.stringify({
    open_id: 'open-id-123',
    created_at: '2026-07-29T00:00:00.000Z',
  }));

  const response = await handleRequest(
    new Request('https://auth.example.test/auth/tiktok/session', {
      headers: {
        Cookie: `${internalsForTests.SESSION_COOKIE}=session-123`,
        Origin: 'https://delapilena-max.github.io',
      },
    }),
    env,
  );

  assert.equal(response.status, 200);
  assert.equal(response.headers.get('access-control-allow-credentials'), 'true');
  const payload = await response.json();
  assert.deepEqual(payload, {
    ok: true,
    session: { connected: true, open_id: 'open-id-123' },
  });
});

test('creator-info uses server-side token and redacts browser response', async () => {
  const env = baseEnv();
  await env.TIKTOK_TOKEN_KV.put('tiktok:session:session-123', JSON.stringify({ open_id: 'open-id-123' }));
  await env.TIKTOK_TOKEN_KV.put('tiktok:user:open-id-123', JSON.stringify({
    open_id: 'open-id-123',
    access_token: 'access-token-secret',
    refresh_token: 'refresh-token-secret',
    expires_at: '2026-07-30T00:00:00.000Z',
  }));
  let providerAuthorization = '';
  const response = await handleRequest(
    new Request('https://auth.example.test/api/tiktok/creator-info', {
      method: 'POST',
      headers: {
        Cookie: `${internalsForTests.SESSION_COOKIE}=session-123`,
        Origin: 'https://delapilena-max.github.io',
      },
    }),
    env,
    {
      now: () => Date.parse('2026-07-29T00:00:00Z'),
      fetcher: async (url, options) => {
        assert.equal(url, internalsForTests.TIKTOK_CREATOR_INFO_URL);
        providerAuthorization = options.headers.Authorization;
        return new Response(JSON.stringify({
          data: {
            creator_username: 'lena_test',
            creator_nickname: 'Lena Test',
            privacy_level_options: ['PUBLIC_TO_EVERYONE', 'SELF_ONLY'],
            comment_disabled: false,
            duet_disabled: true,
            stitch_disabled: false,
            max_video_post_duration_sec: 300,
          },
          error: { code: 'ok', message: '', log_id: 'log-1' },
        }), { status: 200 });
      },
    },
  );

  assert.equal(providerAuthorization, 'Bearer access-token-secret');
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.ok, true);
  assert.equal(payload.creator.creator_username, 'lena_test');
  assert.doesNotMatch(JSON.stringify(payload), /access-token-secret|refresh-token-secret/);
});

test('direct post initializes private FILE_UPLOAD, uploads bytes, and returns publish status ids', async () => {
  const env = baseEnv();
  await env.TIKTOK_TOKEN_KV.put('tiktok:session:session-123', JSON.stringify({ open_id: 'open-id-123' }));
  await env.TIKTOK_TOKEN_KV.put('tiktok:user:open-id-123', JSON.stringify({
    open_id: 'open-id-123',
    access_token: 'access-token-secret',
    refresh_token: 'refresh-token-secret',
    expires_at: '2026-07-30T00:00:00.000Z',
  }));
  const form = new FormData();
  form.set('video', new Blob([new Uint8Array([1, 2, 3, 4])], { type: 'video/mp4' }), 'review.mp4');
  form.set('caption', 'Private demo caption');
  form.set('privacy_level', 'SELF_ONLY');
  form.set('disable_comment', 'true');
  form.set('disable_duet', 'false');
  form.set('disable_stitch', 'true');
  let initBody;
  let uploadHeaders;
  const response = await handleRequest(
    new Request('https://auth.example.test/api/tiktok/publish/direct', {
      method: 'POST',
      headers: {
        Cookie: `${internalsForTests.SESSION_COOKIE}=session-123`,
        Origin: 'https://delapilena-max.github.io',
      },
      body: form,
    }),
    env,
    {
      now: () => Date.parse('2026-07-29T00:00:00Z'),
      fetcher: async (url, options) => {
        if (url === internalsForTests.TIKTOK_CREATOR_INFO_URL) {
          return new Response(JSON.stringify({
            data: {
              creator_username: 'lena_test',
              privacy_level_options: ['SELF_ONLY'],
              comment_disabled: false,
              duet_disabled: false,
              stitch_disabled: false,
            },
            error: { code: 'ok', message: '', log_id: 'log-creator' },
          }), { status: 200 });
        }
        if (url === internalsForTests.TIKTOK_DIRECT_POST_INIT_URL) {
          initBody = JSON.parse(options.body);
          return new Response(JSON.stringify({
            data: {
              publish_id: 'v_pub_file~v2-1.123',
              upload_url: 'https://open-upload.tiktokapis.com/video/?upload_id=upload-123&upload_token=secret-upload-token',
            },
            error: { code: 'ok', message: '', log_id: 'log-init' },
          }), { status: 200 });
        }
        if (String(url).startsWith('https://open-upload.tiktokapis.com/video/')) {
          uploadHeaders = options.headers;
          return new Response('', { status: 200, statusText: 'OK' });
        }
        throw new Error(`unexpected url ${url}`);
      },
    },
  );

  assert.equal(response.status, 200);
  assert.equal(initBody.post_info.privacy_level, 'SELF_ONLY');
  assert.equal(initBody.post_info.title, 'Private demo caption');
  assert.equal(initBody.post_info.disable_comment, true);
  assert.equal(initBody.post_info.disable_stitch, true);
  assert.equal(initBody.post_info.is_aigc, true);
  assert.equal(initBody.source_info.source, 'FILE_UPLOAD');
  assert.equal(initBody.source_info.video_size, 4);
  assert.equal(initBody.source_info.total_chunk_count, 1);
  assert.equal(uploadHeaders['Content-Range'], 'bytes 0-3/4');
  const payload = await response.json();
  assert.equal(payload.ok, true);
  assert.equal(payload.publish_id, 'v_pub_file~v2-1.123');
  assert.equal(payload.upload_id, 'upload-123');
  assert.doesNotMatch(JSON.stringify(payload), /secret-upload-token|access-token-secret|refresh-token-secret/);
});

test('draft upload uses video.upload inbox endpoint and returns caption note', async () => {
  const env = baseEnv();
  await env.TIKTOK_TOKEN_KV.put('tiktok:session:session-123', JSON.stringify({ open_id: 'open-id-123' }));
  await env.TIKTOK_TOKEN_KV.put('tiktok:user:open-id-123', JSON.stringify({
    open_id: 'open-id-123',
    access_token: 'access-token-secret',
    refresh_token: 'refresh-token-secret',
    expires_at: '2026-07-30T00:00:00.000Z',
  }));
  const form = new FormData();
  form.set('video', new Blob([new Uint8Array([1, 2])], { type: 'video/quicktime' }), 'draft.mov');
  form.set('caption', 'Draft caption');
  let initBody;
  const response = await handleRequest(
    new Request('https://auth.example.test/api/tiktok/upload/draft', {
      method: 'POST',
      headers: { Cookie: `${internalsForTests.SESSION_COOKIE}=session-123` },
      body: form,
    }),
    env,
    {
      now: () => Date.parse('2026-07-29T00:00:00Z'),
      fetcher: async (url, options) => {
        if (url === internalsForTests.TIKTOK_DRAFT_UPLOAD_INIT_URL) {
          initBody = JSON.parse(options.body);
          return new Response(JSON.stringify({
            data: {
              publish_id: 'v_inbox_file~v2.123',
              upload_url: 'https://open-upload.tiktokapis.com/video/?upload_id=draft-upload-123&upload_token=secret',
            },
            error: { code: 'ok', message: '', log_id: 'log-draft' },
          }), { status: 200 });
        }
        if (String(url).startsWith('https://open-upload.tiktokapis.com/video/')) {
          return new Response('', { status: 200 });
        }
        throw new Error(`unexpected url ${url}`);
      },
    },
  );

  assert.equal(response.status, 200);
  assert.equal(initBody.source_info.source, 'FILE_UPLOAD');
  const payload = await response.json();
  assert.equal(payload.mode, 'draft_upload');
  assert.equal(payload.publish_id, 'v_inbox_file~v2.123');
  assert.match(payload.caption_note, /does not accept a caption/);
});

test('status endpoint polls TikTok with publish_id and no token exposure', async () => {
  const env = baseEnv();
  await env.TIKTOK_TOKEN_KV.put('tiktok:session:session-123', JSON.stringify({ open_id: 'open-id-123' }));
  await env.TIKTOK_TOKEN_KV.put('tiktok:user:open-id-123', JSON.stringify({
    open_id: 'open-id-123',
    access_token: 'access-token-secret',
    refresh_token: 'refresh-token-secret',
    expires_at: '2026-07-30T00:00:00.000Z',
  }));
  const response = await handleRequest(
    new Request('https://auth.example.test/api/tiktok/status', {
      method: 'POST',
      headers: {
        Cookie: `${internalsForTests.SESSION_COOKIE}=session-123`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ publish_id: 'v_pub_file~v2-1.123' }),
    }),
    env,
    {
      now: () => Date.parse('2026-07-29T00:00:00Z'),
      fetcher: async (url, options) => {
        assert.equal(url, internalsForTests.TIKTOK_POST_STATUS_URL);
        assert.equal(JSON.parse(options.body).publish_id, 'v_pub_file~v2-1.123');
        return new Response(JSON.stringify({
          data: { status: 'PUBLISH_COMPLETE', uploaded_bytes: 4 },
          error: { code: 'ok', message: '', log_id: 'log-status' },
        }), { status: 200 });
      },
    },
  );

  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.status, 'PUBLISH_COMPLETE');
  assert.doesNotMatch(JSON.stringify(payload), /access-token-secret|refresh-token-secret/);
});

test('posting endpoints reject missing session before TikTok API calls', async () => {
  const env = baseEnv();
  let fetchCalls = 0;
  const response = await handleRequest(
    new Request('https://auth.example.test/api/tiktok/creator-info', { method: 'POST' }),
    env,
    { fetcher: async () => { fetchCalls += 1; throw new Error('must not call TikTok'); } },
  );

  assert.equal(response.status, 401);
  assert.equal(fetchCalls, 0);
  const payload = await response.json();
  assert.equal(payload.error, 'not_connected');
});

test('missing configuration fails without exposing secrets', async () => {
  const env = baseEnv({ TIKTOK_CLIENT_SECRET: '' });
  await env.OAUTH_STATE_KV.put(
    'tiktok:oauth:state:state-3',
    JSON.stringify({ state: 'state-3', redirect_uri: env.TIKTOK_REDIRECT_URI }),
  );
  const response = await handleRequest(
    new Request('https://auth.example.test/auth/tiktok/callback?code=oauth-code&state=state-3', {
      headers: { Cookie: `${internalsForTests.STATE_COOKIE}=state-3` },
    }),
    env,
  );

  assert.equal(response.status, 500);
  const payload = await response.json();
  assert.equal(payload.error, 'missing_configuration');
  assert.deepEqual(payload.missing, ['TIKTOK_CLIENT_SECRET']);
  assert.doesNotMatch(JSON.stringify(payload), /oauth-code|test-client-secret/);
});

test('refresh route exchanges refresh token and returns only a redacted summary', async () => {
  const env = baseEnv();
  await env.TIKTOK_TOKEN_KV.put('tiktok:user:open-id-123', JSON.stringify({
    open_id: 'open-id-123',
    access_token: 'old-access-token',
    refresh_token: 'old-refresh-token',
  }));

  const response = await handleRequest(
    new Request('https://auth.example.test/auth/tiktok/refresh', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer refresh-admin-secret',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ open_id: 'open-id-123' }),
    }),
    env,
    {
      now: () => Date.parse('2026-07-29T00:00:00Z'),
      fetcher: async (url, options) => {
        assert.equal(url, internalsForTests.TIKTOK_TOKEN_URL);
        assert.match(String(options.body), /grant_type=refresh_token/);
        return new Response(JSON.stringify({
          open_id: 'open-id-123',
          scope: 'user.info.basic,video.upload,video.publish',
          token_type: 'Bearer',
          access_token: 'new-access-token',
          refresh_token: 'new-refresh-token',
          expires_in: 3600,
          refresh_expires_in: 7200,
        }), { status: 200 });
      },
    },
  );

  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.ok, true);
  assert.equal(payload.token.open_id, 'open-id-123');
  assert.equal(payload.token.expires_at, '2026-07-29T01:00:00.000Z');
  assert.doesNotMatch(JSON.stringify(payload), /new-access-token|new-refresh-token|old-refresh-token/);
  const stored = await env.TIKTOK_TOKEN_KV.get('tiktok:user:open-id-123', 'json');
  assert.equal(stored.access_token, 'new-access-token');
  assert.equal(stored.refresh_token, 'new-refresh-token');
});

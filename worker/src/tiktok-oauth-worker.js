const TIKTOK_AUTHORIZATION_URL = 'https://www.tiktok.com/v2/auth/authorize/';
const TIKTOK_TOKEN_URL = 'https://open.tiktokapis.com/v2/oauth/token/';
const TIKTOK_CREATOR_INFO_URL = 'https://open.tiktokapis.com/v2/post/publish/creator_info/query/';
const TIKTOK_DIRECT_POST_INIT_URL = 'https://open.tiktokapis.com/v2/post/publish/video/init/';
const TIKTOK_DRAFT_UPLOAD_INIT_URL = 'https://open.tiktokapis.com/v2/post/publish/inbox/video/init/';
const TIKTOK_POST_STATUS_URL = 'https://open.tiktokapis.com/v2/post/publish/status/fetch/';
const REQUIRED_SCOPES = ['user.info.basic', 'video.upload', 'video.publish'];
const STATE_TTL_SECONDS = 600;
const SESSION_TTL_SECONDS = 86400;
const STATE_COOKIE = '__Host-lena_tiktok_oauth_state';
const SESSION_COOKIE = '__Host-lena_tiktok_session';
const STATE_KEY_PREFIX = 'tiktok:oauth:state:';
const TOKEN_KEY_PREFIX = 'tiktok:user:';
const SESSION_KEY_PREFIX = 'tiktok:session:';
const PAGES_ORIGIN = 'https://delapilena-max.github.io';
const PUBLIC_SITE_ORIGIN = 'https://delapilena-max.github.io';
const SENSITIVE_FIELDS = new Set([
  'access_token',
  'refresh_token',
  'client_secret',
  'code',
  'authorization',
  'upload_url',
]);

class PublicOAuthError extends Error {
  constructor(code, message, status = 400) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

class ConfigError extends Error {
  constructor(missing) {
    super(`Missing required TikTok OAuth configuration: ${missing.join(', ')}`);
    this.code = 'missing_configuration';
    this.status = 500;
    this.missing = missing;
  }
}

export default {
  async fetch(request, env, ctx) {
    return handleRequest(request, env, { fetcher: globalThis.fetch, now: () => Date.now(), cryptoImpl: globalThis.crypto });
  },
};

export async function handleRequest(request, env, runtime = {}) {
  const url = new URL(request.url);
  const fetcher = runtime.fetcher || globalThis.fetch;
  const now = runtime.now || (() => Date.now());
  const cryptoImpl = runtime.cryptoImpl || globalThis.crypto;

  try {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders(request) });
    }
    if (request.method === 'GET' && url.pathname === '/auth/tiktok/start') {
      return await startTikTokLogin(env, { now, cryptoImpl });
    }
    if (request.method === 'GET' && url.pathname === '/auth/tiktok/callback') {
      return await completeTikTokLogin(request, env, { fetcher, now, cryptoImpl });
    }
    if (request.method === 'POST' && url.pathname === '/auth/tiktok/refresh') {
      return await refreshTikTokToken(request, env, { fetcher, now });
    }
    if (request.method === 'GET' && url.pathname === '/auth/tiktok/session') {
      return await getTikTokSession(request, env);
    }
    if (request.method === 'POST' && url.pathname === '/api/tiktok/creator-info') {
      return await getCreatorInfo(request, env, { fetcher, now });
    }
    if (request.method === 'POST' && url.pathname === '/api/tiktok/publish/direct') {
      return await publishDirectPost(request, env, { fetcher, now });
    }
    if (request.method === 'POST' && url.pathname === '/api/tiktok/upload/draft') {
      return await uploadDraft(request, env, { fetcher, now });
    }
    if (request.method === 'POST' && url.pathname === '/api/tiktok/status') {
      return await fetchPostStatus(request, env, { fetcher, now });
    }
    return jsonResponse({ ok: false, error: 'not_found' }, 404);
  } catch (error) {
    if (error instanceof ConfigError) {
      return jsonResponse({ ok: false, error: error.code, missing: error.missing }, error.status);
    }
    if (error instanceof PublicOAuthError) {
      return jsonResponse({ ok: false, error: error.code, message: error.message }, error.status);
    }
    return jsonResponse({ ok: false, error: 'internal_error' }, 500);
  }
}

export async function startTikTokLogin(env, runtime = {}) {
  requireConfig(env, ['TIKTOK_CLIENT_KEY', 'TIKTOK_REDIRECT_URI', 'OAUTH_STATE_KV']);
  assertStaticHttpsRedirectUri(env.TIKTOK_REDIRECT_URI);

  const now = runtime.now || (() => Date.now());
  const state = generateState(runtime.cryptoImpl || globalThis.crypto);
  const stateRecord = {
    state,
    redirect_uri: env.TIKTOK_REDIRECT_URI,
    scope: REQUIRED_SCOPES.join(','),
    created_at: new Date(now()).toISOString(),
  };

  await env.OAUTH_STATE_KV.put(
    stateKey(state),
    JSON.stringify(stateRecord),
    { expirationTtl: STATE_TTL_SECONDS },
  );

  const authorize = new URL(TIKTOK_AUTHORIZATION_URL);
  authorize.searchParams.set('client_key', env.TIKTOK_CLIENT_KEY);
  authorize.searchParams.set('response_type', 'code');
  authorize.searchParams.set('scope', REQUIRED_SCOPES.join(','));
  authorize.searchParams.set('redirect_uri', env.TIKTOK_REDIRECT_URI);
  authorize.searchParams.set('state', state);

  return new Response(null, {
    status: 302,
    headers: {
      ...noStoreHeaders(),
      Location: authorize.toString(),
      'Set-Cookie': `${STATE_COOKIE}=${state}; Max-Age=${STATE_TTL_SECONDS}; Path=/; HttpOnly; Secure; SameSite=Lax`,
    },
  });
}

export async function completeTikTokLogin(request, env, runtime = {}) {
  requireConfig(env, [
    'TIKTOK_CLIENT_KEY',
    'TIKTOK_REDIRECT_URI',
    'PUBLIC_SUCCESS_REDIRECT',
    'PUBLIC_ERROR_REDIRECT',
    'OAUTH_STATE_KV',
  ]);
  assertRequestMatchesConfiguredRedirect(request, env.TIKTOK_REDIRECT_URI);

  const url = new URL(request.url);
  const tiktokError = url.searchParams.get('error');
  if (tiktokError) {
    return redirectToPublic(env.PUBLIC_ERROR_REDIRECT, {
      status: 'error',
      error: sanitizeForUrl(tiktokError),
      error_description: sanitizeForUrl(url.searchParams.get('error_description') || ''),
    }, expireStateCookie());
  }

  const state = url.searchParams.get('state') || '';
  const code = url.searchParams.get('code') || '';
  const cookieState = parseCookies(request.headers.get('Cookie') || '')[STATE_COOKIE] || '';
  if (!state || !code || state !== cookieState) {
    return redirectToPublic(env.PUBLIC_ERROR_REDIRECT, {
      status: 'error',
      error: 'state_mismatch',
    }, expireStateCookie());
  }

  const storedState = await env.OAUTH_STATE_KV.get(stateKey(state), 'json');
  if (!storedState || storedState.state !== state || storedState.redirect_uri !== env.TIKTOK_REDIRECT_URI) {
    return redirectToPublic(env.PUBLIC_ERROR_REDIRECT, {
      status: 'error',
      error: 'state_mismatch',
    }, expireStateCookie());
  }

  requireConfig(env, ['TIKTOK_CLIENT_SECRET', 'TIKTOK_TOKEN_KV']);
  const tokenPayload = await exchangeCodeForToken(code, env, runtime.fetcher || globalThis.fetch);
  const tokenRecord = buildStoredTokenRecord(tokenPayload, runtime.now || (() => Date.now()));
  await env.TIKTOK_TOKEN_KV.put(tokenKey(tokenRecord.open_id), JSON.stringify(tokenRecord));
  await env.OAUTH_STATE_KV.delete(stateKey(state));
  const sessionId = generateState(runtime.cryptoImpl || globalThis.crypto);
  await env.TIKTOK_TOKEN_KV.put(
    sessionKey(sessionId),
    JSON.stringify({
      open_id: tokenRecord.open_id,
      created_at: new Date((runtime.now || (() => Date.now()))()).toISOString(),
    }),
    { expirationTtl: SESSION_TTL_SECONDS },
  );

  return redirectToPublic(env.PUBLIC_SUCCESS_REDIRECT, {
    status: 'success',
    open_id: tokenRecord.open_id,
    scope: tokenRecord.scope,
  }, [expireStateCookie(), sessionCookie(sessionId)]);
}

export async function refreshTikTokToken(request, env, runtime = {}) {
  requireConfig(env, [
    'TIKTOK_CLIENT_KEY',
    'TIKTOK_CLIENT_SECRET',
    'INTERNAL_REFRESH_BEARER',
    'TIKTOK_TOKEN_KV',
  ]);

  const authorization = request.headers.get('Authorization') || '';
  if (authorization !== `Bearer ${env.INTERNAL_REFRESH_BEARER}`) {
    return jsonResponse({ ok: false, error: 'unauthorized' }, 401);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ ok: false, error: 'malformed_json' }, 400);
  }

  const openId = String(body.open_id || '');
  if (!openId) {
    return jsonResponse({ ok: false, error: 'missing_open_id' }, 400);
  }

  const existing = await env.TIKTOK_TOKEN_KV.get(tokenKey(openId), 'json');
  if (!existing || !existing.refresh_token) {
    return jsonResponse({ ok: false, error: 'token_not_found' }, 404);
  }

  const refreshedPayload = await refreshToken(existing.refresh_token, env, runtime.fetcher || globalThis.fetch);
  const tokenRecord = buildStoredTokenRecord(
    { ...refreshedPayload, open_id: refreshedPayload.open_id || openId },
    runtime.now || (() => Date.now()),
  );
  await env.TIKTOK_TOKEN_KV.put(tokenKey(tokenRecord.open_id), JSON.stringify(tokenRecord));
  return jsonResponse({ ok: true, token: publicTokenSummary(tokenRecord) }, 200);
}

export async function getTikTokSession(request, env) {
  const session = await requirePostingSession(request, env);
  return jsonResponse({ ok: true, session: { connected: true, open_id: session.open_id } }, 200, request);
}

export async function getCreatorInfo(request, env, runtime = {}) {
  const { tokenRecord } = await loadPostingToken(request, env, runtime);
  const payload = await callTikTokJson(
    TIKTOK_CREATOR_INFO_URL,
    tokenRecord.access_token,
    {},
    runtime.fetcher || globalThis.fetch,
  );
  return jsonResponse({ ok: isTikTokOk(payload), creator: payload.data || null, tiktok: redactTikTokPayload(payload) }, 200, request);
}

export async function publishDirectPost(request, env, runtime = {}) {
  const { tokenRecord } = await loadPostingToken(request, env, runtime);
  const form = await readVideoForm(request);
  const creatorPayload = await callTikTokJson(
    TIKTOK_CREATOR_INFO_URL,
    tokenRecord.access_token,
    {},
    runtime.fetcher || globalThis.fetch,
  );
  if (!isTikTokOk(creatorPayload)) {
    return jsonResponse({ ok: false, error: 'creator_info_failed', tiktok: creatorPayload }, 502, request);
  }
  const creator = creatorPayload.data || {};
  const privacyLevel = normalizePrivacyLevel(form.privacyLevel, creator.privacy_level_options || []);
  const initPayload = await callTikTokJson(
    TIKTOK_DIRECT_POST_INIT_URL,
    tokenRecord.access_token,
    {
      post_info: {
        title: form.caption,
        privacy_level: privacyLevel,
        disable_duet: form.disableDuet || Boolean(creator.duet_disabled),
        disable_comment: form.disableComment || Boolean(creator.comment_disabled),
        disable_stitch: form.disableStitch || Boolean(creator.stitch_disabled),
        brand_content_toggle: false,
        brand_organic_toggle: false,
        is_aigc: true,
      },
      source_info: sourceInfoForFile(form.file),
    },
    runtime.fetcher || globalThis.fetch,
  );
  const uploadResult = await uploadFileIfNeeded(initPayload, form.file, runtime.fetcher || globalThis.fetch);
  return jsonResponse({
    ok: isTikTokOk(initPayload) && uploadResult.ok,
    mode: 'direct_post',
    publish_id: initPayload.data?.publish_id || null,
    upload_id: extractUploadId(initPayload.data?.upload_url || ''),
    creator,
    tiktok: redactTikTokPayload(initPayload),
    upload: uploadResult.public,
  }, isTikTokOk(initPayload) && uploadResult.ok ? 200 : 502, request);
}

export async function uploadDraft(request, env, runtime = {}) {
  const { tokenRecord } = await loadPostingToken(request, env, runtime);
  const form = await readVideoForm(request);
  const initPayload = await callTikTokJson(
    TIKTOK_DRAFT_UPLOAD_INIT_URL,
    tokenRecord.access_token,
    { source_info: sourceInfoForFile(form.file) },
    runtime.fetcher || globalThis.fetch,
  );
  const uploadResult = await uploadFileIfNeeded(initPayload, form.file, runtime.fetcher || globalThis.fetch);
  return jsonResponse({
    ok: isTikTokOk(initPayload) && uploadResult.ok,
    mode: 'draft_upload',
    publish_id: initPayload.data?.publish_id || null,
    upload_id: extractUploadId(initPayload.data?.upload_url || ''),
    caption_note: form.caption ? 'TikTok draft upload does not accept a caption in the init API; caption is entered in TikTok when completing the draft.' : '',
    tiktok: redactTikTokPayload(initPayload),
    upload: uploadResult.public,
  }, isTikTokOk(initPayload) && uploadResult.ok ? 200 : 502, request);
}

export async function fetchPostStatus(request, env, runtime = {}) {
  const { tokenRecord } = await loadPostingToken(request, env, runtime);
  const body = await readJson(request);
  const publishId = String(body.publish_id || '').trim();
  if (!publishId) {
    return jsonResponse({ ok: false, error: 'missing_publish_id' }, 400, request);
  }
  const payload = await callTikTokJson(
    TIKTOK_POST_STATUS_URL,
    tokenRecord.access_token,
    { publish_id: publishId },
    runtime.fetcher || globalThis.fetch,
  );
  return jsonResponse({
    ok: isTikTokOk(payload),
    publish_id: publishId,
    status: payload.data?.status || null,
    data: payload.data || null,
    tiktok: redactTikTokPayload(payload),
  }, isTikTokOk(payload) ? 200 : 502, request);
}

async function exchangeCodeForToken(code, env, fetcher) {
  const form = new URLSearchParams({
    client_key: env.TIKTOK_CLIENT_KEY,
    client_secret: env.TIKTOK_CLIENT_SECRET,
    code,
    grant_type: 'authorization_code',
    redirect_uri: env.TIKTOK_REDIRECT_URI,
  });
  return sendTokenRequest(form, fetcher);
}

async function refreshToken(refreshTokenValue, env, fetcher) {
  const form = new URLSearchParams({
    client_key: env.TIKTOK_CLIENT_KEY,
    client_secret: env.TIKTOK_CLIENT_SECRET,
    grant_type: 'refresh_token',
    refresh_token: refreshTokenValue,
  });
  return sendTokenRequest(form, fetcher);
}

async function loadPostingToken(request, env, runtime = {}) {
  requireConfig(env, ['TIKTOK_CLIENT_KEY', 'TIKTOK_CLIENT_SECRET', 'TIKTOK_TOKEN_KV']);
  const session = await requirePostingSession(request, env);
  const tokenRecord = await env.TIKTOK_TOKEN_KV.get(tokenKey(session.open_id), 'json');
  if (!tokenRecord || !tokenRecord.access_token) {
    throw new PublicOAuthError('token_not_found', 'TikTok token was not found for the connected account.', 401);
  }
  if (tokenNeedsRefresh(tokenRecord, runtime.now || (() => Date.now()))) {
    if (!tokenRecord.refresh_token) {
      throw new PublicOAuthError('token_expired', 'TikTok token is expired and no refresh token is available.', 401);
    }
    const refreshedPayload = await refreshToken(tokenRecord.refresh_token, env, runtime.fetcher || globalThis.fetch);
    const refreshedRecord = buildStoredTokenRecord(
      { ...refreshedPayload, open_id: refreshedPayload.open_id || tokenRecord.open_id },
      runtime.now || (() => Date.now()),
    );
    await env.TIKTOK_TOKEN_KV.put(tokenKey(refreshedRecord.open_id), JSON.stringify(refreshedRecord));
    return { session, tokenRecord: refreshedRecord };
  }
  return { session, tokenRecord };
}

async function requirePostingSession(request, env) {
  requireConfig(env, ['TIKTOK_TOKEN_KV']);
  const sessionId = parseCookies(request.headers.get('Cookie') || '')[SESSION_COOKIE] || '';
  if (!sessionId) {
    throw new PublicOAuthError('not_connected', 'TikTok account is not connected in this browser session.', 401);
  }
  const session = await env.TIKTOK_TOKEN_KV.get(sessionKey(sessionId), 'json');
  if (!session || !session.open_id) {
    throw new PublicOAuthError('session_expired', 'TikTok connection session expired. Please log in again.', 401);
  }
  return session;
}

function tokenNeedsRefresh(record, now) {
  if (!record.expires_at) return false;
  return Date.parse(record.expires_at) - now() < 60000;
}

async function callTikTokJson(url, accessToken, body, fetcher) {
  const response = await fetcher(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json; charset=UTF-8',
    },
    body: JSON.stringify(body),
  });
  const rawText = await response.text();
  let payload;
  try {
    payload = JSON.parse(rawText || '{}');
  } catch {
    throw new PublicOAuthError('malformed_tiktok_response', 'TikTok response was not valid JSON.', 502);
  }
  if (!response.ok && !payload.error) {
    payload.error = { code: `http_${response.status}`, message: 'TikTok request failed.' };
  }
  return payload;
}

async function readJson(request) {
  try {
    return await request.json();
  } catch {
    throw new PublicOAuthError('malformed_json', 'Request JSON was malformed.', 400);
  }
}

async function readVideoForm(request) {
  let formData;
  try {
    formData = await request.formData();
  } catch {
    throw new PublicOAuthError('malformed_form', 'Upload form was malformed.', 400);
  }
  const file = formData.get('video');
  if (!isFileLike(file) || file.size <= 0) {
    throw new PublicOAuthError('missing_video', 'Select an MP4 or MOV video file.', 400);
  }
  if (!['video/mp4', 'video/quicktime'].includes(file.type)) {
    throw new PublicOAuthError('unsupported_video_type', 'Only MP4 and MOV files are accepted for this review demo.', 400);
  }
  return {
    file,
    caption: String(formData.get('caption') || '').slice(0, 2200),
    privacyLevel: String(formData.get('privacy_level') || 'SELF_ONLY'),
    disableComment: formData.get('disable_comment') === 'true',
    disableDuet: formData.get('disable_duet') === 'true',
    disableStitch: formData.get('disable_stitch') === 'true',
  };
}

function isFileLike(value) {
  return Boolean(
    value
    && typeof value === 'object'
    && typeof value.size === 'number'
    && typeof value.type === 'string'
    && typeof value.arrayBuffer === 'function',
  );
}

function normalizePrivacyLevel(requested, options) {
  const available = Array.isArray(options) ? options : [];
  if (available.includes(requested)) return requested;
  if (available.includes('SELF_ONLY')) return 'SELF_ONLY';
  throw new PublicOAuthError('privacy_level_unavailable', 'SELF_ONLY/private posting is not available for this TikTok account.', 400);
}

function sourceInfoForFile(file) {
  return {
    source: 'FILE_UPLOAD',
    video_size: file.size,
    chunk_size: file.size,
    total_chunk_count: 1,
  };
}

async function uploadFileIfNeeded(initPayload, file, fetcher) {
  if (!isTikTokOk(initPayload)) {
    return { ok: false, public: { skipped: true, reason: 'init_failed' } };
  }
  const uploadUrl = initPayload.data?.upload_url || '';
  if (!uploadUrl) {
    return { ok: true, public: { skipped: true, transfer: 'PULL_FROM_URL_or_no_upload_url' } };
  }
  const bytes = await file.arrayBuffer();
  const uploadResponse = await fetcher(uploadUrl, {
    method: 'PUT',
    headers: {
      'Content-Type': file.type,
      'Content-Length': String(file.size),
      'Content-Range': `bytes 0-${file.size - 1}/${file.size}`,
    },
    body: bytes,
  });
  return {
    ok: uploadResponse.ok,
    public: {
      status: uploadResponse.status,
      status_text: uploadResponse.statusText,
      uploaded_bytes: uploadResponse.ok ? file.size : 0,
    },
  };
}

function isTikTokOk(payload) {
  return payload?.error?.code === 'ok';
}

function extractUploadId(uploadUrl) {
  if (!uploadUrl) return null;
  try {
    return new URL(uploadUrl).searchParams.get('upload_id');
  } catch {
    return null;
  }
}

async function sendTokenRequest(form, fetcher) {
  const response = await fetcher(TIKTOK_TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  });
  const rawText = await response.text();
  let payload;
  try {
    payload = JSON.parse(rawText);
  } catch {
    throw new PublicOAuthError('malformed_token_response', 'TikTok token response was not valid JSON.', 502);
  }
  if (!response.ok) {
    throw new PublicOAuthError('token_exchange_failed', payload.error || 'TikTok token exchange failed.', 502);
  }
  if (!payload.access_token || !payload.refresh_token || !payload.open_id) {
    throw new PublicOAuthError('malformed_token_response', 'TikTok token response was missing required token fields.', 502);
  }
  return payload;
}

function buildStoredTokenRecord(payload, now) {
  const nowMs = now();
  const expiresIn = Number(payload.expires_in || 0);
  const refreshExpiresIn = Number(payload.refresh_expires_in || 0);
  return {
    open_id: String(payload.open_id),
    scope: String(payload.scope || REQUIRED_SCOPES.join(',')),
    token_type: String(payload.token_type || 'Bearer'),
    access_token: String(payload.access_token),
    refresh_token: String(payload.refresh_token),
    obtained_at: new Date(nowMs).toISOString(),
    expires_at: expiresIn > 0 ? new Date(nowMs + expiresIn * 1000).toISOString() : null,
    refresh_expires_at: refreshExpiresIn > 0 ? new Date(nowMs + refreshExpiresIn * 1000).toISOString() : null,
  };
}

function publicTokenSummary(record) {
  return {
    open_id: record.open_id,
    scope: record.scope,
    token_type: record.token_type,
    expires_at: record.expires_at,
    refresh_expires_at: record.refresh_expires_at,
  };
}

export function redactTikTokPayload(value) {
  if (Array.isArray(value)) {
    return value.map((item) => redactTikTokPayload(item));
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, nested]) => [
        key,
        SENSITIVE_FIELDS.has(key.toLowerCase()) ? '[REDACTED]' : redactTikTokPayload(nested),
      ]),
    );
  }
  return value;
}

function requireConfig(env, requiredKeys) {
  const missing = requiredKeys.filter((key) => env[key] === undefined || env[key] === null || env[key] === '');
  if (missing.length > 0) {
    throw new ConfigError(missing);
  }
}

function assertStaticHttpsRedirectUri(redirectUri) {
  const parsed = new URL(redirectUri);
  if (parsed.protocol !== 'https:' || parsed.search || parsed.hash) {
    throw new ConfigError(['TIKTOK_REDIRECT_URI_static_https_no_query_or_fragment']);
  }
}

function assertRequestMatchesConfiguredRedirect(request, redirectUri) {
  assertStaticHttpsRedirectUri(redirectUri);
  const expected = new URL(redirectUri);
  const actual = new URL(request.url);
  if (actual.origin !== expected.origin || actual.pathname !== expected.pathname) {
    throw new PublicOAuthError('redirect_uri_mismatch', 'Request URL did not match the configured TikTok redirect URI.', 400);
  }
}

function generateState(cryptoImpl) {
  const bytes = new Uint8Array(32);
  cryptoImpl.getRandomValues(bytes);
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function parseCookies(header) {
  return Object.fromEntries(
    header.split(';')
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const index = part.indexOf('=');
        if (index === -1) return [part, ''];
        return [part.slice(0, index), decodeURIComponent(part.slice(index + 1))];
      }),
  );
}

function stateKey(state) {
  return `${STATE_KEY_PREFIX}${state}`;
}

function tokenKey(openId) {
  return `${TOKEN_KEY_PREFIX}${openId}`;
}

function sessionKey(session) {
  return `${SESSION_KEY_PREFIX}${session}`;
}

function sanitizeForUrl(value) {
  return String(value || '').replace(/[^\w .,:@/-]/g, '').slice(0, 180);
}

function redirectToPublic(target, params, cookieHeader) {
  const destination = new URL(target);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      destination.searchParams.set(key, value);
    }
  }
  const headers = new Headers({
    ...noStoreHeaders(),
    Location: destination.toString(),
  });
  if (cookieHeader) {
    const cookies = Array.isArray(cookieHeader) ? cookieHeader : [cookieHeader];
    for (const cookie of cookies) {
      headers.append('Set-Cookie', cookie);
    }
  }
  return new Response(null, { status: 303, headers });
}

function expireStateCookie() {
  return `${STATE_COOKIE}=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Lax`;
}

function sessionCookie(sessionId) {
  return `${SESSION_COOKIE}=${sessionId}; Max-Age=${SESSION_TTL_SECONDS}; Path=/; HttpOnly; Secure; SameSite=None`;
}

function jsonResponse(payload, status, request = null) {
  return new Response(JSON.stringify(redactTikTokPayload(payload)), {
    status,
    headers: {
      ...(request ? corsHeaders(request) : noStoreHeaders()),
      'Content-Type': 'application/json; charset=utf-8',
    },
  });
}

function corsHeaders(request) {
  const origin = request?.headers?.get('Origin') || '';
  const allowOrigin = origin === PAGES_ORIGIN || origin === PUBLIC_SITE_ORIGIN ? origin : PAGES_ORIGIN;
  return {
    ...noStoreHeaders(),
    'Access-Control-Allow-Origin': allowOrigin,
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    Vary: 'Origin',
  };
}

function noStoreHeaders() {
  return {
    'Cache-Control': 'no-store',
    Pragma: 'no-cache',
  };
}

export const internalsForTests = {
  REQUIRED_SCOPES,
  TIKTOK_AUTHORIZATION_URL,
  TIKTOK_TOKEN_URL,
  TIKTOK_CREATOR_INFO_URL,
  TIKTOK_DIRECT_POST_INIT_URL,
  TIKTOK_DRAFT_UPLOAD_INIT_URL,
  TIKTOK_POST_STATUS_URL,
  STATE_COOKIE,
  SESSION_COOKIE,
};

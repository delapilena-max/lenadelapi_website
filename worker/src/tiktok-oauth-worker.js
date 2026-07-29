const TIKTOK_AUTHORIZATION_URL = 'https://www.tiktok.com/v2/auth/authorize/';
const TIKTOK_TOKEN_URL = 'https://open.tiktokapis.com/v2/oauth/token/';
const REQUIRED_SCOPES = ['user.info.basic', 'video.upload', 'video.publish'];
const STATE_TTL_SECONDS = 600;
const STATE_COOKIE = '__Host-lena_tiktok_oauth_state';
const STATE_KEY_PREFIX = 'tiktok:oauth:state:';
const TOKEN_KEY_PREFIX = 'tiktok:user:';
const SENSITIVE_FIELDS = new Set([
  'access_token',
  'refresh_token',
  'client_secret',
  'code',
  'authorization',
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
      return new Response(null, { status: 204, headers: noStoreHeaders() });
    }
    if (request.method === 'GET' && url.pathname === '/auth/tiktok/start') {
      return await startTikTokLogin(env, { now, cryptoImpl });
    }
    if (request.method === 'GET' && url.pathname === '/auth/tiktok/callback') {
      return await completeTikTokLogin(request, env, { fetcher, now });
    }
    if (request.method === 'POST' && url.pathname === '/auth/tiktok/refresh') {
      return await refreshTikTokToken(request, env, { fetcher, now });
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

  return redirectToPublic(env.PUBLIC_SUCCESS_REDIRECT, {
    status: 'success',
    open_id: tokenRecord.open_id,
    scope: tokenRecord.scope,
  }, expireStateCookie());
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
  const headers = {
    ...noStoreHeaders(),
    Location: destination.toString(),
  };
  if (cookieHeader) {
    headers['Set-Cookie'] = cookieHeader;
  }
  return new Response(null, { status: 303, headers });
}

function expireStateCookie() {
  return `${STATE_COOKIE}=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Lax`;
}

function jsonResponse(payload, status) {
  return new Response(JSON.stringify(redactTikTokPayload(payload)), {
    status,
    headers: {
      ...noStoreHeaders(),
      'Content-Type': 'application/json; charset=utf-8',
    },
  });
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
  STATE_COOKIE,
};

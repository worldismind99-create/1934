// X (旧Twitter) API v2 クライアント(OAuth 2.0 Authorization Code + PKCE)
// https://docs.x.com/resources/fundamentals/authentication/oauth-2-0/authorization-code

import crypto from "node:crypto";

const AUTH_BASE = "https://x.com/i/oauth2/authorize";
const API_BASE = "https://api.x.com/2";

/** PKCE用の code_verifier / code_challenge を生成する */
export function generatePkcePair() {
  const verifier = base64url(crypto.randomBytes(32));
  const challenge = base64url(crypto.createHash("sha256").update(verifier).digest());
  return { verifier, challenge };
}

/** 認可画面のURLを生成する */
export function buildAuthorizeUrl({ clientId, redirectUri, state, codeChallenge }) {
  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: ["tweet.read", "users.read", "offline.access"].join(" "),
    state,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
  });
  return `${AUTH_BASE}?${params}`;
}

/** 認可コードをアクセストークン(約2時間有効、リフレッシュトークンつき)に交換する */
export async function exchangeCodeForToken({ clientId, clientSecret, redirectUri, code, codeVerifier }) {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: redirectUri,
    code_verifier: codeVerifier,
  });
  const data = await tokenRequest({ clientId, clientSecret, body });
  return data; // { token_type, expires_in, access_token, scope, refresh_token }
}

/** リフレッシュトークンでアクセストークンを更新する */
export async function refreshToken({ clientId, clientSecret, refreshToken }) {
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: refreshToken,
  });
  return tokenRequest({ clientId, clientSecret, body });
}

async function tokenRequest({ clientId, clientSecret, body }) {
  const headers = { "Content-Type": "application/x-www-form-urlencoded" };
  if (clientSecret) {
    // 機密クライアント: Basic認証
    headers.Authorization = `Basic ${Buffer.from(`${clientId}:${clientSecret}`).toString("base64")}`;
  } else {
    // パブリッククライアント: client_idをボディに含める
    body.set("client_id", clientId);
  }
  const res = await fetch(`${API_BASE}/oauth2/token`, { method: "POST", headers, body });
  const data = await res.json();
  if (!res.ok) throw new XApiError("トークンの取得に失敗しました", data);
  return data;
}

/** ログイン中ユーザーのプロフィールを取得する */
export async function getProfile({ accessToken }) {
  const params = new URLSearchParams({
    "user.fields": "id,name,username,profile_image_url,description,public_metrics,verified",
  });
  const res = await fetch(`${API_BASE}/users/me?${params}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const data = await res.json();
  if (!res.ok) throw new XApiError("プロフィールの取得に失敗しました", data);
  return data.data;
}

/** 指定ユーザーの最近のポスト(ツイート)一覧を取得する */
export async function getTweets({ accessToken, userId, maxResults = 10, paginationToken } = {}) {
  const params = new URLSearchParams({
    max_results: String(Math.min(Math.max(maxResults, 5), 100)),
    "tweet.fields": "id,text,created_at,public_metrics",
    exclude: "retweets,replies",
  });
  if (paginationToken) params.set("pagination_token", paginationToken);
  const res = await fetch(`${API_BASE}/users/${userId}/tweets?${params}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const data = await res.json();
  if (!res.ok) throw new XApiError("ポストの取得に失敗しました", data);
  return data; // { data: [...], meta: {...} }
}

function base64url(buffer) {
  return buffer.toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export class XApiError extends Error {
  constructor(message, response) {
    const detail = response?.error_description || response?.detail || response?.title || "";
    super(detail ? `${message}: ${detail}` : message);
    this.name = "XApiError";
    this.response = response;
  }
}

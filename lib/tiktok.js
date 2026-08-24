// TikTok API クライアント(Login Kit + Display API)
// https://developers.tiktok.com/doc/login-kit-web
// https://developers.tiktok.com/doc/display-api-overview

const AUTH_BASE = "https://www.tiktok.com/v2/auth/authorize/";
const API_BASE = "https://open.tiktokapis.com/v2";

/** 認可画面のURLを生成する */
export function buildAuthorizeUrl({ clientKey, redirectUri, state }) {
  const params = new URLSearchParams({
    client_key: clientKey,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: [
      "user.info.basic",
      "user.info.profile",
      "user.info.stats",
      "video.list",
    ].join(","),
    state,
  });
  return `${AUTH_BASE}?${params}`;
}

/** 認可コードをアクセストークン(約24時間有効、リフレッシュトークンつき)に交換する */
export async function exchangeCodeForToken({ clientKey, clientSecret, redirectUri, code }) {
  const res = await fetch(`${API_BASE}/oauth/token/`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_key: clientKey,
      client_secret: clientSecret,
      grant_type: "authorization_code",
      redirect_uri: redirectUri,
      code,
    }),
  });
  const data = await res.json();
  if (!res.ok || data.error) throw new TikTokApiError("トークン交換に失敗しました", data);
  return data; // { access_token, expires_in, refresh_token, refresh_expires_in, open_id, scope }
}

/** リフレッシュトークンでアクセストークンを更新する */
export async function refreshToken({ clientKey, clientSecret, refreshToken }) {
  const res = await fetch(`${API_BASE}/oauth/token/`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_key: clientKey,
      client_secret: clientSecret,
      grant_type: "refresh_token",
      refresh_token: refreshToken,
    }),
  });
  const data = await res.json();
  if (!res.ok || data.error) throw new TikTokApiError("トークンの更新に失敗しました", data);
  return data;
}

/** ログイン中ユーザーのプロフィールを取得する */
export async function getProfile({ accessToken }) {
  const fields = "open_id,union_id,avatar_url,display_name,bio_description,profile_deep_link,follower_count,following_count,likes_count,video_count";
  const res = await fetch(`${API_BASE}/user/info/?fields=${encodeURIComponent(fields)}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const data = await res.json();
  if (!res.ok || data.error?.code !== "ok") throw new TikTokApiError("プロフィールの取得に失敗しました", data);
  return data.data.user;
}

/** ログイン中ユーザーの動画一覧を取得する */
export async function getVideos({ accessToken, maxCount = 12, cursor } = {}) {
  const fields = "id,title,video_description,cover_image_url,share_url,duration,create_time,view_count,like_count,comment_count,share_count";
  const body = { max_count: maxCount };
  if (cursor) body.cursor = cursor;
  const res = await fetch(`${API_BASE}/video/list/?fields=${encodeURIComponent(fields)}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok || data.error?.code !== "ok") throw new TikTokApiError("動画一覧の取得に失敗しました", data);
  return data.data; // { videos: [...], cursor, has_more }
}

export class TikTokApiError extends Error {
  constructor(message, response) {
    const detail = response?.error_description || response?.error?.message || response?.error?.code || "";
    super(detail && detail !== "ok" ? `${message}: ${detail}` : message);
    this.name = "TikTokApiError";
    this.response = response;
  }
}

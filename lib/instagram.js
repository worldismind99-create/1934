// Instagram API クライアント(Instagramログイン方式)
// https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login
//
// Instagram Basic Display API は 2024年12月に廃止されたため、
// 現行の「Instagram API with Instagram Login」を使用する。
// 利用にはプロアカウント(ビジネス / クリエイター)が必要。

const OAUTH_BASE = "https://api.instagram.com";
const GRAPH_BASE = "https://graph.instagram.com";

/** 認可画面のURLを生成する */
export function buildAuthorizeUrl({ appId, redirectUri, state }) {
  const params = new URLSearchParams({
    client_id: appId,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: [
      "instagram_business_basic",
      // 必要に応じて追加:
      // "instagram_business_content_publish",
      // "instagram_business_manage_comments",
      // "instagram_business_manage_messages",
    ].join(","),
    state,
  });
  return `https://www.instagram.com/oauth/authorize?${params}`;
}

/** 認可コードを短期アクセストークン(有効期限 約1時間)に交換する */
export async function exchangeCodeForToken({ appId, appSecret, redirectUri, code }) {
  const res = await fetch(`${OAUTH_BASE}/oauth/access_token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: appId,
      client_secret: appSecret,
      grant_type: "authorization_code",
      redirect_uri: redirectUri,
      code,
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new InstagramApiError("トークン交換に失敗しました", data);
  return data; // { access_token, user_id, permissions }
}

/** 短期トークンを長期トークン(有効期限 約60日)に交換する */
export async function exchangeForLongLivedToken({ appSecret, accessToken }) {
  const params = new URLSearchParams({
    grant_type: "ig_exchange_token",
    client_secret: appSecret,
    access_token: accessToken,
  });
  const res = await fetch(`${GRAPH_BASE}/access_token?${params}`);
  const data = await res.json();
  if (!res.ok) throw new InstagramApiError("長期トークンへの交換に失敗しました", data);
  return data; // { access_token, token_type, expires_in }
}

/** 長期トークンを更新する(期限が切れる前に呼ぶ) */
export async function refreshLongLivedToken({ accessToken }) {
  const params = new URLSearchParams({
    grant_type: "ig_refresh_token",
    access_token: accessToken,
  });
  const res = await fetch(`${GRAPH_BASE}/refresh_access_token?${params}`);
  const data = await res.json();
  if (!res.ok) throw new InstagramApiError("トークンの更新に失敗しました", data);
  return data; // { access_token, token_type, expires_in }
}

/** ログイン中ユーザーのプロフィールを取得する */
export async function getProfile({ accessToken }) {
  const params = new URLSearchParams({
    fields: "user_id,username,name,account_type,profile_picture_url,followers_count,follows_count,media_count",
    access_token: accessToken,
  });
  const res = await fetch(`${GRAPH_BASE}/v23.0/me?${params}`);
  const data = await res.json();
  if (!res.ok) throw new InstagramApiError("プロフィールの取得に失敗しました", data);
  return data;
}

/** ログイン中ユーザーの投稿(メディア)一覧を取得する */
export async function getMedia({ accessToken, limit = 12, after } = {}) {
  const params = new URLSearchParams({
    fields: "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count",
    limit: String(limit),
    access_token: accessToken,
  });
  if (after) params.set("after", after);
  const res = await fetch(`${GRAPH_BASE}/v23.0/me/media?${params}`);
  const data = await res.json();
  if (!res.ok) throw new InstagramApiError("投稿の取得に失敗しました", data);
  return data; // { data: [...], paging: {...} }
}

export class InstagramApiError extends Error {
  constructor(message, response) {
    const detail = response?.error_message || response?.error?.message || "";
    super(detail ? `${message}: ${detail}` : message);
    this.name = "InstagramApiError";
    this.response = response;
  }
}

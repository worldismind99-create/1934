// SNS連携アプリ(Instagram / TikTok / X) - エントリポイント
// 依存ライブラリなし(Node.js 18+ の標準機能のみ)で動作する。
//
// 起動: npm start  (または node server.js)
// 事前に .env.example を .env にコピーして値を設定すること。
// 3サービスすべての設定は必須ではなく、設定済みのサービスだけ連携できる。

import http from "node:http";
import crypto from "node:crypto";
import { readFileSync, existsSync } from "node:fs";
import * as instagram from "./lib/instagram.js";
import * as tiktok from "./lib/tiktok.js";
import * as x from "./lib/x.js";

loadDotEnv();

const PORT = Number(process.env.PORT || 3000);
const BASE_URL = process.env.BASE_URL || `http://localhost:${PORT}`;

const config = {
  instagram: {
    appId: process.env.INSTAGRAM_APP_ID,
    appSecret: process.env.INSTAGRAM_APP_SECRET,
    redirectUri: process.env.INSTAGRAM_REDIRECT_URI || `${BASE_URL}/auth/callback`,
    enabled: Boolean(process.env.INSTAGRAM_APP_ID && process.env.INSTAGRAM_APP_SECRET),
  },
  tiktok: {
    clientKey: process.env.TIKTOK_CLIENT_KEY,
    clientSecret: process.env.TIKTOK_CLIENT_SECRET,
    redirectUri: process.env.TIKTOK_REDIRECT_URI || `${BASE_URL}/auth/tiktok/callback`,
    enabled: Boolean(process.env.TIKTOK_CLIENT_KEY && process.env.TIKTOK_CLIENT_SECRET),
  },
  x: {
    clientId: process.env.X_CLIENT_ID,
    clientSecret: process.env.X_CLIENT_SECRET, // パブリッククライアントの場合は未設定でよい
    redirectUri: process.env.X_REDIRECT_URI || `${BASE_URL}/auth/x/callback`,
    enabled: Boolean(process.env.X_CLIENT_ID),
  },
};

for (const [name, c] of Object.entries(config)) {
  if (!c.enabled) console.warn(`[warn] ${name} の認証情報が未設定のため、${name} 連携は無効です(.env を参照)`);
}
if (!Object.values(config).some((c) => c.enabled)) {
  console.error("いずれのサービスの認証情報も設定されていません。.env.example を .env にコピーして値を設定してください。");
  process.exit(1);
}

// デモ用のインメモリセッション(本番ではDBや暗号化Cookieに置き換えること)
// sessionId -> { instagram?: {accessToken, expiresAt}, tiktok?: {...}, x?: {...} }
const sessions = new Map();
// CSRF対策のstate -> { provider, codeVerifier?, sessionId }
const pendingStates = new Map();

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  try {
    switch (url.pathname) {
      case "/": return home(req, res);
      // Instagram
      case "/auth/instagram": return startInstagramAuth(req, res);
      case "/auth/callback": // Meta側に登録済みのURIを維持
      case "/auth/instagram/callback": return instagramCallback(req, res, url);
      case "/api/instagram/profile": return withToken(req, res, "instagram", (t) => instagram.getProfile({ accessToken: t }));
      case "/api/instagram/media": return withToken(req, res, "instagram", (t) =>
        instagram.getMedia({ accessToken: t, limit: Number(url.searchParams.get("limit") || 12), after: url.searchParams.get("after") || undefined }));
      case "/auth/instagram/refresh": return refreshInstagram(req, res);
      // TikTok
      case "/auth/tiktok": return startTikTokAuth(req, res);
      case "/auth/tiktok/callback": return tiktokCallback(req, res, url);
      case "/api/tiktok/profile": return withToken(req, res, "tiktok", (t) => tiktok.getProfile({ accessToken: t }));
      case "/api/tiktok/videos": return withToken(req, res, "tiktok", (t) =>
        tiktok.getVideos({ accessToken: t, maxCount: Number(url.searchParams.get("limit") || 12), cursor: url.searchParams.get("cursor") || undefined }));
      // X
      case "/auth/x": return startXAuth(req, res);
      case "/auth/x/callback": return xCallback(req, res, url);
      case "/api/x/profile": return withToken(req, res, "x", (t) => x.getProfile({ accessToken: t }));
      case "/api/x/tweets": return apiXTweets(req, res, url);
      // 共通
      case "/logout": return logout(req, res, url);
      default:
        res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
        res.end("Not Found");
    }
  } catch (err) {
    console.error(err);
    res.writeHead(500, { "Content-Type": "application/json; charset=utf-8" });
    res.end(JSON.stringify({ error: err.message }));
  }
});

server.listen(PORT, () => {
  console.log(`SNS連携アプリを起動しました: ${BASE_URL}`);
  for (const [name, c] of Object.entries(config)) {
    if (c.enabled) console.log(`  ${name}: 有効 (redirect: ${c.redirectUri})`);
  }
});

// ---- 認証開始 ----

function startInstagramAuth(req, res) {
  if (!config.instagram.enabled) return notConfigured(res, "Instagram");
  const state = createState(req, "instagram");
  redirect(res, instagram.buildAuthorizeUrl({
    appId: config.instagram.appId,
    redirectUri: config.instagram.redirectUri,
    state,
  }));
}

function startTikTokAuth(req, res) {
  if (!config.tiktok.enabled) return notConfigured(res, "TikTok");
  const state = createState(req, "tiktok");
  redirect(res, tiktok.buildAuthorizeUrl({
    clientKey: config.tiktok.clientKey,
    redirectUri: config.tiktok.redirectUri,
    state,
  }));
}

function startXAuth(req, res) {
  if (!config.x.enabled) return notConfigured(res, "X");
  const { verifier, challenge } = x.generatePkcePair();
  const state = createState(req, "x", { codeVerifier: verifier });
  redirect(res, x.buildAuthorizeUrl({
    clientId: config.x.clientId,
    redirectUri: config.x.redirectUri,
    state,
    codeChallenge: challenge,
  }));
}

// ---- 認証コールバック ----

async function instagramCallback(req, res, url) {
  const ctx = validateCallback(res, url, "instagram");
  if (!ctx) return;
  const shortLived = await instagram.exchangeCodeForToken({
    appId: config.instagram.appId,
    appSecret: config.instagram.appSecret,
    redirectUri: config.instagram.redirectUri,
    code: ctx.code,
  });
  const longLived = await instagram.exchangeForLongLivedToken({
    appSecret: config.instagram.appSecret,
    accessToken: shortLived.access_token,
  });
  finishLogin(req, res, ctx, "instagram", {
    accessToken: longLived.access_token,
    expiresAt: Date.now() + longLived.expires_in * 1000,
  });
}

async function tiktokCallback(req, res, url) {
  const ctx = validateCallback(res, url, "tiktok");
  if (!ctx) return;
  const token = await tiktok.exchangeCodeForToken({
    clientKey: config.tiktok.clientKey,
    clientSecret: config.tiktok.clientSecret,
    redirectUri: config.tiktok.redirectUri,
    code: ctx.code,
  });
  finishLogin(req, res, ctx, "tiktok", {
    accessToken: token.access_token,
    refreshToken: token.refresh_token,
    expiresAt: Date.now() + token.expires_in * 1000,
  });
}

async function xCallback(req, res, url) {
  const ctx = validateCallback(res, url, "x");
  if (!ctx) return;
  const token = await x.exchangeCodeForToken({
    clientId: config.x.clientId,
    clientSecret: config.x.clientSecret,
    redirectUri: config.x.redirectUri,
    code: ctx.code,
    codeVerifier: ctx.codeVerifier,
  });
  finishLogin(req, res, ctx, "x", {
    accessToken: token.access_token,
    refreshToken: token.refresh_token,
    expiresAt: Date.now() + token.expires_in * 1000,
  });
}

// ---- トークン更新 ----

async function refreshInstagram(req, res) {
  const conn = getConnection(req, "instagram");
  if (!conn) return unauthorized(res, "instagram");
  const refreshed = await instagram.refreshLongLivedToken({ accessToken: conn.accessToken });
  conn.accessToken = refreshed.access_token;
  conn.expiresAt = Date.now() + refreshed.expires_in * 1000;
  sendJson(res, { ok: true, expires_in: refreshed.expires_in });
}

// ---- API ----

async function apiXTweets(req, res, url) {
  const token = await getFreshToken(req, "x");
  if (!token) return unauthorized(res, "x");
  const profile = await x.getProfile({ accessToken: token });
  const tweets = await x.getTweets({
    accessToken: token,
    userId: profile.id,
    maxResults: Number(url.searchParams.get("limit") || 10),
    paginationToken: url.searchParams.get("pagination_token") || undefined,
  });
  sendJson(res, tweets);
}

function logout(req, res, url) {
  const provider = url.searchParams.get("provider");
  const sessionId = parseCookies(req).sid;
  const session = sessionId && sessions.get(sessionId);
  if (session && provider && provider !== "all") {
    delete session[provider];
    return redirect(res, "/");
  }
  if (sessionId) sessions.delete(sessionId);
  res.writeHead(302, { "Set-Cookie": "sid=; HttpOnly; Path=/; Max-Age=0", Location: "/" });
  res.end();
}

// ---- 共通ヘルパー ----

function home(req, res) {
  const session = getOrCreateSession(req, res);
  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    ...(session.setCookie ? { "Set-Cookie": session.setCookie } : {}),
  });
  res.end(renderPage(session.data));
}

function createState(req, provider, extra = {}) {
  const state = crypto.randomBytes(16).toString("hex");
  pendingStates.set(state, { provider, sessionId: parseCookies(req).sid, ...extra });
  setTimeout(() => pendingStates.delete(state), 10 * 60 * 1000).unref();
  return state;
}

/** コールバックの共通検証(エラー・state・code)。失敗時はレスポンス済みでnullを返す */
function validateCallback(res, url, provider) {
  const error = url.searchParams.get("error");
  if (error) {
    res.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
    res.end(`認証がキャンセルまたは失敗しました: ${url.searchParams.get("error_description") || error}`);
    return null;
  }
  const state = url.searchParams.get("state");
  const pending = state && pendingStates.get(state);
  if (!pending || pending.provider !== provider) {
    res.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("不正なリクエストです(stateが一致しません)。もう一度ログインしてください。");
    return null;
  }
  pendingStates.delete(state);
  return { ...pending, code: url.searchParams.get("code") };
}

/** トークンをセッションに保存してトップへ戻す */
function finishLogin(req, res, ctx, provider, connection) {
  let sessionId = ctx.sessionId || parseCookies(req).sid;
  if (!sessionId || !sessions.has(sessionId)) {
    sessionId = crypto.randomBytes(32).toString("hex");
    sessions.set(sessionId, {});
  }
  sessions.get(sessionId)[provider] = connection;
  res.writeHead(302, {
    "Set-Cookie": `sid=${sessionId}; HttpOnly; Path=/; SameSite=Lax`,
    Location: "/",
  });
  res.end();
}

function getOrCreateSession(req) {
  const sessionId = parseCookies(req).sid;
  if (sessionId && sessions.has(sessionId)) {
    return { data: sessions.get(sessionId) };
  }
  const newId = crypto.randomBytes(32).toString("hex");
  sessions.set(newId, {});
  return { data: sessions.get(newId), setCookie: `sid=${newId}; HttpOnly; Path=/; SameSite=Lax` };
}

function getConnection(req, provider) {
  const sessionId = parseCookies(req).sid;
  const session = sessionId && sessions.get(sessionId);
  const conn = session?.[provider];
  if (!conn) return null;
  return conn;
}

/** 有効なアクセストークンを返す。期限切れならリフレッシュを試みる */
async function getFreshToken(req, provider) {
  const conn = getConnection(req, provider);
  if (!conn) return null;
  if (conn.expiresAt > Date.now() + 60 * 1000) return conn.accessToken;
  if (!conn.refreshToken) return null;
  try {
    let refreshed;
    if (provider === "tiktok") {
      refreshed = await tiktok.refreshToken({
        clientKey: config.tiktok.clientKey,
        clientSecret: config.tiktok.clientSecret,
        refreshToken: conn.refreshToken,
      });
    } else if (provider === "x") {
      refreshed = await x.refreshToken({
        clientId: config.x.clientId,
        clientSecret: config.x.clientSecret,
        refreshToken: conn.refreshToken,
      });
    } else {
      return null;
    }
    conn.accessToken = refreshed.access_token;
    if (refreshed.refresh_token) conn.refreshToken = refreshed.refresh_token;
    conn.expiresAt = Date.now() + refreshed.expires_in * 1000;
    return conn.accessToken;
  } catch (err) {
    console.error(`[${provider}] トークン更新に失敗:`, err.message);
    return null;
  }
}

/** 認証チェックつきAPIハンドラ */
async function withToken(req, res, provider, fn) {
  const token = await getFreshToken(req, provider);
  if (!token) return unauthorized(res, provider);
  sendJson(res, await fn(token));
}

function parseCookies(req) {
  const cookies = {};
  for (const part of (req.headers.cookie || "").split(";")) {
    const idx = part.indexOf("=");
    if (idx > 0) cookies[part.slice(0, idx).trim()] = part.slice(idx + 1).trim();
  }
  return cookies;
}

function sendJson(res, data) {
  res.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(data));
}

function redirect(res, location) {
  res.writeHead(302, { Location: location });
  res.end();
}

function unauthorized(res, provider) {
  res.writeHead(401, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify({ error: `${provider} は未接続です。トップページから連携してください。` }));
}

function notConfigured(res, name) {
  res.writeHead(503, { "Content-Type": "text/plain; charset=utf-8" });
  res.end(`${name} の認証情報が設定されていません。.env を確認してください。`);
}

function loadDotEnv() {
  if (!existsSync(".env")) return;
  for (const line of readFileSync(".env", "utf-8").split("\n")) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (match && !(match[1] in process.env)) {
      process.env[match[1]] = match[2].replace(/^["']|["']$/g, "");
    }
  }
}

// ---- 画面 ----

function renderPage(session) {
  const providers = [
    { key: "instagram", name: "Instagram", color: "linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888)" },
    { key: "tiktok", name: "TikTok", color: "linear-gradient(45deg, #010101, #69C9D0, #EE1D52)" },
    { key: "x", name: "X", color: "#000" },
  ];
  const status = JSON.stringify(Object.fromEntries(
    providers.map((p) => [p.key, { connected: Boolean(session[p.key]), enabled: config[p.key].enabled }])
  ));

  const cards = providers.map((p) => {
    const connected = Boolean(session[p.key]);
    const enabled = config[p.key].enabled;
    return `
    <section class="panel" id="panel-${p.key}">
      <div class="panel-head">
        <h2>${p.name}</h2>
        ${connected
          ? `<div><button class="btn small" style="background:${p.color}" data-refresh="${p.key}">更新</button>
             <a class="btn small gray" href="/logout?provider=${p.key}">解除</a></div>`
          : enabled
            ? `<a class="btn" style="background:${p.color}" href="/auth/${p.key}">${p.name}と連携</a>`
            : `<span class="muted">未設定(.envに認証情報を追加してください)</span>`}
      </div>
      <div class="panel-body" data-body="${p.key}">
        ${connected ? '<p class="muted">読み込み中...</p>' : ""}
      </div>
    </section>`;
  }).join("");

  return `<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SNS連携</title>
  <style>
    :root { color-scheme: light dark; }
    body { font-family: -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif; max-width: 1080px; margin: 0 auto; padding: 24px; }
    .btn { display: inline-block; padding: 10px 20px; border-radius: 8px; text-decoration: none; color: #fff; font-weight: 600; border: none; cursor: pointer; }
    .btn.small { padding: 6px 14px; font-size: 13px; }
    .btn.gray { background: #666; }
    .panel { border: 1px solid rgba(128,128,128,.3); border-radius: 14px; padding: 20px; margin: 20px 0; }
    .panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
    .panel-head h2 { margin: 0; }
    .profile { display: flex; align-items: center; gap: 16px; margin: 16px 0; }
    .profile img { width: 64px; height: 64px; border-radius: 50%; object-fit: cover; }
    .stats { display: flex; gap: 20px; color: gray; font-size: 14px; flex-wrap: wrap; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 14px; margin-top: 14px; }
    .card { border: 1px solid rgba(128,128,128,.3); border-radius: 12px; overflow: hidden; text-decoration: none; color: inherit; display: block; }
    .card img { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; }
    .card .meta { padding: 8px 10px; font-size: 13px; }
    .card .caption { overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
    .tweet { border: 1px solid rgba(128,128,128,.3); border-radius: 12px; padding: 12px 14px; margin-top: 10px; }
    .muted { color: gray; }
    .error { color: #c0392b; }
  </style>
</head>
<body>
  <h1>SNS連携</h1>
  <p class="muted">Instagram・TikTok・X のアカウントを連携して、プロフィールと投稿を表示します。</p>
  ${cards}
  <script>
    const status = ${status};
    const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const jp = (d) => new Date(d).toLocaleDateString("ja-JP");

    async function getJson(url) {
      const r = await fetch(url);
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || r.status);
      return data;
    }

    function profileHtml({ img, title, link, stats }) {
      return '<div class="profile">' +
        (img ? '<img src="' + esc(img) + '" alt="">' : "") +
        '<div><strong>' + (link ? '<a href="' + esc(link) + '" target="_blank" rel="noopener">' + esc(title) + '</a>' : esc(title)) + '</strong>' +
        '<div class="stats">' + stats.map((s) => "<span>" + esc(s) + "</span>").join("") + '</div></div></div>';
    }

    async function loadInstagram(body) {
      const [p, m] = await Promise.all([getJson("/api/instagram/profile"), getJson("/api/instagram/media")]);
      body.innerHTML = profileHtml({
        img: p.profile_picture_url, title: "@" + (p.username || ""),
        stats: ["投稿 " + (p.media_count ?? "-"), "フォロワー " + (p.followers_count ?? "-"), "フォロー中 " + (p.follows_count ?? "-")],
      }) + '<div class="grid">' + (m.data || []).map((item) => {
        const src = item.media_type === "VIDEO" ? (item.thumbnail_url || item.media_url) : item.media_url;
        return '<a class="card" href="' + esc(item.permalink) + '" target="_blank" rel="noopener">' +
          '<img src="' + esc(src) + '" alt="">' +
          '<div class="meta"><div class="caption">' + esc(item.caption || "") + '</div>' +
          '<div class="muted">' + jp(item.timestamp) + (item.like_count != null ? " ・ ♥ " + item.like_count : "") + '</div></div></a>';
      }).join("") + '</div>' + ((m.data || []).length ? "" : '<p class="muted">投稿がありません。</p>');
    }

    async function loadTiktok(body) {
      const [p, v] = await Promise.all([getJson("/api/tiktok/profile"), getJson("/api/tiktok/videos")]);
      body.innerHTML = profileHtml({
        img: p.avatar_url, title: p.display_name || "", link: p.profile_deep_link,
        stats: ["動画 " + (p.video_count ?? "-"), "フォロワー " + (p.follower_count ?? "-"), "いいね " + (p.likes_count ?? "-")],
      }) + '<div class="grid">' + (v.videos || []).map((item) =>
        '<a class="card" href="' + esc(item.share_url) + '" target="_blank" rel="noopener">' +
        '<img src="' + esc(item.cover_image_url) + '" alt="">' +
        '<div class="meta"><div class="caption">' + esc(item.title || item.video_description || "") + '</div>' +
        '<div class="muted">再生 ' + (item.view_count ?? "-") + ' ・ ♥ ' + (item.like_count ?? "-") + '</div></div></a>'
      ).join("") + '</div>' + ((v.videos || []).length ? "" : '<p class="muted">動画がありません。</p>');
    }

    async function loadX(body) {
      const [p, t] = await Promise.all([getJson("/api/x/profile"), getJson("/api/x/tweets")]);
      const pm = p.public_metrics || {};
      body.innerHTML = profileHtml({
        img: p.profile_image_url, title: (p.name || "") + " (@" + (p.username || "") + ")",
        link: "https://x.com/" + p.username,
        stats: ["ポスト " + (pm.tweet_count ?? "-"), "フォロワー " + (pm.followers_count ?? "-"), "フォロー中 " + (pm.following_count ?? "-")],
      }) + (t.data || []).map((tw) => {
        const m = tw.public_metrics || {};
        return '<div class="tweet"><div>' + esc(tw.text) + '</div>' +
          '<div class="muted" style="margin-top:6px">' + jp(tw.created_at) +
          ' ・ ♥ ' + (m.like_count ?? 0) + ' ・ RT ' + (m.retweet_count ?? 0) + '</div></div>';
      }).join("") + ((t.data || []).length ? "" : '<p class="muted">ポストがありません。</p>');
    }

    const loaders = { instagram: loadInstagram, tiktok: loadTiktok, x: loadX };
    for (const [key, s] of Object.entries(status)) {
      if (!s.connected) continue;
      const body = document.querySelector('[data-body="' + key + '"]');
      loaders[key](body).catch((err) => {
        body.innerHTML = '<p class="error">読み込みに失敗しました: ' + esc(err.message) + '</p>';
      });
    }

    document.querySelectorAll("[data-refresh]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const key = btn.dataset.refresh;
        if (key === "instagram") {
          const r = await fetch("/auth/instagram/refresh", { method: "POST" });
          alert(r.ok ? "トークンを更新しました" : "更新に失敗しました");
        }
        const body = document.querySelector('[data-body="' + key + '"]');
        body.innerHTML = '<p class="muted">読み込み中...</p>';
        loaders[key](body).catch((err) => {
          body.innerHTML = '<p class="error">読み込みに失敗しました: ' + esc(err.message) + '</p>';
        });
      });
    });
  </script>
</body>
</html>`;
}

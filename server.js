// Instagram連携アプリ - エントリポイント
// 依存ライブラリなし(Node.js 18+ の標準機能のみ)で動作する。
//
// 起動: npm start  (または node server.js)
// 事前に .env.example を .env にコピーして値を設定すること。

import http from "node:http";
import crypto from "node:crypto";
import { readFileSync, existsSync } from "node:fs";
import {
  buildAuthorizeUrl,
  exchangeCodeForToken,
  exchangeForLongLivedToken,
  refreshLongLivedToken,
  getProfile,
  getMedia,
} from "./lib/instagram.js";

loadDotEnv();

const APP_ID = process.env.INSTAGRAM_APP_ID;
const APP_SECRET = process.env.INSTAGRAM_APP_SECRET;
const REDIRECT_URI = process.env.INSTAGRAM_REDIRECT_URI || "https://localhost:8443/auth/callback";
const PORT = Number(process.env.PORT || 3000);

if (!APP_ID || !APP_SECRET) {
  console.error("環境変数 INSTAGRAM_APP_ID / INSTAGRAM_APP_SECRET が未設定です。");
  console.error(".env.example を .env にコピーして値を設定してください。");
  process.exit(1);
}

// デモ用のインメモリセッション(本番ではDBや暗号化Cookieに置き換えること)
const sessions = new Map(); // sessionId -> { accessToken, expiresAt }
const pendingStates = new Set(); // CSRF対策用のstate

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  try {
    if (url.pathname === "/") return home(req, res);
    if (url.pathname === "/auth/instagram") return startAuth(req, res);
    if (url.pathname === "/auth/callback") return authCallback(req, res, url);
    if (url.pathname === "/auth/refresh") return refreshToken(req, res);
    if (url.pathname === "/api/profile") return apiProfile(req, res);
    if (url.pathname === "/api/media") return apiMedia(req, res, url);
    if (url.pathname === "/logout") return logout(req, res);
    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Not Found");
  } catch (err) {
    console.error(err);
    res.writeHead(500, { "Content-Type": "text/plain; charset=utf-8" });
    res.end(`エラーが発生しました: ${err.message}`);
  }
});

server.listen(PORT, () => {
  console.log(`Instagram連携アプリを起動しました: http://localhost:${PORT}`);
  console.log(`リダイレクトURI: ${REDIRECT_URI}`);
});

// ---- ルートハンドラ ----

function home(req, res) {
  const session = getSession(req);
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(renderPage(session));
}

function startAuth(req, res) {
  const state = crypto.randomBytes(16).toString("hex");
  pendingStates.add(state);
  // stateは10分で失効させる
  setTimeout(() => pendingStates.delete(state), 10 * 60 * 1000).unref();
  const authUrl = buildAuthorizeUrl({ appId: APP_ID, redirectUri: REDIRECT_URI, state });
  res.writeHead(302, { Location: authUrl });
  res.end();
}

async function authCallback(req, res, url) {
  const error = url.searchParams.get("error");
  if (error) {
    res.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
    res.end(`認証がキャンセルまたは失敗しました: ${url.searchParams.get("error_description") || error}`);
    return;
  }

  const state = url.searchParams.get("state");
  if (!state || !pendingStates.has(state)) {
    res.writeHead(400, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("不正なリクエストです(stateが一致しません)。もう一度ログインしてください。");
    return;
  }
  pendingStates.delete(state);

  const code = url.searchParams.get("code");
  const shortLived = await exchangeCodeForToken({
    appId: APP_ID,
    appSecret: APP_SECRET,
    redirectUri: REDIRECT_URI,
    code,
  });
  const longLived = await exchangeForLongLivedToken({
    appSecret: APP_SECRET,
    accessToken: shortLived.access_token,
  });

  const sessionId = crypto.randomBytes(32).toString("hex");
  sessions.set(sessionId, {
    accessToken: longLived.access_token,
    expiresAt: Date.now() + longLived.expires_in * 1000,
  });

  res.writeHead(302, {
    "Set-Cookie": `sid=${sessionId}; HttpOnly; Path=/; SameSite=Lax`,
    Location: "/",
  });
  res.end();
}

async function refreshToken(req, res) {
  const session = getSession(req);
  if (!session) return unauthorized(res);
  const refreshed = await refreshLongLivedToken({ accessToken: session.accessToken });
  session.accessToken = refreshed.access_token;
  session.expiresAt = Date.now() + refreshed.expires_in * 1000;
  sendJson(res, { ok: true, expires_in: refreshed.expires_in });
}

async function apiProfile(req, res) {
  const session = getSession(req);
  if (!session) return unauthorized(res);
  sendJson(res, await getProfile({ accessToken: session.accessToken }));
}

async function apiMedia(req, res, url) {
  const session = getSession(req);
  if (!session) return unauthorized(res);
  const media = await getMedia({
    accessToken: session.accessToken,
    limit: Number(url.searchParams.get("limit") || 12),
    after: url.searchParams.get("after") || undefined,
  });
  sendJson(res, media);
}

function logout(req, res) {
  const sessionId = parseCookies(req).sid;
  if (sessionId) sessions.delete(sessionId);
  res.writeHead(302, {
    "Set-Cookie": "sid=; HttpOnly; Path=/; Max-Age=0",
    Location: "/",
  });
  res.end();
}

// ---- ヘルパー ----

function getSession(req) {
  const sessionId = parseCookies(req).sid;
  if (!sessionId) return null;
  const session = sessions.get(sessionId);
  if (!session) return null;
  if (session.expiresAt <= Date.now()) {
    sessions.delete(sessionId);
    return null;
  }
  return session;
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

function unauthorized(res) {
  res.writeHead(401, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify({ error: "未ログインです。/auth/instagram からログインしてください。" }));
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

function renderPage(session) {
  const loggedIn = Boolean(session);
  return `<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Instagram連携</title>
  <style>
    :root { color-scheme: light dark; }
    body { font-family: -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif; max-width: 960px; margin: 0 auto; padding: 24px; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
    .btn { display: inline-block; padding: 10px 20px; border-radius: 8px; text-decoration: none; color: #fff;
           background: linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888); font-weight: 600; border: none; cursor: pointer; }
    .profile { display: flex; align-items: center; gap: 16px; margin: 24px 0; }
    .profile img { width: 72px; height: 72px; border-radius: 50%; object-fit: cover; }
    .stats { display: flex; gap: 24px; color: gray; font-size: 14px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; margin-top: 24px; }
    .card { border: 1px solid rgba(128,128,128,.3); border-radius: 12px; overflow: hidden; }
    .card img, .card video { width: 100%; aspect-ratio: 1; object-fit: cover; display: block; }
    .card .meta { padding: 10px 12px; font-size: 13px; }
    .card .caption { overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
    .muted { color: gray; }
  </style>
</head>
<body>
  <header>
    <h1>Instagram連携</h1>
    ${loggedIn
      ? `<div><button class="btn" id="refresh">トークン更新</button> <a class="btn" href="/logout" style="background:#666">ログアウト</a></div>`
      : `<a class="btn" href="/auth/instagram">Instagramでログイン</a>`}
  </header>
  ${loggedIn ? `
  <div class="profile" id="profile"><p class="muted">プロフィールを読み込み中...</p></div>
  <h2>投稿</h2>
  <div class="grid" id="media"><p class="muted">投稿を読み込み中...</p></div>
  <script>
    async function load() {
      const [profile, media] = await Promise.all([
        fetch("/api/profile").then(r => r.json()),
        fetch("/api/media").then(r => r.json()),
      ]);
      document.getElementById("profile").innerHTML =
        (profile.profile_picture_url ? '<img src="' + profile.profile_picture_url + '" alt="">' : "") +
        '<div><strong>@' + escapeHtml(profile.username || "") + '</strong>' +
        '<div class="stats"><span>投稿 ' + (profile.media_count ?? "-") + '</span>' +
        '<span>フォロワー ' + (profile.followers_count ?? "-") + '</span>' +
        '<span>フォロー中 ' + (profile.follows_count ?? "-") + '</span></div></div>';
      const grid = document.getElementById("media");
      grid.innerHTML = "";
      for (const item of media.data || []) {
        const src = item.media_type === "VIDEO" ? (item.thumbnail_url || item.media_url) : item.media_url;
        const card = document.createElement("a");
        card.className = "card";
        card.href = item.permalink;
        card.target = "_blank";
        card.rel = "noopener";
        card.style.textDecoration = "none";
        card.style.color = "inherit";
        card.innerHTML = '<img src="' + src + '" alt="">' +
          '<div class="meta"><div class="caption">' + escapeHtml(item.caption || "") + '</div>' +
          '<div class="muted">' + new Date(item.timestamp).toLocaleDateString("ja-JP") +
          (item.like_count != null ? ' ・ ♥ ' + item.like_count : "") + '</div></div>';
        grid.appendChild(card);
      }
      if (!(media.data || []).length) grid.innerHTML = '<p class="muted">投稿がありません。</p>';
    }
    function escapeHtml(s) {
      return s.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }
    document.getElementById("refresh").addEventListener("click", async () => {
      const r = await fetch("/auth/refresh", { method: "POST" });
      alert(r.ok ? "トークンを更新しました" : "更新に失敗しました");
    });
    load().catch(err => alert("読み込みに失敗しました: " + err.message));
  </script>` : `
  <p>「Instagramでログイン」を押すと、Instagramの認証画面に移動します。<br>
  認証後、プロフィールと投稿一覧が表示されます。</p>
  <p class="muted">※ 利用にはInstagramのプロアカウント(ビジネス / クリエイター)と、Meta for Developersでのアプリ設定が必要です。詳しくはREADME.mdを参照してください。</p>`}
</body>
</html>`;
}

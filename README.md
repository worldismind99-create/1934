# SNS連携アプリ(Instagram / TikTok / X)

Instagram・TikTok・X(旧Twitter)の公式APIと連携するWebアプリです。
各サービスのアカウントでログインすると、プロフィールと投稿一覧を取得・表示できます。

依存ライブラリなし(Node.js 18以上の標準機能のみ)で動作します。
3サービスすべての設定は必須ではなく、`.env` に認証情報を設定したサービスだけ連携が有効になります。

## 機能

| | Instagram | TikTok | X |
|---|---|---|---|
| 認証方式 | Instagramログイン(OAuth 2.0) | Login Kit(OAuth 2.0) | OAuth 2.0 + PKCE |
| プロフィール取得 | ✅ | ✅ | ✅ |
| 投稿一覧 | ✅ 写真・動画 | ✅ 動画 | ✅ ポスト(ツイート) |
| トークン更新 | ✅ 長期トークン(約60日) | ✅ 自動リフレッシュ | ✅ 自動リフレッシュ |

共通してCSRF対策のstate検証を実装しています。1つのブラウザセッションで3サービスを同時に接続できます。

## セットアップ

```bash
cp .env.example .env
# .env に各サービスの認証情報を記入
npm start
```

ブラウザで `http://localhost:3000` を開くと、サービスごとの連携ボタンが表示されます。

> **HTTPSについて:** InstagramとTikTokのリダイレクトURIはHTTPSが必須です。
> ローカル開発では [ngrok](https://ngrok.com/) などを使い(`ngrok http 3000`)、
> 表示されたHTTPSのURLを `.env` の `BASE_URL` と各リダイレクトURIに設定し、
> 同じURIを各開発者ポータルにも登録してください。

### Instagram(Meta for Developers)

> 旧 Instagram Basic Display API は2024年12月に廃止されたため、現行の
> 「Instagram API with Instagram Login」を使用します。
> **Instagramのプロアカウント(ビジネスまたはクリエイター)** が必要です。
> 個人アカウントはInstagramアプリの設定から無料でプロアカウントに切り替えられます。

1. [Meta for Developers](https://developers.facebook.com/) で「アプリを作成」→ ユースケースは **Instagram** を選択
2. **Instagram > API setup with Instagram business login** を開き、**OAuth redirect URIs** に `https://あなたのドメイン/auth/callback` を登録
3. 同画面の **InstagramアプリID / アプリシークレット** を `.env` の `INSTAGRAM_APP_ID` / `INSTAGRAM_APP_SECRET` に設定
4. 開発モード中は **Roles > Instagram Testers** に自分のアカウントを追加し、Instagram側(設定 > アプリとウェブサイト > テスター招待)で承認

### TikTok(TikTok for Developers)

1. [TikTok for Developers](https://developers.tiktok.com/) でアプリを作成
2. プロダクトとして **Login Kit** を追加し、Redirect URI に `https://あなたのドメイン/auth/tiktok/callback` を登録
3. スコープ `user.info.basic` / `user.info.profile` / `user.info.stats` / `video.list` を申請(Sandboxモードならターゲットユーザーを追加して即テスト可能)
4. **Client Key / Client Secret** を `.env` の `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` に設定

### X(X Developer Portal)

1. [X Developer Portal](https://developer.x.com/) でプロジェクトとアプリを作成(Freeプランで可)
2. アプリの **User authentication settings** で OAuth 2.0 を有効化
   - Type of App: **Web App**(Confidential client)または **Public client**
   - Callback URI: `https://あなたのドメイン/auth/x/callback`(Xはhttp://localhostも登録可)
3. **Client ID** を `.env` の `X_CLIENT_ID` に設定。Confidential client の場合は **Client Secret** も `X_CLIENT_SECRET` に設定
4. 要求スコープは `tweet.read` / `users.read` / `offline.access`

> **注意:** X APIのFreeプランは読み取りレート制限が厳しいため(ユーザーのポスト取得は月間・15分あたりの上限あり)、表示に失敗する場合は時間をおいて再試行してください。

## APIエンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/` | トップページ(各サービスの連携・フィード表示) |
| GET | `/auth/instagram` `/auth/tiktok` `/auth/x` | 各サービスの認証画面へリダイレクト |
| GET | `/auth/callback` | Instagram OAuthコールバック |
| GET | `/auth/tiktok/callback` `/auth/x/callback` | TikTok / X OAuthコールバック |
| POST | `/auth/instagram/refresh` | Instagram長期トークンの更新 |
| GET | `/api/instagram/profile` `/api/instagram/media` | Instagramプロフィール / 投稿(JSON) |
| GET | `/api/tiktok/profile` `/api/tiktok/videos` | TikTokプロフィール / 動画(JSON) |
| GET | `/api/x/profile` `/api/x/tweets` | Xプロフィール / ポスト(JSON) |
| GET | `/logout?provider=instagram\|tiktok\|x\|all` | 連携解除(providerを省略すると全解除) |

TikTokとXのアクセストークンは期限切れが近いとAPI呼び出し時に自動でリフレッシュされます。

## 構成

```
├── server.js          # HTTPサーバー・ルーティング・セッション管理
├── lib/
│   ├── instagram.js   # Instagram APIクライアント
│   ├── tiktok.js      # TikTok APIクライアント(Login Kit / Display API)
│   └── x.js           # X API v2クライアント(OAuth 2.0 + PKCE)
├── .env.example       # 環境変数のテンプレート
└── package.json
```

## 権限(スコープ)の拡張

現在は閲覧系のスコープのみ要求しています。投稿の作成などを行う場合は各クライアントのスコープを追加してください:

- Instagram(`lib/instagram.js`): `instagram_business_content_publish`(投稿作成)、`instagram_business_manage_comments`(コメント管理)など
- TikTok(`lib/tiktok.js`): `video.publish`(動画投稿)、`video.upload` など
- X(`lib/x.js`): `tweet.write`(ポスト作成)、`like.write` など

※ 一般公開するには、各プラットフォームのアプリ審査(Metaアプリレビュー / TikTokアプリ審査)が必要です。

## 本番運用時の注意

- セッションとトークンはデモ用にメモリ上に保持しています。本番ではDBや暗号化Cookieに置き換えてください
- クライアントシークレット・アクセストークンは絶対にリポジトリやフロントエンドに含めないでください
- Instagramの長期トークンは約60日で失効します。失効前に `POST /auth/instagram/refresh` で更新してください

---

## 同梱の別アプリ: 通勤調整判定ツール

このリポジトリには、SNS連携アプリとは独立した静的アプリ
[`commute-adjustment/`](commute-adjustment/) も入っています。
出張の旅費における通勤調整（支給区間と文言）を判定するPWAで、Node.jsサーバーは不要です。
詳細は [`commute-adjustment/README.md`](commute-adjustment/README.md) を参照してください。

# Instagram連携アプリ

Instagram公式API(**Instagram API with Instagram Login**)と連携するWebアプリです。
Instagramアカウントでログインすると、プロフィールと投稿一覧を取得・表示できます。

依存ライブラリなし(Node.js 18以上の標準機能のみ)で動作します。

> **注意:** 旧 Instagram Basic Display API は2024年12月に廃止されました。
> 本アプリは現行のInstagramログイン方式を使用しており、
> **Instagramのプロアカウント(ビジネスまたはクリエイター)** が必要です。
> 個人アカウントの場合は、Instagramアプリの設定から無料でプロアカウントに切り替えられます。

## 機能

- Instagram OAuth認証(CSRF対策のstate検証つき)
- 短期トークン → 長期トークン(約60日有効)への自動交換
- 長期トークンの更新(`POST /auth/refresh`)
- プロフィール取得(ユーザー名・フォロワー数・投稿数など)
- 投稿(メディア)一覧の取得と表示(画像・動画・カルーセル対応)

## セットアップ

### 1. Metaアプリを作成する

1. [Meta for Developers](https://developers.facebook.com/) にログインし、「アプリを作成」を選択
2. ユースケースは **「Instagram」** を選択(その他 → ビジネスでも可)
3. アプリダッシュボードの **Instagram > API setup with Instagram business login** を開く
4. 「Business login settings」の **OAuth redirect URIs** に、コールバックURLを登録する
   - 例: `https://あなたのドメイン/auth/callback`
   - **HTTPSが必須**です。ローカル開発では [ngrok](https://ngrok.com/) などでHTTPSのURLを用意してください
     (`ngrok http 3000` で表示されたURL + `/auth/callback` を登録)
5. 同じ画面に表示される **InstagramアプリID** と **Instagramアプリシークレット** を控える
6. 開発モード中にログインできるのはテスターのみです。**Roles > Instagram Testers** に
   自分のInstagramアカウントを追加し、Instagram側([設定 > アプリとウェブサイト > テスター招待](https://www.instagram.com/accounts/manage_access/))で招待を承認してください

### 2. 環境変数を設定する

```bash
cp .env.example .env
```

`.env` を開いて値を設定します:

| 変数 | 説明 |
|---|---|
| `INSTAGRAM_APP_ID` | InstagramアプリID |
| `INSTAGRAM_APP_SECRET` | Instagramアプリシークレット |
| `INSTAGRAM_REDIRECT_URI` | 手順1-4で登録したリダイレクトURI |
| `PORT` | サーバーのポート番号(既定: 3000) |

### 3. 起動する

```bash
npm start
```

ブラウザで `http://localhost:3000`(ngrok利用時はngrokのURL)を開き、
「Instagramでログイン」を押して認証すると、プロフィールと投稿が表示されます。

## APIエンドポイント

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/` | トップページ(ログイン / フィード表示) |
| GET | `/auth/instagram` | Instagram認証画面へリダイレクト |
| GET | `/auth/callback` | OAuthコールバック(トークン交換) |
| POST | `/auth/refresh` | 長期トークンの更新 |
| GET | `/api/profile` | プロフィール取得(JSON) |
| GET | `/api/media` | 投稿一覧取得(JSON、`limit` / `after` パラメータ対応) |
| GET | `/logout` | ログアウト |

## 構成

```
├── server.js          # HTTPサーバー・ルーティング・セッション管理
├── lib/
│   └── instagram.js   # Instagram APIクライアント(OAuth・プロフィール・メディア)
├── .env.example       # 環境変数のテンプレート
└── package.json
```

## 権限(スコープ)の拡張

現在は閲覧に必要な `instagram_business_basic` のみ要求しています。
投稿の作成やコメント・DM管理を行う場合は、`lib/instagram.js` の
`buildAuthorizeUrl` 内のスコープを有効化してください:

- `instagram_business_content_publish` — 投稿の作成
- `instagram_business_manage_comments` — コメントの管理
- `instagram_business_manage_messages` — DMの管理

※ 一般公開するには、追加スコープごとにMetaの[アプリレビュー](https://developers.facebook.com/docs/resp-plat-initiatives/app-review)が必要です。

## 本番運用時の注意

- セッションとトークンはデモ用にメモリ上に保持しています。本番ではDBや暗号化Cookieに置き換えてください
- アプリシークレット・アクセストークンは絶対にリポジトリやフロントエンドに含めないでください
- 長期トークンは約60日で失効します。失効前に `POST /auth/refresh` で更新してください

# Trip App

旅行スポットを共有・管理するためのWebアプリケーション。

## 機能

- ユーザー登録・ログイン
- スポットの追加・編集・削除
- スポットの写真管理
- ソーシャルメディア連携
- プロフィールページ

## セットアップ手順

### 1. リポジトリのクローン

```bash
git clone https://github.com/fujisawadev/trip.git
cd trip
```

### 2. 仮想環境のセットアップ

```bash
python -m venv venv
source venv/bin/activate  # Linuxの場合
# または
venv\Scripts\activate  # Windowsの場合
```

### 3. 依存関係のインストール

```bash
pip install -r requirements.txt
```

### 4. PostgreSQLのセットアップ

このアプリケーションはPostgreSQLデータベースを使用します。以下の手順でセットアップしてください。

#### PostgreSQLのインストール

- **macOS**:
  ```bash
  brew install postgresql
  brew services start postgresql
  ```

- **Ubuntu/Debian**:
  ```bash
  sudo apt update
  sudo apt install postgresql postgresql-contrib
  sudo systemctl start postgresql
  sudo systemctl enable postgresql
  ```

- **Windows**:
  [PostgreSQLのダウンロードページ](https://www.postgresql.org/download/windows/)からインストーラーをダウンロードしてインストールしてください。

#### データベースの作成

```bash
# PostgreSQLのコマンドラインツールにログイン
psql -U postgres

# データベースを作成（PostgreSQLプロンプト内で）
CREATE DATABASE trip_db;
CREATE USER your_username WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE trip_db TO your_username;
\q
```

### 5. 環境変数の設定

`.env.example`ファイルをコピーして`.env`ファイルを作成し、必要な環境変数を設定します。

```bash
cp .env.example .env
# .envファイルを編集して、必要な環境変数を設定してください
```

特に以下の環境変数を必ず設定してください：
- `DATABASE_URL`: PostgreSQLデータベースへの接続URL（例: `postgresql://username:password@localhost:5432/trip_db`）
- `GOOGLE_MAPS_API_KEY`: Google Maps APIキー
- `SECRET_KEY`: アプリケーションの秘密鍵

### 6. データベースのマイグレーション

```bash
flask db upgrade  # マイグレーションを実行してデータベースを作成
```

### 7. アプリケーションの実行

```bash
flask run
# または
python run.py
```

## 開発ガイドライン

- コミット前に`flask test`を実行してテストを確認してください
- 新しい機能を追加する場合は、対応するテストも追加してください
- 環境変数やデータベースファイルをコミットしないでください
- このアプリケーションはPostgreSQLのみをサポートしています。SQLiteは使用しないでください。

## デプロイ

### Herokuへのデプロイ

```bash
# Herokuにアプリケーションを作成
heroku create your-app-name

# PostgreSQLアドオンを追加
heroku addons:create heroku-postgresql:hobby-dev

# 環境変数を設定
heroku config:set SECRET_KEY=your_secret_key
heroku config:set GOOGLE_MAPS_API_KEY=your_google_maps_api_key

# デプロイ
git push heroku main
```

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。 
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

### 4. 環境変数の設定

`.env.example`ファイルをコピーして`.env`ファイルを作成し、必要な環境変数を設定します。

```bash
cp .env.example .env
# .envファイルを編集して、必要な環境変数（特にGOOGLE_MAPS_API_KEY）を設定してください
```

### 5. データベースのセットアップ

```bash
flask db upgrade  # マイグレーションを実行してデータベースを作成
python scripts/db/init_db.py  # 初期データを投入（オプション）
```

### 6. アプリケーションの実行

```bash
flask run
# または
python run.py
```

## 開発ガイドライン

- コミット前に`flask test`を実行してテストを確認してください
- 新しい機能を追加する場合は、対応するテストも追加してください
- 環境変数やデータベースファイルをコミットしないでください

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。 
#!/bin/bash

echo "🚀 非同期Instagramインポート機能のテストを開始します"

# 環境変数を設定
export FLASK_ENV=development

# 必要な環境変数をチェック
echo "📋 環境変数チェック:"
echo "  FLASK_ENV: $FLASK_ENV"
echo "  OPENAI_API_KEY: $(if [ -n "$OPENAI_API_KEY" ]; then echo "設定済み"; else echo "未設定"; fi)"
echo "  GOOGLE_MAPS_API_KEY: $(if [ -n "$GOOGLE_MAPS_API_KEY" ]; then echo "設定済み"; else echo "未設定"; fi)"

# Redisの状態チェック
echo ""
echo "🔍 Redisプロセス確認:"
if pgrep redis-server > /dev/null; then
    echo "  ✅ Redis is running"
else
    echo "  ❌ Redis is not running. Starting Redis..."
    redis-server --daemonize yes
    sleep 2
fi

echo ""
echo "🎯 テスト手順:"
echo "1. 別のターミナルでFlaskアプリを起動してください:"
echo "   FLASK_ENV=development python run.py"
echo ""
echo "2. さらに別のターミナルでRQワーカーを起動してください:"
echo "   FLASK_ENV=development python worker.py"
echo ""
echo "3. ブラウザで以下にアクセスしてください:"
echo "   https://localhost:8085/import"
echo ""
echo "4. 期間を選択して「インポートを開始」ボタンをクリック"
echo ""
echo "5. 期待される動作:"
echo "   - モックデータ読み込み"
echo "   - OpenAI分析実行"
echo "   - Google Places検索実行"
echo "   - 5件のスポット候補表示"
echo "   - 保存機能テスト"

echo ""
echo "📊 ログ確認:"
echo "RQワーカーのターミナルで以下のようなログが表示されるはずです:"
echo "  [INFO] --- [Job xxx] RUNNING IN DEV MODE: LOADING MOCK INSTAGRAM DATA ---"
echo "  [INFO] [Job xxx] Fetched a total of 3 posts."
echo "  [INFO] [Job xxx] Analysis complete. Found X candidates."
echo "  [INFO] [Job xxx] Successfully enriched 'スポット名' with Google Places data"
echo "  [INFO] [Job xxx] Found X potential spots."
echo ""
echo "準備完了！上記の手順でテストを開始してください 🎉" 
# 🔧 EC2設定変更チェックリスト

## 🎯 必須設定変更項目

### 1. ポート競合回避設定

#### Discord Bot (.env)
```bash
# 変更前（開発環境）
WEBHOOK_PORT=3002
PYTHON_API_URL=http://localhost:8000

# 変更後（EC2本番環境）
WEBHOOK_PORT=3003
PYTHON_API_URL=http://localhost:8001
```

#### Python API (.env)
```bash
# 変更前（開発環境）
API_PORT=8000
DISCORD_WEBHOOK_URL=http://localhost:3002/webhook/meeting-completed

# 変更後（EC2本番環境）
API_PORT=8001
DISCORD_WEBHOOK_URL=http://localhost:3003/webhook/meeting-completed
```

### 2. 本番環境用ディレクトリ設定

#### 共通設定
```bash
# 変更前（開発環境）
TEMP_DIR=./temp
OUTPUT_DIR=./output

# 変更後（EC2本番環境）
TEMP_DIR=/tmp/voice-meeting-bot/temp
OUTPUT_DIR=/tmp/voice-meeting-bot/output
```

### 3. ログレベル調整

#### Discord Bot
```bash
# 変更前（開発環境）
LOG_LEVEL=info

# 変更後（EC2本番環境）
LOG_LEVEL=warn
```

#### Python API
```bash
# 変更前（開発環境）
LOG_LEVEL=INFO
API_DEBUG=true

# 変更後（EC2本番環境）
LOG_LEVEL=WARNING
API_DEBUG=false
```

---

## 📋 設定ファイルテンプレート

### Discord Bot (.env)
```bash
# === 必須設定 ===
DISCORD_BOT_TOKEN=your_production_token
CLIENT_ID=your_production_client_id

# === ネットワーク設定 ===
PYTHON_API_URL=http://localhost:8001
WEBHOOK_PORT=3003
DEV_GUILD_ID=your_production_guild_id

# === ファイル管理 ===
TEMP_DIR=/tmp/voice-meeting-bot/temp
LOG_LEVEL=warn
AUTO_DELETE_AFTER_HOURS=24

# === セキュリティ ===
ADMIN_USER_IDS=123456789012345678,987654321098765432

# === パフォーマンス ===
MAX_RECORDING_DURATION=10800000
CHUNK_DURATION=1800000
```

### Python API (.env)
```bash
# === API設定 ===
API_HOST=0.0.0.0
API_PORT=8001
API_DEBUG=false

# === Discord連携 ===
DISCORD_WEBHOOK_URL=http://localhost:3003/webhook/meeting-completed

# === AI設定 ===
WHISPER_MODEL=base
WHISPER_LANGUAGE=ja
WHISPER_DEVICE=cpu
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma2:2b
OLLAMA_TIMEOUT=300

# === ファイル管理 ===
TEMP_DIR=/tmp/voice-meeting-bot/temp
OUTPUT_DIR=/tmp/voice-meeting-bot/output
MAX_FILE_SIZE_MB=100
AUTO_CLEANUP_HOURS=24

# === データベース ===
DATABASE_URL=sqlite:///./meetings.db

# === ログ設定 ===
LOG_LEVEL=WARNING
LOG_FILE=/tmp/voice-meeting-bot/logs/api.log

# === セキュリティ ===
MAX_CONCURRENT_TRANSCRIPTIONS=3
RATE_LIMIT_PER_MINUTE=10
```

---

## 🛠️ 設定適用手順

### Step 1: ディレクトリ準備
```bash
# 作業ディレクトリ作成
sudo mkdir -p /tmp/voice-meeting-bot/{temp,output,logs}
sudo chown -R ec2-user:ec2-user /tmp/voice-meeting-bot/

# 権限確認
ls -la /tmp/voice-meeting-bot/
```

### Step 2: 設定ファイル作成
```bash
# Discord Bot設定
cd /path/to/voice-meeting-bot/node-bot
cp .env.example .env
# 上記テンプレートに従って編集
nano .env

# Python API設定
cd /path/to/voice-meeting-bot/python-api
cp .env.example .env
# 上記テンプレートに従って編集
nano .env
```

### Step 3: 設定検証
```bash
# 環境変数読み込み確認
cd /path/to/voice-meeting-bot/node-bot
node -e "require('dotenv').config(); console.log('WEBHOOK_PORT:', process.env.WEBHOOK_PORT);"

cd /path/to/voice-meeting-bot/python-api
python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print('API_PORT:', os.getenv('API_PORT'))"
```

### Step 4: ポート確認
```bash
# 競合チェック
sudo netstat -tlnp | grep -E ":(3003|8001)"

# 使用可能確認
nc -zv localhost 3003 2>&1 | grep -q "refused" && echo "Port 3003 available"
nc -zv localhost 8001 2>&1 | grep -q "refused" && echo "Port 8001 available"
```

---

## ⚠️ 設定時の注意事項

### 1. 秘密情報管理
```bash
# .envファイルの権限設定
chmod 600 /path/to/voice-meeting-bot/*/.env

# Gitで管理しないよう確認
git status | grep -q ".env" && echo "⚠️  .env files are tracked by git!"
```

### 2. 既存ボットとの競合確認
```bash
# 既存プロセス確認
ps aux | grep -E "(node|python)" | grep -v grep
sudo netstat -tlnp | grep -E ":(3000|3001|3002|8000)"

# 必要に応じてポート変更
# 例：3003 → 3004, 8001 → 8002
```

### 3. ファイアウォール設定
```bash
# EC2セキュリティグループ確認
# 内部通信のみなので、Inboundルール追加不要

# ローカルファイアウォール確認（必要に応じて）
sudo ufw status
```

---

## 🧪 設定テスト手順

### 1. 単体起動テスト
```bash
# Python API単体テスト
cd /path/to/voice-meeting-bot/python-api
python3 main.py &
sleep 5
curl http://localhost:8001/health
kill %1

# Discord Bot単体テスト
cd /path/to/voice-meeting-bot/node-bot
node index.js &
sleep 10
curl http://localhost:3003/health
kill %1
```

### 2. 通信テスト
```bash
# Python API起動
cd /path/to/voice-meeting-bot/python-api
python3 main.py &
sleep 5

# Discord Bot起動
cd /path/to/voice-meeting-bot/node-bot
node index.js &
sleep 10

# Webhook通信テスト
curl -X POST http://localhost:3003/webhook/meeting-completed \
  -H "Content-Type: application/json" \
  -d '{
    "meeting_id": "test-meeting-001",
    "event": "meeting_completed",
    "timestamp": "2025-06-23T12:00:00Z",
    "download_links": {
      "summary": "/download/meeting/test-meeting-001/summary",
      "transcript": "/download/meeting/test-meeting-001/transcript",
      "chunks": "/download/meeting/test-meeting-001/chunks"
    }
  }'

# プロセス終了
killall node
killall python3
```

### 3. エラーログ確認
```bash
# ログディレクトリ確認
ls -la /tmp/voice-meeting-bot/logs/

# エラーがないことを確認
grep -i error /tmp/voice-meeting-bot/logs/* 2>/dev/null || echo "No errors found"
```

---

## 📊 設定完了チェックリスト

### 基本設定 ✅
- [ ] Discord Bot .env作成・編集完了
- [ ] Python API .env作成・編集完了
- [ ] ディレクトリ作成・権限設定完了
- [ ] ポート競合確認・回避完了

### セキュリティ設定 ✅
- [ ] .envファイル権限設定（600）
- [ ] 秘密情報確認（Gitトラッキング除外）
- [ ] 管理者ユーザーID設定

### ネットワーク設定 ✅
- [ ] ポート設定確認（3003, 8001）
- [ ] Webhook URL設定確認
- [ ] API URL設定確認

### テスト確認 ✅
- [ ] 単体起動テスト完了
- [ ] 通信テスト完了
- [ ] エラーログ確認完了
- [ ] リソース使用量確認完了

---

## 🔄 設定変更履歴

| 日付 | 変更内容 | 理由 | 担当 |
|------|---------|------|------|
| 2025-06-23 | ポート変更：3002→3003, 8000→8001 | 既存ボット競合回避 | Claude |
| 2025-06-23 | ディレクトリ変更：./temp→/tmp/voice-meeting-bot/temp | EC2永続化対応 | Claude |
| 2025-06-23 | ログレベル変更：info→warn | 本番環境最適化 | Claude |

---

**最終更新**: 2025-06-23  
**次回見直し**: システム稼働1週間後
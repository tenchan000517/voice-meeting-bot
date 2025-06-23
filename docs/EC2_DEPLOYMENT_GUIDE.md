# EC2 永続化デプロイメントガイド

## 🎯 概要

Discord音声議事録ボット（Webhook自動ダウンロードシステム）をEC2環境でタスクセッション（Systems Manager Session Manager）を使用して永続化運用するための完全ガイド。

**⚠️ 重要**: 既に他のボットが稼働している環境での追加デプロイメントを想定。

## 📋 現在の実装状況（2025-06-23時点）

### ✅ 完成済み機能
- **Discord Bot** (Node.js): ポート可変対応済み（デフォルト3002）
- **Python API**: ポート可変対応済み（デフォルト8000）
- **Webhook自動ダウンロードシステム**: 完全実装済み
- **24時間録音情報保持**: 実装済み
- **環境変数対応**: ほぼ完了

### 🔧 EC2デプロイ前の必要修正

#### 1. 環境変数追加が必要
```bash
# 新規追加が必要な環境変数
DISCORD_WEBHOOK_URL=http://localhost:3002/webhook/meeting-completed
WEBHOOK_PORT=3002
DEV_GUILD_ID=your_dev_guild_id
```

#### 2. ポート競合対策
既存ボットとの競合を避けるため、以下のポート変更を推奨：
- **Discord Bot Webhook**: 3002 → 3003
- **Python API**: 8000 → 8001

## 🚀 EC2永続化手順

### Step 1: 環境準備

#### 1.1 Systems Manager エージェント確認
```bash
# EC2インスタンスでSSM Agentの状態確認
sudo systemctl status amazon-ssm-agent
```

#### 1.2 必要な依存関係確認
```bash
# Node.js (v18以上)
node --version

# Python (3.8以上)
python3 --version

# npm dependencies確認
cd /path/to/voice-meeting-bot/node-bot
npm list --depth=0

# Python dependencies確認
cd /path/to/voice-meeting-bot/python-api
pip list | grep -E "(fastapi|whisper|httpx)"
```

### Step 2: 環境変数設定

#### 2.1 環境変数ファイル作成
```bash
# Discord Bot環境変数
cat > /path/to/voice-meeting-bot/node-bot/.env << 'EOF'
DISCORD_BOT_TOKEN=your_actual_token
CLIENT_ID=your_actual_client_id
PYTHON_API_URL=http://localhost:8001
WEBHOOK_PORT=3003
DEV_GUILD_ID=your_dev_guild_id
LOG_LEVEL=info
TEMP_DIR=/tmp/voice-meeting-bot/temp
ADMIN_USER_IDS=123456789012345678
AUTO_DELETE_AFTER_HOURS=24
EOF

# Python API環境変数
cat > /path/to/voice-meeting-bot/python-api/.env << 'EOF'
API_HOST=0.0.0.0
API_PORT=8001
DISCORD_WEBHOOK_URL=http://localhost:3003/webhook/meeting-completed
WHISPER_MODEL=base
WHISPER_LANGUAGE=ja
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma2:2b
DATABASE_URL=sqlite:///./meetings.db
LOG_LEVEL=INFO
TEMP_DIR=/tmp/voice-meeting-bot/temp
OUTPUT_DIR=/tmp/voice-meeting-bot/output
EOF
```

#### 2.2 ディレクトリ作成
```bash
sudo mkdir -p /tmp/voice-meeting-bot/{temp,output,logs}
sudo chown $USER:$USER /tmp/voice-meeting-bot/{temp,output,logs}
```

### Step 3: プロセス管理設定

#### 3.1 systemd サービス作成

**Discord Bot Service**
```bash
sudo tee /etc/systemd/system/voice-meeting-discord-bot.service > /dev/null << 'EOF'
[Unit]
Description=Voice Meeting Discord Bot
After=network.target
Wants=voice-meeting-python-api.service

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/path/to/voice-meeting-bot/node-bot
Environment=NODE_ENV=production
ExecStart=/usr/bin/node index.js
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=voice-meeting-discord

[Install]
WantedBy=multi-user.target
EOF
```

**Python API Service**
```bash
sudo tee /etc/systemd/system/voice-meeting-python-api.service > /dev/null << 'EOF'
[Unit]
Description=Voice Meeting Python API
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/path/to/voice-meeting-bot/python-api
Environment=PYTHONPATH=/path/to/voice-meeting-bot/python-api
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=voice-meeting-api

[Install]
WantedBy=multi-user.target
EOF
```

#### 3.2 サービス有効化
```bash
# サービス登録・有効化
sudo systemctl daemon-reload
sudo systemctl enable voice-meeting-python-api.service
sudo systemctl enable voice-meeting-discord-bot.service

# 起動順序確認（Python API → Discord Bot）
sudo systemctl start voice-meeting-python-api.service
sleep 10
sudo systemctl start voice-meeting-discord-bot.service
```

### Step 4: ポート開放・ファイアウォール設定

#### 4.1 セキュリティグループ設定
EC2セキュリティグループに以下を追加（必要に応じて）:
- **Inbound**: なし（全て内部通信）
- **Outbound**: 443 (HTTPS), 11434 (Ollama)

#### 4.2 内部ポート確認
```bash
# ポート使用状況確認
sudo netstat -tlnp | grep -E ":(3003|8001|11434)"

# プロセス確認
ps aux | grep -E "(node|python3)" | grep -v grep
```

### Step 5: 監視・ログ設定

#### 5.1 ログローテーション設定
```bash
sudo tee /etc/logrotate.d/voice-meeting-bot > /dev/null << 'EOF'
/tmp/voice-meeting-bot/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
```

#### 5.2 ヘルスチェックスクリプト
```bash
cat > /path/to/voice-meeting-bot/health-check.sh << 'EOF'
#!/bin/bash

# Python API ヘルスチェック
if ! curl -f http://localhost:8001/health > /dev/null 2>&1; then
    echo "$(date): Python API is down, restarting..."
    sudo systemctl restart voice-meeting-python-api.service
fi

# Discord Bot プロセスチェック
if ! pgrep -f "node.*index.js" > /dev/null; then
    echo "$(date): Discord Bot is down, restarting..."
    sudo systemctl restart voice-meeting-discord-bot.service
fi
EOF

chmod +x /path/to/voice-meeting-bot/health-check.sh

# Cron設定（5分毎にヘルスチェック）
(crontab -l 2>/dev/null; echo "*/5 * * * * /path/to/voice-meeting-bot/health-check.sh >> /tmp/voice-meeting-bot/logs/health-check.log") | crontab -
```

## 🔧 テスト・検証手順

### 1. 単体テスト
```bash
# Python API動作確認
curl http://localhost:8001/health

# Discord Bot Webhook受信テスト
curl -X POST http://localhost:3003/webhook/meeting-completed \
  -H "Content-Type: application/json" \
  -d '{"meeting_id":"test","event":"meeting_completed","timestamp":"2025-06-23T12:00:00Z"}'
```

### 2. 統合テスト
1. Discord botで `/record start` 実行
2. 短時間録音後 `/record stop` 実行
3. 転写・要約完了後の自動メッセージ確認
4. ダウンロードボタン動作確認

### 3. 永続化テスト
```bash
# サービス再起動テスト
sudo systemctl restart voice-meeting-python-api.service
sudo systemctl restart voice-meeting-discord-bot.service

# システム再起動テスト
sudo reboot
# 再起動後、自動起動確認
```

## ⚠️ 運用時の注意事項

### 1. リソース監視
```bash
# ディスク容量監視（音声ファイル蓄積）
df -h /tmp/voice-meeting-bot/

# メモリ使用量監視
free -h
ps aux --sort=-%mem | head
```

### 2. 定期メンテナンス
```bash
# 週次実行推奨
find /tmp/voice-meeting-bot/temp -type f -mtime +7 -delete
find /tmp/voice-meeting-bot/output -type f -mtime +30 -delete
```

### 3. バックアップ
```bash
# 設定バックアップ
tar -czf voice-meeting-bot-config-$(date +%Y%m%d).tar.gz \
  /path/to/voice-meeting-bot/node-bot/.env \
  /path/to/voice-meeting-bot/python-api/.env \
  /etc/systemd/system/voice-meeting-*.service
```

## 🚨 トラブルシューティング

### よくある問題

#### 1. ポート競合
```bash
# 使用中ポート確認
sudo lsof -i :3003
sudo lsof -i :8001

# 代替ポート設定
# .envファイルでWEBHOOK_PORT, API_PORTを変更
```

#### 2. 権限エラー
```bash
# ファイル権限確認
ls -la /tmp/voice-meeting-bot/
sudo chown -R ec2-user:ec2-user /tmp/voice-meeting-bot/
```

#### 3. 依存関係エラー
```bash
# Node.js依存関係再インストール
cd /path/to/voice-meeting-bot/node-bot
npm install

# Python依存関係確認
pip install -r /path/to/voice-meeting-bot/python-api/requirements.txt
```

## 📞 緊急時対応

### サービス停止
```bash
sudo systemctl stop voice-meeting-discord-bot.service
sudo systemctl stop voice-meeting-python-api.service
```

### ログ確認
```bash
# systemdログ
sudo journalctl -u voice-meeting-discord-bot.service -f
sudo journalctl -u voice-meeting-python-api.service -f

# アプリケーションログ
tail -f /tmp/voice-meeting-bot/logs/*.log
```

---

## 🎯 次期エンジニアへの引継ぎ事項

### 実装完了事項 ✅
- Webhook自動ダウンロードシステム（完全動作）
- 24時間録音情報保持機能
- 4種類ダウンロードエンドポイント
- ボタンUI自動生成

### 今後の拡張候補 📈
1. 複数音声チャンクの個別ダウンロードボタン（最大25個制限対応）
2. ユーザー別通知設定
3. ダウンロード統計・利用状況分析
4. データ保存期間の動的設定

### 重要な設計判断 🎨
- ポーリング方式をWebhook方式に変更済み
- ephemeral警告は影響なしのため修正保留
- WSL2環境制限によりdependency変更は慎重に

---
**作成日**: 2025-06-23  
**最終更新**: 2025-06-23  
**対象環境**: EC2 Amazon Linux 2/Ubuntu  
**前提条件**: Node.js v18+, Python 3.8+, Ollama実行中
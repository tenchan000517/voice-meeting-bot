#!/bin/bash

# Discord Bot ヘルスチェックスクリプト

set -e

WEBHOOK_URL="http://localhost:3003/webhook/meeting-completed"
LOG_FILE="/var/log/voice-meeting-bot-health.log"
SERVICE_NAME="voice-meeting-discord-bot.service"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# ヘルスチェック実行
check_health() {
    # 1. プロセス存在確認
    if ! pgrep -f "node index.js" > /dev/null; then
        log "❌ Node.js process not found"
        return 1
    fi

    # 2. ポート3003リスニング確認
    if ! ss -tln | grep -q ":3003"; then
        log "❌ Port 3003 not listening"
        return 1
    fi

    # 3. Webhook応答確認
    if ! curl -s -f "$WEBHOOK_URL" -X POST -H "Content-Type: application/json" -d '{"test":"health"}' > /dev/null; then
        log "❌ Webhook endpoint not responding"
        return 1
    fi

    # 4. systemd status確認
    if ! sudo systemctl is-active --quiet "$SERVICE_NAME"; then
        log "❌ systemd service not active"
        return 1
    fi

    log "✅ Health check passed"
    return 0
}

# メイン処理
if check_health; then
    # 健全な場合は何もしない
    exit 0
else
    log "🔄 Health check failed, attempting restart..."
    
    # サービス再起動
    sudo systemctl restart "$SERVICE_NAME"
    
    # 30秒待機後に再チェック
    sleep 30
    
    if check_health; then
        log "✅ Service recovered after restart"
        exit 0
    else
        log "❌ Service failed to recover, manual intervention required"
        exit 1
    fi
fi
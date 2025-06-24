#!/bin/bash

# Discord Bot 自動更新スクリプト
# EC2での永続稼働用

set -e

LOG_FILE="/var/log/voice-meeting-bot-update.log"
REPO_DIR="/home/ec2-user/voice-meeting-bot"
SERVICE_NAME="voice-meeting-discord-bot.service"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log "=== Discord Bot Auto Update Started ==="

# 現在のコミットハッシュを記録
cd "$REPO_DIR"
CURRENT_COMMIT=$(git rev-parse HEAD)
log "Current commit: $CURRENT_COMMIT"

# リモートの変更をチェック
git fetch origin main
LATEST_COMMIT=$(git rev-parse origin/main)
log "Latest commit: $LATEST_COMMIT"

if [ "$CURRENT_COMMIT" = "$LATEST_COMMIT" ]; then
    log "No updates available"
    exit 0
fi

log "New updates found, starting update process..."

# Git pull実行
log "Pulling latest changes..."
git pull origin main

# npm install (必要な場合のみ)
if [ -f "node-bot/package.json" ]; then
    if git diff --name-only $CURRENT_COMMIT..HEAD | grep -q "package.json\|package-lock.json"; then
        log "Package files changed, running npm install..."
        cd node-bot
        npm install --production
        cd ..
    fi
fi

# サービス再起動
log "Restarting Discord Bot service..."
sudo systemctl restart "$SERVICE_NAME"

# サービス状態確認
sleep 5
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    log "✅ Service restarted successfully"
else
    log "❌ Service restart failed"
    sudo systemctl status "$SERVICE_NAME" >> "$LOG_FILE" 2>&1
    exit 1
fi

# 更新完了ログ
NEW_COMMIT=$(git rev-parse HEAD)
log "✅ Update completed: $CURRENT_COMMIT -> $NEW_COMMIT"
log "=== Discord Bot Auto Update Completed ==="
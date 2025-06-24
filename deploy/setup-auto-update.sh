#!/bin/bash

# Discord Bot 自動更新セットアップスクリプト
# EC2初期設定用

set -e

echo "🚀 Setting up Discord Bot auto-update system..."

# ログディレクトリ作成
sudo mkdir -p /var/log
sudo touch /var/log/voice-meeting-bot-update.log
sudo chown ec2-user:ec2-user /var/log/voice-meeting-bot-update.log

# 更新スクリプトに実行権限付与
chmod +x /home/ec2-user/voice-meeting-bot/deploy/auto-update.sh

# sudoers設定 (ec2-userがsystemctlを実行可能に)
if ! sudo grep -q "ec2-user.*systemctl.*voice-meeting-discord-bot" /etc/sudoers; then
    echo "ec2-user ALL=(ALL) NOPASSWD: /bin/systemctl restart voice-meeting-discord-bot.service" | sudo tee -a /etc/sudoers
    echo "ec2-user ALL=(ALL) NOPASSWD: /bin/systemctl status voice-meeting-discord-bot.service" | sudo tee -a /etc/sudoers
    echo "ec2-user ALL=(ALL) NOPASSWD: /bin/systemctl is-active voice-meeting-discord-bot.service" | sudo tee -a /etc/sudoers
    echo "✅ sudoers configuration updated"
fi

# crontab設定 (5分おきにチェック)
CRON_JOB="*/5 * * * * /home/ec2-user/voice-meeting-bot/deploy/auto-update.sh >> /var/log/voice-meeting-bot-update.log 2>&1"

# 既存のcrontabを取得
crontab -l 2>/dev/null > /tmp/current_crontab || true

# 同じジョブが存在しないかチェック
if ! grep -q "auto-update.sh" /tmp/current_crontab 2>/dev/null; then
    echo "$CRON_JOB" >> /tmp/current_crontab
    crontab /tmp/current_crontab
    echo "✅ Crontab updated - auto-update will run every 5 minutes"
else
    echo "⚠️  Auto-update cron job already exists"
fi

# 手動更新用エイリアス追加
if ! grep -q "alias bot-update" ~/.bashrc; then
    echo "alias bot-update='/home/ec2-user/voice-meeting-bot/deploy/auto-update.sh'" >> ~/.bashrc
    echo "alias bot-status='sudo systemctl status voice-meeting-discord-bot.service'" >> ~/.bashrc
    echo "alias bot-logs='sudo journalctl -u voice-meeting-discord-bot.service -f'" >> ~/.bashrc
    echo "alias bot-restart='sudo systemctl restart voice-meeting-discord-bot.service'" >> ~/.bashrc
    echo "✅ Convenient aliases added to ~/.bashrc"
fi

rm -f /tmp/current_crontab

echo ""
echo "🎉 Auto-update system setup completed!"
echo ""
echo "📋 Available commands:"
echo "  bot-update  - Manual update check and execution"
echo "  bot-status  - Check service status"
echo "  bot-logs    - Follow real-time logs"
echo "  bot-restart - Restart the service"
echo ""
echo "📊 Monitoring:"
echo "  Update logs: tail -f /var/log/voice-meeting-bot-update.log"
echo "  Cron schedule: */5 * * * * (every 5 minutes)"
echo ""
echo "⚠️  Note: Source ~/.bashrc or re-login to use new aliases"
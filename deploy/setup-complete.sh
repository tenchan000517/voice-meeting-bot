#!/bin/bash

# 完全セットアップスクリプト - EC2でワンコマンド実行用

set -e

echo "🚀 Discord Bot 永続稼働システム - 完全セットアップ開始"
echo ""

# 1. 基本セットアップ
echo "📋 Step 1: 基本セットアップ実行中..."
/home/ec2-user/voice-meeting-bot/deploy/setup-auto-update.sh

# 2. systemdサービス更新
echo ""
echo "🔧 Step 2: systemdサービス設定更新中..."
sudo cp /home/ec2-user/voice-meeting-bot/deploy/voice-meeting-discord-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable voice-meeting-discord-bot.service

# 3. ヘルスチェック設定
echo ""
echo "🏥 Step 3: ヘルスチェック設定中..."
chmod +x /home/ec2-user/voice-meeting-bot/deploy/health-check.sh
chmod +x /home/ec2-user/voice-meeting-bot/deploy/monitor-bot.sh

# ヘルスチェックをcronに追加（10分おき）
HEALTH_CRON="*/10 * * * * /home/ec2-user/voice-meeting-bot/deploy/health-check.sh >> /var/log/voice-meeting-bot-health.log 2>&1"
crontab -l 2>/dev/null > /tmp/current_crontab || true
if ! grep -q "health-check.sh" /tmp/current_crontab 2>/dev/null; then
    echo "$HEALTH_CRON" >> /tmp/current_crontab
    crontab /tmp/current_crontab
    echo "✅ ヘルスチェック cron設定完了（10分間隔）"
fi

# 4. 監視コマンドエイリアス追加
echo ""
echo "📊 Step 4: 監視コマンド設定中..."
if ! grep -q "alias monitor-bot" ~/.bashrc; then
    echo "alias monitor-bot='/home/ec2-user/voice-meeting-bot/deploy/monitor-bot.sh'" >> ~/.bashrc
    echo "alias bot-monitor='/home/ec2-user/voice-meeting-bot/deploy/monitor-bot.sh'" >> ~/.bashrc
    echo "alias bot-health='/home/ec2-user/voice-meeting-bot/deploy/health-check.sh'" >> ~/.bashrc
    echo "✅ 監視コマンドエイリアス追加完了"
fi

# 5. ログローテーション設定
echo ""
echo "📝 Step 5: ログローテーション設定中..."
sudo tee /etc/logrotate.d/voice-meeting-bot > /dev/null <<EOF
/var/log/voice-meeting-bot-*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 ec2-user ec2-user
}
EOF
echo "✅ ログローテーション設定完了"

# 6. サービス再起動とテスト
echo ""
echo "🔄 Step 6: サービス再起動とテスト..."
sudo systemctl restart voice-meeting-discord-bot.service
sleep 5

if sudo systemctl is-active --quiet voice-meeting-discord-bot.service; then
    echo "✅ サービス正常稼働中"
else
    echo "❌ サービス起動に失敗"
    sudo systemctl status voice-meeting-discord-bot.service
    exit 1
fi

# 7. 完了報告
echo ""
echo "🎉 Discord Bot 永続稼働システム - セットアップ完了！"
echo ""
echo "📋 設定済み機能:"
echo "  ✅ 自動Git更新（5分間隔）"
echo "  ✅ ヘルスチェック（10分間隔）"
echo "  ✅ systemd自動再起動"
echo "  ✅ ログローテーション"
echo "  ✅ 監視ダッシュボード"
echo ""
echo "🛠️  利用可能コマンド:"
echo "  monitor-bot     - 総合監視ダッシュボード"
echo "  bot-update      - 手動更新"
echo "  bot-restart     - サービス再起動"
echo "  bot-logs        - リアルタイムログ"
echo "  bot-health      - ヘルスチェック実行"
echo ""
echo "📊 ログファイル:"
echo "  更新ログ: /var/log/voice-meeting-bot-update.log"
echo "  ヘルスログ: /var/log/voice-meeting-bot-health.log"
echo "  システムログ: sudo journalctl -u voice-meeting-discord-bot.service"
echo ""
echo "⚠️  注意: 新しいエイリアスを使用するには 'source ~/.bashrc' を実行してください"
echo ""

# 初回監視ダッシュボード表示
echo "📊 現在のシステム状態:"
/home/ec2-user/voice-meeting-bot/deploy/monitor-bot.sh

rm -f /tmp/current_crontab
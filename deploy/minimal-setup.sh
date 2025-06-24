#!/bin/bash

# 最小構成セットアップ - 軽量版
# 必要最低限の機能のみ

set -e

echo "⚡ Discord Bot 軽量自動運用システム - セットアップ開始"
echo ""

# 1. sudoers設定のみ（重い処理なし）
echo "🔧 Step 1: 基本権限設定..."
if ! sudo grep -q "ec2-user.*systemctl.*voice-meeting-discord-bot" /etc/sudoers; then
    echo "ec2-user ALL=(ALL) NOPASSWD: /bin/systemctl restart voice-meeting-discord-bot.service" | sudo tee -a /etc/sudoers
    echo "ec2-user ALL=(ALL) NOPASSWD: /bin/systemctl status voice-meeting-discord-bot.service" | sudo tee -a /etc/sudoers
    echo "✅ sudoers設定完了"
fi

# 2. 手動更新用エイリアスのみ
echo ""
echo "📋 Step 2: 便利コマンド設定..."
if ! grep -q "alias manual-update" ~/.bashrc; then
    cat >> ~/.bashrc << 'EOF'

# Discord Bot管理コマンド（軽量版）
alias manual-update='cd ~/voice-meeting-bot && git pull origin main && sudo systemctl restart voice-meeting-discord-bot.service'
alias bot-status='sudo systemctl status voice-meeting-discord-bot.service'
alias bot-logs='sudo journalctl -u voice-meeting-discord-bot.service -f'
alias bot-restart='sudo systemctl restart voice-meeting-discord-bot.service'
EOF
    echo "✅ 管理コマンド追加完了"
fi

# 3. systemd設定最適化（軽量）
echo ""
echo "🛡️ Step 3: サービス安定化..."
sudo cp /home/ec2-user/voice-meeting-bot/deploy/voice-meeting-discord-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable voice-meeting-discord-bot.service
sudo systemctl restart voice-meeting-discord-bot.service

# 4. 動作確認
sleep 3
if sudo systemctl is-active --quiet voice-meeting-discord-bot.service; then
    echo "✅ Discord Bot正常稼働中"
else
    echo "❌ サービス起動失敗"
    exit 1
fi

echo ""
echo "🎉 軽量自動運用システム - セットアップ完了！"
echo ""
echo "🛠️ 利用可能コマンド:"
echo "  manual-update   - 手動更新（git pull + restart）"
echo "  bot-status      - サービス状態確認"
echo "  bot-logs        - リアルタイムログ表示"
echo "  bot-restart     - サービス再起動"
echo ""
echo "💡 手動更新方法:"
echo "  1. あなた: git push origin main"
echo "  2. EC2: manual-update コマンド実行"
echo ""
echo "⚠️ 注意: source ~/.bashrc で新しいコマンドを有効化してください"
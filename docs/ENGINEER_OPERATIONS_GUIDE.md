# 👨‍💻 エンジニア向け運用ガイド

**対象**: 開発エンジニア・システムエンジニア  
**レベル**: 中級〜上級  
**最終更新**: 2025年6月24日

## 🎯 クイックスタート

### ⚡ 最速デプロイ
```bash
# 1. コード変更・プッシュ
git add .
git commit -m "機能追加"  
git push origin main

# 2. 5分待機 (自動デプロイ完了)

# 3. 稼働確認
ssh find-to-do
monitor-bot
```

### 📊 システム状態即座確認
```bash
ssh find-to-do && monitor-bot
```

## 🔧 高度な運用コマンド

### 🛠️ デバッグ・診断
```bash
# プロセス詳細分析
ps aux --forest | grep -A5 -B5 node

# メモリ使用量詳細
cat /proc/$(pgrep -f "node index.js")/status | grep -E "(VmRSS|VmSize)"

# CPU使用率リアルタイム監視
top -p $(pgrep -f "node index.js")

# ネットワーク接続状態
netstat -tlnp | grep :3003
lsof -i :3003

# ファイルディスクリプタ使用状況  
lsof -p $(pgrep -f "node index.js") | wc -l
```

### 🔍 ログ高度分析
```bash
# エラーパターン分析
sudo journalctl -u voice-meeting-discord-bot.service --since "24 hours ago" | grep -i error | sort | uniq -c

# パフォーマンスログ抽出
sudo journalctl -u voice-meeting-discord-bot.service --since "1 hour ago" | grep -E "(Memory|CPU|Duration)"

# Webhook関連ログ分析
sudo journalctl -u voice-meeting-discord-bot.service | grep -i webhook | tail -20

# 自動更新履歴分析
awk '/Update completed/ {print $1, $2, $NF}' /var/log/voice-meeting-bot-update.log
```

### 📈 パフォーマンス監視
```bash
# リソース使用量詳細レポート
echo "=== システムリソース使用状況 ==="
echo "CPU使用率: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)"
echo "メモリ使用率: $(free | grep Mem | awk '{printf("%.1f%%", $3/$2*100)}')"
echo "ディスク使用率: $(df / | tail -1 | awk '{print $5}')"

# Node.jsプロセス詳細
PID=$(pgrep -f "node index.js")
echo "=== Discord Bot プロセス情報 ==="
echo "PID: $PID"
echo "稼働時間: $(ps -o etime= -p $PID)"
echo "メモリ: $(ps -o rss= -p $PID | awk '{print $1/1024 "MB"}')"
echo "CPU時間: $(ps -o time= -p $PID)"
```

## 🚀 開発・デプロイ ワークフロー

### 🎯 機能開発フロー
```bash
# 1. 機能ブランチ作成
git checkout -b feature/voice-quality-improvement

# 2. 開発・テスト
npm run test
npm run lint  
npm run build  # もしビルドプロセスがあれば

# 3. 段階的デプロイ
git add .
git commit -m "feat: 音声品質向上アルゴリズム実装"

# 4. プルリクエスト (推奨)
git push origin feature/voice-quality-improvement
# → GitHub でPR作成

# 5. メインブランチマージ・自動デプロイ
git checkout main
git merge feature/voice-quality-improvement  
git push origin main  # ← 自動デプロイ開始
```

### 🛡️ 安全デプロイ (重要変更時)
```bash
# 1. 事前バックアップ
ssh find-to-do
cd ~/voice-meeting-bot
git log --oneline -5 > ~/backup/pre-deploy-$(date +%Y%m%d-%H%M%S).log

# 2. 段階的確認デプロイ
git push origin main

# 3. 5分後確認
sleep 300
ssh find-to-do && monitor-bot

# 4. 問題発生時の即座ロールバック
ssh find-to-do
cd ~/voice-meeting-bot  
git log --oneline -3
git reset --hard HEAD~1  # 前のコミットに戻す
bot-restart
```

## 🔧 システム設定・カスタマイズ

### ⚙️ 環境変数管理
```bash
# .env ファイル管理
ssh find-to-do
cd ~/voice-meeting-bot/node-bot

# 現在の設定確認
cat .env

# 安全な設定変更
cp .env .env.backup.$(date +%Y%m%d-%H%M%S)
nano .env
bot-restart  # 設定反映
```

### 🎛️ systemd設定カスタマイズ
```bash
# サービス設定編集
sudo systemctl edit voice-meeting-discord-bot.service

# 設定例: メモリ制限追加
[Service]
MemoryLimit=256M
CPUQuota=50%

# 設定反映
sudo systemctl daemon-reload
sudo systemctl restart voice-meeting-discord-bot.service
```

### 🔄 自動化設定調整
```bash
# 更新頻度変更 (デフォルト: 5分間隔)
crontab -e

# 例: 1分間隔に変更 (開発時)
# */1 * * * * /home/ec2-user/voice-meeting-bot/deploy/auto-update.sh

# 例: 30分間隔に変更 (安定稼働時)  
# */30 * * * * /home/ec2-user/voice-meeting-bot/deploy/auto-update.sh
```

## 🔍 高度なトラブルシューティング

### 🚨 緊急時診断フロー
```bash
# 1. システム全体状況把握
ssh find-to-do
monitor-bot

# 2. プロセス状態詳細確認
sudo systemctl status voice-meeting-discord-bot.service -l
sudo journalctl -u voice-meeting-discord-bot.service -n 100 --no-pager

# 3. リソース状況確認
free -h
df -h
top -bn1 | head -20

# 4. ネットワーク状況確認
ss -tlnp | grep :3003
curl -I http://localhost:3003/

# 5. 依存関係確認
cd ~/voice-meeting-bot/node-bot
npm list --depth=0
```

### 🛠️ パフォーマンス問題解決
```bash
# メモリリーク調査
echo "=== メモリ使用量推移 ==="
for i in {1..10}; do
  echo "$(date): $(ps -o rss= -p $(pgrep -f 'node index.js') | awk '{print $1/1024 "MB"}')"
  sleep 60
done

# CPU使用率異常調査
echo "=== CPU使用率詳細 ==="
pidstat -p $(pgrep -f "node index.js") 1 10

# ディスク I/O 調査
echo "=== ディスク I/O 状況 ==="
iotop -p $(pgrep -f "node index.js") -n 5
```

### 🔧 設定問題解決
```bash
# 権限問題解決
sudo chown -R ec2-user:ec2-user /home/ec2-user/voice-meeting-bot
chmod +x /home/ec2-user/voice-meeting-bot/deploy/*.sh

# 依存関係問題解決
cd ~/voice-meeting-bot/node-bot
rm -rf node_modules package-lock.json
npm cache clean --force  
npm install

# 設定ファイル問題解決
cd ~/voice-meeting-bot/node-bot
cp .env.example .env  # もし.envが破損している場合
nano .env  # 必要な環境変数を設定
```

## 📊 監視・アラート設定

### 🎯 カスタム監視スクリプト
```bash
# CPU/メモリ監視アラート
cat > ~/monitor-alert.sh << 'EOF'
#!/bin/bash
CPU=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1 | cut -d' ' -f1)
MEM=$(free | grep Mem | awk '{printf("%.0f", $3/$2*100)}')

if (( $(echo "$CPU > 80" | bc -l) )); then
    echo "ALERT: High CPU usage: $CPU%"
fi

if (( MEM > 90 )); then
    echo "ALERT: High memory usage: $MEM%"  
fi
EOF

chmod +x ~/monitor-alert.sh
```

### 📈 ログ監視・分析
```bash
# エラーログ監視
tail -f /var/log/voice-meeting-bot-*.log | grep -i error --color=always

# リアルタイム統計
watch -n 1 'echo "=== $(date) ==="; monitor-bot | head -15'

# ログ統計レポート
echo "=== 過去24時間のシステム統計 ==="
echo "更新回数: $(grep "Update completed" /var/log/voice-meeting-bot-update.log | grep "$(date +%Y-%m-%d)" | wc -l)"
echo "エラー件数: $(sudo journalctl -u voice-meeting-discord-bot.service --since "24 hours ago" | grep -i error | wc -l)"
echo "再起動回数: $(sudo journalctl -u voice-meeting-discord-bot.service --since "24 hours ago" | grep "Started" | wc -l)"
```

## 🚀 最適化・チューニング

### ⚡ パフォーマンス最適化
```bash
# Node.js パフォーマンス設定
echo "=== Node.js 最適化設定例 ==="
cat > ~/voice-meeting-bot/node-bot/.env.production << 'EOF'
NODE_ENV=production
NODE_OPTIONS="--max-old-space-size=512 --gc-interval=100"
UV_THREADPOOL_SIZE=4
EOF

# systemd設定最適化
sudo tee /etc/systemd/system/voice-meeting-discord-bot.service.d/override.conf << 'EOF'
[Service]
# プロセス優先度調整
Nice=-5
IOSchedulingClass=1
IOSchedulingPriority=4

# リソース制限最適化
LimitNOFILE=65536
LimitNPROC=8192
EOF

sudo systemctl daemon-reload
sudo systemctl restart voice-meeting-discord-bot.service
```

---

**🎓 このガイドは上級エンジニア向けの包括的運用マニュアルです**  
**システムの深い理解と安全な運用のためのベストプラクティスを提供しています**

**担当エンジニア**: Claude Code + tenchan000517  
**技術スタック**: Node.js, systemd, cron, Amazon Linux 2023  
**更新履歴**: 2025.06.24 - 初版作成
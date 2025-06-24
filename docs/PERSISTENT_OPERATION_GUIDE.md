# 🔄 Discord Bot 永続稼働フロー完全ガイド

**対象**: 開発チーム・運用チーム・エンジニア全般  
**更新日**: 2025年6月24日  
**ステータス**: 🟢 本番運用中

## 🎯 永続稼働システム概要

### 📊 システム構成
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│                 │    │                  │    │                     │
│   開発者        │───▶│   GitHub         │───▶│   EC2 (Auto-Deploy) │
│   (ローカル)     │    │   Repository     │    │   Discord Bot       │
│                 │    │                  │    │                     │
└─────────────────┘    └──────────────────┘    └─────────────────────┘
                                                           │
                                                           ▼
                                                ┌─────────────────────┐
                                                │                     │
                                                │  Python API Server  │
                                                │  (ローカル稼働)      │
                                                │                     │
                                                └─────────────────────┘
```

## 🚀 自動デプロイメントフロー

### ⚡ フル自動フロー (推奨)
```bash
# 1. 開発者側 (ローカル)
git add .
git commit -m "新機能追加"
git push origin main

# 2. EC2側 (完全自動)
# → 5分以内に自動実行される
#   - git fetch origin main
#   - 変更検知
#   - git pull origin main  
#   - npm install (package.json変更時のみ)
#   - systemctl restart voice-meeting-discord-bot.service
#   - 健全性確認

# 3. 結果確認 (手動)
ssh find-to-do
monitor-bot  # 新バージョン稼働確認
```

### 📋 タイムライン例
```
14:00:00  開発者: git push origin main (新機能)
14:02:30  EC2: 変更なし (まだ検出前)  
14:05:00  EC2: 変更検知！自動更新開始
14:05:10  EC2: git pull完了
14:05:15  EC2: service restart完了  
14:05:20  EC2: 新バージョン稼働開始
14:05:30  EC2: ヘルスチェック - 正常確認
```

## 🛠️ 手動運用コマンド

### 📊 監視・確認コマンド
```bash
# 総合ダッシュボード
monitor-bot

# サービス状態確認
bot-status

# リアルタイムログ表示
bot-logs

# 自動更新履歴確認
tail -f /var/log/voice-meeting-bot-update.log

# ヘルスチェック履歴確認
tail -f /var/log/voice-meeting-bot-health.log
```

### 🔧 緊急時対応コマンド
```bash
# 手動サービス再起動
bot-restart

# 手動更新実行
bot-update

# ヘルスチェック実行
bot-health

# cron設定確認
crontab -l

# プロセス詳細確認
ps aux | grep node
ss -tln | grep 3003
```

## 🎯 開発者向けベストプラクティス

### ✅ 推奨開発フロー
```bash
# 1. 機能開発
git checkout -b feature/new-function
# ... 開発作業 ...
git add .
git commit -m "feat: 新機能実装"

# 2. ローカルテスト
npm test
npm run lint

# 3. プッシュ・デプロイ
git checkout main
git merge feature/new-function
git push origin main  # ← ここで自動デプロイ開始

# 4. 本番動作確認 (5-10分後)
ssh find-to-do
monitor-bot
```

### ⚠️ 注意事項
```bash
# 危険な変更時は事前確認
# - package.json の依存関係変更
# - 環境変数の変更
# - systemd設定変更

# 確認手順:
ssh find-to-do
cd ~/voice-meeting-bot
git log --oneline -5  # 最新コミット確認
monitor-bot           # システム状態確認
```

## 🛡️ 障害対応・トラブルシューティング

### 🚨 よくある問題と解決法

#### **問題1**: サービスが起動しない
```bash
# 診断
sudo systemctl status voice-meeting-discord-bot.service
sudo journalctl -u voice-meeting-discord-bot.service -n 50

# 解決
cd /home/ec2-user/voice-meeting-bot/node-bot
node index.js  # 手動起動テスト
bot-restart    # サービス再起動
```

#### **問題2**: 自動更新が動作しない
```bash
# 診断
crontab -l  # cron設定確認
tail -20 /var/log/voice-meeting-bot-update.log

# 解決
./deploy/auto-update.sh  # 手動実行テスト
```

#### **問題3**: Webhook応答なし
```bash
# 診断
curl -X POST http://localhost:3003/webhook/meeting-completed \
  -H "Content-Type: application/json" \
  -d '{"test":"data"}'

# 解決
ss -tln | grep 3003  # ポート確認
bot-restart          # サービス再起動
```

### 🔄 緊急復旧手順
```bash
# 1. サービス状態確認
monitor-bot

# 2. 強制再起動
sudo systemctl stop voice-meeting-discord-bot.service
sudo systemctl start voice-meeting-discord-bot.service

# 3. 設定リセット (最後の手段)
cd ~/voice-meeting-bot
git reset --hard origin/main
./deploy/setup-complete.sh
```

## 📊 監視・メトリクス

### 🎯 監視対象項目
| 項目 | 正常範囲 | 確認方法 |
|------|----------|----------|
| **CPU使用率** | < 10% | `monitor-bot` |
| **メモリ使用率** | < 15% | `monitor-bot` |
| **ディスク使用率** | < 80% | `monitor-bot` |
| **プロセス稼働** | Running | `bot-status` |
| **Port 3003** | Listening | `monitor-bot` |
| **Webhook応答** | 200 OK | `monitor-bot` |

### 📈 パフォーマンス指標
```bash
# リソース使用量詳細
echo "=== CPU・メモリ使用量 ==="
ps aux | grep "node index.js" | grep -v grep

echo "=== ディスク使用量 ==="
df -h /
du -sh /tmp/voice-meeting-bot/temp/

echo "=== ネットワーク状態 ==="
ss -tln | grep 3003
```

## 🔄 定期メンテナンス

### 📅 推奨メンテナンススケジュール

#### **毎日** (自動実行)
- ✅ 自動更新チェック (5分間隔)
- ✅ ヘルスチェック (10分間隔)  
- ✅ ログローテーション

#### **週次** (手動推奨)
```bash
# システム状態総合確認
monitor-bot

# 古い音声ファイルクリーンアップ  
monitor-bot clean

# システム更新確認
sudo dnf check-update
```

#### **月次** (手動推奨)
```bash
# ログファイルアーカイブ
sudo logrotate -f /etc/logrotate.d/voice-meeting-bot

# システム全体更新 (慎重に)
sudo dnf update

# 設定バックアップ
cp -r ~/voice-meeting-bot/node-bot/.env ~/backup/
```

## 🎉 システム拡張・カスタマイズ

### 🚀 追加可能な機能
```bash
# Slack通知連携
# webhook-server.js にSlack通知追加

# 監視メトリクス強化  
# Prometheus/Grafana連携

# 複数環境対応
# staging/production環境分離

# バックアップ自動化
# データベース・設定自動バックアップ
```

---

**🤖 このガイドはDiscord Bot永続稼働システムの完全な運用マニュアルです**  
**質問・問題がある場合は開発チームまでお問い合わせください**

**最終更新**: 2025年6月24日 19:25 JST  
**システム稼働状況**: 🟢 **正常稼働中**
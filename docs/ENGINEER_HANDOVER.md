# 🚀 次期エンジニア向け実行指示書

**緊急度**: HIGH ⚡  
**予想所要時間**: 2-3時間  
**前提条件**: EC2アクセス権限、Systems Manager Session Manager利用可能

---

## 🎯 あなたのミッション

**Discord音声議事録ボットのEC2永続化を完了せよ**

- ✅ **完成済み**: Webhook自動ダウンロードシステム（本番マージ済み）
- 🎯 **あなたの役割**: EC2での永続化運用開始
- ⚠️ **制約条件**: 既存ボットが稼働中の環境

---

## ⚡ 即座実行すべき3ステップ

### Step 1: 現状確認（15分）
```bash
# EC2にSSM接続
aws ssm start-session --target i-xxxxxxxxx

# 現在のポート使用状況確認
sudo netstat -tlnp | grep -E ":(3000|3001|3002|3003|8000|8001)"

# 既存プロセス確認
ps aux | grep -E "(node|python)" | grep -v grep
```

### Step 2: 設定変更（30分）
```bash
# プロジェクトディレクトリに移動
cd /path/to/voice-meeting-bot

# 最新コード取得
git pull origin main

# 設定ファイル作成（ポート競合回避）
# 詳細: docs/EC2_CONFIG_CHECKLIST.md参照
```

### Step 3: 永続化設定（60分）
```bash
# systemdサービス設定
# 詳細手順: docs/EC2_DEPLOYMENT_GUIDE.md参照

# サービス開始
sudo systemctl start voice-meeting-python-api.service
sudo systemctl start voice-meeting-discord-bot.service
```

---

## 📚 必読ドキュメント（優先度順）

### 🔥 最優先
1. **[EC2_CONFIG_CHECKLIST.md](./EC2_CONFIG_CHECKLIST.md)** - 設定変更手順
2. **[EC2_DEPLOYMENT_GUIDE.md](./EC2_DEPLOYMENT_GUIDE.md)** - 永続化手順

### 📋 次優先
3. **[CURRENT_STATUS_REPORT.md](./CURRENT_STATUS_REPORT.md)** - 現状理解

---

## 🚨 重要な注意事項

### ❌ 絶対にやってはいけないこと
1. **`npm install`実行禁止** - WSL2制限によりシステム破綻リスク
2. **既存ポート使用禁止** - 他ボットとの競合
3. **依存関係変更禁止** - ネイティブビルド失敗リスク

### ✅ 必ず確認すること
1. **ポート設定**: 3002→3003, 8000→8001
2. **ディレクトリ権限**: `/tmp/voice-meeting-bot/`
3. **サービス自動起動**: systemctl enable確認

---

## 🧪 成功確認方法

### 1. 基本動作確認
```bash
# サービス状態確認
sudo systemctl status voice-meeting-python-api.service
sudo systemctl status voice-meeting-discord-bot.service

# ヘルスチェック
curl http://localhost:8001/health
curl http://localhost:3003/health
```

### 2. 機能テスト
1. Discordで `/record start` 実行
2. 短時間録音後 `/record stop` 実行
3. 自動メッセージ+ダウンロードボタン表示確認
4. ボタンクリック → ダウンロードURL表示確認

### 3. 永続化テスト
```bash
# システム再起動テスト
sudo reboot

# 再接続後、自動起動確認
sudo systemctl status voice-meeting-*
```

---

## 🔧 トラブル時の対処法

### よくある問題

#### ❌ ポート競合エラー
```bash
# 使用中プロセス確認
sudo lsof -i :3003
sudo lsof -i :8001

# 対処: ポート番号を変更
# .envファイルで WEBHOOK_PORT=3004, API_PORT=8002 など
```

#### ❌ 権限エラー
```bash
# 権限修正
sudo chown -R ec2-user:ec2-user /tmp/voice-meeting-bot/
chmod 600 /path/to/voice-meeting-bot/*/.env
```

#### ❌ サービス起動失敗
```bash
# ログ確認
sudo journalctl -u voice-meeting-python-api.service -f
sudo journalctl -u voice-meeting-discord-bot.service -f

# 手動起動テスト
cd /path/to/voice-meeting-bot/python-api && python3 main.py
cd /path/to/voice-meeting-bot/node-bot && node index.js
```

---

## 📞 緊急時連絡先・手順

### 🚨 システム停止が必要な場合
```bash
# 全サービス停止
sudo systemctl stop voice-meeting-discord-bot.service
sudo systemctl stop voice-meeting-python-api.service

# プロセス強制終了
sudo pkill -f "voice-meeting"
```

### 📋 状況報告テンプレート
```
件名: [緊急] Voice Meeting Bot 永続化作業状況

状況:
- 作業開始時刻: 
- 現在の進捗: Step X/3
- 発生した問題: 
- 対処内容: 
- 次のアクション: 

ログ:
[関連ログを添付]
```

---

## ✅ 完了報告チェックリスト

作業完了時、以下を確認してレポート：

### 基本設定
- [ ] ポート競合回避完了（3003, 8001使用）
- [ ] .env設定完了（両方のプロジェクト）
- [ ] ディレクトリ作成・権限設定完了

### サービス設定
- [ ] systemdサービス作成完了
- [ ] 自動起動設定完了
- [ ] ヘルスチェック設定完了

### 動作確認
- [ ] 基本動作テスト完了
- [ ] 機能テスト完了（録音→ダウンロード）
- [ ] 永続化テスト完了（再起動後自動開始）

### 運用準備
- [ ] ログローテーション設定完了
- [ ] 監視スクリプト設定完了
- [ ] トラブルシューティング手順確認

---

## 🎊 作業完了時のアクション

### 1. 成功報告
```bash
# システム状態確認
sudo systemctl list-units --type=service | grep voice-meeting
ps aux | grep -E "(voice-meeting|node.*index|python.*main)" | grep -v grep

# リソース使用量確認
free -h
df -h /tmp/voice-meeting-bot/
```

### 2. 運用開始
- 監視アラート設定
- 定期メンテナンススケジュール策定
- バックアップ計画実行

### 3. ドキュメント更新
- デプロイ実績の記録
- 遭遇した問題・解決策の追記
- 運用手順の改善提案

---

## 💡 成功のコツ

1. **段階的実行**: 一度に全てやらず、ステップごとに確認
2. **ログ監視**: 常にログを確認しながら作業
3. **バックアップ**: 変更前の設定は必ずバックアップ
4. **テスト重視**: 各段階で動作確認を怠らない

---

**🤖 Generated with [Claude Code](https://claude.ai/code)**

**作成者**: Claude Code Assistant  
**対象**: 次期エンジニア  
**最終更新**: 2025-06-23  
**緊急度**: HIGH ⚡
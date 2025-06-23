# 📊 ログファイル管理状況

**最終更新**: 2025年6月23日 10:55 JST

## 📁 ログファイル構造

```
voice-meeting-bot/
├── node-bot/logs/                    # Discord Bot ログ
│   ├── error.log                     # エラーログ (現在の状況)
│   ├── combined.log                  # 統合ログ (デバッグ用)
│   ├── error.log.backup-*            # バックアップファイル
│   └── bot-session.log               # セッション別ログ
│
├── python-api/logs/                  # Python API ログ
│   ├── api-error.log                 # APIエラーログ
│   ├── api-access.log                # アクセスログ
│   ├── transcription.log             # 文字起こしログ
│   └── summarization.log             # AI要約ログ
│
└── LOG_STATUS.md                     # 本ファイル (ログ状況管理)
```

## 🚀 ログ確認方法 (セッション開始時)

### Discord Bot ログ確認
```bash
# 最新エラー (直近20行)
tail -20 "/mnt/c/voice-meeting-bot/node-bot/logs/error.log"

# 現在のセッション状況
tail -50 "/mnt/c/voice-meeting-bot/node-bot/logs/combined.log"
```

### Python API ログ確認
```bash
# API エラー確認
tail -20 "/mnt/c/voice-meeting-bot/python-api/logs/api-error.log"

# API アクセス状況
tail -20 "/mnt/c/voice-meeting-bot/python-api/logs/api-access.log"
```

## 📈 ログローテーション設定

### Discord Bot (Winston設定)
- **最大ファイルサイズ**: 10MB
- **保持期間**: 7日間
- **最大ファイル数**: 5個

### Python API (Uvicorn設定)
- **最大ファイルサイズ**: 5MB
- **保持期間**: 3日間
- **最大ファイル数**: 3個

## 🧹 定期メンテナンス

### 週次クリーンアップ (毎週実行)
```bash
# 7日以上古いログファイル削除
find "/mnt/c/voice-meeting-bot/*/logs/" -name "*.log.*" -mtime +7 -delete

# バックアップファイル整理
find "/mnt/c/voice-meeting-bot/*/logs/" -name "*.backup-*" -mtime +14 -delete
```

## 🔍 現在のログ状況

### Discord Bot
- **error.log**: ✅ リセット済み (0KB)
- **combined.log**: ✅ リセット済み (0KB)
- **バックアップ**: ✅ 作成済み (error.log.backup-20250623-105500)

### Python API
- **ログディレクトリ**: ✅ 作成済み
- **設定更新**: 🔄 次回起動時に適用

## ⚡ クイックチェックコマンド

```bash
# 全ログファイルサイズ確認
du -sh /mnt/c/voice-meeting-bot/*/logs/

# 最新エラー一覧表示
find /mnt/c/voice-meeting-bot/*/logs/ -name "*error*.log" -exec tail -5 {} \;

# ログファイル更新時刻確認
find /mnt/c/voice-meeting-bot/*/logs/ -name "*.log" -ls
```
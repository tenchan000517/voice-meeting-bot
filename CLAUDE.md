# CLAUDE.md - AI Assistant Guidelines

## ⚠️ WSL2環境での制限事項

**絶対に実行してはいけないコマンド:**
- `python3 -m http.server 8000`
- `python3 -m http.server [任意のポート]`
- バックグラウンドでポートを占有するコマンド

**理由:**
- WSL2のプロセスはセッション終了後も残存する
- ポート衝突の原因となる
- デバッグを困難にする

**原則:**
- ポートを使用するサービスは明示的に停止すること
- WSL2ではなくWindows側での実行を優先すること
- 一時的なテストサーバーは即座に停止すること (`Ctrl+C`)

## 🚫 禁止事項

1. **WSL2での一時的HTTPサーバー起動**
   - `python -m http.server` の使用禁止
   - 代替案: Windows側でのテスト実行

2. **プロセス放置**
   - バックグラウンドプロセスは必ず終了確認
   - セッション終了前に `ps aux | grep [プロセス名]` で確認

## ✅ 推奨事項

1. **環境統一**
   - Discord Bot: Windows側 (Git Bash)
   - Python API: Windows側 (Anaconda)

2. **ポート管理**
   - 使用前: `netstat -ano | findstr :[ポート番号]`
   - 使用後: プロセス終了確認

3. **テスト実行**
   - Windows環境での実行を優先
   - WSL2使用時は明示的な停止処理

## 📊 ログ管理ルール

### セッション開始時の確認事項

1. **ログ状況確認**
   ```bash
   # Discord Bot ログ確認
   tail -20 "/mnt/c/voice-meeting-bot/node-bot/logs/error.log"
   
   # Python API ログ確認  
   tail -20 "/mnt/c/voice-meeting-bot/python-api/logs/api-error.log"
   
   # ログファイルサイズ確認
   du -sh /mnt/c/voice-meeting-bot/*/logs/
   ```

2. **ログクリーンアップ (必要時)**
   ```bash
   # 大容量ログのバックアップ・リセット
   cp error.log error.log.backup-$(date +%Y%m%d-%H%M%S)
   echo "" > error.log
   ```

### ログファイル種別

- **Discord Bot**: `/node-bot/logs/`
  - `error.log`: エラーログ
  - `combined.log`: 統合ログ
  
- **Python API**: `/python-api/logs/`
  - `api-error.log`: APIエラー
  - `api-access.log`: アクセスログ

### 自動ローテーション設定

- **最大ファイルサイズ**: 5MB (Python API), 10MB (Discord Bot)
- **バックアップ数**: 3個
- **自動削除**: 7日以上経過したファイル
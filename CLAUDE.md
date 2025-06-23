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

3. **🔥 CRITICAL: 依存関係の破壊禁止**
   - **絶対に** 新しい依存関係を既存のpackage.jsonに追加してはいけない
   - **絶対に** npm install を実行してはいけない（動作中のシステムでは）
   - **絶対に** node_modulesを削除・変更してはいけない
   - 新機能追加時は別ブランチで作業し、動作確認後にマージする
   - **理由**: ネイティブ依存関係(@discordjs/opus等)がWSL2環境で再ビルドに失敗し、システム全体が起動不能になる

4. **依存関係変更時の必須手順**
   - 現在のnode_modulesをバックアップ
   - Windowsネイティブ環境での作業を強く推奨
   - WSL2では追加ビルドツール(make, python3-dev等)が必要

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

## 🚨 EC2緊急復旧ガイド

### EC2インスタンス停止時の対処法

**症状:**
- SSH接続不可
- Whisperモデルダウンロード中のプロセス強制終了
- 重いパッケージインストール中の接続切断

**原因:**
- メモリ不足によるプロセス強制終了
- 大容量ダウンロード（100MB以上）でのリソース枯渇

**復旧手順:**

1. **AWSコンソールでインスタンス確認**
   ```
   インスタンスID: i-0e8fd60d7508ac84b
   状態確認: 「停止」→「開始」をクリック
   ⚠️ 「終了」は絶対回避（データ消失）
   ```

2. **新しいIPアドレス取得**
   ```
   EC2起動後→新しいパブリックIP確認
   ~/.ssh/config 更新必須
   ```

3. **SSH設定更新**
   ```bash
   # C:\Users\tench\.ssh\config
   Host find-to-do
       HostName [新しいIP]  # 要更新
       User ec2-user
       IdentityFile C:\Users\tench\.ssh\find-to-do-key2.pem
       ServerAliveInterval 60
   ```

### zeroone_support Bot緊急復旧

**最優先復旧対象:** zeroone_supportは稼働中サービス

```bash
# 1. SSH接続確認
ssh find-to-do

# 2. tmuxセッション復旧
tmux list-sessions
tmux attach-session -t dj-eyes

# 3. セッションが無い場合
tmux new-session -d -s dj-eyes
cd ~/zeroone_support
source venv/bin/activate
python3 main.py

# 4. Ctrl+B, D でデタッチ（セッション維持）
```

### Whisperインストール安全ガイド

**危険なモデル:**
- `base` (139MB) → EC2停止リスク
- `small` (244MB) → 確実にクラッシュ
- `medium`, `large` → 絶対禁止

**安全なモデル:**
```bash
# .env設定必須
echo "WHISPER_MODEL=tiny" >> .env  # 72MB - 安全
```

**インストール時の注意:**
- 100MB以上のダウンロードは危険
- CPU版PyTorchのみ使用
- `--no-cache-dir` オプション必須
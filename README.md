# 🎙️ Discord Voice Meeting Recorder Bot

Discord ボイスチャンネルでの会議を自動録音し、AI による文字起こしと要約を行い、議事録を自動生成するボットです。

## 📋 機能概要

- **🎤 自動音声録音**: Discord ボイスチャンネルの会話を最大3時間まで録音
- **🔤 AI文字起こし**: OpenAI Whisper による高精度な日本語文字起こし
- **📝 AI要約生成**: Ollama (Gemma2:2b) による議事録の自動生成
- **⚙️ リアルタイム処理**: 30分ごとのチャンク処理でリアルタイム文字起こし
- **👥 参加者管理**: 発言者の自動識別と分離録音
- **🛡️ プライバシー保護**: 録音前の同意確認、24時間後の自動ファイル削除

## 🏗️ システム構成

```
Discord Server
┌─────────────────────────────────┐
│  👥 Voice Channel  │ 💬 Text Ch │
│  ├── 参加者A       │ ├── 議事録  │
│  ├── 参加者B       │ ├── 通知    │
│  └── 議事録くん     │ └── コマンド │
└─────────────────────────────────┘
           │                ▲
           │ 音声データ      │ 議事録
           ▼                │
┌─────────────────────────────────┐
│           EC2 Instance          │
├─────────────┬───────────────────┤
│ Node.js Bot │    Python API     │
│ (録音)      │   (文字起こし)     │
│ ポート3000  │    ポート8000      │
└─────────────┴───────────────────┘
```

## 🚀 セットアップ

### 前提条件

- Node.js 18以上
- Python 3.11以上
- Discord Bot Token
- FFmpeg
- Ollama (Gemma2:2bモデル)

### 1. リポジトリクローン

```bash
git clone <repository-url>
cd voice-meeting-bot
```

### 2. Node.js Bot セットアップ

```bash
cd node-bot

# 依存関係インストール
npm install

# 環境変数設定
cp .env.example .env
# .envファイルを編集してDiscord Bot Tokenなどを設定
```

### 3. Python API セットアップ

```bash
cd ../python-api

# 仮想環境作成
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate

# 依存関係インストール
pip install -r requirements.txt

# 環境変数設定
cp .env.example .env
# .envファイルを編集
```

### 4. Ollama セットアップ

```bash
# Ollama インストール
curl -fsSL https://ollama.ai/install.sh | sh

# Gemma2:2b モデルダウンロード
ollama pull gemma2:2b
```

### 5. 起動

```bash
# Python API 起動
cd python-api
uvicorn main:app --host 0.0.0.0 --port 8000

# Node.js Bot 起動 (別ターミナル)
cd node-bot
npm start
```

## 🎮 使用方法

### Discord コマンド

| コマンド | 説明 | 例 |
|---------|------|-----|
| `/record start` | 録音開始 | `/record start title:チーム会議` |
| `/record stop` | 録音停止・議事録生成 | `/record stop` |
| `/record status` | 録音状況確認 | `/record status` |
| `/record settings` | 設定変更 | `/record settings quality:high` |

### 使用フロー

1. **ボイスチャンネルに参加**
2. **`/record start` で録音開始**
3. **会議を実施**
4. **`/record stop` で録音停止**
5. **自動で議事録が生成され、チャンネルに投稿**

## ⚙️ 設定

### Node.js Bot (.env)

```env
# Discord設定
DISCORD_BOT_TOKEN=your_bot_token
CLIENT_ID=your_client_id
DEV_GUILD_ID=your_dev_guild_id  # 開発用

# Python API連携
PYTHON_API_URL=http://localhost:8000

# 録音設定
MAX_RECORDING_DURATION=10800000  # 3時間 (ms)
CHUNK_DURATION=1800000           # 30分 (ms)
TEMP_DIR=./temp
AUTO_DELETE_AFTER_HOURS=24

# 管理者設定
ADMIN_USER_IDS=123456789,987654321
```

### Python API (.env)

```env
# API設定
API_HOST=0.0.0.0
API_PORT=8000

# Whisper設定
WHISPER_MODEL=base
WHISPER_LANGUAGE=ja

# Ollama設定
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma2:2b

# ファイル管理
TEMP_DIR=./temp
OUTPUT_DIR=./output
MAX_FILE_SIZE_MB=100

# データベース
DATABASE_URL=sqlite:///./meetings.db
```

## 📁 プロジェクト構造

```
voice-meeting-bot/
├── node-bot/                   # Discord Bot (Node.js)
│   ├── src/
│   │   ├── recorder.js         # 音声録音クラス
│   │   └── commands.js         # Discord コマンド処理
│   ├── index.js                # メインボットファイル
│   └── package.json
│
├── python-api/                 # 処理API (Python)
│   ├── src/
│   │   ├── transcription.py    # 文字起こし (Whisper)
│   │   ├── summarization.py    # 要約生成 (Ollama)
│   │   ├── meeting_manager.py  # 会議データ管理
│   │   └── models.py           # データベースモデル
│   ├── main.py                 # FastAPI メイン
│   └── requirements.txt
│
├── docs/                       # ドキュメント
└── README.md
```

## 🔧 開発

### デバッグ

```bash
# Node.js Bot (開発モード)
npm run dev

# Python API (デバッグモード)
uvicorn main:app --reload --log-level debug
```

### ログ確認

```bash
# Node.js ログ
tail -f node-bot/logs/combined.log

# Python API ログ
tail -f python-api/logs/api.log
```

## 🛡️ セキュリティ・プライバシー

### データ保護
- 音声ファイルは処理後24時間で自動削除
- ローカル処理（外部API送信なし）
- 録音前に参加者同意確認

### アクセス制御
- 管理者のみ録音開始可能
- チャンネル権限に基づく制限
- ログ監査機能

## 📊 パフォーマンス

### 処理時間目標
- 3時間会議: 25分以内で完了
- リアルタイム文字起こし: 5秒遅延以内
- 要約生成: 2分以内

### システム要件
- CPU: 平均50%以下
- メモリ: 6GB以下
- ディスク: 1時間あたり200MB

## 🚨 トラブルシューティング

### よくある問題

1. **ボットが音声チャンネルに参加できない**
   - ボットの権限確認
   - ボイスチャンネルの接続制限確認

2. **文字起こしが失敗する**
   - Whisperモデルの確認
   - 音声ファイルの形式確認

3. **要約生成が失敗する**
   - Ollama の起動状況確認
   - モデルのダウンロード確認

### ログ確認方法

```bash
# 全体のログ確認
docker-compose logs -f

# 特定のサービスのログ
docker-compose logs -f node-bot
docker-compose logs -f python-api
```

## 📝 ライセンス

MIT License

## 🤝 コントリビューション

プルリクエスト歓迎！バグ報告や機能リクエストは Issues でお願いします。

---

**注意**: このボットは会議の録音を行います。使用前に参加者全員の同意を得てください。
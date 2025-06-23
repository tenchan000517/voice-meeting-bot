# Discord音声議事録ボット システム仕様書

**文書バージョン**: 2.0  
**最終更新日**: 2025年6月23日  
**対象システム**: Voice Meeting Recorder Bot  

---

## 目次

1. [システム概要](#1-システム概要)
2. [ボイスチャット機能仕様](#2-ボイスチャット機能仕様)
3. [データベース仕様](#3-データベース仕様)
4. [容量制限と運用指針](#4-容量制限と運用指針)
5. [技術仕様](#5-技術仕様)
6. [運用・保守](#6-運用保守)

---

## 1. システム概要

### 1.1 システム目的
Discord音声チャンネルでの会議録音、文字起こし、AI要約を自動化し、効率的な議事録作成を支援する。

### 1.2 主要機能
- **音声録音機能**: Discord音声チャンネルの自動録音
- **ボイス監視機能**: ミュート状態での音声チャンネル参加・監視
- **文字起こし機能**: Whisper AIによる音声→テキスト変換
- **AI要約機能**: Ollamaによる会議内容の自動要約
- **自動退出機能**: 参加者不在時の自動退出

### 1.3 アーキテクチャ
```
Discord Bot (Node.js) ←→ Python API Server ←→ SQLite Database
                                ↓
                        Whisper AI + Ollama AI
```

---

## 2. ボイスチャット機能仕様

### 2.1 録音機能 (`/record` コマンド)

#### 2.1.1 基本仕様
- **録音形式**: PCM (48kHz, 16-bit, mono)
- **最大録音時間**: 3時間 (10,800,000ms)
- **チャンク処理**: 30分間隔 (1,800,000ms)
- **同時録音上限**: 制限なし（リソース依存）

#### 2.1.2 コマンド仕様
```
/record start [title]    - 録音開始（オプション：会議タイトル）
/record stop            - 録音停止・処理開始
/record status          - 録音状況確認
/record settings        - 録音設定変更
```

#### 2.1.3 権限要件
- Discord管理者権限 (`Administrator`)
- 環境変数 `ADMIN_USER_IDS` による個別指定可能

#### 2.1.4 動作フロー
1. ユーザーがボイスチャンネル参加
2. `/record start` コマンド実行
3. ボット自動参加（ミュート状態）
4. 参加者音声を個別録音
5. 30分毎に中間処理実行
6. `/record stop` で最終処理・議事録生成

### 2.2 ボイス監視機能 (`/voice` コマンド)

#### 2.2.1 基本仕様
- **参加状態**: 常時ミュート
- **監視間隔**: 5秒
- **自動退出条件**: ボット以外の参加者が0人
- **独立動作**: 録音機能と完全分離

#### 2.2.2 コマンド仕様
```
/voice join             - ボイスチャンネル参加（ミュート）
/voice leave            - ボイスチャンネル退出
/voice status           - 接続状況確認
/voice autoleave <bool> - 自動退出機能オン/オフ
```

#### 2.2.3 自動退出ロジック
```javascript
// 5秒間隔で実行
const humanMembers = channel.members.filter(member => !member.user.bot);
if (humanMembers.size === 0) {
    await leaveChannel('Auto-leave: No human participants');
}
```

#### 2.2.4 権限要件
- Discord管理者権限 (`Administrator`)
- ボイスチャンネル接続権限 (`Connect`, `Speak`)

---

## 3. データベース仕様

### 3.1 データベース基本情報
- **タイプ**: SQLite (開発・小規模運用) / PostgreSQL (本格運用)
- **ファイル場所**: `./meetings.db`
- **接続方式**: SQLAlchemy ORM
- **文字エンコーディング**: UTF-8

### 3.2 テーブル構造

#### 3.2.1 meetings テーブル（会議マスタ）
```sql
CREATE TABLE meetings (
    meeting_id VARCHAR PRIMARY KEY,        -- 会議ID（一意識別子）
    discord_guild_id VARCHAR NOT NULL,    -- DiscordサーバーID
    discord_channel_id VARCHAR NOT NULL,  -- DiscordチャンネルID
    meeting_title VARCHAR,                -- 会議タイトル（任意）
    start_time DATETIME,                  -- 開始時刻
    end_time DATETIME,                    -- 終了時刻
    duration_minutes INTEGER,             -- 会議時間（分）
    status VARCHAR DEFAULT 'recording',   -- ステータス
    participants TEXT,                    -- 参加者リスト（JSON）
    created_at DATETIME,                  -- 作成日時
    updated_at DATETIME                   -- 更新日時
);
```

#### 3.2.2 transcripts テーブル（文字起こし）
```sql
CREATE TABLE transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自動連番
    meeting_id VARCHAR NOT NULL,          -- 会議ID（外部キー）
    speaker_id VARCHAR NOT NULL,          -- 発話者ID
    speaker_name VARCHAR,                 -- 発話者名
    text TEXT NOT NULL,                   -- 文字起こしテキスト
    confidence FLOAT,                     -- 信頼度（0.0-1.0）
    start_time DATETIME NOT NULL,         -- 発話開始時刻
    end_time DATETIME,                    -- 発話終了時刻
    duration_seconds FLOAT,               -- 発話時間（秒）
    audio_file_path VARCHAR,              -- 音声ファイルパス
    created_at DATETIME                   -- 作成日時
);
```

#### 3.2.3 summaries テーブル（AI要約）
```sql
CREATE TABLE summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自動連番
    meeting_id VARCHAR NOT NULL,          -- 会議ID（外部キー）
    summary_type VARCHAR DEFAULT 'full',  -- 要約タイプ
    content TEXT NOT NULL,                -- 要約内容
    generated_by VARCHAR DEFAULT 'ollama', -- 生成AI
    generated_at DATETIME,                -- 生成日時
    file_path VARCHAR                     -- ファイルパス
);
```

#### 3.2.4 processing_status テーブル（処理状況）
```sql
CREATE TABLE processing_status (
    meeting_id VARCHAR PRIMARY KEY,       -- 会議ID
    transcription_status VARCHAR,         -- 文字起こし状況
    transcription_progress FLOAT,         -- 進捗（0.0-1.0）
    summarization_status VARCHAR,         -- 要約処理状況
    error_message TEXT,                   -- エラーメッセージ
    processing_start DATETIME,            -- 処理開始時刻
    processing_end DATETIME,              -- 処理完了時刻
    updated_at DATETIME,                  -- 更新日時
    total_chunks INTEGER DEFAULT 0,       -- 総チャンク数
    completed_chunks INTEGER DEFAULT 0    -- 完了チャンク数
);
```

#### 3.2.5 audio_files テーブル（音声ファイル管理）
```sql
CREATE TABLE audio_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- 自動連番
    meeting_id VARCHAR NOT NULL,          -- 会議ID（外部キー）
    file_path VARCHAR NOT NULL,           -- ファイルパス
    file_size_bytes INTEGER,              -- ファイルサイズ（バイト）
    duration_seconds FLOAT,               -- 音声時間（秒）
    format VARCHAR,                       -- ファイル形式
    created_at DATETIME,                  -- 作成日時
    scheduled_deletion DATETIME,          -- 削除予定日時
    deleted BOOLEAN DEFAULT FALSE         -- 削除フラグ
);
```

### 3.3 インデックス設計
```sql
-- パフォーマンス向上のための推奨インデックス
CREATE INDEX idx_meetings_guild_channel ON meetings(discord_guild_id, discord_channel_id);
CREATE INDEX idx_meetings_status ON meetings(status);
CREATE INDEX idx_transcripts_meeting ON transcripts(meeting_id);
CREATE INDEX idx_transcripts_speaker ON transcripts(speaker_id);
CREATE INDEX idx_summaries_meeting ON summaries(meeting_id);
CREATE INDEX idx_audio_files_meeting ON audio_files(meeting_id);
CREATE INDEX idx_audio_files_deletion ON audio_files(scheduled_deletion, deleted);
```

---

## 4. 容量制限と運用指針

### 4.1 容量制限

#### 4.1.1 システム制限
| 項目 | 制限値 | 備考 |
|------|--------|------|
| 最大録音時間 | 3時間/会議 | 設定変更可能 |
| 音声ファイル最大サイズ | 100MB/ファイル | アップロード制限 |
| チャンク処理間隔 | 30分 | メモリ最適化 |
| 同時録音チャンネル数 | 制限なし | リソース依存 |

#### 4.1.2 データベース制限
| 項目 | SQLite制限 | 実用推奨値 |
|------|------------|------------|
| データベース最大サイズ | 281TB | 1TB |
| テーブル最大レコード数 | 2^64 | 1億レコード |
| TEXT型フィールド | 1GB/フィールド | 10MB/フィールド |
| 同時接続数 | 制限なし | 100接続 |

### 4.2 容量使用量予測

#### 4.2.1 会議あたりの使用量
```
1時間会議の場合:
- 音声ファイル: 200MB
- データベース: 50KB（文字起こし含む）
- 一時ファイル: 400MB（処理中のみ）

3時間会議の場合:
- 音声ファイル: 600MB
- データベース: 150KB
- 一時ファイル: 1.2GB（処理中のみ）
```

#### 4.2.2 月間使用量予測（標準的な使用）
```
前提条件:
- 日次会議数: 5回
- 平均会議時間: 1時間
- 月間稼働日: 30日

計算結果:
- 月間会議数: 150回
- 音声ファイル: 30GB/月（クリーンアップ前）
- データベース: 7.5MB/月
- 実効使用量: 200MB（24時間クリーンアップ後）
```

### 4.3 自動クリーンアップ機能

#### 4.3.1 設定値
```bash
# 環境変数設定
AUTO_CLEANUP_HOURS=24          # 音声ファイル保持時間
MEETING_RETENTION_DAYS=30      # 会議データ保持期間
LOG_RETENTION_DAYS=7           # ログファイル保持期間
MAX_FILE_SIZE_MB=100           # アップロード最大サイズ
```

#### 4.3.2 クリーンアップ順序
1. 期限切れ音声ファイル削除
2. 関連する要約データ削除
3. 文字起こしデータ削除
4. 処理状況データ削除
5. 会議マスタデータ削除
6. ログファイルローテーション

### 4.4 運用推奨値

#### 4.4.1 安全な運用範囲
| 指標 | 推奨値 | 警告レベル | 危険レベル |
|------|--------|------------|------------|
| 日次会議数 | ≤10回 | >20回 | >50回 |
| 同時録音数 | ≤3チャンネル | >5チャンネル | >10チャンネル |
| ディスク使用量 | <1GB | >5GB | >10GB |
| データベースサイズ | <100MB | >1GB | >10GB |

#### 4.4.2 スケールアップ検討条件
- 日次会議数が20回を超過
- 同時録音が5チャンネルを超過
- 月間データ保持が必要
- 高可用性が要求される場合

---

## 5. 技術仕様

### 5.1 システム要件

#### 5.1.1 ハードウェア要件
```
最小構成:
- CPU: 2コア以上
- メモリ: 4GB以上
- ディスク: 20GB以上（SSD推奨）
- ネットワーク: 10Mbps以上

推奨構成:
- CPU: 4コア以上
- メモリ: 8GB以上
- ディスク: 100GB以上（SSD）
- ネットワーク: 100Mbps以上
```

#### 5.1.2 ソフトウェア要件
```
Node.js環境:
- Node.js: 18.x以上
- npm: 9.x以上
- FFmpeg: 6.x以上

Python環境:
- Python: 3.9以上
- PyTorch: 2.x以上
- SQLAlchemy: 2.x以上
```

### 5.2 依存関係

#### 5.2.1 Node.js依存関係
```json
{
  "discord.js": "^14.x",
  "@discordjs/voice": "^0.16.x",
  "@discordjs/opus": "^0.9.x",
  "prism-media": "^1.3.x",
  "winston": "^3.x",
  "axios": "^1.x",
  "dotenv": "^16.x"
}
```

#### 5.2.2 Python依存関係
```txt
fastapi>=0.104.0
uvicorn>=0.24.0
sqlalchemy>=2.0.0
whisper-openai>=20231117
torch>=2.1.0
ollama>=0.1.0
python-multipart>=0.0.6
python-dotenv>=1.0.0
```

### 5.3 環境変数設定

#### 5.3.1 Discord Bot設定
```bash
# Discord設定
DISCORD_BOT_TOKEN=your_bot_token_here
DEV_GUILD_ID=your_guild_id_for_testing

# API設定
PYTHON_API_URL=http://localhost:8000
API_TIMEOUT=30000

# 録音設定
TEMP_DIR=./temp
CHUNK_DURATION=1800000
MAX_RECORDING_DURATION=10800000

# ログ設定
LOG_LEVEL=info
```

#### 5.3.2 Python API設定
```bash
# API設定
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=false

# データベース設定
DATABASE_URL=sqlite:///./meetings.db

# AI設定
WHISPER_MODEL=base
WHISPER_LANGUAGE=ja
WHISPER_DEVICE=cpu
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma2:2b

# ファイル設定
MAX_FILE_SIZE_MB=100
AUTO_CLEANUP_HOURS=24
MEETING_RETENTION_DAYS=30

# セキュリティ設定
MAX_CONCURRENT_TRANSCRIPTIONS=3
RATE_LIMIT_PER_MINUTE=10
```

---

## 6. 運用・保守

### 6.1 起動・停止手順

#### 6.1.1 サービス起動順序
```bash
# 1. Python API起動
cd /path/to/python-api
conda activate voice-meeting-bot
python main.py

# 2. Discord Bot起動
cd /path/to/node-bot
npm start
```

#### 6.1.2 正常性確認
```bash
# API疎通確認
curl http://localhost:8000/health

# Discord Bot確認
# Discord上で /ping コマンド実行
```

### 6.2 監視項目

#### 6.2.1 システム監視
- CPU使用率: <80%
- メモリ使用率: <80%
- ディスク使用率: <90%
- ネットワーク接続状況

#### 6.2.2 アプリケーション監視
- Discord Bot接続状況
- Python API応答時間: <5秒
- データベース接続状況
- 音声処理キュー状況

### 6.3 ログ管理

#### 6.3.1 ログファイル場所
```
Discord Bot:
- /node-bot/logs/error.log
- /node-bot/logs/combined.log

Python API:
- /python-api/logs/api-error.log
- /python-api/logs/api-access.log
```

#### 6.3.2 ログローテーション設定
- 最大ファイルサイズ: 5MB
- バックアップファイル数: 3個
- 自動削除期間: 7日

### 6.4 バックアップ戦略

#### 6.4.1 バックアップ対象
- データベースファイル: 日次
- 設定ファイル: 変更時
- 重要音声ファイル: 必要に応じて

#### 6.4.2 復旧手順
1. サービス停止
2. データベースファイル復元
3. 設定ファイル復元
4. サービス再起動
5. 正常性確認

### 6.5 トラブルシューティング

#### 6.5.1 よくある問題と対処法

**Discord Bot接続エラー**
```
原因: トークン期限切れ、権限不足
対処: トークン更新、権限確認
```

**音声録音失敗**
```
原因: ディスク容量不足、権限不足
対処: 容量確保、チャンネル権限確認
```

**文字起こし処理エラー**
```
原因: Whisperモデル読み込み失敗、メモリ不足
対処: モデル再インストール、メモリ増設
```

**データベース接続エラー**
```
原因: ファイル権限、同時接続数超過
対処: 権限修正、接続プール設定
```

---

## 7. 更新履歴

| バージョン | 日付 | 更新内容 | 担当者 |
|------------|------|----------|--------|
| 1.0 | 2025-06-23 | 初版作成（録音機能） | System |
| 2.0 | 2025-06-23 | ボイス監視機能追加、データベース仕様詳細化 | System |

---

## 8. 付録

### 8.1 API仕様書
- [REST API Documentation](./API_SPECIFICATION.md)

### 8.2 セットアップガイド
- [Installation Guide](./INSTALLATION.md)

### 8.3 開発ガイド
- [Development Guide](./DEVELOPMENT.md)

---

**文書終了**
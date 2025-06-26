# Voice Meeting Bot: マイクロサービス設計最適化計画書

**作成日**: 2025-06-26  
**対象**: 引き継ぎエンジニア向け実装ガイド  
**実装時間**: 4-6時間  
**難易度**: 中級

## 🎯 プロジェクト概要

### 目的
現在の重複リソース問題を解決し、ローカル（Python API）+ EC2（Discord Bot）の最適な分散アーキテクチャを構築する。

### 運用方針
- **Python API**: ローカル環境（重い処理: Whisper, Ollama, DB操作）
- **Discord Bot**: EC2環境（軽量処理: WebSocket維持, API中継）

---

## 📊 現状分析

### 🚨 現在の問題点

#### 1. 重複リソース問題
```
voice-meeting-bot/
├── venv/              # ❌ 重複1: 使用されていない
├── meetings.db        # ❌ 重複2: 非同期リスク
├── output/            # ❌ 重複3: データ散逸
├── temp/              # ❌ 重複4: クリーンアップ困難
├── python-api/
│   ├── venv/          # ✅ 実際に使用中
│   ├── meetings.db    # ✅ 実際のDB
│   ├── output/        # ✅ 実際の出力
│   └── temp/          # ✅ 実際の一時ファイル
└── node-bot/
    ├── meetings.db    # ❌ 重複5: 古いデータ
    ├── output/        # ❌ 重複6: 空ディレクトリ
    └── temp/          # ❌ 重複7: 未使用
```

#### 2. 仮想環境の混在
- Linux venv（WSL2で作成）vs Windows実行環境
- モジュール不整合（ollama未インストール等）

#### 3. データベース不整合
- 複数のmeetings.dbファイル存在
- スキーマバージョン不一致の可能性

---

## 🎯 目標アーキテクチャ

```
voice-meeting-bot/
├── README.md                     # プロジェクト概要
├── DEPLOYMENT_GUIDE.md          # デプロイ手順
├── docker-compose.yml           # 開発環境用
├── shared/                      # 共有リソース
│   ├── database-schema.sql      # DBスキーマ定義
│   ├── api-spec.yml            # API仕様書
│   └── config/
│       ├── production.env      # 本番環境設定
│       └── development.env     # 開発環境設定
├── python-api/                 # ローカル重処理サーバー
│   ├── venv/                   # Python専用仮想環境
│   ├── requirements.txt        # Python依存関係
│   ├── data/                   # データ管理
│   │   └── meetings.db        # メインデータベース
│   ├── output/                 # 処理結果出力
│   ├── temp/                   # 一時ファイル
│   ├── logs/                   # API専用ログ
│   ├── src/                    # ソースコード
│   └── tests/                  # テストファイル
└── node-bot/                   # EC2軽量ボット
    ├── package.json            # Node.js依存関係
    ├── node_modules/           # Node依存関係
    ├── logs/                   # ボット専用ログ
    ├── config/                 # ボット設定
    ├── src/                    # ソースコード
    └── tests/                  # テストファイル
```

---

## 📋 実装手順

### Phase 1: バックアップ・準備 (30分)

#### 1.1 現状バックアップ
```bash
# プロジェクトルートで実行
cp -r voice-meeting-bot voice-meeting-bot-backup-$(date +%Y%m%d-%H%M%S)

# 重要データの確認
ls -la python-api/data/meetings.db
ls -la python-api/output/
ls -la node-bot/logs/
```

#### 1.2 動作確認
```bash
# Python API動作確認
cd python-api
python main.py --test

# Discord Bot動作確認  
cd ../node-bot
npm test
```

### Phase 2: 新構造作成 (60分)

#### 2.1 共有リソース作成
```bash
# プロジェクトルートで実行
mkdir -p shared/{config,schemas}

# データベーススキーマ出力
cd python-api
python -c "
from src.models import Base
from sqlalchemy import create_engine
engine = create_engine('sqlite:///data/meetings.db')
with open('../shared/schemas/database-schema.sql', 'w') as f:
    for table in Base.metadata.tables.values():
        f.write(str(table.create_engine.compile(engine)) + ';\\n')
"
```

#### 2.2 Python API構造最適化
```bash
cd python-api

# データディレクトリ作成・移動
mkdir -p data
if [ -f meetings.db ]; then mv meetings.db data/; fi

# ログディレクトリ整理
mkdir -p logs
# 既存のlogsディレクトリがあれば何もしない

# テストディレクトリ作成
mkdir -p tests
```

#### 2.3 Node Bot構造最適化
```bash
cd node-bot

# 設定ディレクトリ作成
mkdir -p config

# テストディレクトリ作成
mkdir -p tests

# 不要なファイル削除確認（重複リソース）
if [ -f meetings.db ]; then
    echo "Warning: node-bot/meetings.db found - should be removed"
fi
```

### Phase 3: 重複リソース削除 (45分)

#### 3.1 安全な削除手順
```bash
# プロジェクトルートで実行

# 1. 親レベルの重複ファイル確認・削除
if [ -d venv ] && [ -d python-api/venv ]; then
    echo "Removing duplicate parent venv..."
    rm -rf venv
fi

if [ -f meetings.db ] && [ -f python-api/data/meetings.db ]; then
    echo "Removing duplicate parent meetings.db..."
    rm -f meetings.db
fi

if [ -d output ] && [ -d python-api/output ]; then
    echo "Removing duplicate parent output..."
    rm -rf output
fi

if [ -d temp ] && [ -d python-api/temp ]; then
    echo "Removing duplicate parent temp..."
    rm -rf temp
fi

# 2. node-bot内の重複削除
cd node-bot
if [ -f meetings.db ]; then
    echo "Removing node-bot meetings.db..."
    rm -f meetings.db
fi

if [ -d output ] && [ ! "$(ls -A output)" ]; then
    echo "Removing empty node-bot output..."
    rm -rf output
fi

if [ -d temp ] && [ ! "$(ls -A temp)" ]; then
    echo "Removing empty node-bot temp..."
    rm -rf temp
fi
```

### Phase 4: 設定ファイル更新 (60分)

#### 4.1 Python API設定更新
```python
# python-api/src/config.py 作成
import os
from pathlib import Path

# プロジェクトルートとデータパス
PROJECT_ROOT = Path(__file__).parent.parent.parent
PYTHON_API_ROOT = Path(__file__).parent.parent

# データベース設定
DATABASE_URL = f"sqlite:///{PYTHON_API_ROOT}/data/meetings.db"

# ディレクトリ設定
OUTPUT_DIR = PYTHON_API_ROOT / "output"
TEMP_DIR = PYTHON_API_ROOT / "temp"
LOG_DIR = PYTHON_API_ROOT / "logs"

# API設定
API_HOST = os.getenv("API_HOST", "localhost")
API_PORT = int(os.getenv("API_PORT", 8001))
```

#### 4.2 既存ファイルのパス修正
```bash
# models.py内のDBパス修正が必要
cd python-api/src
```

#### 4.3 Node Bot設定更新
```javascript
// node-bot/config/config.js 作成
const path = require('path');

module.exports = {
    // API接続設定
    pythonApi: {
        host: process.env.PYTHON_API_HOST || 'localhost',
        port: process.env.PYTHON_API_PORT || 8001,
        baseUrl: process.env.PYTHON_API_URL || 'http://localhost:8001'
    },
    
    // Discord設定
    discord: {
        token: process.env.DISCORD_TOKEN,
        guildId: process.env.DISCORD_GUILD_ID,
        clientId: process.env.DISCORD_CLIENT_ID
    },
    
    // ログ設定
    logging: {
        level: process.env.LOG_LEVEL || 'info',
        directory: path.join(__dirname, '..', 'logs')
    }
};
```

### Phase 5: 仮想環境再構築 (45分)

#### 5.1 Python仮想環境クリーンアップ
```bash
cd python-api

# 既存仮想環境削除（Windowsの場合）
if [ -d venv ]; then
    rm -rf venv
fi

# Windows環境での新仮想環境作成
python -m venv venv

# 仮想環境アクティベート（Windows）
source venv/Scripts/activate  # Git Bash
# または
venv\Scripts\activate.bat     # Command Prompt

# 依存関係インストール
pip install --upgrade pip
pip install -r requirements.txt

# ollama専用インストール確認
pip install ollama>=0.5.0
```

#### 5.2 Node.js依存関係整理
```bash
cd node-bot

# node_modules再構築
rm -rf node_modules package-lock.json
npm install

# 依存関係監査
npm audit fix
```

### Phase 6: テスト・検証 (60分)

#### 6.1 Python API単体テスト
```bash
cd python-api
source venv/Scripts/activate

# データベース接続テスト
python -c "
from src.models import Base
from sqlalchemy import create_engine
engine = create_engine('sqlite:///data/meetings.db')
Base.metadata.create_all(engine)
print('Database connection: OK')
"

# API起動テスト
python main.py &
API_PID=$!
sleep 5

# ヘルスチェック
curl http://localhost:8001/health
kill $API_PID
```

#### 6.2 Discord Bot単体テスト
```bash
cd node-bot

# 設定テスト
node -e "
const config = require('./config/config.js');
console.log('Config loaded:', config.pythonApi);
"

# 接続テスト（実際のDiscordトークンが必要）
# npm test
```

#### 6.3 統合テスト
```bash
# Python API起動
cd python-api
source venv/Scripts/activate
python main.py &
API_PID=$!

# Discord Bot起動
cd ../node-bot
npm start &
BOT_PID=$!

# テスト実行
sleep 10
curl http://localhost:8001/meetings
curl http://localhost:8001/status

# プロセス終了
kill $API_PID $BOT_PID
```

---

## 🔍 検証チェックリスト

### ✅ 構造検証
- [ ] 重複ファイル・ディレクトリの完全削除
- [ ] 新しいディレクトリ構造の作成
- [ ] 設定ファイルの正常配置

### ✅ 機能検証
- [ ] Python API単独起動
- [ ] Discord Bot単独起動
- [ ] API間通信の確認
- [ ] データベース読み書き動作
- [ ] ファイル出力の確認

### ✅ 環境検証
- [ ] Python仮想環境の独立動作
- [ ] Node.js依存関係の正常インストール
- [ ] Windows/Linux環境での動作確認

---

## 🚨 トラブルシューティング

### Python関連問題

#### モジュール未見つかりエラー
```bash
# 仮想環境の再アクティベート
cd python-api
source venv/Scripts/activate
pip install -r requirements.txt
```

#### データベースアクセスエラー
```bash
# データベースファイルの存在確認
ls -la python-api/data/meetings.db

# 権限確認
chmod 664 python-api/data/meetings.db
```

### Node.js関連問題

#### 依存関係エラー
```bash
cd node-bot
rm -rf node_modules package-lock.json
npm install
```

#### API接続エラー
```bash
# Python APIの起動確認
curl http://localhost:8001/health

# 設定ファイル確認
cat node-bot/config/config.js
```

---

## 🔄 ロールバック手順

### 緊急時の復旧
```bash
# バックアップからの復旧
rm -rf voice-meeting-bot
cp -r voice-meeting-bot-backup-YYYYMMDD-HHMMSS voice-meeting-bot
cd voice-meeting-bot

# 即座にサービス復旧
cd python-api && python main.py &
cd ../node-bot && npm start &
```

### 部分ロールバック
特定の問題が発生した場合の段階的復旧手順を Phase 逆順で実行。

---

## 📚 参考資料

### 設定ファイル例
- `shared/config/production.env`
- `shared/config/development.env`  
- `python-api/src/config.py`
- `node-bot/config/config.js`

### API仕様
- `shared/api-spec.yml` - REST API仕様
- エンドポイント一覧とレスポンス形式

### デプロイメント
- `DEPLOYMENT_GUIDE.md` - EC2デプロイ手順
- `docker-compose.yml` - 開発環境セットアップ

---

## ⚠️ 重要な注意事項

1. **バックアップ必須**: 作業前に必ず完全バックアップを取得
2. **段階的実行**: Phaseごとに動作確認を実施
3. **環境依存**: Windows/WSL2環境の違いに注意
4. **データ保護**: meetings.dbとoutput/は特に慎重に扱う
5. **サービス停止**: 作業中はサービス停止状態を維持

---

## 📞 エスカレーション

問題発生時の連絡先・リソース：
- CLAUDE.md内の制約事項確認
- ログファイルの詳細確認（`logs/`ディレクトリ）
- GitHub Issues作成時のテンプレート使用

**作業完了後**: 本ドキュメントの実施結果を`REFACTORING_COMPLETION_REPORT.md`として記録することを推奨。
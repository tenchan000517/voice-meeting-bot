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
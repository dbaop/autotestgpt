from dotenv import load_dotenv
import os
from pathlib import Path
from urllib.parse import quote_plus

load_dotenv(Path(__file__).parent / ".env")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_instance_path = os.path.join(BASE_DIR, "instance")
os.makedirs(_instance_path, exist_ok=True)


class Config:
    MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY", "")
    DOUBAO_API_BASE = os.getenv("DOUBAO_API_BASE", "https://ark.cn-beijing.volces.com/api/v3")
    DOUBAO_VISION_MODEL = os.getenv("DOUBAO_VISION_MODEL", "doubao-seed-1-6-vision-250815")
    SERVER_PORT = int(os.getenv("SERVER_PORT", 8000))
    WORKSPACE = "./workspace"
    REPORT_DIR = "./report"

    # Feature flag: enable conversation-driven test flow (instead of rigid pipeline)
    CONVERSATION_FLOW_ENABLED = os.getenv("CONVERSATION_FLOW_ENABLED", "false").lower() == "true"

    DB_HOST = os.getenv("DB_HOST", "")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "autotestgpt")

    # Prefer DATABASE_URI when set; otherwise build MySQL URI from DB_* settings.
    _raw_database_uri = (os.getenv("DATABASE_URI", "") or "").strip()
    if _raw_database_uri:
        DATABASE_URI = _raw_database_uri
    elif DB_HOST and DB_USER:
        DATABASE_URI = (
            f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD)}@"
            f"{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
        )
    else:
        DATABASE_URI = f"sqlite:///{os.path.join(_instance_path, 'autotestgpt.db')}"

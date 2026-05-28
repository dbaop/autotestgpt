from dotenv import load_dotenv
import os
from urllib.parse import quote_plus

load_dotenv()


class Config:
    MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    SERVER_PORT = int(os.getenv("SERVER_PORT", 8000))
    WORKSPACE = "./workspace"
    REPORT_DIR = "./report"

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
        DATABASE_URI = "sqlite:///autotestgpt.db"

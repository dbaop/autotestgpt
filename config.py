from dotenv import load_dotenv
import os
from urllib.parse import quote_plus

load_dotenv()

class Config:
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-test")  # 测试用
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-test")      # 测试用
    SERVER_PORT = int(os.getenv("SERVER_PORT", 8000))
    WORKSPACE = "./workspace"
    REPORT_DIR = "./report"
    
    # 使用SQLite数据库（简化配置）
    DATABASE_URI = os.getenv("DATABASE_URI", "sqlite:///autotestgpt.db")
    
    # MySQL 数据库配置（备用）
    if DATABASE_URI.startswith("mysql"):
        DB_HOST = os.getenv("DB_HOST", "localhost")
        DB_PORT = int(os.getenv("DB_PORT", 3306))
        DB_USER = os.getenv("DB_USER", "root")
        DB_PASSWORD = os.getenv("DB_PASSWORD", "")
        DB_NAME = os.getenv("DB_NAME", "autotestgpt")
        DATABASE_URI = f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
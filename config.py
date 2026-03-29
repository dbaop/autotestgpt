from dotenv import load_dotenv
import os
from urllib.parse import quote_plus

load_dotenv()

class Config:
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    SERVER_PORT = int(os.getenv("SERVER_PORT", 8000))
    WORKSPACE = "./workspace"
    REPORT_DIR = "./report"
    
    # MySQL 数据库配置
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "autotestgpt")
    
    # 数据库连接字符串（对密码进行 URL 编码）
    DATABASE_URI = f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
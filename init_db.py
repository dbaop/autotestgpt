from models import init_db, Base
from config import Config
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

def create_database():
    encoded_password = quote_plus(Config.DB_PASSWORD)
    engine = create_engine(f"mysql+pymysql://{Config.DB_USER}:{encoded_password}@{Config.DB_HOST}:{Config.DB_PORT}/?charset=utf8mb4")
    
    with engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {Config.DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        print(f"数据库 {Config.DB_NAME} 创建成功")

def create_tables():
    engine = create_engine(Config.DATABASE_URI, echo=True)
    Base.metadata.create_all(engine)
    print("数据表创建成功")

if __name__ == "__main__":
    print("开始初始化数据库...")
    create_database()
    create_tables()
    print("数据库初始化完成！")
#!/usr/bin/env python3
"""
数据库初始化脚本
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from models import db
from config import Config
from flask import Flask

def create_app():
    """创建Flask应用"""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_recycle': 300,
        'pool_pre_ping': True,
    }
    
    db.init_app(app)
    return app

def init_database():
    """初始化数据库"""
    print("正在初始化数据库...")
    
    # 创建Flask应用
    app = create_app()
    
    with app.app_context():
        # 创建所有表
        db.create_all()
        print("✓ 数据库表创建成功")
        
        # 创建默认项目
        from models import Project
        default_project = Project.query.filter_by(name="默认项目").first()
        if not default_project:
            default_project = Project(
                name="默认项目",
                description="AutoTestGPT 默认测试项目",
                config={
                    "environment": "development",
                    "base_url": "http://localhost:8000",
                    "timeout": 30
                }
            )
            db.session.add(default_project)
            db.session.commit()
            print("✓ 默认项目创建成功")
        
        print("数据库初始化完成！")
        print(f"数据库连接: {Config.DATABASE_URI}")

def check_database_connection():
    """检查数据库连接"""
    print("检查数据库连接...")
    
    app = create_app()
    with app.app_context():
        try:
            # 尝试执行一个简单的查询
            db.session.execute("SELECT 1")
            print("✓ 数据库连接正常")
            return True
        except Exception as e:
            print(f"✗ 数据库连接失败: {e}")
            return False

def create_workspace_dirs():
    """创建工作空间目录"""
    print("创建工作空间目录...")
    
    dirs = [
        Config.WORKSPACE,
        Config.REPORT_DIR,
        os.path.join(Config.WORKSPACE, "scripts"),
        os.path.join(Config.WORKSPACE, "logs"),
        os.path.join(Config.WORKSPACE, "temp"),
        os.path.join(Config.REPORT_DIR, "html"),
        os.path.join(Config.REPORT_DIR, "json"),
        os.path.join(Config.REPORT_DIR, "allure"),
    ]
    
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)
        print(f"✓ 创建目录: {dir_path}")
    
    print("工作空间目录创建完成！")

if __name__ == "__main__":
    print("=" * 50)
    print("AutoTestGPT 数据库初始化工具")
    print("=" * 50)
    
    # 检查数据库连接
    if not check_database_connection():
        print("\n请检查数据库配置:")
        print(f"  主机: {Config.DB_HOST}")
        print(f"  端口: {Config.DB_PORT}")
        print(f"  数据库: {Config.DB_NAME}")
        print(f"  用户: {Config.DB_USER}")
        sys.exit(1)
    
    # 创建工作空间目录
    create_workspace_dirs()
    
    # 初始化数据库
    init_database()
    
    print("\n" + "=" * 50)
    print("初始化完成！")
    print("=" * 50)
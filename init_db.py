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
from sqlalchemy import text

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

def seed_model_configs():
    """种子数据：可用的 LLM 模型配置。"""
    from models import ModelConfig

    defaults = [
        {
            "name": "MiniMax",
            "model_name": "minimax/abab6.5s-chat",
            "provider": "minimax",
            "api_base": "https://api.minimax.chat/v1",
            "api_key_env": "MINIMAX_API_KEY",
            "sort_order": 1,
        },
        {
            "name": "DeepSeek",
            "model_name": "deepseek/deepseek-chat",
            "provider": "deepseek",
            "api_base": None,
            "api_key_env": "DEEPSEEK_API_KEY",
            "sort_order": 2,
        },
        {
            "name": "Doubao Vision (火山引擎)",
            "model_name": "openai/doubao-seed-1-6-vision-250815",
            "provider": "volcano",
            "api_base": "https://ark.cn-beijing.volces.com/api/v3",
            "api_key_env": "DOUBAO_API_KEY",
            "sort_order": 3,
        },
    ]

    for cfg in defaults:
        existing = ModelConfig.query.filter_by(name=cfg["name"]).first()
        if not existing:
            db.session.add(ModelConfig(**cfg))
            print(f"[OK] 模型配置创建: {cfg['name']}")
        else:
            # 更新已有配置
            for k, v in cfg.items():
                setattr(existing, k, v)
            print(f"[OK] 模型配置更新: {cfg['name']}")

    db.session.commit()


def seed_agent_configs():
    """种子数据：Agent 配置 — 每个 agent_type 关联默认模型。"""
    from models import AgentConfig, ModelConfig

    # 查找模型配置
    minimax = ModelConfig.query.filter_by(name="MiniMax").first()
    deepseek = ModelConfig.query.filter_by(name="DeepSeek").first()

    defaults = [
        {
            "agent_type": "req_agent",
            "model_config_id": minimax.id if minimax else None,
            "model_name": "minimax/abab6.5s-chat",
            "temperature": 0.1,
            "max_tokens": 4000,
        },
        {
            "agent_type": "browser_agent",
            "model_config_id": deepseek.id if deepseek else None,
            "model_name": "deepseek/deepseek-chat",
            "temperature": 0.1,
            "max_tokens": 4000,
        },
        {
            "agent_type": "case_agent",
            "model_config_id": minimax.id if minimax else None,
            "model_name": "minimax/abab6.5s-chat",
            "temperature": 0.1,
            "max_tokens": 4000,
        },
        {
            "agent_type": "code_agent",
            "model_config_id": deepseek.id if deepseek else None,
            "model_name": "deepseek/deepseek-chat",
            "temperature": 0.1,
            "max_tokens": 4000,
        },
        {
            "agent_type": "exec_agent",
            "model_config_id": minimax.id if minimax else None,
            "model_name": "minimax/abab6.5s-chat",
            "temperature": 0.1,
            "max_tokens": 4000,
        },
        {
            "agent_type": "review_agent",
            "model_config_id": deepseek.id if deepseek else None,
            "model_name": "deepseek/deepseek-chat",
            "temperature": 0.1,
            "max_tokens": 4000,
        },
    ]

    for cfg in defaults:
        existing = AgentConfig.query.filter_by(agent_type=cfg["agent_type"]).first()
        if not existing:
            db.session.add(AgentConfig(**cfg))
            print(f"[OK] Agent 配置创建: {cfg['agent_type']} → {cfg['model_name']}")
        else:
            # 更新已有配置
            for k, v in cfg.items():
                setattr(existing, k, v)
            print(f"[OK] Agent 配置更新: {cfg['agent_type']} → {cfg['model_name']}")

    db.session.commit()


def _run_migrations():
    """为已有表补全新列（db.create_all 不会修改已有表结构）。"""
    from sqlalchemy import inspect
    from sqlalchemy.exc import OperationalError, ProgrammingError

    inspector = inspect(db.engine)

    # --- agent_configs: 补全 model_config_id 列 ---
    if "agent_configs" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("agent_configs")}
        if "model_config_id" not in cols:
            try:
                db.session.execute(text(
                    "ALTER TABLE agent_configs ADD COLUMN model_config_id INT DEFAULT NULL"
                ))
                db.session.commit()
                print("[MIGRATION] agent_configs.model_config_id 列已添加")
            except (OperationalError, ProgrammingError) as e:
                db.session.rollback()
                print(f"[MIGRATION] agent_configs.model_config_id 添加失败（可能已存在）: {e}")


def init_database():
    """初始化数据库"""
    print("正在初始化数据库...")
    
    # 创建Flask应用
    app = create_app()
    
    with app.app_context():
        # 创建所有表（新表会被创建，但已有表的列变更不会被处理）
        db.create_all()
        print("[OK] 数据库表创建成功")

        # 迁移：为已有表补全新列
        _run_migrations()

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
            print("[OK] 默认项目创建成功")

        # 种子数据：模型配置
        seed_model_configs()

        # 种子数据：Agent 配置
        seed_agent_configs()

        print("数据库初始化完成！")
        print(f"数据库连接: {Config.DATABASE_URI}")

def check_database_connection():
    """检查数据库连接"""
    print("检查数据库连接...")
    
    app = create_app()
    with app.app_context():
        try:
            # 尝试执行一个简单的查询
            db.session.execute(text("SELECT 1"))
            print("[OK] 数据库连接正常")
            return True
        except Exception as e:
            print(f"[FAIL] 数据库连接失败: {e}")
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
        print(f"[OK] 创建目录: {dir_path}")
    
    print("工作空间目录创建完成！")

if __name__ == "__main__":
    print("=" * 50)
    print("AutoTestGPT 数据库初始化工具")
    print("=" * 50)
    
    # 检查数据库连接
    if not check_database_connection():
        print("\n请检查数据库配置:")
        print(f"  数据库: {Config.DATABASE_URI}")
        sys.exit(1)
    
    # 创建工作空间目录
    create_workspace_dirs()
    
    # 初始化数据库
    init_database()
    
    print("\n" + "=" * 50)
    print("初始化完成！")
    print("=" * 50)
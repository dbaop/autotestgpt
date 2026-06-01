#!/usr/bin/env python3
"""
AutoTestGPT main application entry.
"""

import os
import sys
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from sqlalchemy import text, inspect
from flask_cors import CORS
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import Config
from models import db, TestCase, TestScript
from api import api_blueprint
from sqlalchemy.exc import OperationalError, ProgrammingError
from service.errors import AppError
from service.flow_service import execute_flow_async as execute_flow_async_service

FRONTEND_DIST = project_root / 'autotestgptFront' / 'dist'

def setup_logging(app):
    log_dir = os.path.join(Config.WORKSPACE, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'autotestgpt.log'),
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    app.logger.handlers.clear()
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG)

    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)


def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_recycle': 300,
        'pool_pre_ping': True,
    }
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'autotestgpt-secret-key')

    db.init_app(app)
    CORS(app)
    app.register_blueprint(api_blueprint, url_prefix='/api')
    setup_logging(app)

    @app.errorhandler(AppError)
    def handle_app_error(err):
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(Exception)
    def handle_uncaught_error(err):
        app.logger.exception("Unhandled server error")
        return jsonify({"error": "INTERNAL_SERVER_ERROR", "message": str(err)}), 500

    return app


def ensure_database_structure():
    with app.app_context():
        try:
            db.session.execute(text('SELECT 1 FROM requirements LIMIT 1'))
        except (OperationalError, ProgrammingError):
            app.logger.info('Database tables not found, creating new tables')
            db.create_all()
            app.logger.info('Database tables created')
            _ensure_default_project()

        # Always run column migrations — wraps each call so a missing table
        # doesn't block remaining migrations.
        _ensure_all_columns()
        db.create_all()
        _ensure_default_project()
        app.logger.info('Database schema is ready')


def _ensure_all_columns():
    """安全地执行所有列迁移 — 每步独立 try/except，单步失败不影响后续。"""
    migrations = [
        ('requirements', 'execution_progress',
         'ALTER TABLE requirements ADD COLUMN execution_progress JSON',
         'ALTER TABLE requirements ADD COLUMN execution_progress JSON NULL'),
        ('requirements', 'knowledge_base_id',
         'ALTER TABLE requirements ADD COLUMN knowledge_base_id INTEGER',
         'ALTER TABLE requirements ADD COLUMN knowledge_base_id INTEGER NULL'),
        ('code_review_tasks', 'repo_path',
         'ALTER TABLE code_review_tasks ADD COLUMN repo_path VARCHAR(1000)',
         'ALTER TABLE code_review_tasks ADD COLUMN repo_path VARCHAR(1000) NULL'),
        ('code_review_tasks', 'repo_type',
         "ALTER TABLE code_review_tasks ADD COLUMN repo_type VARCHAR(20) DEFAULT 'remote'",
         "ALTER TABLE code_review_tasks ADD COLUMN repo_type VARCHAR(20) DEFAULT 'remote'"),
        ('code_review_findings', 'category',
         'ALTER TABLE code_review_findings ADD COLUMN category VARCHAR(50)',
         'ALTER TABLE code_review_findings ADD COLUMN category VARCHAR(50) NULL'),
        ('code_review_findings', 'review_type',
         'ALTER TABLE code_review_findings ADD COLUMN review_type VARCHAR(50)',
         'ALTER TABLE code_review_findings ADD COLUMN review_type VARCHAR(50) NULL'),
        ('code_review_findings', 'suggestion',
         'ALTER TABLE code_review_findings ADD COLUMN suggestion TEXT',
         'ALTER TABLE code_review_findings ADD COLUMN suggestion TEXT NULL'),
        ('requirements', 'current_phase',
         "ALTER TABLE requirements ADD COLUMN current_phase VARCHAR(50) DEFAULT 'idle'",
         "ALTER TABLE requirements ADD COLUMN current_phase VARCHAR(50) DEFAULT 'idle'"),
        ('requirements', 'conversation_messages',
         'ALTER TABLE requirements ADD COLUMN conversation_messages JSON',
         'ALTER TABLE requirements ADD COLUMN conversation_messages JSON NULL'),
    ]
    for table, col, sqlite_ddl, mysql_ddl in migrations:
        try:
            _ensure_column(table, col, sqlite_ddl, mysql_ddl)
        except Exception as exc:
            app.logger.warning("Column migration skipped [%s.%s]: %s", table, col, exc)

    try:
        _ensure_agent_configs_table()
    except Exception as exc:
        app.logger.warning("agent_configs table creation skipped: %s", exc)


def _ensure_agent_configs_table():
    inspector = inspect(db.engine)
    if 'agent_configs' in inspector.get_table_names():
        return
    dialect = db.engine.dialect.name
    if dialect == 'mysql':
        db.session.execute(text(
            'CREATE TABLE IF NOT EXISTS agent_configs (id INT AUTO_INCREMENT PRIMARY KEY, '
            'agent_type VARCHAR(50) NOT NULL, project_id INT, system_prompt TEXT, '
            'model_name VARCHAR(100), temperature FLOAT DEFAULT 0.1, '
            'max_tokens INT DEFAULT 4000, is_enabled BOOLEAN DEFAULT 1, '
            'extra_config JSON, created_at DATETIME, updated_at DATETIME)'
        ))
    else:
        db.session.execute(text(
            'CREATE TABLE IF NOT EXISTS agent_configs (id INTEGER PRIMARY KEY AUTOINCREMENT, '
            'agent_type VARCHAR(50) NOT NULL, project_id INTEGER, system_prompt TEXT, '
            'model_name VARCHAR(100), temperature FLOAT DEFAULT 0.1, '
            'max_tokens INTEGER DEFAULT 4000, is_enabled BOOLEAN DEFAULT 1, '
            'extra_config JSON, created_at DATETIME, updated_at DATETIME)'
        ))
    db.session.commit()


def _ensure_column(table_name, column_name, sqlite_ddl, mysql_ddl):
    inspector = inspect(db.engine)
    try:
        existing_columns = {col['name'] for col in inspector.get_columns(table_name)}
    except Exception:
        return  # table doesn't exist yet — db.create_all() will handle it
    if column_name in existing_columns:
        return
    dialect = db.engine.dialect.name
    ddl = mysql_ddl if dialect == 'mysql' else sqlite_ddl
    db.session.execute(text(ddl))
    db.session.commit()


def _ensure_default_project():
    from models import Project
    if Project.query.first():
        return
    default = Project(
        name='Default Project',
        description='AutoTestGPT default test project',
        config={'environment': 'development', 'base_url': 'http://localhost:8000', 'timeout': 30},
    )
    db.session.add(default)
    db.session.commit()


app = create_app()
ensure_database_structure()


# ---------------------------------------------------------------------------
# 工作流异步执行
# ---------------------------------------------------------------------------

def execute_flow_async(flow, flow_data, requirement_id):
    """兼容旧测试入口：委托到 flow_service。"""
    with app.app_context():
        return execute_flow_async_service(flow, flow_data, requirement_id)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND_DIST, 'index.html')


@app.route('/<path:filename>')
def serve_static(filename):
    if filename.startswith('api/'):
        return jsonify({'error': 'Not found'}), 404
    file_path = FRONTEND_DIST / filename
    if file_path.exists():
        return send_from_directory(FRONTEND_DIST, filename)
    return send_from_directory(FRONTEND_DIST, 'index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        db.session.execute(text('SELECT 1')).fetchone()
        db_status = 'healthy'
    except Exception as e:
        db_status = f'unhealthy: {str(e)}'
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'database': db_status,
        'version': '1.0.0',
    })


@app.route('/api/scripts', methods=['GET'])
def get_test_scripts():
    try:
        requirement_id = request.args.get('requirement_id', type=int)
        if not requirement_id:
            return jsonify({'error': 'Missing requirement_id'}), 400

        cases = TestCase.query.filter_by(requirement_id=requirement_id).all()
        case_ids = [c.id for c in cases]
        scripts = TestScript.query.filter(TestScript.test_case_id.in_(case_ids)).all()

        return jsonify([{
            'id': s.id,
            'test_case_id': s.test_case_id,
            'script_type': s.script_type,
            'file_path': s.file_path,
            'status': s.status,
            'created_at': s.created_at.isoformat() if s.created_at else None,
            'content': s.script_content,
        } for s in scripts]), 200

    except Exception as e:
        app.logger.error(f'Failed to get scripts: {e}')
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print('=' * 50)
    print('AutoTestGPT Service Start')
    print('Version: 1.0.0')
    print(f'Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'Port: {Config.SERVER_PORT}')
    db_info = Config.DATABASE_URI.split('://')[1] if '://' in Config.DATABASE_URI else Config.DATABASE_URI
    print(f'Database: {db_info}')
    print('=' * 50)

    os.makedirs(Config.WORKSPACE, exist_ok=True)
    os.makedirs(Config.REPORT_DIR, exist_ok=True)

    app.run(
        host='0.0.0.0',
        port=Config.SERVER_PORT,
        debug=True,
        threaded=True,
        use_reloader=False,
    )

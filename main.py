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
            _ensure_required_columns()
            db.create_all()
            _ensure_default_project()
            app.logger.info('Database schema is ready')
        except (OperationalError, ProgrammingError):
            app.logger.info('Database tables not found, creating new tables')
            db.create_all()
            app.logger.info('Database tables created')
            _ensure_default_project()


def _ensure_required_columns():
    _ensure_column(
        table_name='requirements',
        column_name='execution_progress',
        sqlite_ddl='ALTER TABLE requirements ADD COLUMN execution_progress JSON',
        mysql_ddl='ALTER TABLE requirements ADD COLUMN execution_progress JSON NULL',
    )
    _ensure_column(
        table_name='requirements',
        column_name='knowledge_base_id',
        sqlite_ddl='ALTER TABLE requirements ADD COLUMN knowledge_base_id INTEGER',
        mysql_ddl='ALTER TABLE requirements ADD COLUMN knowledge_base_id INTEGER NULL',
    )
    db.create_all()


def _ensure_column(table_name, column_name, sqlite_ddl, mysql_ddl):
    inspector = inspect(db.engine)
    existing_columns = {col['name'] for col in inspector.get_columns(table_name)}
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

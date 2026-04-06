#!/usr/bin/env python3
"""
AutoTestGPT 主应用入口
"""

import os
import sys
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from sqlalchemy import text
from flask_cors import CORS
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import Config
from models import db
from api import api_blueprint
from flow.test_flow import AutoTestFlow
from sqlalchemy.exc import OperationalError
from sqlalchemy import text

# 前端构建目录
FRONTEND_DIST = project_root / 'autotestgptFront' / 'dist'

def setup_logging(app):
    """配置日志"""
    log_dir = os.path.join(Config.WORKSPACE, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'autotestgpt.log'),
        maxBytes=10 * 1024 * 1024,
        backupCount=10
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
    """创建Flask应用"""
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

    return app

# 确保数据库表结构最新
def ensure_database_structure():
    with app.app_context():
        try:
            # 尝试执行查询，检查表结构是否存在
            db.session.execute(text('SELECT 1 FROM requirements LIMIT 1'))
            # 检查execution_progress列是否存在
            try:
                db.session.execute(text('SELECT execution_progress FROM requirements LIMIT 1'))
                app.logger.info("数据库表结构完整")
            except OperationalError:
                app.logger.info("需要更新数据库表结构")
                # 删除并重新创建表
                db.drop_all()
                db.create_all()
                app.logger.info("数据库表结构已更新")
                # 创建默认项目
                from models import Project
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
        except OperationalError:
            app.logger.info("数据库表不存在，创建新表")
            db.create_all()
            app.logger.info("数据库表创建成功")
            # 创建默认项目
            from models import Project
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

# 创建应用实例
app = create_app()

# 初始化数据库结构
ensure_database_structure()

# ========== 路由定义 ==========

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
        'version': '1.0.0'
    })

@app.route('/api/flow/start', methods=['POST'])
def start_test_flow():
    try:
        data = request.get_json()

        if not data or 'demand' not in data:
            return jsonify({
                'error': '缺少需求描述',
                'message': '请提供demand字段'
            }), 400

        demand = data['demand']
        project_id = data.get('project_id', 1)

        from models import Requirement
        requirement = Requirement(
            title=f"需求-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
            description=demand[:100] + '...' if len(demand) > 100 else demand,
            raw_text=demand,
            status='pending'
        )
        db.session.add(requirement)
        db.session.commit()

        flow = AutoTestFlow()
        flow_data = {
            'demand': demand,
            'requirement_id': requirement.id,
            'project_id': project_id
        }

        import threading
        thread = threading.Thread(
            target=execute_flow_async,
            args=(flow, flow_data, requirement.id)
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            'message': '测试流程已启动',
            'requirement_id': requirement.id,
            'status': 'processing',
            'flow_id': str(id(flow))
        }), 202

    except Exception as e:
        app.logger.error(f"启动测试流程失败: {e}")
        return jsonify({
            'error': '启动测试流程失败',
            'message': str(e)
        }), 500

def execute_flow_async(flow, flow_data, requirement_id):
    try:
        with app.app_context():
            result = flow.run(flow_data)

            from models import Requirement
            requirement = db.session.get(Requirement, requirement_id)
            if requirement:
                requirement.status = 'completed'
                requirement.structured_data = result
                db.session.commit()
                app.logger.info(f"需求 {requirement_id} 处理完成")
            else:
                app.logger.error(f"未找到需求 {requirement_id}")

    except Exception as e:
        app.logger.error(f"工作流执行失败: {e}")
        with app.app_context():
            from models import Requirement
            requirement = db.session.get(Requirement, requirement_id)
            if requirement:
                requirement.status = 'error'
                db.session.commit()

@app.route('/api/scripts', methods=['GET'])
def get_test_scripts():
    """获取测试脚本"""
    try:
        requirement_id = request.args.get('requirement_id', type=int)
        if not requirement_id:
            return jsonify({'error': '缺少requirement_id参数'}), 400
        
        # 获取该需求的所有测试用例
        requirement_cases = TestCase.query.filter_by(requirement_id=requirement_id).all()
        case_ids = [case.id for case in requirement_cases]
        
        # 获取所有相关的测试脚本
        test_scripts = TestScript.query.filter(TestScript.test_case_id.in_(case_ids)).all()
        
        # 构建响应
        scripts_data = []
        for script in test_scripts:
            scripts_data.append({
                'id': script.id,
                'test_case_id': script.test_case_id,
                'script_type': script.script_type,
                'file_path': script.file_path,
                'status': script.status,
                'created_at': script.created_at.isoformat() if script.created_at else None,
                'content': script.script_content  # 包含脚本内容
            })
        
        return jsonify(scripts_data), 200
        
    except Exception as e:
        app.logger.error(f"获取测试脚本失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/flow/resume/<int:req_id>', methods=['POST'])
def resume_test_flow(req_id):
    try:
        from models import Requirement, TestCase
        
        requirement = db.session.get(Requirement, req_id)
        if not requirement:
            return jsonify({'error': '需求不存在'}), 404
        
        current_status = requirement.status
        
        if current_status == 'error':
            return jsonify({'error': '需求处理失败，请重新创建'}), 400
        
        if current_status == 'executed':
            return jsonify({'message': '流程已完成', 'status': current_status}), 200
        
        flow = AutoTestFlow()
        
        if current_status == 'pending':
            flow_data = {
                'demand': requirement.raw_text,
                'requirement_id': req_id,
                'project_id': requirement.project_id or 1
            }
        elif current_status == 'parsed':
            test_cases = TestCase.query.filter_by(requirement_id=req_id).all()
            if test_cases:
                requirement.status = 'cases_generated'
                db.session.commit()
            
            flow_data = {
                'demand': requirement.raw_text,
                'requirement_id': req_id,
                'project_id': requirement.project_id or 1,
                'resume_from': 'cases_generated'
            }
        elif current_status == 'cases_generated':
            flow_data = {
                'demand': requirement.raw_text,
                'requirement_id': req_id,
                'project_id': requirement.project_id or 1,
                'resume_from': 'code_generated'
            }
        elif current_status == 'code_generated':
            flow_data = {
                'demand': requirement.raw_text,
                'requirement_id': req_id,
                'project_id': requirement.project_id or 1,
                'resume_from': 'executed'
            }
        else:
            flow_data = {
                'demand': requirement.raw_text,
                'requirement_id': req_id,
                'project_id': requirement.project_id or 1
            }
        
        import threading
        thread = threading.Thread(
            target=execute_flow_async,
            args=(flow, flow_data, req_id)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'message': '流程已恢复',
            'requirement_id': req_id,
            'previous_status': current_status,
            'status': 'processing'
        }), 202
        
    except Exception as e:
        app.logger.error(f"恢复流程失败: {e}")
        return jsonify({
            'error': '恢复流程失败',
            'message': str(e)
        }), 500

# ========== 启动入口 ==========

if __name__ == '__main__':
    print("=" * 50)
    print("AutoTestGPT 服务启动")
    print(f"版本: 1.0.0")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"端口: {Config.SERVER_PORT}")
    db_info = Config.DATABASE_URI.split("://")[1] if "://" in Config.DATABASE_URI else Config.DATABASE_URI
    print(f"数据库: {db_info}")
    print("=" * 50)

    os.makedirs(Config.WORKSPACE, exist_ok=True)
    os.makedirs(Config.REPORT_DIR, exist_ok=True)

    app.run(
        host='0.0.0.0',
        port=Config.SERVER_PORT,
        debug=True,
        threaded=True
    )

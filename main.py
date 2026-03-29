#!/usr/bin/env python3
"""
AutoTestGPT 主应用入口
"""

import os
import sys
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
import logging
from logging.handlers import RotatingFileHandler

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import Config
from models import db
from api import api_blueprint
from flow.test_flow import AutoTestFlow

def create_app():
    """创建Flask应用"""
    app = Flask(__name__)
    
    # 配置
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_recycle': 300,
        'pool_pre_ping': True,
    }
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'autotestgpt-secret-key')
    
    # 初始化扩展
    db.init_app(app)
    CORS(app)
    
    # 注册蓝图
    app.register_blueprint(api_blueprint, url_prefix='/api')
    
    # 配置日志
    setup_logging(app)
    
    return app

def setup_logging(app):
    """配置日志"""
    # 创建日志目录
    log_dir = os.path.join(Config.WORKSPACE, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # 文件处理器
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'autotestgpt.log'),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    # 移除默认处理器，添加自定义处理器
    app.logger.handlers.clear()
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG)
    
    # 设置SQLAlchemy日志
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

@app.route('/')
def index():
    """首页"""
    return jsonify({
        'name': 'AutoTestGPT',
        'version': '1.0.0',
        'description': '多智能体一体化测试平台',
        'endpoints': {
            'api_docs': '/api/docs',
            'health': '/api/health',
            'start_flow': '/api/flow/start',
            'requirements': '/api/requirements',
            'test_cases': '/api/cases',
            'executions': '/api/executions'
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    try:
        # 检查数据库连接
        db.session.execute('SELECT 1')
        db_status = 'healthy'
    except Exception as e:
        db_status = f'unhealthy: {str(e)}'
    
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat(),
        'database': db_status,
        'version': '1.0.0'
    })

@app.route('/api/flow/start', methods=['POST'])
def start_test_flow():
    """启动测试流程"""
    try:
        data = request.get_json()
        
        if not data or 'demand' not in data:
            return jsonify({
                'error': '缺少需求描述',
                'message': '请提供demand字段'
            }), 400
        
        demand = data['demand']
        project_id = data.get('project_id', 1)
        
        # 创建需求记录
        from models import Requirement
        requirement = Requirement(
            title=f"需求-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            description=demand[:100] + '...' if len(demand) > 100 else demand,
            raw_text=demand,
            status='pending'
        )
        db.session.add(requirement)
        db.session.commit()
        
        # 启动工作流
        flow = AutoTestFlow()
        flow_data = {
            'demand': demand,
            'requirement_id': requirement.id,
            'project_id': project_id
        }
        
        # 异步执行工作流（实际项目中应该使用Celery等任务队列）
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
    """异步执行工作流"""
    try:
        with app.app_context():
            # 执行工作流
            result = flow.run(flow_data)
            
            # 更新需求状态
            from models import Requirement
            requirement = Requirement.query.get(requirement_id)
            if requirement:
                requirement.status = 'completed'
                requirement.structured_data = result
                db.session.commit()
                
                app.logger.info(f"需求 {requirement_id} 处理完成")
            else:
                app.logger.error(f"未找到需求 {requirement_id}")
                
    except Exception as e:
        app.logger.error(f"工作流执行失败: {e}")
        
        # 更新需求状态为错误
        with app.app_context():
            from models import Requirement
            requirement = Requirement.query.get(requirement_id)
            if requirement:
                requirement.status = 'error'
                db.session.commit()

if __name__ == '__main__':
    from datetime import datetime
    
    app = create_app()
    
    print("=" * 50)
    print("AutoTestGPT 服务启动")
    print(f"版本: 1.0.0")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"端口: {Config.SERVER_PORT}")
    print(f"数据库: {Config.DB_NAME}@{Config.DB_HOST}:{Config.DB_PORT}")
    print("=" * 50)
    
    # 确保工作空间目录存在
    os.makedirs(Config.WORKSPACE, exist_ok=True)
    os.makedirs(Config.REPORT_DIR, exist_ok=True)
    
    # 启动服务
    app.run(
        host='0.0.0.0',
        port=Config.SERVER_PORT,
        debug=True,
        threaded=True
    )
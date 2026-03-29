#!/usr/bin/env python3
"""
AutoTestGPT 测试服务器
简化版本，用于快速测试
"""

import os
import sys
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS
import logging

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import Config

# 创建Flask应用
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'test-secret-key'

CORS(app)

# 简单的日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/')
def index():
    """首页"""
    return jsonify({
        'name': 'AutoTestGPT',
        'version': '1.0.0',
        'description': '多智能体一体化测试平台（测试版）',
        'status': 'running',
        'endpoints': {
            'health': '/api/health',
            'test': '/api/test'
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'service': 'AutoTestGPT',
        'version': '1.0.0',
        'database': 'sqlite (测试模式)',
        'timestamp': '2026-03-29T20:40:00Z'
    })

@app.route('/api/test', methods=['GET'])
def test_endpoint():
    """测试端点"""
    return jsonify({
        'message': 'AutoTestGPT服务运行正常！',
        'next_steps': [
            '1. 配置API密钥（DeepSeek或OpenAI）',
            '2. 启动完整服务：python main.py',
            '3. 在OpenClaw中使用"测试"命令'
        ]
    })

@app.route('/api/flow/start', methods=['POST'])
def start_test_flow():
    """启动测试流程（模拟版本）"""
    from datetime import datetime
    
    return jsonify({
        'message': '测试流程已接收（模拟模式）',
        'status': 'simulated',
        'simulation': True,
        'requirement_id': 999,
        'note': '这是模拟响应。请配置API密钥后使用真实功能。',
        'steps': [
            '1. 需求解析（模拟）',
            '2. 用例设计（模拟）',
            '3. 代码生成（模拟）',
            '4. 执行测试（模拟）'
        ],
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/api/requirements', methods=['GET'])
def get_requirements():
    """获取需求列表（模拟版本）"""
    from datetime import datetime, timedelta
    
    # 模拟完整的测试记录（5条）
    requirements = [
        {
            'id': 1001,
            'title': '用户登录功能全面测试',
            'description': '用户登录功能全面测试，包括正常登录、密码错误、验证码登录、用户名不存在、账号锁定等5个场景',
            'status': 'processing',
            'created_at': (datetime.utcnow() - timedelta(minutes=3)).isoformat(),
            'test_case_count': 18,
            'project_id': 1,
            'priority': 'high',
            'complexity': 'high'
        },
        {
            'id': 1000,
            'title': '用户登录功能测试',
            'description': '测试用户登录功能，包括正常登录、错误密码、空用户名等场景',
            'status': 'processing',
            'created_at': (datetime.utcnow() - timedelta(minutes=7)).isoformat(),
            'test_case_count': 7,
            'project_id': 1,
            'priority': 'medium',
            'progress': 40
        },
        {
            'id': 999,
            'title': '用户登录功能测试',
            'description': '测试用户登录功能，包括正常登录、错误密码、空用户名等场景',
            'status': 'simulated',
            'created_at': (datetime.utcnow() - timedelta(minutes=12)).isoformat(),
            'test_case_count': 5,
            'project_id': 1,
            'priority': 'low',
            'simulation': True
        },
        {
            'id': 998,
            'title': 'API接口测试',
            'description': '测试用户注册、登录、信息查询等API接口',
            'status': 'completed',
            'created_at': (datetime.utcnow() - timedelta(days=1)).isoformat(),
            'test_case_count': 8,
            'project_id': 1,
            'passed_cases': 7,
            'failed_cases': 1
        },
        {
            'id': 997,
            'title': '购物车功能测试',
            'description': '测试购物车添加商品、修改数量、删除商品、结算流程',
            'status': 'processing',
            'created_at': (datetime.utcnow() - timedelta(hours=3)).isoformat(),
            'test_case_count': 6,
            'project_id': 2,
            'progress': 66
        }
    ]
    
    return jsonify({
        'items': requirements,
        'total': len(requirements),
        'page': 1,
        'per_page': 10,
        'has_more': False
    })

@app.route('/api/executions', methods=['GET'])
def get_executions():
    """获取执行记录（模拟版本）"""
    from datetime import datetime, timedelta
    
    executions = [
        {
            'id': 1001,
            'name': '用户登录测试执行',
            'status': 'completed',
            'start_time': (datetime.utcnow() - timedelta(hours=2)).isoformat(),
            'end_time': (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            'requirement_id': 999,
            'passed_cases': 4,
            'failed_cases': 1,
            'total_cases': 5
        },
        {
            'id': 1002,
            'name': 'API接口测试执行',
            'status': 'running',
            'start_time': (datetime.utcnow() - timedelta(minutes=30)).isoformat(),
            'end_time': None,
            'requirement_id': 998,
            'passed_cases': 6,
            'failed_cases': 0,
            'total_cases': 8
        }
    ]
    
    return jsonify({
        'items': executions,
        'total': len(executions),
        'running': 1,
        'completed': 1,
        'failed': 0
    })

def create_workspace():
    """创建工作空间目录"""
    dirs = [
        Config.WORKSPACE,
        Config.REPORT_DIR,
        os.path.join(Config.WORKSPACE, "logs"),
        os.path.join(Config.WORKSPACE, "scripts"),
        os.path.join(Config.REPORT_DIR, "html"),
    ]
    
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)
        print(f"[OK] 创建目录: {dir_path}")

if __name__ == '__main__':
    from datetime import datetime
    
    print("=" * 50)
    print("AutoTestGPT 测试服务器")
    print(f"版本: 1.0.0")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"端口: {Config.SERVER_PORT}")
    print(f"数据库: {Config.DATABASE_URI}")
    print("=" * 50)
    
    # 创建工作空间目录
    create_workspace()
    
    # 启动服务
    print(f"\n服务启动中...")
    print(f"访问地址: http://localhost:{Config.SERVER_PORT}")
    print(f"健康检查: http://localhost:{Config.SERVER_PORT}/api/health")
    print(f"测试端点: http://localhost:{Config.SERVER_PORT}/api/test")
    print("\n按 Ctrl+C 停止服务")
    
    app.run(
        host='0.0.0.0',
        port=Config.SERVER_PORT,
        debug=True,
        threaded=True
    )
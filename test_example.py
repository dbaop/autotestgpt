#!/usr/bin/env python3
"""
AutoTestGPT 示例测试
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_imports():
    """测试导入"""
    print("测试导入模块...")
    
    try:
        from config import Config
        print("[OK] config.py 导入成功")
        
        from models import db
        print("[OK] models.py 导入成功")
        
        from agent.base_agent import BaseAgent
        print("[OK] base_agent.py 导入成功")
        
        from agent.req_agent import ReqAgent
        print("[OK] req_agent.py 导入成功")
        
        from agent.case_agent import CaseAgent
        print("[OK] case_agent.py 导入成功")
        
        from agent.code_agent import CodeAgent
        print("[OK] code_agent.py 导入成功")
        
        from agent.exec_agent import ExecAgent
        print("[OK] exec_agent.py 导入成功")
        
        from flow.test_flow import AutoTestFlow
        print("[OK] test_flow.py 导入成功")
        
        print("\n所有模块导入成功！")
        return True
        
    except ImportError as e:
        print(f"[ERROR] 导入失败: {e}")
        return False

def test_config():
    """测试配置"""
    print("\n测试配置...")
    
    from config import Config
    
    print(f"服务器端口: {Config.SERVER_PORT}")
    print(f"工作空间: {Config.WORKSPACE}")
    print(f"报告目录: {Config.REPORT_DIR}")
    print(f"数据库URI: {Config.DATABASE_URI}")
    
    # 检查目录是否存在
    os.makedirs(Config.WORKSPACE, exist_ok=True)
    os.makedirs(Config.REPORT_DIR, exist_ok=True)
    
    print("[OK] 配置检查完成")
    return True

def test_database_connection():
    """测试数据库连接"""
    print("\n测试数据库连接...")
    
    try:
        from config import Config
        from models import db
        from flask import Flask
        
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URI
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        db.init_app(app)
        
        with app.app_context():
            # 尝试连接数据库
            db.session.execute('SELECT 1')
            print("[OK] 数据库连接成功")
            return True
            
    except Exception as e:
        print(f"[ERROR] 数据库连接失败: {e}")
        print("提示: 请确保MySQL服务已启动，并正确配置.env文件")
        return False

def test_agent_initialization():
    """测试智能体初始化"""
    print("\n测试智能体初始化...")
    
    try:
        from agent.req_agent import ReqAgent
        from agent.case_agent import CaseAgent
        from agent.code_agent import CodeAgent
        from agent.exec_agent import ExecAgent
        
        req_agent = ReqAgent()
        print("[OK] ReqAgent 初始化成功")
        
        case_agent = CaseAgent()
        print("[OK] CaseAgent 初始化成功")
        
        code_agent = CodeAgent()
        print("[OK] CodeAgent 初始化成功")
        
        exec_agent = ExecAgent()
        print("[OK] ExecAgent 初始化成功")
        
        print("[OK] 所有智能体初始化成功")
        return True
        
    except Exception as e:
        print(f"[ERROR] 智能体初始化失败: {e}")
        return False

def test_workflow_initialization():
    """测试工作流初始化"""
    print("\n测试工作流初始化...")
    
    try:
        from flow.test_flow import AutoTestFlow
        
        workflow = AutoTestFlow()
        print("[OK] AutoTestFlow 初始化成功")
        
        status = workflow.get_status()
        print(f"工作流状态: {status['status']}")
        
        print("[OK] 工作流初始化成功")
        return True
        
    except Exception as e:
        print(f"[ERROR] 工作流初始化失败: {e}")
        return False

def main():
    """主测试函数"""
    print("=" * 50)
    print("AutoTestGPT 项目测试")
    print("=" * 50)
    
    tests = [
        ("模块导入", test_imports),
        ("配置检查", test_config),
        ("数据库连接", test_database_connection),
        ("智能体初始化", test_agent_initialization),
        ("工作流初始化", test_workflow_initialization),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n[{test_name}]")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"[ERROR] 测试异常: {e}")
            results.append((test_name, False))
    
    # 汇总结果
    print("\n" + "=" * 50)
    print("测试结果汇总:")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "[OK] 通过" if result else "[ERROR] 失败"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n通过率: {passed}/{total} ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n[SUCCESS] 所有测试通过！项目可以正常运行。")
        print("\n下一步:")
        print("1. 配置.env文件中的API密钥和数据库密码")
        print("2. 运行 python init_db.py 初始化数据库")
        print("3. 运行 python main.py 启动服务")
        print("4. 访问 http://localhost:8000 查看API文档")
    else:
        print("\n[WARNING] 部分测试失败，请检查相关问题。")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
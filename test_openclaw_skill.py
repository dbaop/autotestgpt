#!/usr/bin/env python3
"""
测试OpenClaw技能
"""

import sys
import os
from pathlib import Path

# 添加OpenClaw技能路径
skill_path = Path("C:/Users/dbaop/AppData/Roaming/npm/node_modules/openclaw-cn/skills/autotestgpt")
sys.path.insert(0, str(skill_path.parent))

def test_skill_loading():
    """测试技能加载"""
    print("测试OpenClaw技能加载...")
    
    try:
        # 尝试导入技能
        import autotestgpt.index as skill_module
        print("[OK] 技能模块导入成功")
        
        # 检查技能对象
        skill = skill_module
        print(f"[OK] 技能名称: {skill.name}")
        print(f"[OK] 技能描述: {skill.description}")
        print(f"[OK] 技能版本: {skill.version}")
        
        # 检查命令
        print(f"[OK] 支持命令: {list(skill.commands.keys())}")
        
        return True
        
    except ImportError as e:
        print(f"[ERROR] 导入技能失败: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] 技能检查失败: {e}")
        return False

def test_skill_function():
    """测试技能功能"""
    print("\n测试技能功能...")
    
    try:
        import autotestgpt.index as skill
        
        # 测试帮助命令
        print("测试帮助命令...")
        help_result = skill.showHelp("", {})
        print(f"[OK] 帮助命令返回: {type(help_result)}")
        
        # 测试消息处理
        print("\n测试消息处理...")
        test_messages = [
            "帮助",
            "测试用户登录功能",
            "查看测试进度",
            "测试报告 1",
        ]
        
        for msg in test_messages:
            print(f"\n测试消息: '{msg}'")
            result = skill.handleMessage({"text": msg}, {})
            if result:
                print(f"[OK] 返回结果: {result.get('type', 'unknown')}")
                if 'content' in result:
                    content = result['content']
                    print(f"内容预览: {content[:100]}...")
            else:
                print(f"[INFO] 无返回结果（可能不是技能命令）")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] 技能功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_api_connection():
    """测试API连接"""
    print("\n测试API连接...")
    
    try:
        import requests
        
        # 测试健康检查
        print("测试健康检查API...")
        response = requests.get("http://localhost:8000/api/health", timeout=5)
        print(f"[OK] 状态码: {response.status_code}")
        print(f"[OK] 响应: {response.json()}")
        
        # 测试流程启动API
        print("\n测试流程启动API...")
        test_data = {
            "demand": "测试用户登录功能",
            "project_id": 1
        }
        response = requests.post(
            "http://localhost:8000/api/flow/start",
            json=test_data,
            timeout=10
        )
        print(f"[OK] 状态码: {response.status_code}")
        print(f"[OK] 响应: {response.json()}")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("[ERROR] 无法连接到API服务")
        print("请确保AutoTestGPT服务已启动: python test_server.py")
        return False
    except Exception as e:
        print(f"[ERROR] API测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("=" * 50)
    print("AutoTestGPT OpenClaw技能测试")
    print("=" * 50)
    
    tests = [
        ("技能加载", test_skill_loading),
        ("技能功能", test_skill_function),
        ("API连接", test_api_connection),
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
        print("\n[SUCCESS] 所有测试通过！技能可以正常使用。")
        print("\n下一步:")
        print("1. 在OpenClaw中发送'帮助'查看技能命令")
        print("2. 发送'测试用户登录功能'启动测试")
        print("3. 发送'查看测试进度'查看测试状态")
    else:
        print("\n[WARNING] 部分测试失败，请检查相关问题。")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
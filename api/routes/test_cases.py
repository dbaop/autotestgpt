"""
测试用例相关路由
"""

from flask import request, jsonify
from models import db, TestCase, TestScript, Requirement

def get_test_cases():
    """获取测试用例列表"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        requirement_id = request.args.get('requirement_id')
        test_type = request.args.get('test_type')
        
        query = TestCase.query
        
        if requirement_id:
            query = query.filter_by(requirement_id=requirement_id)
        if test_type:
            query = query.filter_by(test_type=test_type)
        
        # 按创建时间倒序排列
        query = query.order_by(TestCase.created_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        test_cases = pagination.items
        
        return jsonify({
            'items': [tc.to_dict() for tc in test_cases],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        })
        
    except Exception as e:
        return jsonify({
            'error': '获取测试用例列表失败',
            'message': str(e)
        }), 500

def get_test_case(case_id):
    """获取单个测试用例详情"""
    try:
        test_case = TestCase.query.get_or_404(case_id)
        
        # 获取关联的测试脚本
        test_scripts = TestScript.query.filter_by(test_case_id=case_id).all()
        
        # 获取需求信息
        requirement = Requirement.query.get(test_case.requirement_id)
        
        result = test_case.to_dict()
        result['test_scripts'] = [ts.to_dict() for ts in test_scripts]
        result['requirement'] = requirement.to_dict() if requirement else None
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'error': '获取测试用例详情失败',
            'message': str(e)
        }), 500
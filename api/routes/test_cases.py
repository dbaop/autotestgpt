"""
测试用例相关路由
"""

from flask import request, jsonify
from models import db, TestCase, TestScript, Requirement


def handle_cases():
    """Dispatch /api/cases by HTTP method."""
    if request.method == 'POST':
        return create_test_case()
    return get_test_cases()


def handle_case_by_id(case_id):
    """Dispatch /api/cases/<id> by HTTP method."""
    if request.method == 'PUT':
        return update_test_case(case_id)
    if request.method == 'DELETE':
        return delete_test_case(case_id)
    return get_test_case(case_id)


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
        test_case = db.get_or_404(TestCase, case_id)
        
        # 获取关联的测试脚本
        test_scripts = TestScript.query.filter_by(test_case_id=case_id).all()
        
        # 获取需求信息
        requirement = db.session.get(Requirement, test_case.requirement_id)
        
        result = test_case.to_dict()
        result['test_scripts'] = [ts.to_dict() for ts in test_scripts]
        result['requirement'] = requirement.to_dict() if requirement else None
        
        return jsonify(result)

    except Exception as e:
        return jsonify({
            'error': '获取测试用例详情失败',
            'message': str(e)
        }), 500


def update_test_case(case_id):
    """更新测试用例（用于 case review gate 中的编辑）"""
    try:
        test_case = db.get_or_404(TestCase, case_id)
        data = request.get_json() or {}

        if 'title' in data:
            test_case.title = data['title']
        if 'description' in data:
            test_case.description = data['description']
        if 'test_type' in data:
            test_case.test_type = data['test_type']
        if 'priority' in data:
            test_case.priority = data['priority']
        if 'methodology' in data:
            test_case.methodology = data['methodology']
        if 'steps' in data:
            test_case.steps = data['steps']
        if 'expected_results' in data:
            test_case.expected_results = data['expected_results']

        db.session.commit()
        return jsonify({'message': 'updated', 'test_case': test_case.to_dict()})
    except Exception as e:
        return jsonify({'error': '更新测试用例失败', 'message': str(e)}), 500


def delete_test_case(case_id):
    """删除测试用例（用于 case review gate 中的删除）"""
    try:
        test_case = db.get_or_404(TestCase, case_id)
        db.session.delete(test_case)
        db.session.commit()
        return jsonify({'message': 'deleted', 'case_id': case_id})
    except Exception as e:
        return jsonify({'error': '删除测试用例失败', 'message': str(e)}), 500


def create_test_case():
    """创建测试用例（用于 case review gate 中的手动添加）"""
    try:
        data = request.get_json() or {}
        tc = TestCase(
            requirement_id=data.get('requirement_id'),
            title=data.get('title', '未命名'),
            description=data.get('description', ''),
            test_type=data.get('test_type', 'api'),
            priority=data.get('priority', 'medium'),
            methodology=data.get('methodology'),
            steps=data.get('steps') or data.get('test_steps', []),
            expected_results=data.get('expected_results'),
        )
        db.session.add(tc)
        db.session.commit()
        return jsonify({'message': 'created', 'test_case': tc.to_dict()}), 201
    except Exception as e:
        return jsonify({'error': '创建测试用例失败', 'message': str(e)}), 500
"""
需求相关路由
"""

from flask import request, jsonify
from models import db, Requirement, TestCase
from datetime import datetime

def get_requirements():
    """获取需求列表"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = request.args.get('status')
        
        query = Requirement.query
        
        if status:
            query = query.filter_by(status=status)
        
        # 按创建时间倒序排列
        query = query.order_by(Requirement.created_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        requirements = pagination.items
        
        return jsonify({
            'items': [req.to_dict() for req in requirements],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        })
        
    except Exception as e:
        return jsonify({
            'error': '获取需求列表失败',
            'message': str(e)
        }), 500

def get_requirement(req_id):
    """获取单个需求详情"""
    try:
        requirement = Requirement.query.get_or_404(req_id)
        
        # 获取关联的测试用例
        test_cases = TestCase.query.filter_by(requirement_id=req_id).all()
        
        result = requirement.to_dict()
        result['test_cases'] = [tc.to_dict() for tc in test_cases]
        result['structured_data'] = requirement.structured_data
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'error': '获取需求详情失败',
            'message': str(e)
        }), 500

def create_requirement():
    """创建需求"""
    try:
        data = request.get_json()
        
        if not data or 'title' not in data or 'description' not in data:
            return jsonify({
                'error': '缺少必要字段',
                'message': '请提供title和description字段'
            }), 400
        
        requirement = Requirement(
            title=data['title'],
            description=data['description'],
            raw_text=data.get('raw_text', data['description']),
            status='pending',
            structured_data=data.get('structured_data')
        )
        
        if 'project_id' in data:
            requirement.project_id = data['project_id']
        
        db.session.add(requirement)
        db.session.commit()
        
        return jsonify({
            'message': '需求创建成功',
            'requirement': requirement.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': '创建需求失败',
            'message': str(e)
        }), 500

def update_requirement(req_id):
    """更新需求"""
    try:
        requirement = Requirement.query.get_or_404(req_id)
        data = request.get_json()
        
        if 'title' in data:
            requirement.title = data['title']
        if 'description' in data:
            requirement.description = data['description']
        if 'status' in data:
            requirement.status = data['status']
        if 'structured_data' in data:
            requirement.structured_data = data['structured_data']
        
        requirement.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'message': '需求更新成功',
            'requirement': requirement.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': '更新需求失败',
            'message': str(e)
        }), 500

def delete_requirement(req_id):
    """删除需求"""
    try:
        requirement = Requirement.query.get_or_404(req_id)
        
        db.session.delete(requirement)
        db.session.commit()
        
        return jsonify({
            'message': '需求删除成功'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': '删除需求失败',
            'message': str(e)
        }), 500
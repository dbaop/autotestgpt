"""
项目相关路由
"""

from flask import request, jsonify
from models import db, Project, Requirement
from datetime import datetime

def get_projects():
    """获取项目列表"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        query = Project.query.order_by(Project.created_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        projects = pagination.items
        
        return jsonify({
            'items': [project.to_dict() for project in projects],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        })
        
    except Exception as e:
        return jsonify({
            'error': '获取项目列表失败',
            'message': str(e)
        }), 500

def get_project(project_id):
    """获取单个项目详情"""
    try:
        project = Project.query.get_or_404(project_id)
        
        # 获取项目下的需求
        requirements = Requirement.query.filter_by(project_id=project_id).all()
        
        result = project.to_dict()
        result['requirements'] = [req.to_dict() for req in requirements]
        result['config'] = project.config
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'error': '获取项目详情失败',
            'message': str(e)
        }), 500

def create_project():
    """创建项目"""
    try:
        data = request.get_json()
        
        if not data or 'name' not in data:
            return jsonify({
                'error': '缺少必要字段',
                'message': '请提供name字段'
            }), 400
        
        project = Project(
            name=data['name'],
            description=data.get('description', ''),
            config=data.get('config', {
                'environment': 'development',
                'base_url': 'http://localhost:8000',
                'timeout': 30
            })
        )
        
        db.session.add(project)
        db.session.commit()
        
        return jsonify({
            'message': '项目创建成功',
            'project': project.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': '创建项目失败',
            'message': str(e)
        }), 500
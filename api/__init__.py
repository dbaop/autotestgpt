"""
API 模块
"""

from flask import Blueprint
from .routes import requirements, test_cases, executions, projects

api_blueprint = Blueprint('api', __name__)

# 注册路由
api_blueprint.add_url_rule('/requirements', view_func=requirements.get_requirements, methods=['GET'])
api_blueprint.add_url_rule('/requirements', view_func=requirements.create_requirement, methods=['POST'])
api_blueprint.add_url_rule('/requirements/<int:req_id>', view_func=requirements.get_requirement, methods=['GET'])
api_blueprint.add_url_rule('/requirements/<int:req_id>', view_func=requirements.update_requirement, methods=['PUT'])
api_blueprint.add_url_rule('/requirements/<int:req_id>', view_func=requirements.delete_requirement, methods=['DELETE'])

api_blueprint.add_url_rule('/cases', view_func=test_cases.get_test_cases, methods=['GET'])
api_blueprint.add_url_rule('/cases/<int:case_id>', view_func=test_cases.get_test_case, methods=['GET'])

api_blueprint.add_url_rule('/executions', view_func=executions.get_executions, methods=['GET'])
api_blueprint.add_url_rule('/executions/<int:exec_id>', view_func=executions.get_execution, methods=['GET'])

api_blueprint.add_url_rule('/projects', view_func=projects.get_projects, methods=['GET'])
api_blueprint.add_url_rule('/projects', view_func=projects.create_project, methods=['POST'])
api_blueprint.add_url_rule('/projects/<int:project_id>', view_func=projects.get_project, methods=['GET'])
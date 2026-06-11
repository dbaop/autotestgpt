"""
API module
"""

from flask import Blueprint

from .routes import requirements, test_cases, executions, projects, conversations, code_reviews, knowledge_bases, reports, autofix, flow, agent_workbench, agent_config

api_blueprint = Blueprint('api', __name__)

# Requirements
api_blueprint.add_url_rule('/requirements', view_func=requirements.get_requirements, methods=['GET'])
api_blueprint.add_url_rule('/requirements', view_func=requirements.create_requirement, methods=['POST'])
api_blueprint.add_url_rule('/requirements/import', view_func=requirements.import_requirement, methods=['POST'])
api_blueprint.add_url_rule('/requirements/<int:req_id>', view_func=requirements.get_requirement, methods=['GET'])
api_blueprint.add_url_rule('/requirements/<int:req_id>', view_func=requirements.update_requirement, methods=['PUT'])
api_blueprint.add_url_rule('/requirements/<int:req_id>', view_func=requirements.delete_requirement, methods=['DELETE'])

# Test cases
api_blueprint.add_url_rule('/cases', view_func=test_cases.handle_cases, methods=['GET', 'POST'])
api_blueprint.add_url_rule('/cases/<int:case_id>', view_func=test_cases.handle_case_by_id, methods=['GET', 'PUT', 'DELETE'])

# Executions
api_blueprint.add_url_rule('/executions', view_func=executions.get_executions, methods=['GET'])
api_blueprint.add_url_rule('/executions/<int:exec_id>', view_func=executions.get_execution, methods=['GET'])

# Projects
api_blueprint.add_url_rule('/projects', view_func=projects.get_projects, methods=['GET'])
api_blueprint.add_url_rule('/projects', view_func=projects.create_project, methods=['POST'])
api_blueprint.add_url_rule('/projects/<int:project_id>', view_func=projects.get_project, methods=['GET'])

# Conversations
api_blueprint.add_url_rule('/conversations', view_func=conversations.get_conversations, methods=['GET'])
api_blueprint.add_url_rule('/conversations', view_func=conversations.create_conversation, methods=['POST'])
api_blueprint.add_url_rule('/conversations/<int:conv_id>', view_func=conversations.get_conversation, methods=['GET'])
api_blueprint.add_url_rule('/conversations/<int:conv_id>', view_func=conversations.delete_conversation, methods=['DELETE'])
api_blueprint.add_url_rule('/conversations/<int:conv_id>/messages', view_func=conversations.get_messages, methods=['GET'])
api_blueprint.add_url_rule('/conversations/<int:conv_id>/messages', view_func=conversations.send_message, methods=['POST'])
api_blueprint.add_url_rule('/conversations/<int:conv_id>/agent-context', view_func=conversations.get_agent_context, methods=['GET'])
api_blueprint.add_url_rule('/conversations/<int:conv_id>/stream', view_func=conversations.stream_conversation, methods=['GET'])
api_blueprint.add_url_rule('/conversations/<int:conv_id>/read', view_func=conversations.mark_conversation_read, methods=['POST'])

# Code reviews (Phase 1)
api_blueprint.add_url_rule('/code-reviews', view_func=code_reviews.list_review_tasks, methods=['GET'])
api_blueprint.add_url_rule('/code-reviews', view_func=code_reviews.create_review_task, methods=['POST'])
api_blueprint.add_url_rule('/code-reviews/<int:task_id>', view_func=code_reviews.get_review_task, methods=['GET'])

# Knowledge bases (Phase 2)
api_blueprint.add_url_rule('/knowledge-bases', view_func=knowledge_bases.list_knowledge_bases, methods=['GET'])
api_blueprint.add_url_rule('/knowledge-bases', view_func=knowledge_bases.create_knowledge_base, methods=['POST'])
api_blueprint.add_url_rule('/knowledge-bases/<int:knowledge_base_id>', view_func=knowledge_bases.get_knowledge_base, methods=['GET'])
api_blueprint.add_url_rule('/knowledge-bases/<int:knowledge_base_id>/entries', view_func=knowledge_bases.create_knowledge_entry, methods=['POST'])
api_blueprint.add_url_rule('/knowledge-bases/<int:knowledge_base_id>/import', view_func=knowledge_bases.import_knowledge_entry, methods=['POST'])
api_blueprint.add_url_rule('/knowledge-bases/search', view_func=knowledge_bases.search_knowledge_entries, methods=['POST'])

# Reports and defect analysis (Phase 3)
api_blueprint.add_url_rule('/reports', view_func=reports.create_requirement_report, methods=['POST'])
api_blueprint.add_url_rule('/reports/<int:report_id>', view_func=reports.get_report, methods=['GET'])
api_blueprint.add_url_rule('/reports/<int:report_id>/preview', view_func=reports.preview_report, methods=['GET'])

# AutoFix suggestions (Phase 4)
api_blueprint.add_url_rule('/autofix/suggestions', view_func=autofix.generate_fix_suggestions, methods=['POST'])

# Agent workbench
api_blueprint.add_url_rule('/agent-workbench', view_func=agent_workbench.list_agent_workbench, methods=['GET'])
api_blueprint.add_url_rule('/agent-workbench/<int:requirement_id>', view_func=agent_workbench.get_agent_workbench, methods=['GET'])

# Flow routes
api_blueprint.add_url_rule('/flow/start', view_func=flow.start_test_flow, methods=['POST'])
api_blueprint.add_url_rule('/flow/status/<int:req_id>', view_func=flow.get_test_flow_status, methods=['GET'])
api_blueprint.add_url_rule('/flow/resume/<int:req_id>', view_func=flow.resume_test_flow, methods=['POST'])
api_blueprint.add_url_rule('/flow/cancel/<int:req_id>', view_func=flow.cancel_test_flow, methods=['POST'])
api_blueprint.add_url_rule('/flow/confirm-cases/<int:req_id>', view_func=flow.confirm_cases_test_flow, methods=['POST'])
api_blueprint.add_url_rule('/flow/re-execute/<int:req_id>', view_func=flow.re_execute_test_flow, methods=['POST'])
api_blueprint.add_url_rule('/flow/retry-script/<int:script_id>', view_func=flow.retry_test_script, methods=['POST'])

# Agent config
api_blueprint.add_url_rule('/agent-configs', view_func=agent_config.list_agent_configs, methods=['GET'])
api_blueprint.add_url_rule('/agent-configs', view_func=agent_config.upsert_agent_config, methods=['POST'])
api_blueprint.add_url_rule('/agent-configs/<int:config_id>', view_func=agent_config.update_agent_config, methods=['PUT'])

# Environment config
api_blueprint.add_url_rule('/environment/<int:requirement_id>', view_func=agent_config.get_environment_config, methods=['GET'])
api_blueprint.add_url_rule('/environment', view_func=agent_config.save_environment_config, methods=['POST'])

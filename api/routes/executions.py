"""
执行记录相关路由
"""

from flask import request, jsonify
from models import db, ExecutionRecord, TestScript, TestCase

def get_executions():
    """获取执行记录列表"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = request.args.get('status')
        test_script_id = request.args.get('test_script_id')
        
        query = ExecutionRecord.query
        
        if status:
            query = query.filter_by(status=status)
        if test_script_id:
            query = query.filter_by(test_script_id=test_script_id)
        
        # 按开始时间倒序排列
        query = query.order_by(ExecutionRecord.started_at.desc())
        
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        executions = pagination.items
        
        return jsonify({
            'items': [exec.to_dict() for exec in executions],
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'pages': pagination.pages
        })
        
    except Exception as e:
        return jsonify({
            'error': '获取执行记录列表失败',
            'message': str(e)
        }), 500

def get_execution(exec_id):
    """获取单个执行记录详情"""
    try:
        execution = ExecutionRecord.query.get_or_404(exec_id)
        
        # 获取关联的测试脚本和测试用例
        test_script = TestScript.query.get(execution.test_script_id)
        test_case = TestCase.query.get(test_script.test_case_id) if test_script else None
        
        result = execution.to_dict()
        result['test_script'] = test_script.to_dict() if test_script else None
        result['test_case'] = test_case.to_dict() if test_case else None
        result['result_data'] = execution.result_data
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'error': '获取执行记录详情失败',
            'message': str(e)
        }), 500
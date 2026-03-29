from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Requirement(db.Model):
    """需求表"""
    __tablename__ = 'requirements'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    raw_text = db.Column(db.Text, nullable=False)  # 原始需求文本
    structured_data = db.Column(db.JSON)  # 结构化需求数据
    status = db.Column(db.String(50), default='pending')  # pending, parsed, error
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    test_cases = db.relationship('TestCase', backref='requirement', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'test_case_count': len(self.test_cases)
        }

class TestCase(db.Model):
    """测试用例表"""
    __tablename__ = 'test_cases'
    
    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirements.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    test_type = db.Column(db.String(50))  # api, ui, performance, security
    priority = db.Column(db.String(20), default='medium')  # high, medium, low
    steps = db.Column(db.JSON)  # 测试步骤
    expected_results = db.Column(db.JSON)  # 预期结果
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关系
    test_scripts = db.relationship('TestScript', backref='test_case', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'requirement_id': self.requirement_id,
            'title': self.title,
            'description': self.description,
            'test_type': self.test_type,
            'priority': self.priority,
            'steps': self.steps,
            'expected_results': self.expected_results,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'script_count': len(self.test_scripts)
        }

class TestScript(db.Model):
    """测试脚本表"""
    __tablename__ = 'test_scripts'
    
    id = db.Column(db.Integer, primary_key=True)
    test_case_id = db.Column(db.Integer, db.ForeignKey('test_cases.id'), nullable=False)
    script_type = db.Column(db.String(50))  # python, javascript, etc.
    script_content = db.Column(db.Text, nullable=False)
    file_path = db.Column(db.String(500))
    status = db.Column(db.String(50), default='generated')  # generated, executed, error
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关系
    executions = db.relationship('ExecutionRecord', backref='test_script', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'test_case_id': self.test_case_id,
            'script_type': self.script_type,
            'status': self.status,
            'file_path': self.file_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'execution_count': len(self.executions)
        }

class ExecutionRecord(db.Model):
    """执行记录表"""
    __tablename__ = 'execution_records'
    
    id = db.Column(db.Integer, primary_key=True)
    test_script_id = db.Column(db.Integer, db.ForeignKey('test_scripts.id'), nullable=False)
    status = db.Column(db.String(50))  # passed, failed, error, running
    result_data = db.Column(db.JSON)  # 执行结果数据
    error_message = db.Column(db.Text)
    execution_time = db.Column(db.Float)  # 执行时间（秒）
    report_path = db.Column(db.String(500))  # 报告文件路径
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'test_script_id': self.test_script_id,
            'status': self.status,
            'execution_time': self.execution_time,
            'error_message': self.error_message,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'report_path': self.report_path
        }

class Project(db.Model):
    """项目表"""
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    config = db.Column(db.JSON)  # 项目配置
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关系
    requirements = db.relationship('Requirement', backref='project', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'requirement_count': len(self.requirements)
        }
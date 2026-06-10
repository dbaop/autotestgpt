from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

REQUIREMENT_STATUS_FLOW = {
    'pending': {'parsed', 'error'},
    'parsed': {'cases_generated', 'error'},
    'cases_generated': {'code_generated', 'error'},
    'code_generated': {'executing', 'error'},
    'executing': {'executed', 'error'},
    'executed': {'completed', 'error'},
    'completed': set(),
    'error': {'pending', 'parsed', 'cases_generated', 'code_generated', 'executing'},
}


class Requirement(db.Model):
    __tablename__ = 'requirements'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    raw_text = db.Column(db.Text, nullable=False)
    structured_data = db.Column(db.JSON)
    status = db.Column(db.String(50), default='pending')
    execution_progress = db.Column(db.JSON)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    knowledge_base_id = db.Column(db.Integer, db.ForeignKey('knowledge_bases.id'), nullable=True)
    current_phase = db.Column(db.String(50), default='idle')
    conversation_messages = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    test_cases = db.relationship('TestCase', backref='requirement', lazy=True, cascade='all, delete-orphan')

    def can_transition_to(self, target_status: str) -> bool:
        if self.status == target_status:
            return True
        return target_status in REQUIREMENT_STATUS_FLOW.get(self.status, set())

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'status': self.status,
            'execution_progress': self.execution_progress,
            'knowledge_base_id': self.knowledge_base_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'test_case_count': len(self.test_cases),
            'current_phase': self.current_phase,
        }


class TestSuite(db.Model):
    __tablename__ = 'test_suites'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    tags = db.Column(db.JSON)
    requirement_pattern = db.Column(db.Text)
    is_reusable = db.Column(db.Boolean, default=True)
    usage_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    test_cases = db.relationship('TestCase', backref='test_suite', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'tags': self.tags or [],
            'requirement_pattern': self.requirement_pattern,
            'is_reusable': self.is_reusable,
            'usage_count': self.usage_count,
            'test_case_count': len(self.test_cases),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class TestCase(db.Model):
    __tablename__ = 'test_cases'

    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirements.id'), nullable=False)
    test_suite_id = db.Column(db.Integer, db.ForeignKey('test_suites.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    test_type = db.Column(db.String(50))
    priority = db.Column(db.String(20), default='medium')
    methodology = db.Column(db.String(50))  # boundary_value / equivalence_partitioning / error_guessing / state_transition / decision_table / pairwise
    steps = db.Column(db.JSON)
    expected_results = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    test_scripts = db.relationship('TestScript', backref='test_case', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'requirement_id': self.requirement_id,
            'test_suite_id': self.test_suite_id,
            'title': self.title,
            'description': self.description,
            'test_type': self.test_type,
            'priority': self.priority,
            'methodology': self.methodology,
            'steps': self.steps,
            'expected_results': self.expected_results,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'script_count': len(self.test_scripts),
        }


class TestScript(db.Model):
    __tablename__ = 'test_scripts'

    id = db.Column(db.Integer, primary_key=True)
    test_case_id = db.Column(db.Integer, db.ForeignKey('test_cases.id'), nullable=False)
    script_type = db.Column(db.String(50))
    script_content = db.Column(db.Text, nullable=False)
    file_path = db.Column(db.String(500))
    status = db.Column(db.String(50), default='generated')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    executions = db.relationship('ExecutionRecord', backref='test_script', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'test_case_id': self.test_case_id,
            'script_type': self.script_type,
            'status': self.status,
            'file_path': self.file_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'execution_count': len(self.executions),
        }


class ExecutionRecord(db.Model):
    __tablename__ = 'execution_records'

    id = db.Column(db.Integer, primary_key=True)
    test_script_id = db.Column(db.Integer, db.ForeignKey('test_scripts.id'), nullable=False)
    status = db.Column(db.String(50))
    result_data = db.Column(db.JSON)
    error_message = db.Column(db.Text)
    execution_time = db.Column(db.Float)
    report_path = db.Column(db.String(500))
    screenshot_paths = db.Column(db.JSON)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'test_script_id': self.test_script_id,
            'status': self.status,
            'execution_time': self.execution_time,
            'error_message': self.error_message,
            'screenshot_paths': self.screenshot_paths or [],
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'report_path': self.report_path,
        }


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    config = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    requirements = db.relationship('Requirement', backref='project', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'requirement_count': len(self.requirements),
        }


class KnowledgeBase(db.Model):
    __tablename__ = 'knowledge_bases'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    entries = db.relationship('KnowledgeEntry', backref='knowledge_base', lazy=True, cascade='all, delete-orphan')
    requirements = db.relationship('Requirement', backref='knowledge_base', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'entry_count': len(self.entries),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class KnowledgeEntry(db.Model):
    __tablename__ = 'knowledge_entries'

    id = db.Column(db.Integer, primary_key=True)
    knowledge_base_id = db.Column(db.Integer, db.ForeignKey('knowledge_bases.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    tags = db.Column(db.JSON)
    source_type = db.Column(db.String(50), default='manual')
    source_ref = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'knowledge_base_id': self.knowledge_base_id,
            'title': self.title,
            'content': self.content,
            'tags': self.tags or [],
            'source_type': self.source_type,
            'source_ref': self.source_ref,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Conversation(db.Model):
    __tablename__ = 'conversations'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirements.id'), nullable=True)
    status = db.Column(db.String(50), default='active')
    last_read_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    messages = db.relationship('Message', backref='conversation', lazy=True, cascade='all, delete-orphan', order_by='Message.created_at')

    def unread_count(self) -> int:
        """Count non-user messages newer than last_read_at (treat NULL as 'never read')."""
        if not self.messages:
            return 0
        last_read = self.last_read_at
        count = 0
        for msg in self.messages:
            if msg.sender == 'user':
                continue
            if last_read is None or (msg.created_at and msg.created_at > last_read):
                count += 1
        return count

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'requirement_id': self.requirement_id,
            'status': self.status,
            'last_read_at': self.last_read_at.isoformat() if self.last_read_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'message_count': len(self.messages),
            'unread_count': self.unread_count(),
        }


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False)
    sender = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    agent_type = db.Column(db.String(50))
    extra_data = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'sender': self.sender,
            'content': self.content,
            'agent_type': self.agent_type,
            'metadata': self.extra_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class CodeReviewTask(db.Model):
    __tablename__ = 'code_review_tasks'

    id = db.Column(db.Integer, primary_key=True)
    repo_url = db.Column(db.String(500), nullable=True)
    repo_path = db.Column(db.String(1000), nullable=True)
    repo_type = db.Column(db.String(20), nullable=False, default='remote')
    branch = db.Column(db.String(200), nullable=False, default='main')
    days = db.Column(db.Integer, nullable=False, default=7)
    status = db.Column(db.String(50), default='pending')
    summary = db.Column(db.Text)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)

    findings = db.relationship('CodeReviewFinding', backref='task', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'repo_url': self.repo_url,
            'repo_path': self.repo_path,
            'repo_type': self.repo_type,
            'branch': self.branch,
            'days': self.days,
            'status': self.status,
            'summary': self.summary,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'finding_count': len(self.findings),
        }


class CodeReviewFinding(db.Model):
    __tablename__ = 'code_review_findings'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('code_review_tasks.id'), nullable=False)
    commit_sha = db.Column(db.String(100))
    file_path = db.Column(db.String(1000))
    severity = db.Column(db.String(30), default='info')
    category = db.Column(db.String(50))
    review_type = db.Column(db.String(50))
    suggestion = db.Column(db.Text)
    title = db.Column(db.String(300), nullable=False)
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'commit_sha': self.commit_sha,
            'file_path': self.file_path,
            'severity': self.severity,
            'category': self.category,
            'review_type': self.review_type,
            'suggestion': self.suggestion,
            'title': self.title,
            'detail': self.detail,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class DefectCandidate(db.Model):
    __tablename__ = 'defect_candidates'

    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirements.id'), nullable=False)
    review_task_id = db.Column(db.Integer, db.ForeignKey('code_review_tasks.id'), nullable=True)
    test_case_id = db.Column(db.Integer, db.ForeignKey('test_cases.id'), nullable=True)
    execution_record_id = db.Column(db.Integer, db.ForeignKey('execution_records.id'), nullable=True)
    source_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(30), default='medium')
    title = db.Column(db.String(300), nullable=False)
    summary = db.Column(db.Text)
    evidence = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    requirement = db.relationship('Requirement', backref='defect_candidates', lazy=True)
    review_task = db.relationship('CodeReviewTask', backref='defect_candidates', lazy=True)
    test_case = db.relationship('TestCase', backref='defect_candidates', lazy=True)
    execution_record = db.relationship('ExecutionRecord', backref='defect_candidates', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'requirement_id': self.requirement_id,
            'review_task_id': self.review_task_id,
            'test_case_id': self.test_case_id,
            'execution_record_id': self.execution_record_id,
            'source_type': self.source_type,
            'severity': self.severity,
            'title': self.title,
            'summary': self.summary,
            'evidence': self.evidence,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class FinalReport(db.Model):
    __tablename__ = 'final_reports'

    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirements.id'), nullable=False)
    review_task_id = db.Column(db.Integer, db.ForeignKey('code_review_tasks.id'), nullable=True)
    report_type = db.Column(db.String(50), default='requirement_analysis')
    title = db.Column(db.String(300), nullable=False)
    html_content = db.Column(db.Text, nullable=False)
    summary = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    requirement = db.relationship('Requirement', backref='final_reports', lazy=True)
    review_task = db.relationship('CodeReviewTask', backref='final_reports', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'requirement_id': self.requirement_id,
            'review_task_id': self.review_task_id,
            'report_type': self.report_type,
            'title': self.title,
            'summary': self.summary,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class AgentEvent(db.Model):
    __tablename__ = 'agent_events'

    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirements.id'), nullable=False)
    agent = db.Column(db.String(80), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    payload = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    requirement = db.relationship('Requirement', backref='agent_events', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'requirement_id': self.requirement_id,
            'agent': self.agent,
            'event_type': self.event_type,
            'message': self.message,
            'payload': self.payload or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class FixSuggestion(db.Model):
    __tablename__ = 'fix_suggestions'

    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirements.id'), nullable=False)
    defect_candidate_id = db.Column(db.Integer, db.ForeignKey('defect_candidates.id'), nullable=False)
    mode = db.Column(db.String(50), default='suggestion_only')
    title = db.Column(db.String(300), nullable=False)
    root_cause = db.Column(db.Text)
    suggested_action = db.Column(db.Text)
    target_files = db.Column(db.JSON)
    patch_preview = db.Column(db.Text)
    confidence = db.Column(db.Float, default=0.5)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    requirement = db.relationship('Requirement', backref='fix_suggestions', lazy=True)
    defect_candidate = db.relationship('DefectCandidate', backref='fix_suggestions', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'requirement_id': self.requirement_id,
            'defect_candidate_id': self.defect_candidate_id,
            'mode': self.mode,
            'title': self.title,
            'root_cause': self.root_cause,
            'suggested_action': self.suggested_action,
            'target_files': self.target_files or [],
            'patch_preview': self.patch_preview,
            'confidence': self.confidence,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class AgentConfig(db.Model):
    __tablename__ = 'agent_configs'

    id = db.Column(db.Integer, primary_key=True)
    agent_type = db.Column(db.String(50), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    system_prompt = db.Column(db.Text)
    model_name = db.Column(db.String(100))
    temperature = db.Column(db.Float, default=0.1)
    max_tokens = db.Column(db.Integer, default=4000)
    is_enabled = db.Column(db.Boolean, default=True)
    extra_config = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'agent_type': self.agent_type,
            'project_id': self.project_id,
            'system_prompt': self.system_prompt,
            'model_name': self.model_name,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'is_enabled': self.is_enabled,
            'extra_config': self.extra_config or {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from config import Config

Base = declarative_base()

class Requirement(Base):
    __tablename__ = 'requirements'
    
    id = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False)
    parsed_result = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    
    cases = relationship("TestCase", back_populates="requirement")


class TestCase(Base):
    __tablename__ = 'test_cases'
    
    id = Column(Integer, primary_key=True)
    requirement_id = Column(Integer, ForeignKey('requirements.id'))
    case_type = Column(String(20))  # 'api' or 'ui'
    case_data = Column(Text)  # JSON 格式的用例数据
    created_at = Column(DateTime, default=datetime.now)
    
    requirement = relationship("Requirement", back_populates="cases")
    scripts = relationship("TestScript", back_populates="test_case")


class TestScript(Base):
    __tablename__ = 'test_scripts'
    
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey('test_cases.id'))
    script_type = Column(String(20))  # 'api' or 'ui'
    script_content = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    
    test_case = relationship("TestCase", back_populates="scripts")
    executions = relationship("ExecutionRecord", back_populates="script")


class ExecutionRecord(Base):
    __tablename__ = 'execution_records'
    
    id = Column(Integer, primary_key=True)
    script_id = Column(Integer, ForeignKey('test_scripts.id'))
    status = Column(String(20))  # 'success', 'failed', 'running'
    result = Column(Text)  # JSON 格式的执行结果
    report_path = Column(String(255))
    created_at = Column(DateTime, default=datetime.now)
    
    script = relationship("TestScript", back_populates="executions")


def init_db():
    engine = create_engine(Config.DATABASE_URI, echo=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session
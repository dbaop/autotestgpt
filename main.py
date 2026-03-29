from flask import Flask, request, jsonify
from flow.test_flow import AutoTestFlow
from config import Config
from models import init_db, Requirement, TestCase, TestScript, ExecutionRecord
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
import json

app = Flask(__name__)

# 数据库初始化
engine = create_engine(Config.DATABASE_URI, echo=False)
Session = sessionmaker(bind=engine)
session = Session()

flow = AutoTestFlow()

@app.route("/api/flow/start", methods=["POST"])
def start_flow():
    data = request.json
    demand = data.get("demand", "")
    if not demand:
        return jsonify({"code": 400, "msg": "demand is required"})
    
    # 保存需求到数据库
    requirement = Requirement(content=demand)
    session.add(requirement)
    session.commit()
    
    # 执行工作流
    result = flow.execute({"demand": demand})
    
    # 更新需求的解析结果
    requirement.parsed_result = json.dumps(result.get("parse_req", {}), ensure_ascii=False)
    session.commit()
    
    return jsonify({
        "code": 200,
        "msg": "success",
        "data": result,
        "requirement_id": requirement.id
    })

@app.route("/api/requirements", methods=["GET"])
def get_requirements():
    requirements = session.query(Requirement).order_by(Requirement.created_at.desc()).limit(10).all()
    return jsonify({
        "code": 200,
        "data": [
            {
                "id": req.id,
                "content": req.content,
                "parsed_result": json.loads(req.parsed_result) if req.parsed_result else None,
                "created_at": req.created_at.isoformat()
            }
            for req in requirements
        ]
    })

@app.route("/api/requirements/<int:req_id>", methods=["GET"])
def get_requirement(req_id):
    requirement = session.query(Requirement).filter(Requirement.id == req_id).first()
    if not requirement:
        return jsonify({"code": 404, "msg": "requirement not found"})
    
    return jsonify({
        "code": 200,
        "data": {
            "id": requirement.id,
            "content": requirement.content,
            "parsed_result": json.loads(requirement.parsed_result) if requirement.parsed_result else None,
            "created_at": requirement.created_at.isoformat()
        }
    })

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "code": 200,
        "status": "healthy",
        "database": "connected"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.SERVER_PORT, debug=True)
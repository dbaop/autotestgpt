from models import db, Requirement
from main import app

with app.app_context():
    req = Requirement.query.get(5)
    if req:
        print(f"Status: {req.status}")
        print(f"Execution Progress: {req.execution_progress}")
    else:
        print("Requirement not found")
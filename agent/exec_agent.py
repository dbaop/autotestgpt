import os
import subprocess
from config import Config

class ExecAgent:
    def __init__(self):
        os.makedirs(Config.WORKSPACE, exist_ok=True)
        os.makedirs(Config.REPORT_DIR, exist_ok=True)

    def run_api(self, code, filename="test_api.py"):
        path = os.path.join(Config.WORKSPACE, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        subprocess.run(["pytest", path, "--alluredir", Config.REPORT_DIR], capture_output=True)
        return {"status": "done", "report_dir": Config.REPORT_DIR}

    def run_ui(self, code, filename="test_ui.py"):
        path = os.path.join(Config.WORKSPACE, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        subprocess.run(["pytest", path, "--alluredir", Config.REPORT_DIR], capture_output=True)
        return {"status": "done", "report_dir": Config.REPORT_DIR}
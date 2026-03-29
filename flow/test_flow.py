# from liteflow import Flow, step
from liteflow.core import *
from liteflow.core import Workflow, StepBody, WorkflowBuilder, ExecutionResult, StepExecutionContext
from agent.req_agent import ReqAgent
from agent.case_agent import CaseAgent
from agent.code_agent import CodeAgent
from agent.exec_agent import ExecAgent

@Flow(name="autotest_full_flow")
class AutoTestFlow:
    def __init__(self):
        self.req_agent = ReqAgent()
        self.case_agent = CaseAgent()
        self.code_agent = CodeAgent()
        self.exec_agent = ExecAgent()

    @step(name="parse_req")
    def parse_req(self, data):
        return self.req_agent.parse(data["demand"])

    @step(name="gen_case", deps=["parse_req"])
    def gen_case(self, ctx):
        return self.case_agent.gen(ctx["parse_req"])

    @step(name="gen_api_code", deps=["gen_case"])
    def gen_api_code(self, ctx):
        return self.code_agent.gen_api(ctx["gen_case"])

    @step(name="gen_ui_code", deps=["gen_case"])
    def gen_ui_code(self, ctx):
        return self.code_agent.gen_ui(ctx["gen_case"])

    @step(name="run_api", deps=["gen_api_code"])
    def run_api(self, ctx):
        return self.exec_agent.run_api(ctx["gen_api_code"])

    @step(name="run_ui", deps=["gen_ui_code"])
    def run_ui(self, ctx):
        return self.exec_agent.run_ui(ctx["gen_ui_code"])
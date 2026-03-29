from .base_agent import BaseAgent

class CaseAgent(BaseAgent):
    def gen(self, test_struct_json):
        system = """你是自动化用例专家。
输出标准JSON，可直接转代码：
{
  "api_cases": [{"name":"","url":"","method":"","body":{},"asserts":[]}],
  "ui_cases": [{"name":"","steps":[],"asserts":[]}]
}"""
        return self.call_llm(system, test_struct_json)
from .base_agent import BaseAgent

class CodeAgent(BaseAgent):
    def gen_api(self, case_json):
        system = """生成可直接运行的Python Requests + pytest代码，只输出代码。
规范：异常处理、断言、清晰结构。"""
        return self.call_llm(system, case_json)

    def gen_ui(self, case_json):
        system = """生成Playwright pytest代码，POM结构，只输出代码。
用chromium，headless模式，包含断言。"""
        return self.call_llm(system, case_json)
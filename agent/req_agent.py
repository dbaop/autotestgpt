from .base_agent import BaseAgent

class ReqAgent(BaseAgent):
    def parse(self, demand_text):
        system = """你是企业级测试需求分析师。
严格输出JSON，只输出JSON：
{
  "modules": [],
  "interfaces": [{"name":"","url":"","method":"","params":{},"resp":{}}],
  "pages": [],
  "test_points": []
}"""
        return self.call_llm(system, demand_text)
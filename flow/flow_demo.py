# flow_demo.py
from liteflow.core import *
from api_executor import APIExecutor
from ui_executor import UIExecutor

class TestFlow(Flow):
    def __init__(self):
        super().__init__()
        self.api = APIExecutor()
        self.ui = UIExecutor()

    def run(self):
        # 执行 API 流程
        res = self.api.send_get("https://httpbin.org/get")
        self.api.assert_status(res, 200)

        # 执行 UI 流程
        self.ui.init_browser()
        self.ui.open_url("https://www.baidu.com")
        self.ui.input_text((By.ID, "kw"), "LiteFlow")
        self.ui.click_element((By.ID, "su"))
        self.ui.close_browser()

if __name__ == "__main__":
    flow = TestFlow()
    flow.run()
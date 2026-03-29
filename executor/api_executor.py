# api_executor.py
import requests
from liteflow.decorators import step


class APIExecutor:
    """API 用例执行器"""

    @step
    def send_get(self, url: str, params: dict = None, headers: dict = None):
        """发送 GET 请求"""
        response = requests.get(url, params=params, headers=headers)
        print(f"[API GET] {url} 状态码: {response.status_code}")
        return response

    @step
    def send_post(self, url: str, json: dict = None, headers: dict = None):
        """发送 POST 请求"""
        response = requests.post(url, json=json, headers=headers)
        print(f"[API POST] {url} 状态码: {response.status_code}")
        return response

    @step
    def assert_status(self, response, expected_code: int = 200):
        """断言响应状态码"""
        assert response.status_code == expected_code, \
            f"状态码错误！预期：{expected_code}，实际：{response.status_code}"
        print("✅ API 断言通过")
        return True
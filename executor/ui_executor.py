# ui_executor.py
from selenium import webdriver
from selenium.webdriver.common.by import By
from liteflow.decorators import step


class UIExecutor:
    """UI 自动化执行器"""

    def __init__(self):
        self.driver = None

    @step
    def init_browser(self, browser_type: str = "chrome"):
        """初始化浏览器"""
        if browser_type.lower() == "chrome":
            self.driver = webdriver.Chrome()
        self.driver.maximize_window()
        print("✅ 浏览器启动成功")

    @step
    def open_url(self, url: str):
        """打开页面"""
        self.driver.get(url)
        print(f"✅ 打开页面: {url}")

    @step
    def input_text(self, locator: tuple, text: str):
        """输入文本"""
        by, value = locator
        element = self.driver.find_element(by, value)
        element.clear()
        element.send_keys(text)
        print(f"✅ 输入文本: {text}")

    @step
    def click_element(self, locator: tuple):
        """点击元素"""
        by, value = locator
        self.driver.find_element(by, value).click()
        print("✅ 点击完成")

    @step
    def close_browser(self):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()
            print("✅ 浏览器已关闭")
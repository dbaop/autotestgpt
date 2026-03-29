from litellm import completion
from config import Config

class BaseAgent:
    def __init__(self):
        self.model = "deepseek/deepseek-coder"
        self.api_key = Config.DEEPSEEK_API_KEY

    def call_llm(self, system_prompt, user_content):
        resp = completion(
            model=self.model,
            api_key=self.api_key,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.1
        )
        return resp.choices[0].message.content.strip()
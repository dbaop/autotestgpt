"""
基础智能体类
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, List, Optional
import litellm
from config import Config

logger = logging.getLogger(__name__)

# 模型优先级配置: (config_key, model_name, api_base)
_MODEL_PRIORITY = [
    ('MINIMAX_API_KEY', 'minimax/abab6.5s-chat', 'https://api.minimax.chat/v1'),
    ('DEEPSEEK_API_KEY', 'deepseek/deepseek-chat', None),
    ('OPENAI_API_KEY', 'gpt-4', None),
]


def _resolve_llm_config():
    """按优先级解析可用的 LLM 配置"""
    for key, model, base in _MODEL_PRIORITY:
        api_key = getattr(Config, key, None)
        if api_key:
            return model, api_key, base
    return 'deepseek/deepseek-chat', None, None


def load_agent_config(agent_type: str) -> dict | None:
    """从数据库加载 Agent 的自定义配置。"""
    try:
        from models import AgentConfig, db
        config = AgentConfig.query.filter_by(
            agent_type=agent_type, is_enabled=True
        ).first()
        if config:
            return config.to_dict()
    except Exception:
        pass
    return None


class BaseAgent(ABC):
    """基础智能体类"""

    def __init__(self, model: str = "deepseek/deepseek-chat", temperature: float = 0.1,
                 force_model: Optional[str] = None, api_key: Optional[str] = None,
                 api_base: Optional[str] = None, agent_type: Optional[str] = None):
        self.model = model
        self.temperature = temperature
        self.max_tokens = 4000
        self.force_model = force_model
        self._api_key = api_key
        self._api_base = api_base
        self.agent_type = agent_type
        self.custom_system_prompt: Optional[str] = None
        if agent_type:
            self._apply_custom_config()

    def _apply_custom_config(self):
        """从数据库加载自定义配置并应用。"""
        config = load_agent_config(self.agent_type)
        if not config:
            return
        if config.get("system_prompt"):
            self.custom_system_prompt = config["system_prompt"]
        if config.get("model_name"):
            self.force_model = config["model_name"]
        if config.get("temperature") is not None:
            self.temperature = config["temperature"]
        if config.get("max_tokens") is not None:
            self.max_tokens = config["max_tokens"]

    def call_llm(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """调用大模型 — 优先使用实例指定的模型，否则按优先级自动选择"""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            if self.force_model:
                resolved_model = self.force_model
                api_key = self._api_key
                api_base = self._api_base
            else:
                resolved_model, api_key, api_base = _resolve_llm_config()

            kwargs = dict(
                model=resolved_model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            if api_key:
                kwargs['api_key'] = api_key
            if api_base:
                kwargs['api_base'] = api_base

            response = litellm.completion(**kwargs)
            content = response.choices[0].message.content
            logger.info(f"LLM调用成功，模型: {resolved_model}, 响应长度: {len(content)}")
            return content

        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            raise

    def call_llm_stream(
        self, messages: List[Dict[str, str]]
    ) -> Generator[str, None, None]:
        token_count = 0
        try:
            if self.force_model:
                resolved_model = self.force_model
                api_key = self._api_key
                api_base = self._api_base
            else:
                resolved_model, api_key, api_base = _resolve_llm_config()

            kwargs = dict(
                model=resolved_model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )
            if api_key:
                kwargs["api_key"] = api_key
            if api_base:
                kwargs["api_base"] = api_base

            response = litellm.completion(**kwargs)
            for chunk in response:
                delta = getattr(chunk.choices[0].delta, "content", None)
                if delta:
                    token_count += 1
                    yield delta
            logger.info("LLM流式调用成功, token数: %s", token_count)

        except Exception as e:
            logger.error(f"LLM流式调用失败: {e}")
            yield f"\n[LLM error: {e}]"

    def parse_json_response(self, response: str) -> Dict[str, Any]:
        """从 LLM 响应中提取 JSON（正确处理嵌套对象）"""
        import re

        # Try to find a fenced ```json ... ``` block with balanced braces
        json_str = self._extract_fenced_json(response)

        if json_str is None:
            # Fallback: find the outermost { ... } using brace counting
            start = response.find('{')
            if start == -1:
                # Try to find a JSON array
                start = response.find('[')
                if start != -1:
                    json_str = self._extract_balanced(response, start, '[', ']')
            else:
                json_str = self._extract_balanced(response, start, '{', '}')

        if json_str is None:
            json_str = response

        # Try json5 first (handles trailing commas, comments, single quotes)
        try:
            import json5
            return json5.loads(json_str)
        except Exception:
            pass

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败 (尝试修复): {e}")
            repaired = self._repair_json(json_str)
            if repaired:
                try:
                    result = json.loads(repaired)
                    logger.info("JSON修复成功")
                    return result
                except json.JSONDecodeError:
                    pass
            logger.error(f"JSON解析失败: {e}, 响应内容前500字符: {response[:500]}...")
            raise ValueError(f"无法解析模型响应为JSON: {e}")

    @staticmethod
    def _repair_json(text: str) -> Optional[str]:
        """Attempt to repair common LLM JSON errors."""
        import re
        repaired = text
        # Remove trailing commas before } or ]
        repaired = re.sub(r',\s*}', '}', repaired)
        repaired = re.sub(r',\s*\]', ']', repaired)
        # Remove trailing comma at end of string
        repaired = re.sub(r',\s*$', '', repaired)
        # Fix missing comma: "value"\n  "key" → "value",\n  "key"
        repaired = re.sub(r'"\s*\n\s*"', '",\n  "', repaired)
        # Fix missing comma: }\n  "key" → },\n  "key"
        repaired = re.sub(r'}\s*\n\s*"', '},\n  "', repaired)
        # Fix missing comma: ]\n  "key" → ],\n  "key"
        repaired = re.sub(r']\s*\n\s*"', '],\n  "', repaired)
        if repaired == text:
            return None
        return repaired

    @staticmethod
    def _extract_fenced_json(response: str) -> Optional[str]:
        """Extract JSON from a ```json ... ``` fenced block, handling nested braces."""
        import re

        for match in re.finditer(r'```(?:json)?\s*\n?', response):
            fence_start = match.end()
            brace_pos = response.find('{', fence_start)
            bracket_pos = response.find('[', fence_start)
            open_char = None
            close_char = None

            if brace_pos != -1 and (bracket_pos == -1 or brace_pos < bracket_pos):
                start_pos = brace_pos
                open_char, close_char = '{', '}'
            elif bracket_pos != -1:
                start_pos = bracket_pos
                open_char, close_char = '[', ']'
            else:
                continue

            # Find the matching closing ``` after the JSON
            extracted = BaseAgent._extract_balanced(response, start_pos, open_char, close_char)
            if extracted is None:
                continue

            # Verify there's a closing ``` after the extracted JSON
            end_pos = start_pos + len(extracted)
            remaining = response[end_pos:].strip()
            if remaining.startswith('```'):
                return extracted
            # If no ``` found, still return if it looks like valid JSON
            try:
                json.loads(extracted)
                return extracted
            except json.JSONDecodeError:
                continue

        return None

    @staticmethod
    def _extract_balanced(text: str, start: int, open_char: str, close_char: str) -> Optional[str]:
        """Extract a balanced bracket/brace pair starting from a given position."""
        if start >= len(text) or text[start] != open_char:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i in range(start, len(text)):
            ch = text[i]

            if escape_next:
                escape_next = False
                continue

            if ch == '\\':
                escape_next = True
                continue

            if ch == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch == open_char:
                depth += 1
            elif ch == close_char:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]

        return None
    
    def save_to_file(self, data: Dict[str, Any], file_path: str):
        """
        保存数据到文件
        
        Args:
            data: 要保存的数据
            file_path: 文件路径
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"数据已保存到: {file_path}")
        except Exception as e:
            logger.error(f"保存文件失败: {e}")
            raise
    
    def load_from_file(self, file_path: str) -> Dict[str, Any]:
        """
        从文件加载数据
        
        Args:
            file_path: 文件路径
            
        Returns:
            加载的数据
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载文件失败: {e}")
            raise
    
    @abstractmethod
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理输入数据
        
        Args:
            input_data: 输入数据
            
        Returns:
            处理结果
        """
        pass
    
    def validate_input(self, input_data: Dict[str, Any], required_fields: list) -> bool:
        """
        验证输入数据
        
        Args:
            input_data: 输入数据
            required_fields: 必需字段列表
            
        Returns:
            是否验证通过
        """
        for field in required_fields:
            if field not in input_data:
                logger.error(f"缺少必需字段: {field}")
                return False
        
        return True
    
    def log_processing(self, input_data: Dict[str, Any], output_data: Dict[str, Any]):
        """
        记录处理日志
        
        Args:
            input_data: 输入数据
            output_data: 输出数据
        """
        logger.info(f"智能体处理完成")
        logger.debug(f"输入数据: {json.dumps(input_data, ensure_ascii=False)[:500]}...")
        logger.debug(f"输出数据: {json.dumps(output_data, ensure_ascii=False)[:500]}...")
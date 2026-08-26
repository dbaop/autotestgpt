"""
基础智能体类
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, List, Optional, Tuple
import litellm
from config import Config

logger = logging.getLogger(__name__)

# 模型优先级配置: (config_key, model_name, api_base) — 兜底 fallback
_MODEL_PRIORITY = [
    ('MINIMAX_API_KEY', 'minimax/abab6.5s-chat', 'https://api.minimax.chat/v1'),
    ('DEEPSEEK_API_KEY', 'deepseek/deepseek-chat', None),
    ('OPENAI_API_KEY', 'gpt-4', None),
]

# 模型标识 → env key 映射：当 Agent.__init__ 指定了 self.model 时，用此表查找 API Key
_MODEL_ENV_MAP: Dict[str, Tuple[str, Optional[str]]] = {
    'minimax/abab6.5s-chat': ('MINIMAX_API_KEY', 'https://api.minimax.chat/v1'),
    'deepseek/deepseek-chat': ('DEEPSEEK_API_KEY', None),
    'gpt-4': ('OPENAI_API_KEY', None),
    'openai/doubao-seed-1-6-vision-250815': ('DOUBAO_API_KEY', 'https://ark.cn-beijing.volces.com/api/v3'),
}

# 视觉模型配置（豆包 doubao-seed-1-6-vision，火山引擎 ARK）
_VISION_MODEL_CONFIG = {
    'api_key_attr': 'DOUBAO_API_KEY',
    'model': 'openai/doubao-seed-1-6-vision-250815',
    'api_base': 'https://ark.cn-beijing.volces.com/api/v3',
}


def _resolve_llm_config():
    """按优先级解析可用的 LLM 配置（兜底 fallback）"""
    for key, model, base in _MODEL_PRIORITY:
        api_key = getattr(Config, key, None)
        if api_key:
            return model, api_key, base
    return 'deepseek/deepseek-chat', None, None


def _resolve_vision_config():
    """解析视觉模型配置（豆包 doubao-seed-1-6-vision）"""
    api_key = getattr(Config, _VISION_MODEL_CONFIG['api_key_attr'], None)
    if api_key:
        return _VISION_MODEL_CONFIG['model'], api_key, _VISION_MODEL_CONFIG['api_base']
    return None, None, None


def _lookup_model_api(model_name: str) -> Tuple[Optional[str], Optional[str]]:
    """根据 litellm 模型标识查找 API Key 和 API Base。

    优先查 _MODEL_ENV_MAP，找不到则通过 _MODEL_PRIORITY 前缀匹配。
    """
    if model_name in _MODEL_ENV_MAP:
        env_key, api_base = _MODEL_ENV_MAP[model_name]
        api_key = getattr(Config, env_key, None)
        return api_key, api_base

    # 前缀模糊匹配（支持 "minimax/xxx" 匹配 "minimax" provider）
    for prefix, (env_key, api_base) in _MODEL_ENV_MAP.items():
        if model_name.startswith(prefix.split('/')[0]):
            api_key = getattr(Config, env_key, None)
            return api_key, api_base

    # 兜底：遍历 _MODEL_PRIORITY
    for env_key, _, api_base in _MODEL_PRIORITY:
        api_key = getattr(Config, env_key, None)
        if api_key:
            return api_key, api_base

    return None, None


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
        # model_config_id 优先于 model_name：从关联的 ModelConfig 读取
        if config.get("model_config_id"):
            try:
                from models import ModelConfig, db
                mc = db.session.get(ModelConfig, config["model_config_id"])
                if mc and mc.is_enabled:
                    self.force_model = mc.model_name
                    # 从 ModelConfig 读取 api_key_env → Config 读取 key
                    api_key = getattr(Config, mc.api_key_env, None) if mc.api_key_env else None
                    self._api_key = api_key
                    self._api_base = mc.api_base
            except Exception:
                pass
        elif config.get("model_name"):
            self.force_model = config["model_name"]
        if config.get("temperature") is not None:
            self.temperature = config["temperature"]
        if config.get("max_tokens") is not None:
            self.max_tokens = config["max_tokens"]

    def _resolve_model(self) -> Tuple[str, Optional[str], Optional[str]]:
        """三级优先级解析模型、API Key 和 API Base：

        1. force_model（来自 DB agent_configs.model_config_id 或 model_name）
        2. self.model 映射到 env vars（使 Agent.__init__ 中指定的 model 真正生效）
        3. _resolve_llm_config() 优先级链（兜底）
        """
        # Level 1: force_model（DB 覆盖）
        if self.force_model:
            api_key, api_base = _lookup_model_api(self.force_model)
            return self.force_model, api_key or self._api_key, api_base or self._api_base

        # Level 2: self.model → env var 映射
        if self.model:
            api_key, api_base = _lookup_model_api(self.model)
            if api_key:
                return self.model, api_key, api_base

        # Level 3: 兜底优先级链
        return _resolve_llm_config()

    def call_llm(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """调用大模型 — 三级优先级：force_model > self.model 映射 > 优先级链"""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            resolved_model, api_key, api_base = self._resolve_model()

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
            resolved_model, api_key, api_base = self._resolve_model()

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

    def call_vision_llm(
        self,
        prompt: str,
        image_urls: Optional[List[str]] = None,
        image_bases: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """调用视觉模型（豆包 doubao-seed-1-6-vision），支持图片识别。

        Args:
            prompt: 文本提示
            image_urls: 图片 URL 列表（HTTP/HTTPS 链接）
            image_bases: base64 编码的图片列表
            system_prompt: 系统提示（可选）
            temperature: 温度参数（可选，默认使用实例的 temperature）
            max_tokens: 最大 token 数（可选，默认 4000）

        Returns:
            模型返回的文本内容
        """
        try:
            resolved_model, api_key, api_base = _resolve_vision_config()
            if not api_key:
                raise ValueError("未配置 DOUBAO_API_KEY，无法使用视觉模型")

            # 构建多模态消息内容
            content_parts = []

            # 添加图片（支持 URL 和 base64）
            if image_urls:
                for url in image_urls:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": url},
                    })

            if image_bases:
                for b64_img in image_bases:
                    # 如果未带前缀，自动添加 data:image/png;base64,
                    if not b64_img.startswith("data:"):
                        b64_img = f"data:image/png;base64,{b64_img}"
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": b64_img},
                    })

            if not content_parts:
                raise ValueError("至少需要提供一个图片 URL 或 base64 图片数据")

            # 添加文本提示
            content_parts.append({"type": "text", "text": prompt})

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": content_parts})

            kwargs = dict(
                model=resolved_model,
                messages=messages,
                temperature=temperature if temperature is not None else self.temperature,
                max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
                api_key=api_key,
                api_base=api_base,
            )

            response = litellm.completion(**kwargs)
            content = response.choices[0].message.content
            logger.info(
                f"视觉模型调用成功，模型: {resolved_model}, "
                f"图片数量: {len(content_parts) - 1}, 响应长度: {len(content)}"
            )
            return content

        except Exception as e:
            logger.error(f"视觉模型调用失败: {e}")
            raise

    def parse_json_response(self, response: str) -> Dict[str, Any]:
        """从 LLM 响应中提取 JSON（正确处理嵌套对象）"""
        import re

        # Try to find a fenced ```json ... ``` block with balanced braces
        json_str = self._extract_fenced_json(response)

        if json_str is None:
            # Fallback: scan for the first balanced { ... } / [ ... ] that
            # actually parses — avoids grabbing JS object literals like
            # `{ test, expect }` from leftover code blocks.
            json_str = self._find_first_parsable_block(response)

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
            # 解析彻底失败时，不抛异常阻塞流程；返回一个包含原始文本的
            # fallback dict，让上游（orchestrator / router）能拿到 agent 的
            # 实际回复并将其作为消息展示给用户，避免流程直接跳到 error 状态。
            logger.warning(
                "JSON解析彻底失败（%s），返回 fallback 结构。响应前500字符: %s",
                e, response[:300]
            )
            fallback_text = response[:2000].strip()
            return {
                "status": "agent_fallback",
                "raw_response": fallback_text,
                "message": fallback_text,
                "error": f"无法解析模型响应为JSON: {e}",
            }

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
        # Fix LLM template placeholders in JSON values
        repaired = re.sub(r'"(true/false)"', '"false"', repaired)  # "required": true/false → false
        repaired = re.sub(r':\s*true/false\b', ': false', repaired)  # required: true/false → false
        repaired = re.sub(r'"(string/integer/boolean|string|integer|boolean|number|object|array)"', '"string"', repaired)
        repaired = re.sub(r':\s*(string/integer/boolean)\b', ': "string"', repaired)
        # Fix missing comma: "value"\n  "key" → "value",\n  "key"
        repaired = re.sub(r'"\s*\n\s*"', '",\n  "', repaired)
        # Fix missing comma: }\n  "key" → },\n  "key"
        repaired = re.sub(r'}\s*\n\s*"', '},\n  "', repaired)
        # Fix missing comma: ]\n  "key" → ],\n  "key"
        repaired = re.sub(r']\s*\n\s*"', '],\n  "', repaired)
        if repaired == text:
            return None
        return repaired

    # Code-block languages that must NOT be treated as JSON. Without this guard
    # a ```javascript block's `{ test, expect }` destructuring gets misparsed as
    # JSON and fails at "char 2".
    _NON_JSON_FENCE_LANGS = {
        "javascript", "js", "jsx", "typescript", "ts", "tsx", "python", "py",
        "bash", "sh", "shell", "java", "go", "rust", "ruby", "rb", "php",
        "html", "css", "xml", "yaml", "yml", "sql", "c", "cpp", "csharp",
    }

    @staticmethod
    def _extract_fenced_json(response: str) -> Optional[str]:
        """Extract JSON from a ```json ... ``` (or untagged) fenced block.

        Skips code-language fences (```javascript / ```python / …) so their
        object literals are never misread as JSON. Among candidate fences,
        returns the first whose content actually parses.
        """
        import re

        def _parses(text: str) -> bool:
            try:
                json.loads(text)
                return True
            except Exception:
                pass
            try:
                import json5
                json5.loads(text)
                return True
            except Exception:
                return False

        for match in re.finditer(r'```([A-Za-z0-9_+#-]*)[ \t]*\r?\n?', response):
            lang = (match.group(1) or "").lower()
            if lang in BaseAgent._NON_JSON_FENCE_LANGS:
                continue  # not a JSON block — skip

            fence_start = match.end()
            brace_pos = response.find('{', fence_start)
            bracket_pos = response.find('[', fence_start)

            if brace_pos != -1 and (bracket_pos == -1 or brace_pos < bracket_pos):
                start_pos, open_char, close_char = brace_pos, '{', '}'
            elif bracket_pos != -1:
                start_pos, open_char, close_char = bracket_pos, '[', ']'
            else:
                continue

            extracted = BaseAgent._extract_balanced(response, start_pos, open_char, close_char)
            if extracted is None:
                continue

            # Only accept if the extracted block actually parses as JSON.
            if _parses(extracted):
                return extracted

        return None

    @staticmethod
    def _find_first_parsable_block(response: str) -> Optional[str]:
        """Scan all { and [ positions; return the first balanced block that
        parses as JSON/JSON5. Falls back to the first balanced block if none
        parse (so _repair_json still gets a chance downstream)."""
        def _parses(text: str) -> bool:
            try:
                json.loads(text)
                return True
            except Exception:
                pass
            try:
                import json5
                json5.loads(text)
                return True
            except Exception:
                return False

        first_block: Optional[str] = None
        for idx, ch in enumerate(response):
            if ch == '{':
                block = BaseAgent._extract_balanced(response, idx, '{', '}')
            elif ch == '[':
                block = BaseAgent._extract_balanced(response, idx, '[', ']')
            else:
                continue
            if not block:
                continue
            if first_block is None:
                first_block = block
            if _parses(block):
                return block
        return first_block

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
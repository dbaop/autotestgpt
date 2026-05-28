"""
基础智能体类
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
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


class BaseAgent(ABC):
    """基础智能体类"""

    def __init__(self, model: str = "deepseek/deepseek-chat", temperature: float = 0.1):
        self.model = model
        self.temperature = temperature
        self.max_tokens = 4000

    def call_llm(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """调用大模型，按优先级自动选择可用的 API"""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

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

    def parse_json_response(self, response: str) -> Dict[str, Any]:
        """从 LLM 响应中提取 JSON"""
        import re

        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1 and end > start:
                json_str = response[start:end + 1]
            else:
                json_str = response

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}, 响应内容: {response[:500]}...")
            raise ValueError(f"无法解析模型响应为JSON: {e}")
    
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
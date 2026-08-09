"""LLM 配置 —— OpenAI 兼容接口.

换模型只需改环境变量或传参:
    # DeepSeek (默认)
    config = LLMConfig.from_env()

    # OpenAI
    config = LLMConfig(
        api_key="sk-...",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
    )

    # 本地模型 (vLLM / Ollama)
    config = LLMConfig(
        api_key="not-needed",
        base_url="http://localhost:8000/v1",
        model="qwen2.5-7b",
    )

环境变量:
    LLM_API_KEY   — API 密钥
    LLM_BASE_URL  — API 地址 (默认 https://api.deepseek.com)
    LLM_MODEL     — 模型名 (默认 deepseek-chat)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from openai import OpenAI


@dataclass
class LLMConfig:
    """OpenAI 兼容的 LLM 配置.

    使用 openai 包，通过 base_url 切换服务商。
    """

    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    temperature: float = 0.0
    max_tokens: int = 2048
    timeout: float = 60.0

    # ---- 工厂方法 ----

    @classmethod
    def from_env(cls, **overrides) -> "LLMConfig":
        """从环境变量读取配置，overrides 可覆盖任意字段."""
        cfg = cls(
            api_key=os.getenv("LLM_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            model=os.getenv("LLM_MODEL", "deepseek-chat"),
        )
        for k, v in overrides.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg

    # ---- 客户端 ----

    def create_client(self) -> OpenAI:
        """创建 OpenAI 兼容客户端."""
        if not self.api_key:
            raise ValueError(
                "LLM_API_KEY 未设置。请设置环境变量或传入 api_key 参数。"
            )
        return OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)

    # ---- 快捷预设 ----

    @classmethod
    def deepseek(cls, api_key: str = "") -> "LLMConfig":
        return cls(
            api_key=api_key or os.getenv("LLM_API_KEY", ""),
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )

    @classmethod
    def openai(cls, api_key: str = "") -> "LLMConfig":
        return cls(
            api_key=api_key or os.getenv("LLM_API_KEY", ""),
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
        )

    @classmethod
    def local(cls, port: int = 8000, model: str = "qwen2.5-7b") -> "LLMConfig":
        return cls(
            api_key="not-needed",
            base_url=f"http://localhost:{port}/v1",
            model=model,
        )

"""统一模型适配层。

不同厂商/模型支持的参数并不一致（部分模型不接受 `temperature`，部分用
`max_output_tokens` 而非 `max_tokens`）。Agent 只声明"我想要什么"，
由适配层决定"实际能传什么"。

因此替换 Agent 的模型时只需要改 YAML，不需要改任何 Agent 代码。
"""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

from ..agents.base.errors import MissingApiKeyError, UnsupportedProviderError
from ..config.schema import AgentConfig

DEFAULT_API_KEY_ENV: dict[str, str] = {"deepseek": "DEEPSEEK_API_KEY"}


@runtime_checkable
class ModelAdapterProtocol(Protocol):
    provider: str

    def supported_params(self) -> frozenset[str]: ...

    def build_request_params(self, config: AgentConfig) -> dict[str, Any]: ...

    def resolve_api_key(self, config: AgentConfig) -> str: ...


class _BaseAdapter:
    provider: str = ""
    _SUPPORTED: frozenset[str] = frozenset(
        {
            "model",
            "messages",
            "temperature",
            "max_tokens",
            "stream",
            "tools",
            "tool_choice",
            "response_format",
            "stop",
        }
    )

    def supported_params(self) -> frozenset[str]:
        return self._SUPPORTED

    def build_request_params(self, config: AgentConfig) -> dict[str, Any]:
        params: dict[str, Any] = {"model": config.model_name}
        if config.temperature is not None and "temperature" in self._SUPPORTED:
            params["temperature"] = config.temperature
        if config.max_tokens is not None and "max_tokens" in self._SUPPORTED:
            params["max_tokens"] = config.max_tokens
        return params

    def resolve_api_key(self, config: AgentConfig) -> str:
        env_name = config.api_key_env or DEFAULT_API_KEY_ENV.get(self.provider, "")
        if not env_name:
            raise MissingApiKeyError(
                f"provider {self.provider!r} 未配置默认 API Key 环境变量名"
            )
        value = os.environ.get(env_name)
        if not value:
            raise MissingApiKeyError(
                f"环境变量 {env_name} 未设置；API Key 不得写入 YAML 或提交到仓库"
            )
        return value


class DeepSeekAdapter(_BaseAdapter):
    provider = "deepseek"


# 静态白名单：新增厂商必须在此显式登记，配置里的 provider 字符串无法触发任意导入
_ADAPTERS: dict[str, ModelAdapterProtocol] = {
    "deepseek": DeepSeekAdapter(),
}


def get_adapter(provider: str) -> ModelAdapterProtocol:
    adapter = _ADAPTERS.get(provider)
    if adapter is None:
        raise UnsupportedProviderError(
            f"未登记的模型厂商: {provider!r}；已支持: {sorted(_ADAPTERS)}"
        )
    return adapter

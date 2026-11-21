"""模型客户端工厂（Task 018 / Task 031）。

把"配置里的模型声明"翻译成具体客户端，并保证**每个 Agent 用自己 YAML 的模型**。

三个 provider，语义必须清晰区分：

| provider | 客户端 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| `offline` | 无（`None`） | 确定性链路正确 | 与模型相关的任何结论 |
| `scripted` | `ScriptedToolModel` | 装配接好了：白名单、预算、Trace、事实提取 | 模型质量、真实延迟/成本 |
| `deepseek` | `DeepSeekChatModelClient` | 真实模型闭环 | —— |

Task 031 / 2.5：领域 Agent 过去都共用 `single.yaml` 创建的同一个客户端，
各自 YAML 里的 `model_name/temperature/max_tokens/timeout` 根本不生效。现在：

- `validate_model_config(config)` 校验单个 Agent 的模型声明并返回**可审计**的扁平字典；
- `build_model_client_for_config(config, cache=...)` 按该配置构造客户端，
  参数完全相同的配置通过 `ModelClientCache` 共享实例；
- 配置非法（未知 provider、缺 `api_key_env`、参数越界）**启动期直接失败**，
  不静默回退到默认模型或别的 Agent 的客户端。

`build_model_client(provider, ...)` 保留原有语义（`cli.py` 的 Provider 级入口）：
`deepseek` 仍按 `single.yaml` 构造，`scripted` 仍需要显式脚本。
"""

from __future__ import annotations

import os
from typing import Any, Iterable, Mapping

from ..agents.base.errors import AgentConfigError

__all__ = [
    "CONFIGURABLE_PROVIDERS",
    "MODEL_PROVIDERS",
    "ModelClientCache",
    "build_model_client",
    "build_model_client_for_config",
    "describe_agent_model",
    "validate_model_config",
]

MODEL_PROVIDERS: tuple[str, ...] = ("offline", "scripted", "deepseek")

#: 可以由 YAML 直接构造客户端的 provider。
#: `scripted` 不在其中：脚本化模型必须显式提供 `scripted_calls`，
#: 让 YAML 里的一个字符串凭空变成"模型"就是把测试桩伪装成真实调用。
CONFIGURABLE_PROVIDERS: tuple[str, ...] = ("offline", "deepseek")

#: 需要 API Key 的 provider（必须显式声明 `api_key_env`，不允许静默套默认值）
_API_KEY_PROVIDERS = frozenset({"deepseek"})

#: 与 `app.config.schema.AgentConfig` 的字段边界保持一致。
#: 这里重复校验的原因：`AgentConfig.model_copy(update=...)` 会**绕过** pydantic 校验，
#: 而装配层必须在构造客户端之前把非法参数挡住。
_TEMPERATURE_MIN, _TEMPERATURE_MAX = 0.0, 2.0
_TIMEOUT_MIN, _TIMEOUT_MAX = 0.0, 600.0
_MAX_TOKENS_MIN = 1


def validate_model_config(config: Any) -> dict[str, Any]:
    """校验一个 Agent 的模型声明，返回可审计字典；非法即抛 `AgentConfigError`。

    返回键固定为：
    `provider, model_name, temperature, max_tokens, timeout_seconds, api_key_env,
    api_key_env_present`。

    `api_key_env_present` 只表示"环境变量此刻是否有值"，有值也不代表可用——
    本函数**不调用**任何模型接口。
    """

    provider = str(getattr(config, "model_provider", "") or "").strip()
    model_name = str(getattr(config, "model_name", "") or "").strip()

    if not provider:
        raise AgentConfigError("模型配置缺少 provider（model_provider）")
    if provider not in MODEL_PROVIDERS:
        raise AgentConfigError(
            f"未知模型 provider: {provider!r}（可选 {list(MODEL_PROVIDERS)}）"
        )
    if provider not in CONFIGURABLE_PROVIDERS:
        raise AgentConfigError(
            f"provider {provider!r} 不能由 YAML 配置直接构造："
            "脚本化模型必须显式注入脚本（build_model_client('scripted', scripted_calls=...)），"
            "拒绝把配置字符串静默变成模型"
        )
    if not model_name:
        raise AgentConfigError(f"provider {provider!r} 的模型配置缺少 model_name")

    temperature = _validate_optional_number(
        getattr(config, "temperature", None), name="temperature"
    )
    if temperature is not None and not (
        _TEMPERATURE_MIN <= temperature <= _TEMPERATURE_MAX
    ):
        raise AgentConfigError(
            f"temperature={temperature!r} 越界：必须在 "
            f"[{_TEMPERATURE_MIN}, {_TEMPERATURE_MAX}] 之间（或为 null 表示不下发）"
        )

    max_tokens = getattr(config, "max_tokens", None)
    if max_tokens is not None:
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
            raise AgentConfigError(f"max_tokens={max_tokens!r} 必须是整数或 null")
        if max_tokens < _MAX_TOKENS_MIN:
            raise AgentConfigError(
                f"max_tokens={max_tokens!r} 越界：必须 >= {_MAX_TOKENS_MIN}"
            )

    timeout = getattr(config, "timeout_seconds", 30.0)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise AgentConfigError(f"timeout_seconds={timeout!r} 必须是数字")
    timeout_value = float(timeout)
    if not (_TIMEOUT_MIN < timeout_value <= _TIMEOUT_MAX):
        raise AgentConfigError(
            f"timeout_seconds={timeout!r} 越界：必须在 "
            f"({_TIMEOUT_MIN}, {_TIMEOUT_MAX}] 之间"
        )

    api_key_env = getattr(config, "api_key_env", None)
    if api_key_env is not None:
        api_key_env = str(api_key_env).strip() or None
    if provider in _API_KEY_PROVIDERS and not api_key_env:
        raise AgentConfigError(
            f"provider {provider!r} 必须显式声明 api_key_env（环境变量名）；"
            "不允许回退到默认变量名，否则报告无法证明密钥来源"
        )

    return {
        "provider": provider,
        "model_name": model_name,
        "temperature": temperature,
        "max_tokens": int(max_tokens) if max_tokens is not None else None,
        "timeout_seconds": round(timeout_value, 6),
        "api_key_env": api_key_env,
        "api_key_env_present": bool(api_key_env and os.environ.get(api_key_env)),
    }


def _validate_optional_number(value: Any, *, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentConfigError(f"{name}={value!r} 必须是数字或 null")
    return float(value)


class ModelClientCache:
    """按"影响模型行为的全部参数"缓存客户端实例。

    缓存键包含 provider / model_name / temperature / max_tokens / api_key_env /
    timeout_seconds——任何一个不同都必须构造新客户端；`description` 等无语义
    字段不参与缓存键。缓存只做对象复用，不做任何模型调用。
    """

    def __init__(self) -> None:
        self._clients: dict[tuple[Any, ...], Any] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key_for(audit: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            audit.get("provider"),
            audit.get("model_name"),
            audit.get("temperature"),
            audit.get("max_tokens"),
            audit.get("api_key_env"),
            audit.get("timeout_seconds"),
        )

    def get(self, key: tuple[Any, ...]) -> Any:
        return self._clients.get(key)

    def put(self, key: tuple[Any, ...], client: Any) -> Any:
        self._clients[key] = client
        return client

    def clear(self) -> None:
        """清空缓存（供测试隔离用；不重置命中统计）。"""

        self._clients.clear()

    def snapshot(self) -> dict[str, Any]:
        return {"size": len(self._clients), "hits": self.hits, "misses": self.misses}

    def __len__(self) -> int:
        return len(self._clients)


def build_model_client_for_config(
    config: Any, *, cache: ModelClientCache | None = None
) -> Any:
    """按单个 Agent 的配置构造模型客户端。

    - `provider="offline"` → 返回 `None`（该 Agent 不使用模型）；
    - `provider="deepseek"` → 真实客户端；缺少环境变量时抛 `MissingApiKeyError`；
    - 其它情况（未知 provider / scripted / 参数越界 / 缺 `api_key_env`）→ `AgentConfigError`。

    传入 `cache` 时，参数完全相同的配置复用同一实例。
    """

    audit = validate_model_config(config)
    if audit["provider"] == "offline":
        return None

    key = ModelClientCache.key_for(audit) if cache is not None else None
    if cache is not None:
        cached = cache.get(key)  # type: ignore[arg-type]
        if cached is not None:
            cache.hits += 1
            return cached

    from .langchain_client import build_chat_client

    client = build_chat_client(config)
    if cache is not None:
        cache.misses += 1
        cache.put(key, client)  # type: ignore[arg-type]
    return client


def describe_agent_model(
    config: Any,
    *,
    client: Any = None,
    client_is_shared: bool = False,
    config_source: str = "",
) -> dict[str, Any]:
    """生成"这个 Agent 实际用什么模型"的可审计条目（形状在全项目保持一致）。

    `provider/model_name` 以**实际客户端**为准（注入脚本化客户端时会与 YAML 不同），
    其余参数来自该 Agent 的 YAML 声明。`config_source` 写 YAML 文件名，方便回溯。
    """

    audit = validate_model_config(config)
    entry: dict[str, Any] = {
        "provider": audit["provider"],
        "model_name": audit["model_name"],
        "temperature": audit["temperature"],
        "max_tokens": audit["max_tokens"],
        "timeout_seconds": audit["timeout_seconds"],
        "api_key_env": audit["api_key_env"],
        "api_key_env_present": audit["api_key_env_present"],
        "client_is_shared": bool(client_is_shared),
        "config_source": config_source,
    }
    if client is not None:
        entry["provider"] = str(getattr(client, "provider", audit["provider"]))
        entry["model_name"] = str(getattr(client, "model_name", audit["model_name"]))
    return entry


def build_model_client(
    provider: str,
    *,
    scripted_calls: Iterable[tuple[str, dict[str, Any]]] | None = None,
    summary: str | None = None,
) -> Any:
    if provider == "offline":
        return None
    if provider == "scripted":
        from .scripted import scripted_client_for_tools

        return scripted_client_for_tools(list(scripted_calls or ()), summary=summary)
    if provider == "deepseek":
        from .langchain_client import build_chat_client
        from ..config.loader import load_agent_config
        from ..paths import CONFIG_DIR

        config = load_agent_config(CONFIG_DIR / "single.yaml")
        return build_chat_client(config)
    raise ValueError(f"未知模型 provider: {provider!r}（可选 {list(MODEL_PROVIDERS)}）")

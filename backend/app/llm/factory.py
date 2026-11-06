"""模型客户端工厂（Task 018）：把 `--model-provider` 翻译成具体客户端。

三个 provider，语义必须清晰区分：

| provider | 客户端 | 能证明什么 | 不能证明什么 |
|---|---|---|---|
| `offline` | 无（`None`） | 确定性链路正确 | 与模型相关的任何结论 |
| `scripted` | `ScriptedToolModel` | 装配接好了：白名单、预算、Trace、事实提取 | 模型质量、真实延迟/成本 |
| `deepseek` | `DeepSeekChatModelClient` | 真实模型闭环 | —— |

`deepseek` 缺少 `DEEPSEEK_API_KEY` 时**直接失败**（`MissingApiKeyError`），
不会静默降级成 offline——否则报告会把离线结果当成真实调用。
"""

from __future__ import annotations

from typing import Any, Iterable

__all__ = ["MODEL_PROVIDERS", "build_model_client"]

MODEL_PROVIDERS: tuple[str, ...] = ("offline", "scripted", "deepseek")


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

        return scripted_client_for_tools(
            list(scripted_calls or ()), summary=summary
        )
    if provider == "deepseek":
        from .langchain_client import build_chat_client
        from ..config.loader import load_agent_config
        from ..paths import CONFIG_DIR

        config = load_agent_config(CONFIG_DIR / "single.yaml")
        return build_chat_client(config)
    raise ValueError(f"未知模型 provider: {provider!r}（可选 {list(MODEL_PROVIDERS)}）")

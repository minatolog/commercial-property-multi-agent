"""Agent 配置 Schema。

设计要点：
1. `extra="forbid"` —— 任何人想把 `api_key: sk-xxx` 写进 YAML 都会被直接拒绝，
   从结构上杜绝密钥入库。
2. 每个 Agent 一个 YAML 文件，字段互相独立，改 lease 不会影响 billing。
3. 模型参数只做"声明"，真正的参数裁剪交给 `app.llm.adapter`。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..agents.base.contracts import CAPABILITY_PATTERN

_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

# 这些字段名一旦出现在 YAML 里，说明有人把密钥写进了配置文件
_FORBIDDEN_SECRET_KEYS = frozenset(
    {"api_key", "apikey", "password", "passwd", "token", "secret", "access_key", "secret_key"}
)


class RetrievalSettings(BaseModel):
    """检索配置：**只声明当前真实实现的能力**（Task 031 / 2.6）。

    实际实现只有 BM25（`app/rag/bm25.py` + `app/rag/service.py`）：确定性、零外部服务。
    向量库（chroma）、嵌入模型（bge）、重排（rerank）、混合权重等**尚未实现**，
    因此不再出现在 Schema 里——写了会因 `extra="forbid"` 在加载期直接失败，
    而不是留下一份"看起来支持、实际被忽略"的运行配置。未来计划写进文档，不写进配置。

    保留字段的取舍：
    - `enabled`：该 Agent 是否启用文档检索（装配层据此决定是否挂检索工具）。
    - `top_k`：检索返回条数的声明值；当前检索工具由调用方 payload 指定 `top_k`，
      因此该字段是**声明**而非强约束，保留它是为了记录 Agent 的意图上限。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    top_k: int = Field(default=5, ge=1, le=50)


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=32)
    version: str = Field(min_length=1, max_length=32)
    enabled: bool = True
    description: str = ""
    capabilities: tuple[str, ...] = Field(min_length=1)

    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    api_key_env: str | None = None

    timeout_seconds: float = Field(default=30.0, gt=0.0, le=600.0)
    max_retries: int = Field(default=1, ge=0, le=5)
    max_tool_rounds: int = Field(default=3, ge=1, le=8)
    prompt_path: str = Field(min_length=1)
    allowed_tools: tuple[str, ...] = ()
    retrieval_settings: RetrievalSettings | None = None
    log_level: str = "INFO"

    @field_validator("capabilities")
    @classmethod
    def _validate_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        invalid = [c for c in value if not CAPABILITY_PATTERN.match(c)]
        if invalid:
            raise ValueError(f"capability 必须形如 '<domain>.<action>'，非法值: {invalid}")
        if len(set(value)) != len(value):
            raise ValueError("capabilities 存在重复项")
        return value

    @field_validator("api_key_env")
    @classmethod
    def _validate_env_name(cls, value: str | None) -> str | None:
        if value is not None and not _ENV_NAME.match(value):
            raise ValueError(f"api_key_env 必须是环境变量名（大写下划线），收到: {value!r}")
        return value

    @field_validator("prompt_path")
    @classmethod
    def _validate_prompt_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute():
            raise ValueError("prompt_path 必须是相对 backend/ 的路径")
        if ".." in path.parts:
            raise ValueError("prompt_path 不允许包含 '..'")
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in LOG_LEVELS:
            raise ValueError(f"log_level 必须是 {sorted(LOG_LEVELS)} 之一")
        return normalized

    @model_validator(mode="before")
    @classmethod
    def _reject_secret_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            hits = sorted(k for k in data if str(k).lower() in _FORBIDDEN_SECRET_KEYS)
            if hits:
                raise ValueError(
                    f"配置中不允许出现敏感字段 {hits}；请使用环境变量并通过 api_key_env 声明变量名"
                )
        return data


class PlannerConfig(BaseModel):
    """规划器配置（Task 034，`app/config/planner.yaml`）。

    模型参数字段与 `AgentConfig` **同名**（`model_provider` / `model_name` / `temperature` /
    `max_tokens` / `timeout_seconds` / `api_key_env`），因此直接复用
    `validate_model_config` 与 `build_model_client_for_config`，不另造一套校验。

    `mode` 默认 `rule`：不加参数时 CLI / API / 评测的行为与 Task 034 之前完全一致。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["rule", "llm", "hybrid"] = "rule"
    #: hybrid 下规则命中**多个**领域且无歧义信号时：`llm`=交给模型复核，`rule`=直接用规则
    hybrid_multi_domain: Literal["rule", "llm"] = "llm"
    #: 模型一次最多选几个领域（领域只有 3 个，超过即视为非法输出）
    max_domains: int = Field(default=3, ge=1, le=3)

    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    api_key_env: str | None = None
    timeout_seconds: float = Field(default=20.0, gt=0.0, le=600.0)
    prompt_path: str = Field(min_length=1)
    #: 回问文本的最大长度（模型给出的回问超过即改用默认回问并记录告警）
    max_clarification_chars: int = Field(default=120, ge=10, le=500)

    @field_validator("api_key_env")
    @classmethod
    def _validate_api_key_env(cls, value: str | None) -> str | None:
        if value is not None and not _ENV_NAME.match(value):
            raise ValueError(f"api_key_env 必须是环境变量名（大写下划线），收到: {value!r}")
        return value

    @field_validator("prompt_path")
    @classmethod
    def _validate_prompt_path(cls, value: str) -> str:
        if Path(value).is_absolute():
            raise ValueError("prompt_path 必须是相对 backend/ 的路径")
        if ".." in Path(value).parts:
            raise ValueError("prompt_path 不允许包含 '..'")
        return value

    @model_validator(mode="before")
    @classmethod
    def _reject_secret_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            hits = sorted(k for k in data if str(k).lower() in _FORBIDDEN_SECRET_KEYS)
            if hits:
                raise ValueError(
                    f"配置中不允许出现敏感字段 {hits}；请使用环境变量并通过 api_key_env 声明变量名"
                )
        return data

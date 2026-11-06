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
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..agents.base.contracts import CAPABILITY_PATTERN

_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

# 这些字段名一旦出现在 YAML 里，说明有人把密钥写进了配置文件
_FORBIDDEN_SECRET_KEYS = frozenset(
    {"api_key", "apikey", "password", "passwd", "token", "secret", "access_key", "secret_key"}
)


class RetrievalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    top_k: int = Field(default=5, ge=1, le=50)
    rerank_top_n: int = Field(default=3, ge=1, le=50)
    vector_store: str = "chroma"
    embedding_model: str = "BAAI/bge-base-zh-v1.5"
    bm25_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_weights(self) -> "RetrievalSettings":
        if self.rerank_top_n > self.top_k:
            raise ValueError("rerank_top_n 不能大于 top_k")
        if self.bm25_weight + self.vector_weight <= 0:
            raise ValueError("bm25_weight 与 vector_weight 不能同时为 0")
        return self


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

"""Agent 配置加载器。

只负责"读文件 → 校验 → 返回强类型对象"。不做任何 Agent 实例化，
避免配置层与实现层耦合。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from ..agents.base.errors import AgentConfigError
from .schema import AgentConfig, PlannerConfig


def load_agent_config(path: str | Path) -> AgentConfig:
    file_path = Path(path)
    if not file_path.is_file():
        raise AgentConfigError(f"配置文件不存在: {file_path}")

    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AgentConfigError(f"YAML 解析失败: {file_path}: {exc}") from exc

    if raw is None:
        raise AgentConfigError(f"配置文件为空: {file_path}")
    if not isinstance(raw, dict):
        raise AgentConfigError(f"配置文件顶层必须是 mapping: {file_path}")

    try:
        return AgentConfig.model_validate(raw)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        )
        raise AgentConfigError(f"配置校验失败: {file_path}: {details}") from exc


def load_all_agent_configs(directory: str | Path) -> dict[str, AgentConfig]:
    """加载目录下全部 `<name>.yaml`，并以文件名作为键做一致性校验。"""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise AgentConfigError(f"配置目录不存在: {dir_path}")

    configs: dict[str, AgentConfig] = {}
    for file_path in sorted(dir_path.glob("*.yaml")):
        config = load_agent_config(file_path)
        if config.name != file_path.stem:
            raise AgentConfigError(
                f"配置文件名与 name 不一致: {file_path.name} 的 name 为 {config.name!r}"
            )
        if config.name in configs:
            raise AgentConfigError(f"Agent 配置重名: {config.name}")
        configs[config.name] = config

    if not configs:
        raise AgentConfigError(f"配置目录中没有找到任何 *.yaml: {dir_path}")
    return configs


def load_planner_config(path: str | Path | None = None) -> PlannerConfig:
    """加载并校验规划器配置（Task 034）。

    结构校验之外，模型参数再经 `validate_model_config` 校验（与 Agent 同一实现），
    非法配置在启动期 / `check` 时失败，不会等到运行时才静默回退。
    """

    from ..llm.factory import validate_model_config
    from ..paths import BACKEND_ROOT, PLANNER_CONFIG_PATH

    file_path = Path(path) if path is not None else PLANNER_CONFIG_PATH
    if not file_path.is_file():
        raise AgentConfigError(f"规划器配置文件不存在: {file_path}")
    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AgentConfigError(f"YAML 解析失败: {file_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise AgentConfigError(f"规划器配置顶层必须是 mapping: {file_path}")
    try:
        config = PlannerConfig.model_validate(raw)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        )
        raise AgentConfigError(f"规划器配置校验失败: {file_path}: {details}") from exc
    validate_model_config(config)
    prompt = BACKEND_ROOT / config.prompt_path
    if not prompt.is_file():
        raise AgentConfigError(f"规划器 prompt_path 指向的文件不存在: {config.prompt_path}")
    return config

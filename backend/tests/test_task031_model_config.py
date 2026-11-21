"""Task 031 工作项 2.5（每 Agent 模型配置真正生效）+ 2.6（配置不声明未实现能力）。

验证边界：

- **不联网、不调用任何模型**：deepseek 客户端只在设置占位环境变量后**构造**
  （`ChatOpenAI` 构造不发请求），真正的模型调用全部用脚本化客户端或 `client_factory` 替身；
- 用临时配置目录证明"改某个领域 YAML 的 `model_name` 只影响该 Agent"；
- 缓存键包含全部影响模型行为的参数；改任一参数必须得到新实例；
- 未知 provider / 缺 `api_key_env` / 参数越界在**构造期**失败，不静默回退；
- 声明未实现的检索能力（vector_store / embedding_model / rerank 等）在**加载期**失败。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
import unittest
from pathlib import Path

from app.agents.base.errors import AgentConfigError, MissingApiKeyError
from app.agents.factory import build_registry
from app.config.loader import load_agent_config, load_all_agent_configs
from app.config.schema import AgentConfig, RetrievalSettings
from app.evaluation.baselines import build_baseline
from app.evaluation.cases import load_cases
from app.evaluation.runner import evaluate, render_markdown
from app.investigation_demo import build_investigation_bundle
from app.llm.factory import (
    MODEL_PROVIDERS,
    ModelClientCache,
    build_model_client_for_config,
    validate_model_config,
)
from app.llm.model_client import FakeChatModelClient
from app.llm.scripted import ScriptedToolModel, scripted_client_for_tools
from app.paths import CONFIG_DIR

LEASE = "lease_xh_a301_2025"

#: `build_investigation_bundle.agent_models` 条目的固定形状（Task 031 / 2.5）
#: R2：评测 `models_by_agent` 额外记录的实际应答模型字段
SERVED_MODEL_KEYS = {"served_models", "served_model_mismatch"}

AGENT_MODEL_KEYS = {
    "provider",
    "model_name",
    "temperature",
    "max_tokens",
    "timeout_seconds",
    "api_key_env",
    "api_key_env_present",
    "client_is_shared",
    "config_source",
}

#: `validate_model_config` 返回的固定键（对外审计契约）
AUDIT_KEYS = {
    "provider",
    "model_name",
    "temperature",
    "max_tokens",
    "timeout_seconds",
    "api_key_env",
    "api_key_env_present",
}


@contextlib.contextmanager
def _env(**values: str | None):
    saved: dict[str, str | None] = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _copy_configs(tmp: str, *, replacements: dict[str, list[tuple[str, str]]] | None = None) -> Path:
    """把真实 agents 配置复制到临时目录，并按需替换文本（保持 UTF-8）。"""

    directory = Path(tmp)
    for source in sorted(CONFIG_DIR.glob("*.yaml")):
        text = source.read_text(encoding="utf-8")
        for old, new in (replacements or {}).get(source.stem, []):
            if old not in text:
                raise AssertionError(f"临时配置替换失败：{source.name} 中找不到 {old!r}")
            text = text.replace(old, new)
        (directory / source.name).write_text(text, encoding="utf-8")
    return directory


class _RecordingFactory:
    """`client_factory` 替身：按每个 Agent 自己的 YAML 构造脚本化客户端并记录。"""

    def __init__(self, *, model_name_from_config: bool = True) -> None:
        self.configs: dict[str, AgentConfig] = {}
        self.calls: list[str] = []
        self._model_name_from_config = model_name_from_config

    def __call__(self, config: AgentConfig) -> ScriptedToolModel:
        self.calls.append(config.name)
        self.configs[config.name] = config
        client = scripted_client_for_tools([], summary="factory-stub")
        if self._model_name_from_config:
            client.model_name = config.model_name
        return client


def _h01_case():
    cases = load_cases(split="heldout")
    return next(case for case in cases if case.case_id == "H01")


class TestPerAgentModelConfig(unittest.TestCase):
    """2.5：模型客户端按各 Agent 自己的 YAML 创建。"""

    def test_changing_one_yaml_only_affects_that_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            probe_name = "billing-probe-model-X"
            directory = _copy_configs(
                tmp, replacements={"billing": [("model_name: deepseek-flash", f"model_name: {probe_name}")]}
            )
            factory = _RecordingFactory()
            bundle = build_investigation_bundle(
                model_provider="deepseek",
                client_factory=factory,
                config_dir=directory,
            )

            self.assertEqual(bundle.engine, "llm")
            self.assertEqual(bundle.model_provider, "deepseek")
            self.assertEqual(
                set(bundle.agent_models), {"billing", "lease", "property", "single"}
            )
            # 只有 billing 拿到探针模型名，其余保持各自 YAML 声明的值
            self.assertEqual(bundle.agent_models["billing"]["model_name"], probe_name)
            for name, expected in (
                ("lease", "deepseek-flash"),
                ("property", "deepseek-flash"),
                ("single", "deepseek-flash"),
            ):
                self.assertEqual(bundle.agent_models[name]["model_name"], expected)
            # client_factory 真实地按每个 YAML 各调用一次
            self.assertEqual(factory.calls.count("billing"), 1)
            self.assertEqual(set(factory.calls), set(bundle.agent_models))
            self.assertEqual(factory.configs["billing"].model_name, probe_name)
            self.assertEqual(factory.configs["lease"].model_name, "deepseek-flash")
            # 每个条目形状固定、config_source 指向自己的 YAML
            for name, entry in bundle.agent_models.items():
                self.assertEqual(set(entry), AGENT_MODEL_KEYS)
                self.assertEqual(entry["config_source"], f"{name}.yaml")

    def test_factory_receives_each_agents_own_parameters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = _copy_configs(tmp)
            factory = _RecordingFactory()
            build_investigation_bundle(
                model_provider="deepseek", client_factory=factory, config_dir=directory
            )
            # 参数必须来自各自的 YAML，而不是某个全局配置
            self.assertEqual(factory.configs["lease"].temperature, 0.1)
            self.assertEqual(factory.configs["lease"].max_tokens, 2048)
            self.assertEqual(factory.configs["lease"].timeout_seconds, 30)
            self.assertIsNone(factory.configs["billing"].temperature)
            self.assertEqual(factory.configs["billing"].max_tokens, 1024)
            self.assertEqual(factory.configs["billing"].timeout_seconds, 20)
            self.assertEqual(factory.configs["single"].temperature, 0.0)
            self.assertEqual(factory.configs["single"].timeout_seconds, 60)

    def test_real_configs_give_per_agent_model_parameters(self) -> None:
        bundle = build_investigation_bundle(
            model_provider="deepseek", client_factory=_RecordingFactory()
        )
        self.assertEqual(bundle.agent_models["lease"]["temperature"], 0.1)
        self.assertEqual(bundle.agent_models["lease"]["max_tokens"], 2048)
        self.assertEqual(bundle.agent_models["billing"]["max_tokens"], 1024)
        self.assertEqual(bundle.agent_models["single"]["timeout_seconds"], 60.0)
        self.assertEqual(bundle.agent_models["billing"]["config_source"], "billing.yaml")

    def test_deepseek_branch_shares_cache_for_identical_params(self) -> None:
        """billing 与 property 参数完全相同 → 复用同一客户端；lease/single 不复用。"""

        with _env(DEEPSEEK_API_KEY="task031-placeholder-not-used"):
            bundle = build_investigation_bundle(model_provider="deepseek")
            clients = {
                name: bundle.registry.get(name)._model_client
                for name in bundle.agent_models
            }
        self.assertIs(clients["billing"], clients["property"])
        self.assertIsNot(clients["lease"], clients["billing"])
        self.assertIsNot(clients["single"], clients["lease"])
        self.assertTrue(bundle.agent_models["billing"]["client_is_shared"])
        self.assertTrue(bundle.agent_models["property"]["client_is_shared"])
        self.assertFalse(bundle.agent_models["lease"]["client_is_shared"])
        self.assertFalse(bundle.agent_models["single"]["client_is_shared"])
        self.assertEqual(
            {entry["model_name"] for entry in bundle.agent_models.values()},
            {"deepseek-flash"},
        )

    def test_deepseek_branch_without_key_fails_at_construction(self) -> None:
        with _env(DEEPSEEK_API_KEY=None):
            with self.assertRaises(MissingApiKeyError):
                build_investigation_bundle(model_provider="deepseek")

    def test_offline_bundle_has_no_agent_models(self) -> None:
        bundle = build_investigation_bundle()
        self.assertEqual(bundle.engine, "deterministic")
        self.assertEqual(bundle.agent_models, {})

    def test_scripted_bundle_injects_one_client_into_all_llm_agents(self) -> None:
        bundle = build_investigation_bundle(
            model_provider="scripted",
            scripted_calls=[("billing.statement.read", {"lease_id": LEASE})],
        )
        self.assertEqual(bundle.engine, "llm")
        self.assertEqual(bundle.model_provider, "scripted")
        self.assertEqual(
            set(bundle.agent_models), {"lease", "billing", "property", "single"}
        )
        for entry in bundle.agent_models.values():
            self.assertEqual(entry["provider"], "scripted")
            self.assertEqual(entry["model_name"], "scripted-tool-model")
            self.assertTrue(entry["client_is_shared"])

    def test_legacy_engine_and_model_client_still_work(self) -> None:
        client = scripted_client_for_tools([], summary="legacy")
        bundle = build_investigation_bundle(engine="llm", model_client=client)
        self.assertEqual(bundle.engine, "llm")
        self.assertEqual(bundle.model_provider, "scripted")
        self.assertTrue(bundle.agent_models)
        for name in bundle.agent_models:
            self.assertIs(bundle.registry.get(name)._model_client, client)

    def test_conflicting_combinations_raise(self) -> None:
        with self.assertRaises(ValueError):
            build_investigation_bundle(engine="deterministic", model_provider="deepseek")
        with self.assertRaises(ValueError):
            build_investigation_bundle(
                engine="llm", model_provider="deepseek", model_client=object()
            )
        with self.assertRaises(ValueError):
            build_investigation_bundle(engine="llm")
        with self.assertRaises(ValueError):
            build_investigation_bundle(engine="magic")
        with self.assertRaises(ValueError):
            build_investigation_bundle(model_provider="openai")


class TestValidateModelConfig(unittest.TestCase):
    """2.5：模型配置校验 + 非法配置构造期失败。"""

    def test_audit_shape_and_values(self) -> None:
        config = load_agent_config(CONFIG_DIR / "lease.yaml")
        audit = validate_model_config(config)
        self.assertEqual(set(audit), AUDIT_KEYS)
        self.assertEqual(audit["provider"], "deepseek")
        self.assertEqual(audit["model_name"], "deepseek-flash")
        self.assertEqual(audit["temperature"], 0.1)
        self.assertEqual(audit["max_tokens"], 2048)
        self.assertEqual(audit["timeout_seconds"], 30.0)
        self.assertEqual(audit["api_key_env"], "DEEPSEEK_API_KEY")

    def test_api_key_env_present_flag_reflects_environment(self) -> None:
        config = load_agent_config(CONFIG_DIR / "lease.yaml")
        with _env(DEEPSEEK_API_KEY=None):
            self.assertFalse(validate_model_config(config)["api_key_env_present"])
        with _env(DEEPSEEK_API_KEY="placeholder"):
            self.assertTrue(validate_model_config(config)["api_key_env_present"])

    def test_all_real_configs_validate(self) -> None:
        configs = load_all_agent_configs(CONFIG_DIR)
        self.assertEqual(len(configs), 5)
        for name, config in configs.items():
            audit = validate_model_config(config)
            self.assertEqual(audit["model_name"], "deepseek-flash", name)

    def test_unknown_provider_is_rejected(self) -> None:
        config = load_agent_config(CONFIG_DIR / "lease.yaml")
        broken = config.model_copy(update={"model_provider": "openai"})
        with self.assertRaises(AgentConfigError):
            validate_model_config(broken)
        with self.assertRaises(AgentConfigError):
            build_model_client_for_config(broken)

    def test_scripted_provider_cannot_come_from_yaml(self) -> None:
        config = load_agent_config(CONFIG_DIR / "lease.yaml")
        broken = config.model_copy(update={"model_provider": "scripted"})
        with self.assertRaises(AgentConfigError):
            build_model_client_for_config(broken)

    def test_missing_api_key_env_is_rejected(self) -> None:
        config = load_agent_config(CONFIG_DIR / "lease.yaml")
        broken = config.model_copy(update={"api_key_env": None})
        with self.assertRaises(AgentConfigError):
            build_model_client_for_config(broken)

    def test_out_of_range_parameters_are_rejected(self) -> None:
        config = load_agent_config(CONFIG_DIR / "lease.yaml")
        for update in (
            {"temperature": 9.9},
            {"temperature": -0.1},
            {"max_tokens": 0},
            {"timeout_seconds": 0},
            {"timeout_seconds": 9999},
            {"model_name": ""},
        ):
            with self.subTest(update=update):
                with self.assertRaises(AgentConfigError):
                    build_model_client_for_config(config.model_copy(update=update))

    def test_missing_environment_variable_raises_missing_api_key(self) -> None:
        config = load_agent_config(CONFIG_DIR / "lease.yaml").model_copy(
            update={"api_key_env": "TASK031_TEST_KEY_NOT_SET"}
        )
        with _env(TASK031_TEST_KEY_NOT_SET=None):
            with self.assertRaises(MissingApiKeyError):
                build_model_client_for_config(config)

    def test_offline_provider_returns_no_client(self) -> None:
        config = AgentConfig.model_validate(
            {
                "name": "offline_probe",
                "version": "1.0.0",
                "capabilities": ["offline.probe"],
                "model_provider": "offline",
                "model_name": "none",
                "prompt_path": "app/agents/lease/prompts/system.md",
            }
        )
        audit = validate_model_config(config)
        self.assertEqual(audit["provider"], "offline")
        self.assertIsNone(build_model_client_for_config(config))


class TestModelClientCache(unittest.TestCase):
    """2.5：缓存键必须包含全部影响行为的参数。"""

    def test_identical_parameters_share_one_client(self) -> None:
        base = load_agent_config(CONFIG_DIR / "lease.yaml")
        # description 是无语义字段，不参与缓存键
        same = base.model_copy(update={"description": "另一个描述"})
        cache = ModelClientCache()
        with _env(DEEPSEEK_API_KEY="placeholder-a"):
            first = build_model_client_for_config(base, cache=cache)
            second = build_model_client_for_config(same, cache=cache)
        self.assertIs(first, second)
        self.assertEqual(len(cache), 1)
        self.assertEqual((cache.hits, cache.misses), (1, 1))

    def test_each_behavior_parameter_change_misses_cache(self) -> None:
        base = load_agent_config(CONFIG_DIR / "lease.yaml")
        cache = ModelClientCache()
        with _env(
            DEEPSEEK_API_KEY="placeholder-a",
            TASK031_ALT_KEY="placeholder-b",
        ):
            original = build_model_client_for_config(base, cache=cache)
            for update in (
                {"temperature": 0.2},
                {"max_tokens": 512},
                {"timeout_seconds": 31},
                {"api_key_env": "TASK031_ALT_KEY"},
            ):
                with self.subTest(update=update):
                    changed = build_model_client_for_config(
                        base.model_copy(update=update), cache=cache
                    )
                    self.assertIsNot(changed, original)
            # 再取一次原配置必须仍复用原实例
            self.assertIs(
                build_model_client_for_config(base, cache=cache), original
            )
        self.assertEqual(len(cache), 5)
        self.assertEqual(cache.misses, 5)

    def test_cache_clear_is_available_for_tests(self) -> None:
        base = load_agent_config(CONFIG_DIR / "lease.yaml")
        cache = ModelClientCache()
        with _env(DEEPSEEK_API_KEY="placeholder-a"):
            build_model_client_for_config(base, cache=cache)
            self.assertEqual(len(cache), 1)
            cache.clear()
            self.assertEqual(len(cache), 0)
            rebuilt = build_model_client_for_config(base, cache=cache)
            self.assertIsNotNone(rebuilt)

    def test_without_cache_clients_are_not_shared(self) -> None:
        base = load_agent_config(CONFIG_DIR / "lease.yaml")
        with _env(DEEPSEEK_API_KEY="placeholder-a"):
            first = build_model_client_for_config(base)
            second = build_model_client_for_config(base)
        self.assertIsNot(first, second)


class TestRegistryModelClientInjection(unittest.TestCase):
    """2.5：build_registry 按 Agent 名注入客户端，缺失时显式失败。"""

    def _clients(self) -> dict[str, FakeChatModelClient]:
        return {
            name: FakeChatModelClient([], provider="fake", model_name=f"probe-{name}")
            for name in ("billing", "lease", "property", "single")
        }

    def test_model_clients_mapping_is_used_per_name(self) -> None:
        clients = self._clients()
        report = build_registry(engine="llm", model_clients=clients)
        for name, client in clients.items():
            self.assertIs(report.registry.get(name)._model_client, client)

    def test_missing_client_for_one_agent_fails(self) -> None:
        clients = self._clients()
        clients.pop("billing")
        with self.assertRaises(AgentConfigError) as ctx:
            build_registry(engine="llm", model_clients=clients)
        self.assertIn("billing", str(ctx.exception))

    def test_no_client_at_all_fails_instead_of_falling_back(self) -> None:
        with self.assertRaises(AgentConfigError):
            build_registry(engine="llm")

    def test_explicit_single_client_still_supported(self) -> None:
        client = FakeChatModelClient([], provider="fake", model_name="single-inject")
        report = build_registry(engine="llm", model_client=client)
        for name in ("billing", "lease", "property", "single"):
            self.assertIs(report.registry.get(name)._model_client, client)

    def test_deterministic_registry_path_unchanged(self) -> None:
        report = build_registry()
        self.assertEqual(
            set(report.registered),
            {"lease", "billing", "compliance", "property", "single"},
        )
        # 确定性引擎不依赖任何模型客户端
        report_llm_names = build_registry(engine="llm", model_clients=self._clients())
        self.assertEqual(
            set(report_llm_names.registered), {"lease", "billing", "property", "single"}
        )


class TestRetrievalConfigTruthfulness(unittest.TestCase):
    """2.6：检索配置只能声明真实实现的能力（BM25）。"""

    def test_schema_only_keeps_implemented_fields(self) -> None:
        self.assertEqual(set(RetrievalSettings.model_fields), {"enabled", "top_k"})

    def test_real_configs_only_use_implemented_fields(self) -> None:
        configs = load_all_agent_configs(CONFIG_DIR)
        self.assertEqual(
            set(configs),
            {"lease", "billing", "compliance", "property", "single"},
        )
        self.assertEqual(configs["lease"].retrieval_settings.top_k, 6)
        self.assertTrue(configs["lease"].retrieval_settings.enabled)
        self.assertFalse(configs["compliance"].enabled)
        for name, config in configs.items():
            if config.retrieval_settings is not None:
                self.assertLessEqual(
                    set(config.retrieval_settings.model_fields_set),
                    {"enabled", "top_k"},
                    name,
                )
        # 修正后的真实配置必须能装配（check 命令走同一条加载路径）
        build_registry()
        build_registry(engine="llm", model_clients={"billing": object(), "lease": object(), "property": object(), "single": object()})

    def test_unimplemented_retrieval_fields_are_rejected_at_load(self) -> None:
        body = (
            "name: lease\nversion: 1.0.0\ncapabilities: [lease.query]\n"
            "model_provider: deepseek\nmodel_name: deepseek-flash\n"
            "api_key_env: DEEPSEEK_API_KEY\n"
            "prompt_path: app/agents/lease/prompts/system.md\n"
        )
        for snippet, field in (
            ("  vector_store: chroma\n", "vector_store"),
            ("  embedding_model: BAAI/bge-base-zh-v1.5\n", "embedding_model"),
            ("  rerank_top_n: 3\n", "rerank_top_n"),
            ("  bm25_weight: 0.4\n", "bm25_weight"),
            ("  vector_weight: 0.6\n", "vector_weight"),
            ("  min_score: 0.2\n", "min_score"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "lease.yaml"
                path.write_text(
                    body + "retrieval_settings:\n  enabled: true\n  top_k: 5\n" + snippet,
                    encoding="utf-8",
                )
                with self.assertRaises(AgentConfigError) as ctx:
                    load_all_agent_configs(tmp)
                self.assertIn(field, str(ctx.exception))

    def test_cli_check_loads_corrected_configs(self) -> None:
        """`app.cli check` 依赖 `load_all_agent_configs`：修正后的配置必须全部通过。"""

        configs = load_all_agent_configs(CONFIG_DIR)
        self.assertEqual(len(configs), 5)
        self.assertFalse(configs["compliance"].enabled)


class TestEvaluationModelsByAgent(unittest.TestCase):
    """2.5：评测/报告按 Agent 输出实际模型。"""

    @staticmethod
    def _factory(config: AgentConfig) -> ScriptedToolModel:
        return scripted_client_for_tools(
            [
                ("lease.lookup", {"lease_id": LEASE}),
                ("billing.statement.read", {"lease_id": LEASE}),
                ("property.work_orders.read", {"lease_id": LEASE}),
            ],
            summary="已按工具结果核对。",
            model_name=config.model_name,
        )

    def test_offline_report_has_empty_models_by_agent(self) -> None:
        case = _h01_case()
        report = asyncio.run(
            evaluate(baseline="A_deterministic", cases=[case], split="heldout")
        )
        self.assertEqual(report.summary["models_by_agent"], {})
        self.assertEqual(report.as_dict()["bindings"]["models_by_agent"], {})
        markdown = render_markdown([report])
        self.assertIn("## 各 Agent 实际模型", markdown)
        self.assertIn("离线 = 确定性引擎，无模型参与", markdown)

    def test_c_baseline_records_per_agent_models_from_bundle(self) -> None:
        case = _h01_case()
        report = asyncio.run(
            evaluate(
                baseline="C_multi_agent",
                cases=[case],
                split="heldout",
                model_provider="deepseek",
                client_factory=self._factory,
            )
        )
        models = report.summary["models_by_agent"]
        self.assertEqual(
            set(models), {"lease", "billing", "property", "single"}
        )
        for name, entry in models.items():
            # R2：评测汇总在配置条目之外，增加"服务端实际应答模型"两个字段
            self.assertEqual(set(entry), AGENT_MODEL_KEYS | SERVED_MODEL_KEYS)
            self.assertEqual(entry["model_name"], "deepseek-flash", name)
            # 替身客户端不返回响应元数据：未记录 ≠ 一致
            self.assertEqual(entry["served_models"], [], name)
            self.assertIsNone(entry["served_model_mismatch"], name)
            self.assertEqual(entry["config_source"], f"{name}.yaml")
        payload = report.as_dict()
        self.assertEqual(payload["bindings"]["models_by_agent"], models)
        self.assertIn("按各 Agent 自己的 YAML", report.model["note"])
        markdown = render_markdown([report])
        self.assertIn("## 各 Agent 实际模型", markdown)
        self.assertIn("billing.yaml", markdown)

    def test_b_baseline_records_single_agent_model(self) -> None:
        case = _h01_case()
        report = asyncio.run(
            evaluate(
                baseline="B_single_agent",
                cases=[case],
                split="heldout",
                model_provider="deepseek",
                client_factory=self._factory,
            )
        )
        models = report.summary["models_by_agent"]
        self.assertEqual(set(models), {"single"})
        self.assertEqual(models["single"]["model_name"], "deepseek-flash")
        self.assertEqual(models["single"]["config_source"], "single.yaml")
        self.assertEqual(models["single"]["served_models"], [])
        self.assertIsNone(models["single"]["served_model_mismatch"])
        # 行级 JSON 里也要有逐 Agent 模型
        self.assertEqual(report.rows[0]["result"]["models_by_agent"], models)

    def test_a_baseline_rejects_model_provider(self) -> None:
        with self.assertRaises(ValueError):
            build_baseline("A_deterministic", model_provider="deepseek")


class TestModelNameNotRetired(unittest.TestCase):
    """2.5：模型名核对结果落进 YAML（deepseek-chat 已于 2026-07-24 下线）。"""

    def test_configured_model_name_is_current_official_name(self) -> None:
        configs = load_all_agent_configs(CONFIG_DIR)
        self.assertEqual(
            {config.model_name for config in configs.values()}, {"deepseek-flash"}
        )

    def test_provider_choices_are_documented(self) -> None:
        self.assertEqual(list(MODEL_PROVIDERS), ["offline", "scripted", "deepseek"])


if __name__ == "__main__":
    unittest.main()

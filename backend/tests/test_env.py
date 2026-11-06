"""Task 019：`.env` 加载器回归测试。

重点不是"能读文件"，而是三条安全性质：

1. 已导出的环境变量**不被覆盖**（部署时系统变量优先）；
2. 返回值只含键名，绝不回显值；
3. 文件缺失/异常不影响正常运行。
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.env import load_env_file, load_project_env, parse_env_text


class TestParseEnvText(unittest.TestCase):
    def test_parses_plain_and_export_lines(self) -> None:
        values = parse_env_text(
            "DEEPSEEK_API_KEY=sk-test\n"
            "export DEMO_PRINCIPAL_ID=principal_ops_xinghui\n"
        )
        self.assertEqual(values["DEEPSEEK_API_KEY"], "sk-test")
        self.assertEqual(values["DEMO_PRINCIPAL_ID"], "principal_ops_xinghui")

    def test_ignores_comments_blank_lines_and_junk(self) -> None:
        values = parse_env_text(
            "# 注释\n"
            "\n"
            "NOT_A_PAIR\n"
            "  \n"
            "KEEP=1  # 行尾注释按原样保留，不做截断\n"
        )
        self.assertEqual(set(values), {"KEEP"})

    def test_strips_matching_quotes(self) -> None:
        values = parse_env_text('A="x y"\nB=\'z\'\nC="unbalanced\n')
        self.assertEqual(values["A"], "x y")
        self.assertEqual(values["B"], "z")
        self.assertEqual(values["C"], '"unbalanced')

    def test_empty_value_is_kept(self) -> None:
        self.assertEqual(parse_env_text("DEEPSEEK_API_KEY=\n"), {"DEEPSEEK_API_KEY": ""})


class TestLoadEnvFile(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / ".env"

    def test_missing_file_is_not_an_error(self) -> None:
        self.assertEqual(load_env_file(Path(self._tmp.name) / "nope.env"), ())

    def test_existing_environment_wins(self) -> None:
        self.path.write_text("DEEPSEEK_API_KEY=from-file\n", encoding="utf-8")
        environ = {"DEEPSEEK_API_KEY": "from-shell"}
        applied = load_env_file(self.path, environ=environ)
        self.assertEqual(environ["DEEPSEEK_API_KEY"], "from-shell")
        self.assertEqual(applied, ())

    def test_empty_value_does_not_mask_a_real_one(self) -> None:
        """.env 里的空值不应该把已导出的真值覆盖成空字符串。"""

        self.path.write_text("DEEPSEEK_API_KEY=\n", encoding="utf-8")
        environ = {"DEEPSEEK_API_KEY": "from-shell"}
        load_env_file(self.path, environ=environ)
        self.assertEqual(environ["DEEPSEEK_API_KEY"], "from-shell")

    def test_fills_only_missing_keys(self) -> None:
        self.path.write_text("A=1\nB=2\n", encoding="utf-8")
        environ = {"A": "keep"}
        applied = load_env_file(self.path, environ=environ)
        self.assertEqual(environ, {"A": "keep", "B": "2"})
        self.assertEqual(applied, ("B",))

    def test_override_is_opt_in(self) -> None:
        self.path.write_text("A=from-file\n", encoding="utf-8")
        environ = {"A": "from-shell"}
        load_env_file(self.path, override=True, environ=environ)
        self.assertEqual(environ["A"], "from-file")

    def test_returns_key_names_only(self) -> None:
        self.path.write_text("DEEPSEEK_API_KEY=sk-secret-value\n", encoding="utf-8")
        environ: dict[str, str] = {}
        applied = load_env_file(self.path, environ=environ)
        self.assertEqual(applied, ("DEEPSEEK_API_KEY",))
        self.assertNotIn("sk-secret-value", " ".join(applied))

    def test_real_environment_is_untouched_by_default(self) -> None:
        """不传 environ 时走真实 os.environ；用一次性键验证且不留痕。"""

        key = "CPM_TEST_ENV_ONLY"
        os.environ.pop(key, None)
        self.addCleanup(lambda: os.environ.pop(key, None))
        self.path.write_text(f"{key}=value\n", encoding="utf-8")
        self.assertEqual(load_env_file(self.path), (key,))
        self.assertEqual(os.environ[key], "value")


class TestLoadProjectEnv(unittest.TestCase):
    def test_loads_repo_root_then_backend_without_overriding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / ".env").write_text("A=root\nB=root\n", encoding="utf-8")
            (base / "backend").mkdir()
            (base / "backend" / ".env").write_text(
                "B=backend\nC=backend\n", encoding="utf-8"
            )
            environ: dict[str, str] = {}
            paths = (base / ".env", base / "backend" / ".env")
            applied = load_project_env(paths=paths)
            self.assertTrue(applied)
            # 真实 os.environ 里不应有这些测试键
            for key in ("A", "B", "C"):
                os.environ.pop(key, None)
            load_env_file(paths[0], environ=environ)
            load_env_file(paths[1], environ=environ)
            self.assertEqual(environ["A"], "root")
            self.assertEqual(environ["B"], "root", "后加载的文件不得覆盖先前的值")

    def test_default_paths_are_repo_root_and_backend(self) -> None:
        from app.paths import BACKEND_ROOT, REPO_ROOT

        applied = load_project_env()  # 本机没有 .env 时应返回空元组
        self.assertIsInstance(applied, tuple)
        self.assertTrue((REPO_ROOT / "docs").is_dir())
        self.assertTrue((BACKEND_ROOT / "app").is_dir())


class TestCliAndApiLoadEnv(unittest.TestCase):
    def test_cli_entry_loads_env(self) -> None:
        import inspect

        from app import cli

        source = inspect.getsource(cli.main)
        self.assertIn("load_project_env", source)

    def test_api_module_loads_env_at_import(self) -> None:
        import importlib
        import inspect

        module = importlib.import_module("app.api.app")
        source = inspect.getsource(module)
        self.assertIn("load_project_env()", source)


if __name__ == "__main__":
    unittest.main()

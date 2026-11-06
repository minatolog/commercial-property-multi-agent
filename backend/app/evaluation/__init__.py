"""评测层（Task 013）：数据集、三基线、确定性断言与报告。

设计原则：

1. **确定性断言与人工量表分开**：`kind="rubric"` 的断言不计入自动通过率，只列入人工待评清单。
2. **路由只算效率**：`allowed_routes` 命中与否写入 `efficiency`，绝不参与 `correctness`。
3. **基线与模型解耦**：三基线用同一套 fixture、同一套工具白名单与同一份全任务预算；
   离线（Fake/无模型）结果只能说明**架构与工具链**的行为，不能当作真实模型质量或成本。
4. **报告可追溯**：代码提交、数据集校验和、fixture 校验和、评分规则版本一起写进报告头。
"""

from __future__ import annotations

from .cases import EvalCase, load_cases
from .runner import EvaluationReport, evaluate, render_markdown, write_report
from .scoring import CaseScore, score_case

__all__ = [
    "CaseScore",
    "EvalCase",
    "EvaluationReport",
    "evaluate",
    "load_cases",
    "render_markdown",
    "score_case",
    "write_report",
]

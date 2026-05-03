"""
Scanner Agent — 扫描代码库，识别技术债
"""

import ast
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class DebtItem:
    file: str
    line: int
    debt_type: str
    description: str
    severity: str  # high / medium / low


@dataclass
class ScanReport:
    repo_path: str
    total_files: int
    debt_items: List[DebtItem] = field(default_factory=list)

    def summary(self) -> str:
        high = sum(1 for d in self.debt_items if d.severity == "high")
        medium = sum(1 for d in self.debt_items if d.severity == "medium")
        return (
            f"扫描完成：共 {self.total_files} 个文件，"
            f"发现技术债 {len(self.debt_items)} 处 "
            f"（高危 {high} / 中危 {medium}）"
        )


class ScannerAgent:
    """静态分析代码库，输出结构化技术债报告"""

    MAX_FUNCTION_LINES = 80
    MAX_COMPLEXITY = 10

    def run(self, repo_path: str) -> ScanReport:
        py_files = self._collect_python_files(repo_path)
        report = ScanReport(repo_path=repo_path, total_files=len(py_files))

        for filepath in py_files:
            try:
                source = open(filepath, encoding="utf-8").read()
                tree = ast.parse(source)
            except Exception:
                continue

            report.debt_items.extend(self._check_long_functions(filepath, tree))
            report.debt_items.extend(self._check_complexity(filepath, tree))
            report.debt_items.extend(self._check_deprecated_api(filepath, source))

        print(report.summary())
        return report

    # ── 内部检测方法 ──────────────────────────────────────

    def _collect_python_files(self, root: str) -> List[str]:
        result = []
        for dirpath, _, filenames in os.walk(root):
            if any(skip in dirpath for skip in [".git", "__pycache__", "venv", ".tox"]):
                continue
            for fn in filenames:
                if fn.endswith(".py"):
                    result.append(os.path.join(dirpath, fn))
        return result

    def _check_long_functions(self, filepath: str, tree: ast.AST) -> List[DebtItem]:
        items = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = (node.end_lineno or node.lineno) - node.lineno
                if length > self.MAX_FUNCTION_LINES:
                    items.append(DebtItem(
                        file=filepath,
                        line=node.lineno,
                        debt_type="long_function",
                        description=f"函数 `{node.name}` 共 {length} 行，超过 {self.MAX_FUNCTION_LINES} 行阈值",
                        severity="medium",
                    ))
        return items

    def _check_complexity(self, filepath: str, tree: ast.AST) -> List[DebtItem]:
        """简化版圈复杂度检测：统计分支节点数"""
        items = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                branches = sum(
                    1 for n in ast.walk(node)
                    if isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                                      ast.With, ast.Assert, ast.comprehension))
                )
                if branches > self.MAX_COMPLEXITY:
                    items.append(DebtItem(
                        file=filepath,
                        line=node.lineno,
                        debt_type="high_complexity",
                        description=f"函数 `{node.name}` 圈复杂度约为 {branches}，超过阈值 {self.MAX_COMPLEXITY}",
                        severity="high",
                    ))
        return items

    def _check_deprecated_api(self, filepath: str, source: str) -> List[DebtItem]:
        deprecated = {
            "collections.Callable": "collections.abc.Callable",
            "asyncio.coroutine": "async def",
            "imp.load_source": "importlib",
        }
        items = []
        for lineno, line in enumerate(source.splitlines(), 1):
            for old, new in deprecated.items():
                if old in line:
                    items.append(DebtItem(
                        file=filepath,
                        line=lineno,
                        debt_type="deprecated_api",
                        description=f"使用了已废弃的 API `{old}`，建议替换为 `{new}`",
                        severity="high",
                    ))
        return items


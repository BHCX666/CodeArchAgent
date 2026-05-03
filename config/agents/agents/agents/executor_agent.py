"""
Executor Agent — 根据重构计划自动生成代码并提交 PR
"""

import anthropic
from dataclasses import dataclass
from typing import List

from agents.planner_agent import RefactorTask
from core.github_client import GitHubClient


@dataclass
class PRResult:
    task: RefactorTask
    pr_url: str
    branch: str
    success: bool
    error: str = ""


class ExecutorAgent:
    """
    调用 Claude API 生成重构代码，
    通过 GitHub API 提交 PR，PR 描述自动关联技术债 Issue。
    """

    BRANCH_PREFIX = "arch-agent/"

    def __init__(self, github: GitHubClient, model: str = "claude-sonnet-4-20250514"):
        self.github = github
        self.client = anthropic.Anthropic()
        self.model = model

    def run(self, tasks: List[RefactorTask]) -> List[PRResult]:
        results = []
        for task in tasks:
            print(f"⚙️  执行重构：{task.debt.description[:50]}...")
            result = self._execute_task(task)
            results.append(result)
            if result.success:
                print(f"✅ PR 已创建：{result.pr_url}")
            else:
                print(f"❌ PR 创建失败：{result.error}")
        return results

    def _execute_task(self, task: RefactorTask) -> PRResult:
        branch = f"{self.BRANCH_PREFIX}{task.debt.debt_type}-L{task.debt.line}"
        try:
            # 1. 读取原始文件内容
            original_code = self.github.get_file_content(task.debt.file)

            # 2. 让 Claude 生成重构后的代码
            refactored_code = self._generate_refactored_code(task, original_code)

            # 3. 生成对应的单元测试
            test_code = self._generate_tests(task, refactored_code)

            # 4. 提交文件到新分支
            self.github.create_branch(branch)
            self.github.update_file(
                branch=branch,
                path=task.debt.file,
                content=refactored_code,
                message=f"refactor: {task.debt.debt_type} in {task.debt.file}",
            )
            test_path = task.debt.file.replace(".py", "_test_arch.py")
            self.github.create_file(
                branch=branch,
                path=test_path,
                content=test_code,
                message=f"test: add tests for refactored {task.debt.file}",
            )

            # 5. 创建 PR
            pr_url = self.github.create_pr(
                title=f"[ArchAgent] {task.debt.debt_type}: {task.debt.file}",
                body=self._build_pr_body(task),
                head=branch,
            )
            return PRResult(task=task, pr_url=pr_url, branch=branch, success=True)

        except Exception as e:
            return PRResult(task=task, pr_url="", branch=branch, success=False, error=str(e))

    def _generate_refactored_code(self, task: RefactorTask, original: str) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": (
                    f"以下是需要重构的 Python 代码，位于 `{task.debt.file}` 第 {task.debt.line} 行附近：\n\n"
                    f"```python\n{original}\n```\n\n"
                    f"问题描述：{task.debt.description}\n"
                    f"重构方案：{task.refactor_plan}\n\n"
                    "请输出完整的重构后代码，只输出代码，不要任何解释。"
                )
            }]
        )
        code = resp.content[0].text
        # 去除 markdown 代码块标记
        code = code.replace("```python", "").replace("```", "").strip()
        return code

    def _generate_tests(self, task: RefactorTask, refactored_code: str) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": (
                    f"以下是重构后的代码：\n\n```python\n{refactored_code}\n```\n\n"
                    "请为其生成 pytest 单元测试，覆盖主要逻辑分支。只输出测试代码。"
                )
            }]
        )
        code = resp.content[0].text
        return code.replace("```python", "").replace("```", "").strip()

    def _build_pr_body(self, task: RefactorTask) -> str:
        return (
            f"## 🤖 自动重构 PR（由 CodeArchAgent 生成）\n\n"
            f"### 技术债信息\n"
            f"- **文件**：`{task.debt.file}` 第 {task.debt.line} 行\n"
            f"- **类型**：{task.debt.debt_type}\n"
            f"- **问题**：{task.debt.description}\n"
            f"- **风险评分**：{task.risk_score:.2f}\n"
            f"- **预计工时**：{task.estimated_hours} 小时\n\n"
            f"### 重构方案\n{task.refactor_plan}\n\n"
            f"### Checklist\n"
            f"- [x] 自动生成重构代码\n"
            f"- [x] 自动生成单元测试\n"
            f"- [ ] CI 通过\n"
            f"- [ ] 人工 Review\n"
        )


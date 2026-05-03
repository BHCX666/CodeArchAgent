"""
Verifier Agent — 监听 CI 结果，失败时自动修复（最多 3 轮）
"""

import time
import anthropic
from typing import List

from agents.executor_agent import PRResult
from core.github_client import GitHubClient


class VerifierAgent:
    """
    轮询 PR 关联的 CI 状态。
    若 CI 失败，调用 Claude 分析错误日志并自动提交修复 commit。
    最多重试 MAX_FIX_ROUNDS 轮，超过则标记为需人工介入。
    """

    MAX_FIX_ROUNDS = 3
    POLL_INTERVAL = 60  # 秒

    def __init__(self, github: GitHubClient, model: str = "claude-sonnet-4-20250514"):
        self.github = github
        self.client = anthropic.Anthropic()
        self.model = model

    def run(self, pr_results: List[PRResult]) -> dict:
        summary = {"passed": [], "fixed": [], "failed": [], "manual": []}

        for pr in pr_results:
            if not pr.success:
                summary["failed"].append(pr)
                continue

            print(f"🔍 验证 PR：{pr.pr_url}")
            outcome = self._verify_and_fix(pr)
            summary[outcome].append(pr)

        self._print_summary(summary)
        return summary

    def _verify_and_fix(self, pr: PRResult) -> str:
        for round_num in range(1, self.MAX_FIX_ROUNDS + 1):
            print(f"  ⏳ 等待 CI 结果（第 {round_num} 轮）...")
            time.sleep(self.POLL_INTERVAL)

            status = self.github.get_ci_status(pr.branch)

            if status == "success":
                print(f"  ✅ CI 通过！")
                self.github.request_review(pr.pr_url)
                return "passed" if round_num == 1 else "fixed"

            if status == "pending":
                continue  # 继续等待

            # CI 失败
            print(f"  ❌ CI 失败，尝试自动修复（第 {round_num}/{self.MAX_FIX_ROUNDS} 轮）...")
            log = self.github.get_ci_log(pr.branch)
            fixed = self._auto_fix(pr, log)

            if not fixed:
                break

        # 超过最大轮次，标记为需人工介入
        self.github.add_label(pr.pr_url, "needs-manual-review")
        self.github.add_comment(
            pr.pr_url,
            f"⚠️ CodeArchAgent 已尝试 {self.MAX_FIX_ROUNDS} 轮自动修复，仍未通过 CI，请人工介入。"
        )
        print(f"  ⚠️ 超过最大修复轮次，已通知人工介入")
        return "manual"

    def _auto_fix(self, pr: PRResult, ci_log: str) -> bool:
        """调用 Claude 分析 CI 日志并生成修复代码"""
        try:
            current_code = self.github.get_file_content(pr.task.debt.file, branch=pr.branch)

            resp = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{
                    "role": "user",
                    "content": (
                        f"以下代码在 CI 中失败，错误日志如下：\n\n"
                        f"```\n{ci_log[-3000:]}\n```\n\n"
                        f"当前代码：\n```python\n{current_code}\n```\n\n"
                        "请分析错误原因并输出修复后的完整代码，只输出代码。"
                    )
                }]
            )
            fixed_code = resp.content[0].text
            fixed_code = fixed_code.replace("```python", "").replace("```", "").strip()

            self.github.update_file(
                branch=pr.branch,
                path=pr.task.debt.file,
                content=fixed_code,
                message="fix: auto-fix CI failure by CodeArchAgent",
            )
            return True

        except Exception as e:
            print(f"  ❌ 自动修复失败：{e}")
            return False

    def _print_summary(self, summary: dict):
        print("\n📊 验证结果汇总：")
        print(f"  ✅ CI 直接通过：{len(summary['passed'])} 个")
        print(f"  🔧 自动修复后通过：{len(summary['fixed'])} 个")
        print(f"  ⚠️  需人工介入：{len(summary['manual'])} 个")
        print(f"  ❌ PR 创建失败：{len(summary['failed'])} 个")


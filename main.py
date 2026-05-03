"""
CodeArchAgent 入口
用法: python main.py --repo ./your-project --owner your-org --repo-name your-repo
"""

import typer
import yaml

from agents.scanner_agent import ScannerAgent
from agents.planner_agent import PlannerAgent
from agents.executor_agent import ExecutorAgent
from agents.verifier_agent import VerifierAgent
from core.github_client import GitHubClient

app = typer.Typer()


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


@app.command()
def main(
    repo: str = typer.Option(..., help="本地代码库路径"),
    owner: str = typer.Option(..., help="GitHub 组织/用户名"),
    repo_name: str = typer.Option(..., help="GitHub 仓库名"),
    config: str = typer.Option("config/config.yaml", help="配置文件路径"),
):
    cfg = load_config(config)
    model = cfg.get("model", "claude-sonnet-4-20250514")
    risk_threshold = cfg.get("planner", {}).get("risk_threshold", 0.7)

    print("🚀 CodeArchAgent 启动")
    print(f"   仓库路径：{repo}")
    print(f"   GitHub：{owner}/{repo_name}")
    print(f"   模型：{model}\n")

    # Step 1: 扫描
    print("=" * 50)
    print("📡 Step 1 — Scanner Agent 扫描技术债")
    scanner = ScannerAgent()
    scan_report = scanner.run(repo)

    if not scan_report.debt_items:
        print("✨ 恭喜！未发现技术债。")
        return

    # Step 2: 规划
    print("\n" + "=" * 50)
    print("🧠 Step 2 — Planner Agent 生成重构计划（CoT 推理）")
    planner = PlannerAgent(model=model)
    tasks = planner.run(scan_report, risk_threshold=risk_threshold)

    if not tasks:
        print("⚠️ 所有技术债风险过高，跳过本次重构。")
        return

    # Step 3: 执行
    print("\n" + "=" * 50)
    print("⚙️  Step 3 — Executor Agent 生成代码并提交 PR")
    github = GitHubClient(owner=owner, repo_name=repo_name)
    executor = ExecutorAgent(github=github, model=model)
    pr_results = executor.run(tasks)

    # Step 4: 验证
    print("\n" + "=" * 50)
    print("✅ Step 4 — Verifier Agent 验证 CI 并自动修复")
    verifier = VerifierAgent(github=github, model=model)
    verifier.run(pr_results)

    print("\n🎉 CodeArchAgent 运行完成！")


if __name__ == "__main__":
    app()


"""
Planner Agent — 多轮 CoT 长链推理，生成优先级重构计划
"""

import json
import anthropic
from dataclasses import dataclass
from typing import List

from agents.scanner_agent import ScanReport, DebtItem


@dataclass
class RefactorTask:
    debt: DebtItem
    priority: int          # 1（最高）~ 5（最低）
    risk_score: float      # 0.0 ~ 1.0
    refactor_plan: str     # 具体重构方案描述
    estimated_hours: float


class PlannerAgent:
    """
    使用 Claude claude-sonnet-4-20250514 进行多轮 Chain-of-Thought 推理，
    对技术债进行风险/收益评估，生成优先级排序的重构计划。
    """

    COT_ROUNDS = 3

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic()
        self.model = model

    def run(self, report: ScanReport, risk_threshold: float = 0.7) -> List[RefactorTask]:
        if not report.debt_items:
            print("✅ 未发现技术债，无需重构")
            return []

        print(f"🧠 Planner Agent 开始分析 {len(report.debt_items)} 个技术债...")
        tasks = []

        for debt in report.debt_items[:10]:  # 每次最多处理 10 个
            task = self._plan_single(debt)
            if task and task.risk_score < risk_threshold:
                tasks.append(task)
            elif task:
                print(f"⚠️ 跳过高风险项（风险分 {task.risk_score:.2f}）：{debt.description}")

        tasks.sort(key=lambda t: (t.priority, t.risk_score))
        print(f"📋 生成重构计划 {len(tasks)} 项")
        return tasks

    def _plan_single(self, debt: DebtItem) -> RefactorTask | None:
        """多轮 CoT 推理评估单个技术债"""
        messages = []

        # 第一轮：理解问题
        messages.append({
            "role": "user",
            "content": (
                f"我在代码文件 `{debt.file}` 第 {debt.line} 行发现了以下技术债：\n"
                f"类型：{debt.debt_type}\n"
                f"描述：{debt.description}\n\n"
                f"请先分析这个问题的根本原因和潜在影响。"
            )
        })
        r1 = self._call(messages)
        messages.append({"role": "assistant", "content": r1})

        # 第二轮：评估风险
        messages.append({
            "role": "user",
            "content": "请评估修复这个问题的风险（0.0～1.0），并说明主要风险点。"
        })
        r2 = self._call(messages)
        messages.append({"role": "assistant", "content": r2})

        # 第三轮：生成结构化方案
        messages.append({
            "role": "user",
            "content": (
                "请给出具体的重构方案，并以 JSON 格式输出：\n"
                "{\n"
                '  "priority": 1-5,\n'
                '  "risk_score": 0.0-1.0,\n'
                '  "refactor_plan": "具体重构步骤",\n'
                '  "estimated_hours": 预计工时\n'
                "}"
            )
        })
        r3 = self._call(messages)

        return self._parse_plan(debt, r3)

    def _call(self, messages: list) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=messages,
        )
        return resp.content[0].text

    def _parse_plan(self, debt: DebtItem, text: str) -> RefactorTask | None:
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            data = json.loads(text[start:end])
            return RefactorTask(
                debt=debt,
                priority=int(data.get("priority", 3)),
                risk_score=float(data.get("risk_score", 0.5)),
                refactor_plan=data.get("refactor_plan", ""),
                estimated_hours=float(data.get("estimated_hours", 2.0)),
            )
        except Exception as e:
            print(f"❌ 解析规划结果失败：{e}")
            return None


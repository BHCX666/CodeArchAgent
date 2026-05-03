"""
DAG 任务调度器 — 支持有向无环图并行调度多个重构任务
"""

import concurrent.futures
from dataclasses import dataclass, field
from typing import List, Callable, Dict, Any


@dataclass
class DAGNode:
    name: str
    fn: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)


class DAGScheduler:
    """
    按依赖顺序调度 Agent 节点，
    无依赖关系的节点并行执行。
    """

    def __init__(self, max_workers: int = 4):
        self.nodes: Dict[str, DAGNode] = {}
        self.max_workers = max_workers

    def add_node(self, node: DAGNode):
        self.nodes[node.name] = node

    def run(self) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        completed = set()

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while len(completed) < len(self.nodes):
                ready = [
                    n for name, n in self.nodes.items()
                    if name not in completed
                    and all(dep in completed for dep in n.depends_on)
                ]
                if not ready:
                    break

                futures = {
                    executor.submit(n.fn, *n.args, **n.kwargs): n
                    for n in ready
                }
                for future in concurrent.futures.as_completed(futures):
                    node = futures[future]
                    try:
                        results[node.name] = future.result()
                        completed.add(node.name)
                        print(f"  ✅ [{node.name}] 完成")
                    except Exception as e:
                        print(f"  ❌ [{node.name}] 失败：{e}")
                        completed.add(node.name)
                        results[node.name] = None

        return results


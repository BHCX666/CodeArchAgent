"""
Agent 间消息总线 — 结构化 JSON 消息传递
"""

import json
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Callable


@dataclass
class Message:
    sender: str
    receiver: str
    msg_type: str       # scan_done / plan_done / exec_done / verify_done
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class MessageBus:
    """简单的内存消息总线，支持 Agent 间发布/订阅"""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._history: List[Message] = []

    def subscribe(self, msg_type: str, handler: Callable):
        self._subscribers.setdefault(msg_type, []).append(handler)

    def publish(self, msg: Message):
        self._history.append(msg)
        for handler in self._subscribers.get(msg.msg_type, []):
            handler(msg)

    def history(self) -> List[Message]:
        return list(self._history)


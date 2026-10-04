"""V2 编排器内核：自动推进循环 + 决策门。

状态规则：循环每轮开头从 store 重读任务状态（支持外部 pause）；
review 阶段发言完成后开启决策门并退出循环，由 submit_decision 驱动后续轮次。
"""

import asyncio
import time
from typing import Protocol

from web.v2 import demo
from web.v2.models import (
    STAGES,
    Constraint,
    Decision,
    DecisionOption,
    Stage,
    Turn,
    V2Task,
)
from web.v2.store import V2Store


class SpeakerBackend(Protocol):
    async def speak(self, task: V2Task, author: str, key: str) -> tuple[str, str, bool]:
        """返回 (title, body, verified)，orchestrator 据此建 Turn。"""


class Broadcaster(Protocol):
    def publish(self, task_id: str, event: str, data: dict) -> None:
        """向订阅者广播编排事件（真实版由 Task 8 实现）。"""


class NullBroadcaster:
    def publish(self, task_id: str, event: str, data: dict) -> None:
        pass


STAGE_PLAN: list[tuple[Stage, list[str], str]] = [
    ("clarify", ["ada"], "澄清需求"),
    ("compare", ["turing"], "比较方案"),
    ("review", ["linus"], "评审风险"),
]

_AUTHOR_BY_KEY: dict[str, str] = {
    "clarify_ada": "ada",
    "compare_turing": "turing",
    "review_linus": "linus",
    "uncertain_turing": "turing",
    "uncertain_linus": "linus",
    "revise_turing": "turing",
    "recommend_sage": "sage",
}

_STAGE_BY_KEY: dict[str, Stage] = {
    "clarify_ada": "clarify",
    "compare_turing": "compare",
    "review_linus": "review",
    "uncertain_turing": "review",
    "uncertain_linus": "review",
    "revise_turing": "review",
    "recommend_sage": "recommend",
}


class Orchestrator:
    def __init__(self, store: V2Store, backend: SpeakerBackend, broadcaster: Broadcaster):
        self.store = store
        self.backend = backend
        self.broadcaster = broadcaster
        self._running: dict[str, asyncio.Task] = {}

    def _save(self, task: V2Task) -> None:
        task.updated_at = time.time()
        self.store.save_task(task)

    def _publish(self, task_id: str, event: str, data: dict) -> None:
        self.broadcaster.publish(task_id, event, data)

    def _make_turn(
        self,
        task: V2Task,
        stage: Stage,
        author: str,
        kind: str,
        title: str = "",
        body: str = "",
        verified: bool = False,
    ) -> Turn:
        turn = Turn(
            id=f"turn-{task.next_seq()}",
            seq=task.next_seq(),
            stage=stage,
            author=author,
            kind=kind,
            title=title,
            body=body,
            verified=verified,
        )
        task.turns.append(turn)
        return turn

    async def _speak(self, task: V2Task, key: str) -> Turn:
        author = _AUTHOR_BY_KEY[key]
        title, body, verified = await self.backend.speak(task, author, key)
        turn = self._make_turn(
            task, _STAGE_BY_KEY[key], author, "statement",
            title=title, body=body, verified=verified,
        )
        self._save(task)
        self._publish(task.id, "turn_done", {"turn_id": turn.id, "seq": turn.seq})
        return turn

    def _open_gate(self, task: V2Task) -> Decision:
        round_no = len(task.decisions) + 1
        decision = Decision(
            id=f"d{round_no}",
            round=round_no,
            question=demo.DEMO_QUESTION,
            options=[DecisionOption(**opt) for opt in demo.DEMO_OPTIONS],
        )
        task.decisions.append(decision)
        task.status = "waiting_confirmation"
        self._save(task)
        self._publish(
            task.id,
            "decision_required",
            {
                "decision_id": decision.id,
                "question": decision.question,
                "options": [opt.model_dump() for opt in decision.options],
            },
        )
        self._publish(task.id, "status_change", {"status": task.status})
        return decision

    def _advance_stage(self, task: V2Task) -> None:
        task.stage_index += 1
        task.current_stage = STAGES[task.stage_index]
        self._save(task)
        self._publish(task.id, "stage_change", {"stage": task.current_stage})

    async def _step(self, task: V2Task) -> bool:
        """执行一个推进单元；返回 False 表示循环应退出（到达决策门或无可做之事）。"""
        if task.stage_index >= len(STAGE_PLAN):
            return False
        stage, speakers, _label = STAGE_PLAN[task.stage_index]
        spoken = sum(1 for t in task.turns if t.stage == stage and t.kind == "statement")
        if spoken < len(speakers):
            await self._speak(task, f"{stage}_{speakers[spoken]}")
            return True
        if stage == "review":
            self._open_gate(task)
            return False
        self._advance_stage(task)
        return True

    async def run_task(self, task_id: str) -> None:
        current = asyncio.current_task()
        existing = self._running.get(task_id)
        if existing is not None and not existing.done():
            return
        if current is not None:
            self._running[task_id] = current
        try:
            task = self.store.get_task(task_id)
            if task is None:
                return
            if task.status in ("preparing", "paused"):
                task.status = "running"
                self._save(task)
                self._publish(task_id, "status_change", {"status": "running"})
                self._publish(task_id, "stage_change", {"stage": task.current_stage})
            while True:
                task = self.store.get_task(task_id)
                if task is None or task.status != "running":
                    break
                if not await self._step(task):
                    break
        finally:
            if current is not None and self._running.get(task_id) is current:
                self._running.pop(task_id, None)

    def pause(self, task_id: str) -> None:
        task = self.store.get_task(task_id)
        if task is None or task.status != "running":
            return
        task.status = "paused"
        self._save(task)
        self._publish(task_id, "status_change", {"status": "paused"})

    def resume(self, task_id: str) -> None:
        task = self.store.get_task(task_id)
        if task is None or task.status != "paused":
            return
        task.status = "running"
        self._save(task)
        self._publish(task_id, "status_change", {"status": "running"})

    async def submit_decision(self, task_id: str, decision_id: str, option_id: str) -> V2Task:
        task = self.store.get_task(task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        decision = next((d for d in task.decisions if d.id == decision_id), None)
        if decision is None or decision.status == "resolved":
            return task
        option = next((o for o in decision.options if o.id == option_id), None)
        if option is None:
            return task
        decision.chosen_id = option.id
        decision.status = "resolved"
        turn = self._make_turn(
            task, task.current_stage, "user", "decision_record",
            title=f"你已确认：{option.label}", body=option.impact,
        )
        task.constraints.append(Constraint(text=option.label, confirmed=True))
        self._save(task)
        self._publish(task_id, "turn_done", {"turn_id": turn.id, "seq": turn.seq})
        if option.uncertain:
            await self._speak(task, "uncertain_turing")
            await self._speak(task, "uncertain_linus")
            self._open_gate(task)
        else:
            await self._speak(task, "revise_turing")
            task.stage_index = STAGES.index("recommend")
            task.current_stage = "recommend"
            self._save(task)
            self._publish(task_id, "stage_change", {"stage": "recommend"})
            await self._speak(task, "recommend_sage")
            task.outcome = demo.build_outcome(task)
            task.status = "completed"
            self._save(task)
            self._publish(task_id, "outcome_update", {"status": "completed"})
            self._publish(task_id, "status_change", {"status": "completed"})
        return task

    async def end_now(self, task_id: str) -> V2Task:
        task = self.store.get_task(task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        if task.outcome is None:
            task.outcome = demo.build_outcome(task)
        if task.status not in ("completed", "failed"):
            task.status = "completed"
        self._save(task)
        self._publish(task_id, "outcome_update", {"status": "completed"})
        self._publish(task_id, "status_change", {"status": task.status})
        return task

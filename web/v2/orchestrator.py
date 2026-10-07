"""V2 编排器内核：自动推进循环 + 决策门。

状态规则：循环每轮开头从 store 重读任务状态（支持外部 pause）；
review 阶段发言完成后开启决策门并退出循环，由 submit_decision 驱动后续轮次。
"""

import asyncio
import time
from typing import Protocol

from web.v2 import demo
from web.v2.experts import DEFAULT_ASSIGNMENTS
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


class AgentCallError(Exception):
    """后端调用失败（backend 内部重试一次仍失败时抛出，Task 6 接入）。"""


STAGE_PLAN: list[tuple[Stage, list[str], str]] = [
    ("clarify", ["ada"], "澄清需求"),
    ("compare", ["turing"], "比较方案"),
    ("review", ["linus"], "评审风险"),
]

_PURPOSE_BY_KEY: dict[str, str] = {
    "clarify_ada": "research",
    "compare_turing": "propose",
    "review_linus": "challenge",
    "uncertain_turing": "propose",
    "uncertain_linus": "challenge",
    "revise_turing": "propose",
    "recommend_sage": "synthesize",
}


def expert_for(task: V2Task, key: str) -> str:
    """key→purpose→任务指派；无指派时回退默认映射，指派不在快照中再回退默认（确定性）。"""
    purpose = _PURPOSE_BY_KEY[key]
    author = task.assignments.get(purpose) or DEFAULT_ASSIGNMENTS[purpose]
    if task.experts and task.expert_by_id(author) is None:
        author = DEFAULT_ASSIGNMENTS[purpose]
    return author

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
        self._continuing: dict[str, asyncio.Task] = {}
        self._pending_interventions: dict[str, list[dict]] = {}

    def _save(self, task: V2Task) -> None:
        task.updated_at = time.time()
        self.store.save_task(task)

    def _adopt_persisted(self, task: V2Task) -> None:
        """await 窗口内外部可能已改库（pause/resume/end_now/retry）；发言落盘前同步这些字段，
        避免用旧对象整行覆盖掉外部变更（status/outcome 等）。"""
        fresh = self.store.get_task(task.id)
        if fresh is None:
            return
        for field in ("status", "current_stage", "stage_index", "error", "outcome"):
            setattr(task, field, getattr(fresh, field))

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
        intent: str | None = None,
    ) -> Turn:
        seq = task.next_seq()
        turn = Turn(
            id=f"turn-{seq}",
            seq=seq,
            stage=stage,
            author=author,
            kind=kind,
            title=title,
            body=body,
            verified=verified,
            intent=intent,
        )
        task.turns.append(turn)
        return turn

    async def _speak(self, task: V2Task, key: str) -> Turn:
        author = expert_for(task, key)
        # 发言生成可能耗时较长（LLM 思考期无增量）：先广播 turn_start，
        # 前端据此在会议舱与讨论区显示「思考中」动画，避免看起来像连接中断。
        self._publish(task.id, "turn_start", {"author": author, "key": key})
        title, body, verified = await self.backend.speak(task, author, key)
        self._adopt_persisted(task)
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

    def _drain_interventions(self, task: V2Task) -> None:
        """把待处理的用户补充落成 user_note turn（推进循环每条发言后 / 决策记录后调用）。"""
        queue = self._pending_interventions.get(task.id)
        if not queue:
            return
        for item in queue:
            turn = self._make_turn(
                task, task.current_stage, "user", "user_note",
                title=f"你 · {item['intent']}", body=item["text"], intent=item["intent"],
            )
            self._save(task)
            self._publish(
                task.id,
                "intervention_ack",
                {"turn_id": turn.id, "seq": turn.seq, "intent": item["intent"], "text": item["text"]},
            )
        self._pending_interventions[task.id] = []

    async def _step(self, task: V2Task) -> bool:
        """执行一个推进单元；返回 False 表示循环应退出（到达决策门或无可做之事）。"""
        if task.stage_index >= len(STAGE_PLAN):
            return False
        stage, speakers, _label = STAGE_PLAN[task.stage_index]
        spoken = sum(1 for t in task.turns if t.stage == stage and t.kind == "statement")
        if spoken < len(speakers):
            await self._speak(task, f"{stage}_{speakers[spoken]}")
            self._drain_interventions(task)
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
                try:
                    if not await self._step(task):
                        break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._mark_failed(task, exc)
                    return
        finally:
            if current is not None and self._running.get(task_id) is current:
                self._running.pop(task_id, None)

    def _mark_failed(self, task: V2Task, exc: Exception) -> None:
        task.error = f"发言生成失败：{exc}"
        task.status = "failed"
        self._save(task)
        self._publish(task.id, "status_change", {"status": "failed"})

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

    def resolve_decision(self, task_id: str, decision_id: str, option_id: str) -> V2Task:
        """同步落盘决策：写 chosen、追加约束、记录 decision_record、转 running。

        只做校验与落盘，不做后续发言——HTTP 侧可立即返回，续推交给 continue_after_decision。
        """
        task = self.store.get_task(task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        decision = next((d for d in task.decisions if d.id == decision_id), None)
        if decision is None or decision.status == "resolved":
            return task  # 幂等：未知或已确认的决策不再重复处理
        option = next((o for o in decision.options if o.id == option_id), None)
        if option is None:
            return task
        decision.chosen_id = option.id
        decision.status = "resolved"
        turn = self._make_turn(
            task, task.current_stage, "user", "decision_record",
            title=f"你已确认：{option.label}", body=option.impact,
        )
        # 「暂不确定」也记录约束但不确认，避免出现在下游已确认列表中。
        task.constraints.append(Constraint(text=option.label, confirmed=not option.uncertain))
        task.status = "running"
        self._save(task)
        self._publish(task_id, "status_change", {"status": "running"})
        self._publish(task_id, "turn_done", {"turn_id": turn.id, "seq": turn.seq})
        return task

    async def continue_after_decision(self, task_id: str) -> None:
        """决策落盘后的续推；有已确认但未走完的决策时执行（供 submit_decision / retry 复用）。"""
        current = asyncio.current_task()
        existing = self._continuing.get(task_id)
        if existing is not None and not existing.done():
            return
        if current is not None:
            self._continuing[task_id] = current
        try:
            task = self.store.get_task(task_id)
            if task is None:
                return
            resolved = [d for d in task.decisions if d.status == "resolved"]
            if not resolved or resolved[-1] is not task.decisions[-1]:
                return  # 无待续推的决策；或其后已开出新门（等待用户确认）
            option = next(
                (o for o in resolved[-1].options if o.id == resolved[-1].chosen_id), None
            )
            if option is None or (not option.uncertain and task.status == "completed"):
                return  # 确认路径已走完
            try:
                await self._continue_after_decision(task)
            except Exception as exc:
                self._mark_failed(task, exc)
        finally:
            if current is not None and self._continuing.get(task_id) is current:
                self._continuing.pop(task_id, None)

    async def submit_decision(self, task_id: str, decision_id: str, option_id: str) -> V2Task:
        self.resolve_decision(task_id, decision_id, option_id)
        await self.continue_after_decision(task_id)
        return self.store.get_task(task_id)

    async def _continue_after_decision(self, task: V2Task) -> None:
        """门决策后的续推；按本决策记录之后的已完成发言数续传（供 submit_decision / retry 复用）。"""
        self._drain_interventions(task)
        decision = task.decisions[-1]
        option = next(o for o in decision.options if o.id == decision.chosen_id)
        record = next(t for t in reversed(task.turns) if t.kind == "decision_record")
        post = [t for t in task.turns if t.seq > record.seq and t.kind == "statement"]
        if option.uncertain:
            if len(post) < 1:
                await self._speak(task, "uncertain_turing")
            if len(post) < 2:
                await self._speak(task, "uncertain_linus")
            self._open_gate(task)
        else:
            if len(post) < 1:
                await self._speak(task, "revise_turing")
            if task.stage_index != STAGES.index("recommend"):
                task.stage_index = STAGES.index("recommend")
                task.current_stage = "recommend"
                self._save(task)
                self._publish(task.id, "stage_change", {"stage": "recommend"})
            if len(post) < 2:
                await self._speak(task, "recommend_sage")
            task.outcome = demo.build_outcome(task)
            task.status = "completed"
            self._save(task)
            self._publish(task.id, "outcome_update", {"status": "completed"})
            self._publish(task.id, "status_change", {"status": "completed"})

    async def submit_intervention(self, task_id: str, intent: str, text: str) -> dict:
        task = self.store.get_task(task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        if task.status not in ("preparing", "running", "waiting_confirmation", "paused"):
            raise ValueError("任务当前无法接收补充内容")
        queue = self._pending_interventions.setdefault(task_id, [])
        queue.append({"intent": intent, "text": text})
        return {"received": True, "position": len(queue), "ack": demo.ACK_RECEIVED}

    def retry_prepare(self, task_id: str) -> V2Task:
        """同步重置失败任务：清 error、转 running（HTTP 立即返回，续跑交给 resume_driver）。"""
        task = self.store.get_task(task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        if task.status != "failed":
            raise ValueError("仅失败任务可重试")
        task.error = None
        task.status = "running"
        self._save(task)
        self._publish(task_id, "status_change", {"status": "running"})
        return task

    async def resume_driver(self, task_id: str) -> None:
        """失败重试后的续跑：有开着的门等确认；有已确认决策则续推；否则从头推进循环。"""
        task = self.store.get_task(task_id)
        if task is None:
            return
        last = task.decisions[-1] if task.decisions else None
        if last is not None and last.status == "open":
            task.status = "waiting_confirmation"
            self._save(task)
            self._publish(task_id, "status_change", {"status": "waiting_confirmation"})
        elif last is not None:
            await self.continue_after_decision(task_id)
        else:
            await self.run_task(task_id)

    async def retry(self, task_id: str) -> V2Task:
        self.retry_prepare(task_id)
        await self.resume_driver(task_id)
        return self.store.get_task(task_id)

    async def end_now(self, task_id: str) -> V2Task:
        task = self.store.get_task(task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        if task.status == "completed":
            return task
        if task.status not in ("running", "waiting_confirmation", "paused"):
            raise ValueError("任务当前状态无法提前结束")
        # 先置 completed：推进循环下一次状态检查观察到后自行退出。
        task.outcome = demo.build_outcome(task)
        task.status = "completed"
        task.current_stage = "recommend"
        self._save(task)
        self._publish(task_id, "status_change", {"status": "completed"})
        self._publish(task_id, "outcome_update", {"status": "completed"})
        return task

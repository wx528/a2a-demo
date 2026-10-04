"""V2 SSE 事件广播器：按任务 fan-out 事件给所有订阅流。"""

import asyncio

_QUEUE_MAX = 200


class Broadcaster:
    """每个任务维护一组订阅队列；publish 复制事件到所有队列，慢流直接丢事件。"""

    def __init__(self, maxsize: int = _QUEUE_MAX):
        self._maxsize = maxsize
        self._subs: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subs.setdefault(task_id, set()).add(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        queues = self._subs.get(task_id)
        if queues is not None:
            queues.discard(queue)
            if not queues:
                self._subs.pop(task_id, None)

    def publish(self, task_id: str, event: str, data: dict) -> None:
        for queue in list(self._subs.get(task_id, ())):
            try:
                queue.put_nowait((event, data))
            except asyncio.QueueFull:
                pass  # 消费端卡住的慢流丢弃事件，不阻塞编排循环

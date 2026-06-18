"""
A2A JSON-RPC 2.0 服务端公共组件。
用于简化 research_agent / writing_agent 的 JSON-RPC 端点实现。
"""

import asyncio
import json
import uuid
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .models import (
    AgentCard,
    CancelTaskRequest,
    GetTaskRequest,
    JSONRPCError,
    JSONRPCRequest,
    JSONRPCResponse,
    ListTasksRequest,
    ListTasksResponse,
    Message,
    Role,
    SendMessageRequest,
    StreamResponse,
    SubscribeToTaskRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    artifact_from_text,
    text_part,
    utc_now_iso,
)


class JSONRPCErrorException(Exception):
    """用于在方法处理器内抛出 JSON-RPC 错误。"""

    def __init__(self, error: JSONRPCError):
        self.error = error


def _rpc_error(code: int, message: str, a2a_error: Optional[str] = None) -> JSONRPCError:
    data = {"a2aError": a2a_error} if a2a_error else None
    return JSONRPCError(code=code, message=message, data=data)


def _task_status(state: TaskState, text: Optional[str] = None) -> TaskStatus:
    msg = None
    if text:
        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.AGENT,
            parts=[text_part(text)],
        )
    return TaskStatus(state=state, message=msg, timestamp=utc_now_iso())


def _extract_text(message: Message) -> str:
    texts = []
    for part in message.parts:
        if part.text:
            texts.append(part.text)
    return "\n".join(texts)


class InMemoryTaskStore:
    """内存任务存储，提供基础 CRUD。"""

    def __init__(self):
        self._tasks: Dict[str, Task] = {}

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def list(
        self,
        context_id: Optional[str] = None,
        status: Optional[TaskState] = None,
        page_size: int = 50,
    ) -> List[Task]:
        result = list(self._tasks.values())
        if context_id:
            result = [t for t in result if t.context_id == context_id]
        if status:
            result = [t for t in result if t.status.state == status]
        return result[:page_size]

    def total(self) -> int:
        return len(self._tasks)

    def create(self, message: Message) -> Task:
        task_id = str(uuid.uuid4())
        context_id = message.context_id or str(uuid.uuid4())
        user_msg = Message(
            message_id=message.message_id or str(uuid.uuid4()),
            context_id=context_id,
            task_id=task_id,
            role=Role.USER,
            parts=message.parts,
            metadata=message.metadata,
        )
        task = Task(
            id=task_id,
            context_id=context_id,
            status=_task_status(TaskState.SUBMITTED, "任务已提交"),
            history=[user_msg],
        )
        self._tasks[task_id] = task
        return task

    def update_status(
        self, task: Task, state: TaskState, text: Optional[str] = None
    ):
        task.status = _task_status(state, text)

    def add_artifact(
        self,
        task: Task,
        name: str,
        text: str,
        media_type: str = "text/plain",
    ):
        artifact = artifact_from_text(name, text, media_type)
        if task.artifacts is None:
            task.artifacts = []
        task.artifacts.append(artifact)
        agent_msg = Message(
            message_id=str(uuid.uuid4()),
            context_id=task.context_id,
            task_id=task.id,
            role=Role.AGENT,
            parts=[text_part(text, media_type)],
        )
        task.history.append(agent_msg)


class A2AJSONRPCServer:
    """
    A2A JSON-RPC 2.0 服务端封装。

    用法：
        def process_task(task: Task, store: InMemoryTaskStore):
            ...

        server = A2AJSONRPCServer(agent_card, process_task)
        app = server.build_app()
    """

    def __init__(
        self,
        agent_card: AgentCard,
        process_task: Callable[[Task, InMemoryTaskStore], None],
    ):
        self.agent_card = agent_card
        self.process_task = process_task
        self.store = InMemoryTaskStore()

    def _task_to_dict(
        self, task: Task, history_length: Optional[int] = None
    ) -> Dict[str, Any]:
        t = task.model_copy(deep=True)
        if history_length is not None and history_length >= 0:
            if history_length == 0:
                t.history = []
            else:
                t.history = t.history[-history_length:]
        return t.model_dump(by_alias=True, exclude_none=True)

    # -----------------------------------------------------------------------
    # 方法处理器
    # -----------------------------------------------------------------------

    def _handle_send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        req = SendMessageRequest.model_validate(params)
        return_immediately = False
        if req.configuration and req.configuration.return_immediately:
            return_immediately = True

        task = self.store.create(req.message)

        if return_immediately:
            asyncio.create_task(self._run_task_async(task.id))
            return self._task_to_dict(task)

        self.process_task(task, self.store)
        return self._task_to_dict(task)

    async def _run_task_async(self, task_id: str):
        await asyncio.sleep(0.3)
        task = self.store.get(task_id)
        if task:
            await asyncio.to_thread(self.process_task, task, self.store)

    def _handle_get_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        req = GetTaskRequest.model_validate(params)
        task = self.store.get(req.id)
        if not task:
            raise JSONRPCErrorException(
                _rpc_error(-32100, "Task not found", "TaskNotFoundError")
            )
        return self._task_to_dict(task, req.history_length)

    def _handle_cancel_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        req = CancelTaskRequest.model_validate(params)
        task = self.store.get(req.id)
        if not task:
            raise JSONRPCErrorException(
                _rpc_error(-32100, "Task not found", "TaskNotFoundError")
            )
        if task.status.state in (
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELED,
            TaskState.REJECTED,
        ):
            raise JSONRPCErrorException(
                _rpc_error(-32101, "Task is not cancelable", "TaskNotCancelableError")
            )
        self.store.update_status(task, TaskState.CANCELED, "任务已取消")
        return self._task_to_dict(task)

    def _handle_list_tasks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        req = ListTasksRequest.model_validate(params)
        page_size = req.page_size or 50
        page = self.store.list(
            context_id=req.context_id,
            status=req.status,
            page_size=page_size,
        )
        resp = ListTasksResponse(
            tasks=page,
            next_page_token="",
            page_size=len(page),
            total_size=self.store.total(),
        )
        return resp.model_dump(by_alias=True, exclude_none=True)

    def _dispatch(self, method: str, params: Optional[Dict[str, Any]]) -> Any:
        params = params or {}
        handlers = {
            "tasks/send": self._handle_send_message,
            "tasks/get": self._handle_get_task,
            "tasks/cancel": self._handle_cancel_task,
            "tasks/list": self._handle_list_tasks,
        }
        if method not in handlers:
            raise JSONRPCErrorException(
                _rpc_error(-32601, f"Method not found: {method}")
            )
        return handlers[method](params)

    # -----------------------------------------------------------------------
    # FastAPI 应用构建
    # -----------------------------------------------------------------------

    def build_app(self, title: str = "A2A Agent") -> FastAPI:
        app = FastAPI(title=title)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/.well-known/agent.json")
        async def get_agent_card():
            return self.agent_card.model_dump(by_alias=True, exclude_none=True)

        @app.post("/rpc")
        async def rpc_endpoint(req: Request):
            body = await req.json()
            rpc_id: Any = body.get("id") if isinstance(body, dict) else None
            try:
                rpc_req = JSONRPCRequest.model_validate(body)
            except Exception as e:
                return JSONResponse(
                    JSONRPCResponse(
                        id=rpc_id,
                        error=JSONRPCError(code=-32700, message=f"Parse error: {e}"),
                    ).model_dump(),
                    status_code=400,
                )

            try:
                result = self._dispatch(rpc_req.method, rpc_req.params)
                return JSONResponse(
                    JSONRPCResponse(id=rpc_req.id, result=result).model_dump()
                )
            except JSONRPCErrorException as e:
                return JSONResponse(
                    JSONRPCResponse(id=rpc_req.id, error=e.error).model_dump()
                )
            except Exception as e:
                return JSONResponse(
                    JSONRPCResponse(
                        id=rpc_req.id,
                        error=JSONRPCError(code=-32603, message=f"Internal error: {e}"),
                    ).model_dump(),
                    status_code=500,
                )

        @app.post("/rpc/stream")
        async def rpc_stream_endpoint(req: Request):
            body = await req.json()
            rpc_req = JSONRPCRequest.model_validate(body)
            method = rpc_req.method

            async def event_stream():
                if method == "tasks/sendSubscribe":
                    send_req = SendMessageRequest.model_validate(rpc_req.params or {})
                    task = self.store.create(send_req.message)
                    yield self._sse_event(StreamResponse(task=task))

                    self.store.update_status(task, TaskState.WORKING, "正在处理...")
                    yield self._sse_event(
                        StreamResponse(
                            status_update=TaskStatusUpdateEvent(
                                task_id=task.id,
                                context_id=task.context_id,
                                status=task.status,
                            )
                        )
                    )

                    await asyncio.sleep(0.5)
                    await asyncio.to_thread(self.process_task, task, self.store)

                    yield self._sse_event(
                        StreamResponse(
                            status_update=TaskStatusUpdateEvent(
                                task_id=task.id,
                                context_id=task.context_id,
                                status=task.status,
                            )
                        )
                    )
                    if task.artifacts:
                        yield self._sse_event(
                            StreamResponse(
                                artifact_update=TaskArtifactUpdateEvent(
                                    task_id=task.id,
                                    context_id=task.context_id,
                                    artifact=task.artifacts[-1],
                                )
                            )
                        )
                elif method == "tasks/subscribe":
                    sub_req = SubscribeToTaskRequest.model_validate(
                        rpc_req.params or {}
                    )
                    task = self.store.get(sub_req.id)
                    if not task:
                        yield self._sse_event(
                            StreamResponse(
                                task=Task(
                                    id=sub_req.id,
                                    status=_task_status(
                                        TaskState.FAILED, "Task not found"
                                    ),
                                )
                            )
                        )
                        return
                    yield self._sse_event(StreamResponse(task=task))
                else:
                    yield self._sse_event(
                        StreamResponse(
                            task=Task(
                                id="",
                                status=_task_status(
                                    TaskState.FAILED,
                                    f"Unsupported streaming method: {method}",
                                ),
                            )
                        )
                    )

            return StreamingResponse(event_stream(), media_type="text/event-stream")

        @app.get("/")
        async def root():
            return {
                "agent": self.agent_card.name,
                "protocol": "A2A",
                "binding": "JSON-RPC 2.0",
                "agent_card": f"{self.agent_card.supported_interfaces[0].url}/.well-known/agent.json",
                "rpc_endpoint": self.agent_card.supported_interfaces[0].url,
            }

        return app

    @staticmethod
    def _sse_event(stream_resp: StreamResponse) -> str:
        return (
            f"data: {json.dumps(stream_resp.model_dump(by_alias=True, exclude_none=True), ensure_ascii=False)}\n\n"
        )

"""SqliteTaskStore 持久化测试：write-through、重启恢复。"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.task_store import SqliteTaskStore
from shared.models import Role, Message, TaskState, text_part


def _user_msg(text, context_id=None, task_id=None):
    return Message(
        message_id=f"m-{text}",
        context_id=context_id,
        task_id=task_id,
        role=Role.USER,
        parts=[text_part(text)],
    )


def test_create_and_reload(tmp_path):
    db = os.path.join(tmp_path, "t1.db")
    store = SqliteTaskStore(db)
    task = store.create(_user_msg("hello"))
    store.update_status(task, TaskState.WORKING, "processing")
    store.add_artifact(task, "response", "world")
    store.update_status(task, TaskState.COMPLETED, "done")
    store.close()

    # 模拟重启：新实例从磁盘加载
    store2 = SqliteTaskStore(db)
    try:
        loaded = store2.get(task.id)
        assert loaded is not None, "task must survive restart"
        assert loaded.status.state == TaskState.COMPLETED
        assert loaded.artifacts[0].parts[0].text == "world"
        assert loaded.history[0].parts[0].text == "hello"
        assert store2.total() == 1
    finally:
        store2.close()
    print("[OK] create -> restart -> reload")


def test_context_seeding_after_restart(tmp_path):
    db = os.path.join(tmp_path, "t2.db")
    store = SqliteTaskStore(db)
    try:
        t1 = store.create(_user_msg("first"))
        store.update_status(t1, TaskState.WORKING)
        store.add_artifact(t1, "response", "answer-1")
        store.update_status(t1, TaskState.COMPLETED)
    finally:
        store.close()

    store2 = SqliteTaskStore(db)
    try:
        t2 = store2.create(_user_msg("second", context_id=t1.context_id))
        texts = [p.text for m in t2.history for p in m.parts if p.text]
        assert "first" in texts and "second" in texts, texts
    finally:
        store2.close()
    print("[OK] context history seeding works across restart")


def test_append_user_message_persists(tmp_path):
    db = os.path.join(tmp_path, "t3.db")
    store = SqliteTaskStore(db)
    task = store.create(_user_msg("q1"))
    store.update_status(task, TaskState.INPUT_REQUIRED, "need more")

    store.append_user_message(task, _user_msg("q2"))
    store.close()

    store2 = SqliteTaskStore(db)
    try:
        loaded = store2.get(task.id)
        user_turns = [m for m in loaded.history if m.role == Role.USER]
        assert len(user_turns) == 2
        assert loaded.status.state == TaskState.WORKING
    finally:
        store2.close()
    print("[OK] append_user_message persists")


def test_list_filter_and_delete(tmp_path):
    db = os.path.join(tmp_path, "t4.db")
    store = SqliteTaskStore(db)
    t1 = store.create(_user_msg("a"))
    store.create(_user_msg("b"))
    store.update_status(t1, TaskState.COMPLETED)
    store.close()

    store2 = SqliteTaskStore(db)
    try:
        done = store2.list(status=TaskState.COMPLETED)
        assert [t.id for t in done] == [t1.id]
        assert len(store2.list()) == 2
        assert store2.get("nonexistent") is None
    finally:
        store2.close()
    print("[OK] list/filter/get-miss after reload")


def main():
    for fn in [test_create_and_reload, test_context_seeding_after_restart,
               test_append_user_message_persists, test_list_filter_and_delete]:
        with tempfile.TemporaryDirectory() as d:
            fn(d)
    print("\nAll task store tests passed!")


if __name__ == "__main__":
    main()

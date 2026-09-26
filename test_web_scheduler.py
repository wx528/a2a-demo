"""web/turns.py 纯调度器测试：三种模式的序列与游标推进，无需起服务。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web.turns import build_sequence, next_turn, skip_fallback, advance, PIPELINE_STEPS

_msg_counter = [0]


def _meeting(mode="pipeline", max_rounds=1, messages=None, turn_state=None,
             pro="socrates", con="hume"):
    from web.main import Meeting, Participant

    parts = [Participant(id="user", name="你", role="user", avatar="👤")]
    return Meeting(
        id="t1", topic="辩题X", mode=mode, max_rounds=max_rounds,
        created_at="12:00:00", participants=parts,
        messages=messages or [], status="active",
        pro_persona=pro, con_persona=con,
        turn_state=turn_state or {},
    )


def _msg(pid, mtype="message", content="用户消息"):
    from web.main import ChatMessage

    _msg_counter[0] += 1
    return ChatMessage(
        id=f"m-{pid}-{mtype}-{_msg_counter[0]}", meeting_id="t1",
        participant_id=pid, participant_name=pid, role="agent",
        content=content, timestamp="12:00:00", type=mtype,
    )


def test_build_sequence_shapes():
    assert build_sequence("pipeline", 1) == [("agent", k) for k in PIPELINE_STEPS]
    rt = build_sequence("roundtable", 2)
    assert rt[0] == ("agent", "moderator") and rt[-1] == ("agent", "moderator")
    assert ("fallback", "research") in rt
    assert len(rt) == 1 + 10 + 2
    db = build_sequence("debate", 2)
    assert db == [("debate", "pro"), ("debate", "con")] * 2 + [("judge", "judge")]


def test_pipeline_walk_and_done():
    m = _meeting(mode="pipeline")
    seen = []
    for _ in range(5):
        spec, st = next_turn(m)
        assert spec is not None
        seen.append(spec["key"])
        m.turn_state = advance(m)
    assert seen == PIPELINE_STEPS
    spec, _ = next_turn(m)
    assert spec is None  # done


def test_pipeline_restart_on_user_message_after_done():
    m = _meeting(mode="pipeline")
    m.turn_state = {"seq_index": 5}
    spec, _ = next_turn(m)
    assert spec is None  # 耗尽且无新用户消息 -> done
    m.messages.append(_msg("user", content="请改聊 Docker"))
    spec, st = next_turn(m)
    assert spec == {"kind": "agent", "key": "research", "index": 0}
    assert st["topic_override"] == "请改聊 Docker"
    assert st["seq_index"] == 0


def test_debate_sequence_and_done():
    m = _meeting(mode="debate", max_rounds=2)
    order = []
    for _ in range(5):
        spec, st = next_turn(m)
        order.append((spec["kind"], spec["key"]))
        m.turn_state = advance(m)
    assert order == [("debate", "pro"), ("debate", "con")] * 2 + [("judge", "judge")]
    spec, _ = next_turn(m)
    assert spec is None


def test_skip_fallback_when_someone_spoke():
    m = _meeting(mode="roundtable", max_rounds=1)
    seq = build_sequence("roundtable", 1)
    fb_index = seq.index(("fallback", "research"))
    assert skip_fallback(seq, fb_index, m) is False  # 无人发言：执行保底步
    m.messages.append(_msg("research"))
    assert skip_fallback(seq, fb_index, m) is True


def test_advance_keeps_topic_override_for_whole_flow():
    m = _meeting(mode="pipeline", turn_state={"seq_index": 0, "topic_override": "新主题"})
    st = advance(m)
    assert st["seq_index"] == 1 and st["topic_override"] == "新主题"

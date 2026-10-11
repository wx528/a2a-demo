"""Committee vote 纯函数测试：解析 / 聚合 / split / 洗牌确定性。"""

from web.v2 import vote
from web.v2.models import Ballot, V2Task


def _task(task_id="t1"):
    return V2Task(id=task_id, goal_text="判断团队是否需要引入 A2A", created_at=1.0, updated_at=1.0)


def test_parse_ballot_plain_json():
    b = vote.parse_ballot('{"verdict": "approve", "confidence": 4, "reason": "与约束一致"}')
    assert b == Ballot(verdict="approve", confidence=4, reason="与约束一致")


def test_parse_ballot_with_fence_and_noise():
    text = '好的，以下是我的票：\n```json\n{"verdict": "reject", "confidence": 2, "reason": "权限面未讨论"}\n```\n以上。'
    assert vote.parse_ballot(text).verdict == "reject"


def test_parse_ballot_invalid_returns_none():
    assert vote.parse_ballot("这不是 JSON") is None
    assert vote.parse_ballot('{"verdict": "maybe"}') is None  # 非法 verdict


def test_aggregate_majority_and_quorum():
    task = _task()
    v = vote.aggregate(task, {
        "ada": Ballot(verdict="approve", confidence=4, reason="r1"),
        "turing": Ballot(verdict="adjust", confidence=3, reason="r2"),
        "linus": Ballot(verdict="reject", confidence=2, reason="r3"),
        "sage": Ballot(verdict="approve", confidence=4, reason="r4"),
    })
    assert v.tally == {"approve": 2, "adjust": 1, "reject": 1}
    assert v.split == "majority" and v.quorum == 4


def test_aggregate_unanimous_and_split():
    unanimous = vote.aggregate(_task(), {s: Ballot(verdict="approve", confidence=5, reason="r") for s in ("ada", "turing", "linus", "sage")})
    assert unanimous.split == "unanimous"
    sp = vote.aggregate(_task(), {
        "ada": Ballot(verdict="approve", confidence=5, reason="r"),
        "turing": Ballot(verdict="adjust", confidence=5, reason="r"),
        "linus": Ballot(verdict="reject", confidence=5, reason="r"),
        "sage": Ballot(verdict="abstain", confidence=0, reason=""),
    })
    assert sp.split == "split" and sp.quorum == 3


def test_aggregate_all_abstain_means_zero_quorum():
    v = vote.aggregate(_task(), {s: Ballot(verdict="abstain") for s in ("ada", "turing", "linus", "sage")})
    assert v.quorum == 0 and v.split == "split"


def test_ballot_order_shuffled_deterministically_by_task_id():
    seats = {s: Ballot(verdict="approve", confidence=i + 1, reason=s) for i, s in enumerate(("ada", "turing", "linus", "sage"))}
    a = vote.aggregate(_task("xyz"), dict(seats))
    b = vote.aggregate(_task("xyz"), dict(seats))
    c = vote.aggregate(_task("other"), dict(seats))
    assert [x.reason for x in a.ballots] == [x.reason for x in b.ballots]
    assert [x.reason for x in a.ballots] != [x.reason for x in c.ballots]  # 不同任务不同序（弱断言：seed 不同）


def test_render_summary_contains_tally_and_anonymous_labels():
    v = vote.aggregate(_task("xyz"), {
        "ada": Ballot(verdict="approve", confidence=4, reason="与约束一致"),
        "turing": Ballot(verdict="abstain"),
        "linus": Ballot(verdict="reject", confidence=2, reason="权限面"),
        "sage": Ballot(verdict="approve", confidence=3, reason="无分歧"),
    })
    text = vote.render_summary(v)
    assert "委员会投票" in text and "赞成 2" in text
    assert "评审 1" in text and "ada" not in text and "turing" not in text  # 匿名


def test_build_vote_prompt_contains_rubric_and_constraints():
    from web.v2.models import Constraint

    task = _task()
    task.constraints = [Constraint(text="首阶段私有化", confirmed=True)]
    prompt = vote.build_vote_prompt(task)
    assert vote.REVIEW_VOTE_QUESTION in prompt
    assert "首阶段私有化" in prompt and "可行性" in prompt

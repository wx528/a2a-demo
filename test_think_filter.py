"""ThinkFilter 回归：任意数量 think 块（含跨增量截断标签）都不泄漏到可见输出。"""

from web.v2.util import ThinkFilter


def _collect(chunks: list[str]) -> str:
    f = ThinkFilter()
    visible = "".join(f.feed(c) for c in chunks)
    return visible + f.final_text()


def test_single_block_across_deltas():
    visible = _collect([
        "[PHASE] 整理思路并起草",
        "<think>\n推理第一段",
        "继续推理 still hidden",
        "done</think>\n最终发言",
        "后续增量",
    ])
    assert "推理" not in visible and "hidden" not in visible
    assert "think" not in visible
    assert "最终发言" in visible and "后续增量" in visible


def test_multiple_blocks_all_suppressed():
    visible = _collect(["<think>草稿</think>可见一<think>自审</think>可见二"])
    assert visible == "可见一可见二"


def test_split_tag_not_leaked():
    visible = _collect(["前置<thi", "nk>隐藏内容</th", "ink>可见"])
    assert "<thi" not in visible and "隐藏内容" not in visible
    assert visible.startswith("前置") and visible.endswith("可见")


def test_unclosed_think_final_drops_pending():
    visible = _collect(["开头<think>\n只有推理没有闭合"])
    assert "推理" not in visible and "<think>" not in visible
    assert "开头" in visible


def test_no_think_at_all_passes_through():
    visible = _collect(["直接正文", "第二段"])
    assert visible == "直接正文第二段"

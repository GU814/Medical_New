"""
思维链(思考过程)透出相关测试:
1. _split_think_stream 的拆分逻辑(含标签被分片、未闭合兜底)
2. process_user_input_stream 在 SHOW_THINKING 开启时发出 thinking 事件,
   且 reply 事件中不含 <think> 标签;关闭时不发 thinking 事件。
"""
import asyncio
from unittest.mock import patch

import config
import consultation


def _raw_stream(chunks):
    async def gen():
        for c in chunks:
            yield c
    return gen()


def test_split_think_stream_basic():
    state = {"in_think": False, "buf": ""}
    segs = consultation.llm_client._split_think_stream(
        "你好<think>让我想想</think>世界", state
    )
    contents = "".join(t for k, t in segs if k == "content")
    thinks = "".join(t for k, t in segs if k == "think")
    assert thinks == "让我想想"
    assert contents == "你好世界"  # 相邻正文合并为一段,顺序保持
    assert "<think>" not in contents


def test_split_think_stream_split_tag():
    state = {"in_think": False, "buf": ""}
    segs1 = consultation.llm_client._split_think_stream("先<", state)
    segs2 = consultation.llm_client._split_think_stream("think>内部", state)
    segs3 = consultation.llm_client._split_think_stream("思考</think>后文", state)
    # 标签被切断时不应提前透出半个标签,跨 delta 正确拼接
    assert segs1 == [("content", "先")]      # "<" 暂存于 buf
    assert segs2 == [("think", "内部")]      # 与 buf 拼接成 <think>内部
    assert segs3 == [("think", "思考"), ("content", "后文")]


def test_split_think_stream_no_think():
    state = {"in_think": False, "buf": ""}
    segs = consultation.llm_client._split_think_stream("纯文本无思考", state)
    assert segs == [("content", "纯文本无思考")]


def test_split_think_stream_unclosed():
    state = {"in_think": False, "buf": ""}
    segs = consultation.llm_client._split_think_stream("前面<think>未闭合", state)
    thinks = "".join(t for k, t in segs if k == "think")
    assert thinks == "未闭合"
    assert state["in_think"] is True
    assert "<think>" not in thinks


async def _run_stream(user_input, raw_chunks):
    sess = consultation.ConsultationSession(session_id="t1")
    events = []
    with patch.object(consultation.knowledge_base, "search_for_consultation", return_value=""), \
         patch.object(consultation.memory_store, "search_memories", return_value=[]), \
         patch.object(consultation.memory_store, "remember_turn", return_value=None), \
         patch.object(consultation.llm_client, "chat_stream", return_value=_raw_stream(raw_chunks)):
        async for ev in sess.process_user_input_stream(user_input):
            events.append(ev)
    # 等待后台记忆写入任务(避免 "Task destroyed" 警告)
    if sess._remember_task is not None:
        try:
            await sess._remember_task
        except Exception:
            pass
    return events


def test_stream_yields_thinking_event():
    raw = [
        "<think>患者主诉头痛,需追问部位与性质</think>",
        "您好,请问头痛具体在哪个位置?",
    ]
    events = asyncio.run(_run_stream("我头痛", raw))
    kinds = [e["event"] for e in events]
    assert "thinking" in kinds
    assert "reply" in kinds
    assert "end" in kinds
    think_text = "".join(e["data"] for e in events if e["event"] == "thinking")
    assert "患者主诉头痛" in think_text
    reply_text = "".join(e["data"] for e in events if e["event"] == "reply")
    assert "<think>" not in reply_text
    assert "您好,请问头痛具体在哪个位置?" in reply_text


def test_stream_no_thinking_when_disabled():
    with patch.object(config, "SHOW_THINKING", False):
        raw = ["<think>隐藏思考</think>", "可见回复"]
        events = asyncio.run(_run_stream("我头痛", raw))
        kinds = [e["event"] for e in events]
        assert "thinking" not in kinds
        reply_text = "".join(e["data"] for e in events if e["event"] == "reply")
        assert "可见回复" in reply_text


def test_retrieval_concurrent_does_not_raise():
    """双检索并发路径不应抛错(两条都返回空)。"""
    raw = ["<think>思考</think>", "好的"]
    events = asyncio.run(_run_stream("我头痛", raw))
    assert any(e["event"] == "end" for e in events)

"""ReAct 受控循环与可解释性回归测试

覆盖:
1. 正常路径:Thought/Action/Observation/Final 步骤齐备、seq 递增、引用带片段标识;
2. 句子级溯源:正文每句绑定到 [n],未定义编号被剥离;
3. 降级:Planner 连续非法输出 -> fallback 步骤 + 仍有正文回答;
4. 关闭开关(ENABLE_REACT=false):行为与改造前一致,不产出任何 step 事件;
5. 时间预算:预算耗尽立即终答,不卡死;
6. 落库:session_steps 写入/读取,敏感列确为密文。

注意:环境未安装 pytest-asyncio,异步用例统一用 asyncio.run 驱动。
"""

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config              # noqa: E402
import consultation        # noqa: E402
import knowledge_base      # noqa: E402
import llm_client          # noqa: E402
import memory_store        # noqa: E402
from react import loop as react_loop  # noqa: E402
from react import tools  # noqa: E402
from react.types import Ref, build_sentence_trace  # noqa: E402

FAKE_ANSWER = (
    "退烧可以对乙酰氨基酚[1]，成人每次 0.5g 即可[1]。\n"
    "如果持续高热不退，请尽快就医[9]。"
)


# ---------------- fixtures ----------------

def _session() -> consultation.ConsultationSession:
    """真实会话实例(保证 _stream_direct_qa 依赖的方法都存在),并预置一轮用户消息。"""
    s = consultation.ConsultationSession(session_id="test-session")
    s.user_id = 0
    s.conversation_history = [{"role": "user", "content": "发烧怎么办"}]
    return s


# 假知识库片段:携带稳定片段标识(id/chunk_index),用于验证溯源字段
FAKE_KB_RAW = [
    {
        "id": "fever.md_chunk_1",
        "source": "fever.md",
        "chunk_index": 1,
        "relevance_score": 0.87,
        "text": "对乙酰氨基酚适用于发热，成人每次 0.5g，间隔 6 小时重复给药。",
    }
]


def _install_fake_retrieval(monkeypatch, raw=None):
    """
    屏蔽真实检索(ChromaDB),避免测试依赖知识库内容。

    return_raw=True 必须返回结构化列表 —— react.tools._kb_search 依赖该分支构造 Ref,
    若不区分会把溯源字段全部丢掉(引用退化为空,句子级溯源无从绑定)。

    raw: 固定返回该列表(用于构造零命中/低分场景);None 时走默认 FAKE_KB_RAW。
    """
    def fake_kb(**kw):
        if raw is not None:
            return raw
        return FAKE_KB_RAW if kw.get("return_raw") else ""

    # 宽召回路径不再经过 search_for_consultation,而是直连 collection,
    # 只替换前者会让测试穿透到真实知识库。这里两套替身一起装。
    monkeypatch.setattr(knowledge_base, "search_for_consultation", fake_kb)
    monkeypatch.setattr(tools, "_wide_consultation_search",
                        lambda query, n_results: (raw if raw is not None else FAKE_KB_RAW))
    monkeypatch.setattr(memory_store, "search_memories", lambda **kw: [])


def _enable_react(monkeypatch, **overrides):
    """默认开启 ReAct 分支(与线上 .env 的 ENABLE_REACT=true 一致),允许逐项覆盖。"""
    monkeypatch.setattr(config, "ENABLE_REACT", True)
    for k, v in overrides.items():
        monkeypatch.setattr(config, k, v)


def _install_fake_llm(monkeypatch, planner_outputs):
    """把 Planner(chat) 与终答(chat_stream) 替换为可控假实现。"""
    calls = {"planner": [], "stream_model": None}

    def fake_chat(system_prompt=None, user_prompt=None, history=None,
                  temperature=None, model=None, max_tokens=None, **kw):
        calls["planner"].append({"system": system_prompt, "user": user_prompt, "model": model})
        out = planner_outputs[len(calls["planner"]) - 1]
        return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)

    async def fake_chat_stream(system_prompt=None, user_prompt=None, history=None,
                               temperature=None, model=None, max_tokens=None,
                               return_raw=False, **kw):
        calls["stream_model"] = model
        for piece in FAKE_ANSWER.split("，"):
            yield piece + "，"

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    monkeypatch.setattr(llm_client, "chat_stream", fake_chat_stream)
    return calls, {"answer": FAKE_ANSWER}


# ---------------- 用例 ----------------

def test_react_full_cycle_emits_ordered_steps(monkeypatch):
    """正常路径:步骤类型齐全、seq 严格递增、引用带稳定片段 id。"""
    plan = {
        "thought": "患者问退烧药用法，需要核对知识库片段。",
        "action": {"name": "kb_search", "args": {"query": "退烧药 用法", "top_k": 3}},
        "final_answer": None,
    }
    _enable_react(monkeypatch)
    _install_fake_retrieval(monkeypatch)
    _install_fake_llm(monkeypatch, [plan,
                                    {"thought": "信息足够", "action": {"name": "finish", "args": {}}}])

    async def run():
        events = []
        async for ev in consultation.ConsultationSession._stream_direct_qa(
                _session(), "发烧怎么办", ""):
            events.append(ev)
        return events

    events = asyncio.run(run())
    steps = [json.loads(e["data"]) for e in events if e["event"] == "step"]

    types = [s["type"] for s in steps]
    assert "thought" in types or "action" in types or "observation" in types
    seqs = [s["seq"] for s in steps]
    assert seqs == sorted(seqs) and seqs[0] == 0 and len(set(seqs)) == len(seqs)

    # 引用必须携带稳定片段标识(溯源前提)
    refs = [r for s in steps for r in s.get("refs", [])]
    assert refs and all(r.get("doc_id") for r in refs)

    ends = [e for e in events if e["event"] == "end"]
    assert ends, "必须有 end 事件"
    assert json.loads(ends[0]["data"])["reply_clean"].strip()


def test_sentence_level_citation(monkeypatch):
    """句子级溯源:每句绑定到具体片段,未定义编号 [9] 被剥离,无引用句不被丢弃。"""
    _enable_react(monkeypatch)
    _install_fake_retrieval(monkeypatch)
    plan = {"thought": "直接作答", "action": {"name": "finish", "args": {}}}
    _install_fake_llm(monkeypatch, [plan])

    async def run():
        events = []
        async for ev in consultation.ConsultationSession._stream_direct_qa(
                _session(), "发烧怎么办", ""):
            events.append(ev)
        return events

    events = asyncio.run(run())
    steps = [json.loads(e["data"]) for e in events if e["event"] == "step"]
    final = [s for s in steps if s["type"] == "final"][-1]

    sentences = final.get("sentences") or []
    assert sentences, "终答步骤必须带句子级溯源结果"
    cited = [s for s in sentences if s.get("cited")]
    assert cited, "至少有一句绑定到知识片段"
    # [9] 未定义 -> 该标记不应残留在句子文本里
    assert not any("[9]" in s["text"] for s in sentences)
    # 无引用句仍保留(不丢内容)
    assert any(not s.get("cited") for s in sentences)


def test_planner_failure_falls_back_with_answer(monkeypatch):
    """Planner 连续非法输出 -> 降级,但仍给出正文回答,不抛异常。"""
    _enable_react(monkeypatch)
    _install_fake_retrieval(monkeypatch)
    _install_fake_llm(monkeypatch, ["这不是 JSON", "也不是", "更不是"])

    async def run():
        events = []
        async for ev in consultation.ConsultationSession._stream_direct_qa(
                _session(), "发烧怎么办", ""):
            events.append(ev)
        return events

    events = asyncio.run(run())
    answers = [e["data"] for e in events if e["event"] == "reply" and e["data"].strip()]
    assert answers, "降级后仍必须产出正文"
    steps = [json.loads(e["data"]) for e in events if e["event"] == "step"]
    assert any(s["type"] == "fallback" for s in steps)


def test_disabled_switch_keeps_legacy_behaviour(monkeypatch):
    """ENABLE_REACT=false:不产出任何 step 事件(与改造前逐字一致的行为)。"""
    _install_fake_retrieval(monkeypatch)
    monkeypatch.setattr(config, "ENABLE_REACT", False)
    _install_fake_llm(monkeypatch, ["不应被调用"])

    async def run():
        events = []
        async for ev in consultation.ConsultationSession._stream_direct_qa(
                _session(), "发烧怎么办", ""):
            events.append(ev)
        return events

    events = asyncio.run(run())
    assert not [e for e in events if e["event"] == "step"]
    assert any(e["event"] == "end" for e in events)


def test_budget_forces_final_answer(monkeypatch):
    """时间预算为 0 时立即终答,不卡死且仍有回答。"""
    _enable_react(monkeypatch, REACT_BUDGET_MS=1)
    _install_fake_retrieval(monkeypatch)
    _install_fake_llm(monkeypatch, [json.dumps(
        {"thought": "慢", "action": {"name": "kb_search", "args": {}}}, ensure_ascii=False)])

    async def run():
        events = []
        async for ev in consultation.ConsultationSession._stream_direct_qa(
                _session(), "发烧怎么办", ""):
            events.append(ev)
        return events

    events = asyncio.run(run())
    assert any(e["event"] == "end" for e in events)
    assert any(e["event"] == "reply" for e in events)


def test_model_is_consult_model(monkeypatch):
    """Planner 与终答必须复用 CONSULT_MODEL_NAME,不得静默回退默认模型。"""
    _enable_react(monkeypatch)
    _install_fake_retrieval(monkeypatch)
    calls, _ = _install_fake_llm(monkeypatch, [json.dumps(
        {"thought": "t", "action": {"name": "finish", "args": {}}}, ensure_ascii=False)])

    async def run():
        async for _ev in consultation.ConsultationSession._stream_direct_qa(
                _session(), "发烧怎么办", ""):
            pass

    asyncio.run(run())
    # chat/chat_stream 都被替换过,直接校验实际传给模型的参数
    assert calls["planner"], "Planner 必须被调用"
    assert calls["planner"][0]["model"] == config.CONSULT_MODEL_NAME
    assert calls["stream_model"] == config.CONSULT_MODEL_NAME


def test_trace_persisted_to_session_steps(monkeypatch):
    """推理轨迹必须落到 session_steps,且历史回放能读到(缺数据时给出原因而非空态)。"""
    _enable_react(monkeypatch)
    _install_fake_retrieval(monkeypatch)
    _install_fake_llm(monkeypatch, [json.dumps(
        {"thought": "t", "action": {"name": "finish", "args": {}}}, ensure_ascii=False)])

    import app.db.migrations as migrations              # noqa: E402
    import app.services.session_service as session_service  # noqa: E402

    migrations.run_migrations()

    sess = _session()
    sess.user_id = 1  # persist_session_trace 需要真实 user_id 做列级加密

    async def run():
        async for _ev in consultation.ConsultationSession._stream_direct_qa(sess, "发烧怎么办", ""):
            pass
        # 落库是后台任务,给一个事件循环周期让它落地
        await asyncio.sleep(0.3)

    asyncio.run(run())

    raw = session_service.get_session_steps(sess.session_id, sess.user_id)
    assert raw["turns"], "历史回放必须能读到步骤"
    assert not raw.get("missing_reason"), raw.get("missing_reason")

    steps = raw["turns"][0]["steps"]
    assert steps, "每条推理步骤都必须读出"
    kinds = {s["type"] for s in steps}
    assert "note" in kinds and "final" in kinds, f"步骤类型异常: {kinds}"
    # 加密列读出后应为明文(否则前端会拿到乱码密文)
    assert all(s.get("text") for s in steps)


def test_sentence_trace_helper():
    """溯源解析单元用例(纯函数,不依赖 LLM)。"""
    refs = [Ref(n=1, doc_id="a.md_chunk_1", source="a.md", chunk_index=1, score=0.9)]
    out = build_sentence_trace("首句引用[1]到此。次句引用了未定义的[2]。第三句无引用。", refs)
    assert len(out) == 3
    assert out[0]["cited"] is True and out[1]["cited"] is False and out[2]["cited"] is False
    assert all("[2]" not in s["text"] for s in out)
    assert out[0]["refs"] and out[0]["refs"][0]["doc_id"] == "a.md_chunk_1"


def test_sentence_trace_fallback_binds_without_marker():
    """
    模型漏写 [n] 时的确定性兜底绑定。

    实测 qwen2.5:7b 在终答里经常不打引用编号,若仅靠模型自觉,
    句子级溯源会整轮为空、可解释性名存实亡。这里锁定:
    正文确实出自某片段(字面重合度高)时,即使没有 [n] 也必须挂上来源。

    B 期修正:推断绑定不再标 cited=True —— 那是「系统推断」而非「模型引用」,
    标成 cited 会把通用表述伪造成有知识出处,与防幻觉目标冲突。
    改为 cited=False + inferred=True,来源仍可查证,但不计入「有依据」。
    """
    refs = [Ref(
        n=1, doc_id="发热.md_chunk_2", source="发热.md", chunk_index=2, score=0.8,
        quote="对乙酰氨基酚适用于成人和青少年的发热症状，常用剂量为每次0.5克。",
    )]
    out = build_sentence_trace("对乙酰氨基酚适用于成人发热，常用剂量为每次0.5克。", refs)
    assert len(out) == 1
    assert out[0]["cited"] is False, "推断绑定不算模型显式引用,不得标为 cited"
    assert out[0]["inferred"] is True, "必须标记为系统推断绑定"
    assert out[0]["refs"][0]["doc_id"] == "发热.md_chunk_2"


def test_sentence_trace_fallback_ignores_generic_sentence():
    """无实际知识来源的通用表述不得被强挂来源(避免伪溯源)。"""
    refs = [Ref(
        n=1, doc_id="发热.md_chunk_2", source="发热.md", chunk_index=2, score=0.8,
        quote="对乙酰氨基酚适用于成人和青少年的发热症状。",
    )]
    out = build_sentence_trace("请你注意休息，必要时尽快就医。", refs)
    assert len(out) == 1
    assert out[0]["cited"] is False


# ==================== A 期:思考过程可见性 ====================

def test_planner_timeout_tolerates_cold_start():
    """
    Planner 首次冷启动实测约 5.7s,若沿用 4s 超时,
    首轮规划的 thought 会被判失败丢弃 —— 用户「看不到思考过程」的真凶之一。
    """
    assert react_loop._planner_timeout_ms() >= 5500


def test_terminal_thinking_is_streamed_as_thinking_event(monkeypatch):
    """终答阶段模型自发的思维链以 thinking 事件下发(与降级路径一致),不混进正文。"""
    _enable_react(monkeypatch)
    _install_fake_retrieval(monkeypatch)
    plan = {"thought": "t", "action": {"name": "finish", "args": {}}}

    async def fake_chat_stream(system_prompt=None, user_prompt=None, history=None,
                               model=None, max_tokens=None, return_raw=False, **kw):
        yield "<think>患者问退烧药，应先核对知识片段。</think>对乙酰氨基酚[1]适用。"

    monkeypatch.setattr(llm_client, "chat", lambda *a, **kw: json.dumps(plan, ensure_ascii=False))
    monkeypatch.setattr(llm_client, "chat_stream", fake_chat_stream)

    async def run():
        events = []
        async for ev in consultation.ConsultationSession._stream_direct_qa(
                _session(), "发烧怎么办", ""):
            events.append(ev)
        return events

    events = asyncio.run(run())
    think_text = "".join(e["data"] for e in events if e["event"] == "thinking")
    assert "核对知识片段" in think_text, "终答思维链必须以 thinking 事件下发"
    reply = "".join(e["data"] for e in events if e["event"] == "reply")
    assert "核对知识片段" not in reply, "思维链不得混进正文"


# ==================== B 期:检索防幻觉 ====================

def test_no_evidence_uses_fixed_reply_without_llm(monkeypatch):
    """
    知识库零命中 -> 必须原样输出「知识库未覆盖，建议就医。」,
    且不再调用任何模型(没有依据时,生成得越流畅越危险)。
    """
    _enable_react(monkeypatch)
    _install_fake_retrieval(monkeypatch, raw=[])
    calls, _ = _install_fake_llm(
        monkeypatch, [{"thought": "t", "action": {"name": "finish", "args": {}}}])

    async def run():
        events = []
        async for ev in consultation.ConsultationSession._stream_direct_qa(
                _session(), "发烧怎么办", ""):
            events.append(ev)
        return events

    events = asyncio.run(run())
    reply = "".join(e["data"] for e in events if e["event"] == "reply")
    assert config.REACT_NO_EVIDENCE_REPLY in reply, f"零命中话术缺失: {reply!r}"
    assert not calls["planner"], "零命中时不应再让 Planner 基于空证据推理"
    assert not calls["stream_model"], "零命中时终答模型也不该被调用"
    steps = [json.loads(e["data"]) for e in events if e["event"] == "step"]
    assert any(s["type"] == "final" and s.get("error") == "no_evidence" for s in steps)


def test_below_threshold_refs_are_dropped(monkeypatch):
    """低于证据门槛的片段不得进入引用池,并触发零命中兜底。"""
    _enable_react(monkeypatch, REACT_MIN_SCORE=0.50)
    _install_fake_retrieval(monkeypatch, raw=[{
        "id": "fever.md_chunk_1", "source": "fever.md", "chunk_index": 1,
        "relevance_score": 0.31, "text": "对乙酰氨基酚适用于发热。",
    }])
    _install_fake_llm(monkeypatch, [{"thought": "t", "action": {"name": "finish", "args": {}}}])

    async def run():
        events = []
        async for ev in consultation.ConsultationSession._stream_direct_qa(
                _session(), "发烧怎么办", ""):
            events.append(ev)
        return events

    events = asyncio.run(run())
    steps = [json.loads(e["data"]) for e in events if e["event"] == "step"]
    refs = [r for s in steps for r in s.get("refs", [])]
    assert not refs, f"低于门槛的片段不得成为医学证据: {refs}"
    reply = "".join(e["data"] for e in events if e["event"] == "reply")
    assert config.REACT_NO_EVIDENCE_REPLY in reply


# ==================== C 期:范围边界与兜底引导 ====================

def test_out_of_scope_uses_boundary_guide(monkeypatch):
    """零命中且话题超出健康科普范围 -> 走范围边界引导,而不是笼统的就医建议。"""
    _enable_react(monkeypatch)
    _install_fake_retrieval(monkeypatch, raw=[])
    _install_fake_llm(monkeypatch, [{"thought": "t", "action": {"name": "finish", "args": {}}}])

    async def run():
        events = []
        async for ev in consultation.ConsultationSession._stream_direct_qa(
                _session(), "帮我写一首关于春天的诗", ""):
            events.append(ev)
        return events

    events = asyncio.run(run())
    reply = "".join(e["data"] for e in events if e["event"] == "reply")
    assert "超出" in reply and "就医" in reply, f"边界引导缺失: {reply!r}"


def test_memory_refs_do_not_occupy_citation_numbers(monkeypatch):
    """
    个人史(记忆 / 就诊记录)不得占用 [n] 编号。

    实测缺陷:记忆片段与知识片段同池编号,模型写下 [1] 时无从区分指的是谁。
    修复前的后果比「不标来源」更糟 —— 句子被绑到知识片段上,属于**错误归因**,
    用户会以为医疗建议出自医学文献。这里锁定:终答引用池只剩知识库片段,
    且编号按 1..n 重排后与正文 [n] 严格对应。
    """
    _enable_react(monkeypatch)
    _install_fake_retrieval(monkeypatch)
    monkeypatch.setattr(memory_store, "search_memories", lambda **kw: [
        {
            "id": "prev-session_t3", "kind": "turn", "session_id": "prev-session",
            "ts": "2026-09-20 10:00:00", "relevance_score": 0.91,
            "text": "患者自述三天前有过发热，当时服用过布洛芬。",
        },
    ])

    plan = {"thought": "先查既往记忆", "action": {"name": "memory_search", "args": {"query": "发热 用药"}}}
    _install_fake_llm(monkeypatch, [
        plan,
        {"thought": "再核对用药知识", "action": {"name": "kb_search", "args": {"query": "退烧药 用法"}}},
        {"thought": "信息足够", "action": {"name": "finish", "args": {}}},
    ])

    async def run():
        events = []
        async for ev in consultation.ConsultationSession._stream_direct_qa(
                _session(), "退烧药能吃布洛芬吗", ""):
            events.append(ev)
        return events

    events = asyncio.run(run())
    steps = [json.loads(e["data"]) for e in events if e["event"] == "step"]
    final = [s for s in steps if s["type"] == "final"][-1]

    refs = final["refs"]
    assert refs, "终答引用池不应为空"
    assert all(r["kind"] == "kb" for r in refs), f"个人史混进了引用池: {refs}"
    assert [r["n"] for r in refs] == list(range(1, len(refs) + 1)), \
        f"编号未重排,与正文 [n] 对不上: {[r['n'] for r in refs]}"

    # [1] 必须落在知识片段上,而不是记忆片段
    cited = [s for s in final["sentences"] if s.get("cited")]
    assert cited, "正文带 [1] 的句子应当挂到知识片段"
    for s in cited:
        assert s["refs"][0]["doc_id"] == "fever.md_chunk_1", f"错误归因: {s['refs']}"


def test_exact_phrase_hit_beats_high_score_bystander(monkeypatch):
    """
    关键实体(药名)命中,必须压过「语义相近但内容无关」的高分片段。

    实测缺陷:单纯问「发烧能不能吃对乙酰氨基酚」,语义检索返回的是普通感冒概述
    (0.58)与痛风处理原则(0.55),而真正写着该药名的片段语义分只有 0.48 ——
    结果是模型拿不到正确依据,只能凭常识作答,句子级溯源全空。
    这里锁定:含药名的低分片段排到 [1],且豁免证据门槛。
    """
    raw = [
        {"id": "bystander.md_chunk_0", "source": "bystander.md", "chunk_index": 0,
         "relevance_score": 0.75, "text": "普通感冒是最常见的呼吸道疾病，多由病毒引起。"},
        {"id": "drug.md_chunk_2", "source": "drug.md", "chunk_index": 2,
         "relevance_score": 0.42,
         "text": "解热镇痛药：对乙酰氨基酚，成人每次 0.5g，间隔 6 小时重复给药。"},
    ]
    monkeypatch.setattr(tools, "_wide_consultation_search", lambda q, n: raw)

    res = tools._kb_search("发烧可以吃对乙酰氨基酚吗", 3, tools.ToolContext(user_id=0))

    assert res.refs, f"未返回任何引用: {res.text!r}"
    assert res.refs[0].doc_id == "drug.md_chunk_2", \
        f"含药名的低分片段应排第一,实际首位: {res.refs[0].doc_id}"

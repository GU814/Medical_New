# -*- coding: utf-8 -*-
"""
问诊上下文保持回归测试（「说了不用」+「反复追问」两个现象的修复锁定）

背景（2026-09-28）：
    线上两个典型现象的根因都落在「用户信息进不了模型视野」这条链路上：
      A. 提供的背景资料不被使用 —— 信息没被提取进结构化字段,3 轮后又滑出
         conversation_history[-6:] 窗口,从此永久消失；
      B. 反复问同样的问题 —— 原 _update_patient_info 每轮整体**覆盖**自由文本字段,
         7b 模型只写本轮内容时,前几轮采集的细节被更短的新值顶掉,
         上下文里的「已收集-现病史」随之缩水,模型判定信息不足于是重问。

    本文件锁死三条修复：
      1) 自由文本字段累积合并,且重复内容不堆砌；
      2) 模型漏输出 JSON 时(empty info),确定性兜底提取仍要执行；
      3) 兜底提取保守:年龄只抽患者本人(排除亲属表述),性别只抽明确表述。

运行：
    python tests/test_context_retention.py        # 独立运行,打印明细
    pytest tests/test_context_retention.py -q     # 计入回归
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import consultation  # noqa: E402
from consultation import ConsultationSession  # noqa: E402


# ==================== 1. 自由文本字段累积合并 ====================

def test_merge_appends_new_details():
    """第二轮的细节必须追加,而不是把第一轮整段顶掉(现象 B 的直接根因)。"""
    s = ConsultationSession(session_id="t-merge")
    s._update_patient_info({"present_illness": "头痛三天，伴恶心"}, user_text="")
    s._update_patient_info({"present_illness": "疼痛为搏动性"}, user_text="")
    assert "头痛三天" in s.present_illness, f"第一轮细节丢失: {s.present_illness!r}"
    assert "搏动性" in s.present_illness, f"第二轮未写入: {s.present_illness!r}"


def test_merge_does_not_pile_up_repeated_content():
    """模型复述同样的内容时不应越攒越长。"""
    s = ConsultationSession(session_id="t-dup")
    s._update_patient_info({"present_illness": "疼痛为搏动性"}, user_text="")
    before = s.present_illness
    s._update_patient_info({"present_illness": "疼痛为搏动性"}, user_text="")
    assert s.present_illness == before, (
        f"重复追加: {len(before)} -> {len(s.present_illness)}")


def test_merge_takes_fuller_value_when_old_is_substring():
    """旧值是新值子串时取更完整的那条(且不擅自补标点污染模型原文)。"""
    s = ConsultationSession(session_id="t-sub")
    s._update_patient_info({"past_history": "高血压"}, user_text="")
    s._update_patient_info({"past_history": "高血压病史五年，服用氨氯地平"}, user_text="")
    assert s.past_history == "高血压病史五年，服用氨氯地平", f"实际={s.past_history!r}"


def test_merge_can_be_disabled(monkeypatch):
    """保留回滚能力:关闭开关应退回旧的覆盖行为。"""
    monkeypatch.setattr(config, "CONSULT_FIELDS_MERGE", False)
    s = ConsultationSession(session_id="t-off")
    s._update_patient_info({"present_illness": "头痛三天"}, user_text="")
    s._update_patient_info({"present_illness": "刺痛"}, user_text="")
    assert s.present_illness == "刺痛", f"实际={s.present_illness!r}"


# ==================== 2. 模型漏输出 JSON 的兜底提取 ====================

def test_fallback_runs_even_when_model_returns_empty_json():
    """
    模型整轮没给 JSON 时,年龄/性别仍要能被确定性补抽。

    这是修复的关键点:旧实现在调用点写了 `if extracted_info:` 才更新,
    提取失败那一轮的用户陈述因此永久丢失(现象 A)。
    """
    s = ConsultationSession(session_id="t-fb")
    s._update_patient_info({}, user_text="我今年35岁，男，最近总是头晕")
    assert s.patient_age == 35, f"年龄未补抽: {s.patient_age}"
    assert s.patient_gender == "男", f"性别未补抽: {s.patient_gender!r}"


def test_fallback_never_overwrites_model_value():
    """模型已给出值时,兜底提取不得覆盖(避免把 28 错改成消息里的无关数字)。"""
    s = ConsultationSession(session_id="t-fb2")
    s._update_patient_info({"patient_age": "28"}, user_text="我今年35岁")
    assert s.patient_age == 28, f"覆盖了模型值: {s.patient_age}"


def test_fallback_skips_age_of_relative():
    """「我女儿5岁」不该被抽成患者年龄(抽错会直接写进报告)。"""
    s = ConsultationSession(session_id="t-fb3")
    s._update_patient_info({}, user_text="我女儿5岁，最近发烧")
    assert s.patient_age == 0, f"误抽亲属年龄: {s.patient_age}"


def test_fallback_extracts_explicit_gender():
    s = ConsultationSession(session_id="t-fb4")
    s._update_patient_info({}, user_text="性别：女")
    assert s.patient_gender == "女", f"实际={s.patient_gender!r}"


def test_fallback_can_be_disabled(monkeypatch):
    monkeypatch.setattr(config, "CONSULT_REGEX_FALLBACK", False)
    s = ConsultationSession(session_id="t-fb5")
    s._update_patient_info({}, user_text="我今年35岁，男")
    assert s.patient_age == 0 and s.patient_gender == ""


# ==================== 3. 主诉与上下文呈现 ====================

def test_chief_complaint_keeps_longer_description():
    s = ConsultationSession(session_id="t-cc")
    s._update_patient_info({"chief_complaint": "头痛"}, user_text="")
    s._update_patient_info({"chief_complaint": "阵发性头痛三天"}, user_text="")
    assert s.chief_complaint == "阵发性头痛三天", f"实际={s.chief_complaint!r}"


def test_collected_fields_reach_build_context():
    """已收集字段必须出现在注入模型的上下文里,否则模型还是会重复问。"""
    s = ConsultationSession(session_id="t-ctx")
    s._update_patient_info(
        {"patient_name": "张三", "patient_age": "40", "patient_gender": "男",
         "present_illness": "咳嗽两周"},
        user_text="",
    )
    ctx = s._build_context()
    assert "已收集 - 现病史" in ctx and "张三" in ctx, f"上下文缺失: {ctx!r}"


def test_long_field_is_capped():
    """累积合并必须有上限,否则字段会无限增长拖慢后续生成。"""
    s = ConsultationSession(session_id="t-cap")
    limit = config.CONSULT_FIELD_MAX_LEN
    for i in range(12):
        s._update_patient_info({"present_illness": f"第{i}轮补充的描述内容"}, user_text="")
    assert len(s.present_illness) <= limit + 2, (
        f"字段未被截断: {len(s.present_illness)} > {limit}")


# ==================== 4. 对话历史窗口 ====================

def test_history_window_covers_more_than_three_turns():
    """
    窗口必须能容纳 3 轮以上的历史。

    旧实现硬编码 [-6:](6 条 = 3 轮),第 1 轮说的话到第 4 轮就完全不可见了。
    """
    s = ConsultationSession(session_id="t-win")
    for i in range(10):   # 造 5 轮(10 条)
        s.conversation_history.append({"role": "user", "content": f"第{i}轮提问"})
        s.conversation_history.append({"role": "assistant", "content": f"第{i}轮回答"})
    window = s.history_window()
    assert len(window) == config.CONSULT_HISTORY_TURNS, (
        f"窗口长度不符: {len(window)} != {config.CONSULT_HISTORY_TURNS}")
    assert len(window) >= 8, f"窗口过小,早期信息仍会被截断: {len(window)}"


def test_history_window_respects_config(monkeypatch):
    monkeypatch.setattr(config, "CONSULT_HISTORY_TURNS", 4)
    s = ConsultationSession(session_id="t-win2")
    for i in range(6):
        s.conversation_history.append({"role": "user", "content": f"m{i}"})
    assert len(s.history_window()) == 4


# ==================== 5. 禁止重复询问提示 ====================

def test_no_repeat_hint_lists_collected_fields():
    """已收集字段必须出现在贴用户消息的紧凑提示里(对抗长提示开头的指令衰减)。"""
    s = ConsultationSession(session_id="t-hint")
    hint = s._no_repeat_hint()
    assert hint == "", f"无已收集信息时不应产生提示: {hint!r}"

    s._update_patient_info({"patient_name": "张三", "patient_age": "40"}, user_text="")
    hint = s._no_repeat_hint()
    assert "姓名" in hint and "年龄" in hint, f"提示未列出已收集项: {hint!r}"
    assert "严禁重复询问" in hint, f"提示缺少禁令措辞: {hint!r}"
    assert "现病史" not in hint, f"不应列入未收集的字段: {hint!r}"


def test_no_repeat_hint_can_be_disabled(monkeypatch):
    monkeypatch.setattr(config, "CONSULT_NO_REPEAT_HINT", False)
    s = ConsultationSession(session_id="t-hint2")
    s._update_patient_info({"patient_name": "张三"}, user_text="")
    assert s._no_repeat_hint() == ""


def test_global_prompt_forbids_repeating_questions():
    """系统提示词必须含禁止重复询问的硬约束,否则小模型仍会照问。"""
    prompt = consultation.SYSTEM_PROMPT_GLOBAL
    assert "重复询问" in prompt, "SYSTEM_PROMPT_GLOBAL 缺少禁止重复询问的约束"


# ==================== 6. 意图路由与 QA 轮补抽 ====================

def test_short_answers_are_treated_as_intake():
    """「男」「35岁」「没有」这类短答复不得被引到问答分支(会漏采本轮信息)。"""
    s = ConsultationSession(session_id="t-intent")
    for text in ("男", "35岁", "没有", "三天了", "有点咳嗽"):
        assert s._classify_intent(text) == "intake", f"误判为提问: {text!r}"


def test_real_questions_still_route_to_qa():
    s = ConsultationSession(session_id="t-intent2")
    for text in ("发烧能吃对乙酰氨基酚吗？", "布洛芬和对乙酰氨基酚有什么区别",
                 "高血压患者能吃什么药"):
        assert s._classify_intent(text) == "question", f"误判为采集: {text!r}"


def test_qa_turn_still_extracts_deterministic_fields():
    """
    QA 轮必须补抽背景信息。

    旧实现注释写着「QA 分支不做字段抽取」,用户在提问里交代的年龄/性别因此丢失。
    """
    s = ConsultationSession(session_id="t-qa")
    s._finalize_direct_qa("我今年40岁，男，血压高能吃这个药吗", "可以，但需监测血压。")
    assert s.patient_age == 40, f"QA 轮未补抽年龄: {s.patient_age}"
    assert s.patient_gender == "男", f"QA 轮未补抽性别: {s.patient_gender!r}"


# ==================== 7. 端到端最小复现 ====================

def test_multiturn_detail_survives_later_summary(monkeypatch):
    """
    最小复现「反复追问 / 说了不用」:

    第 1 轮患者说「我对青霉素过敏」,模型提取到 past_history;
    第 2 轮模型只写了更短的摘要「有过敏史」—— 旧实现直接覆盖,
    "青霉素"这个关键细节就此消失,后续模型无从判断,于是再问一遍过敏史。
    """
    import asyncio

    session = ConsultationSession(session_id="t-e2e")
    replies = [
        '好的，已记下。\n```json\n{"past_history": "青霉素过敏", '
        '"stage_complete": false, "next_stage": 1}\n```',
        '了解。\n```json\n{"past_history": "有过敏史", '
        '"stage_complete": false, "next_stage": 1}\n```',
        '好的。\n```json\n{"present_illness": "咳嗽三天", '
        '"stage_complete": false, "next_stage": 2}\n```',
    ]
    calls = {"n": 0}

    async def fake_chat_stream(**kwargs):
        idx = min(calls["n"], len(replies) - 1)
        calls["n"] += 1
        yield replies[idx]

    monkeypatch.setattr(consultation.llm_client, "chat_stream", fake_chat_stream)
    # 检索走真实 Chroma 会拖慢用例且与本用例无关,置空
    monkeypatch.setattr(session, "_retrieve_kb", lambda _u: "")
    monkeypatch.setattr(session, "_retrieve_memory", lambda _u: "")

    async def run():
        for text in ("我对青霉素过敏", "嗯，还有就是最近有点咳嗽", "是的"):
            async for _ in session.process_user_input_stream(text):
                pass

    asyncio.run(run())

    assert "青霉素" in session.past_history, (
        f"关键细节被后续摘要顶掉: {session.past_history!r}")
    # 第 3 轮时第 1 轮的原话仍应在窗口内(旧实现 6 条窗口此时已把它挤出去)
    window_text = "".join(m.get("content", "") for m in session.history_window())
    assert "青霉素过敏" in window_text, "早期轮次原话已滑出历史窗口"


if __name__ == "__main__":
    # 独立运行时逐条打印,便于定位
    failed = 0
    for name in sorted(k for k in list(globals()) if k.startswith("test_")):
        fn = globals()[name]
        try:
            if fn.__code__.co_argcount:   # 需要 monkeypatch 的用例跳过
                print(f"  [SKIP] {name} (需要 pytest fixture)")
                continue
            fn()
            print(f"  [PASS] {name}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {name}  {e}")
    print(f"\n独立运行结果: FAIL={failed}")
    sys.exit(1 if failed else 0)

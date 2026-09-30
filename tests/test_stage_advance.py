# -*- coding: utf-8 -*-
"""
问诊阶段推进回归测试（consultation.ConsultationSession）

背景（2026-09-22 修复的线上故障）：
    提示词 JSON 模板里 patient_age 写在引号内（"年龄（如未提及则为0）"），
    模型会照抄模板输出字符串 "35"。而 `_update_patient_info` 用
    `info["patient_age"] > 0` 做比较，str 与 int 比较直接抛 TypeError。

    异常上抛后，本轮后处理被整体跳过：
      - 阶段推进不执行 → stage 永远停在 1
      - assistant 消息不入历史 / 会话不落库
      - is_complete 永远为 False → 报告从不生成 → 「记录」页永远为空

    因此这里锁死两类行为：
      1) 字段类型容错：字符串年龄不得抛异常；
      2) 阶段推进：收到 stage_complete=true 时必须推进到 next_stage。

运行：python tests/test_stage_advance.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import consultation  # noqa: E402
import llm_client  # noqa: E402
import report_generator  # noqa: E402
from consultation import ConsultationSession  # noqa: E402

# 本模块靠「导入即执行」驱动问诊流程,里面用了模块级替换(consultation.llm_client.chat_stream
# 等)且不是 pytest monkeypatch,无法自动回滚。若不在这里预留原件,被 pytest 后续收集的测试
# 模块会拿到被替换后的实现 —— 实测会误伤 test_report_visit_date 的流式就诊日期用例。
_ORIG_GENERATE_REPORT_STREAM = report_generator.generate_report_stream
_ORIG_CHAT_STREAM = llm_client.chat_stream

PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  [PASS] {name}: {got!r}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}: got={got!r} want={want!r}")


def reply_with(stage_complete, next_stage, **fields):
    """构造一段「正文 + 末尾 JSON」的模型回复（模拟真实模型输出）"""
    payload = {
        "patient_name": "周敏",
        "patient_gender": "女",
        "patient_age": "28",  # 注意：模板带引号，模型常输出字符串
        "chief_complaint": "上腹隐痛",
        "present_illness": "",
        "past_history": "",
        "personal_history": "",
        "family_history": "",
        "system_review": "",
        "stage_complete": stage_complete,
        "next_stage": next_stage,
    }
    payload.update(fields)
    import json as _json
    return "好的，我了解了。\n\n【JSON块】\n" + _json.dumps(payload, ensure_ascii=False)


# --- 1. 字段类型容错 ------------------------------------------------------
print("\n[1] _update_patient_info 类型容错")
for label, raw in [("字符串数字", "28"), ("纯数字", 28), ("带单位", "28岁"), ("空串", ""), ("None", None)]:
    sess = ConsultationSession(session_id="t")
    try:
        sess._update_patient_info({"patient_age": raw})
        check(f"{label} 不抛异常", getattr(sess, "patient_age", None),
              28 if str(raw).strip() not in ("", "None") else 0)
    except Exception as e:
        FAIL += 1
        print(f"  [FAIL] {label} 抛出异常: {e!r}")

# --- 2. 布尔/阶段号归一化 -------------------------------------------------
print("\n[2] _as_bool / _normalize_stage 归一化")
for raw, want in [(True, True), ("true", True), ("false", False), ("True", True), (0, False), (None, False)]:
    check(f"_as_bool({raw!r})", ConsultationSession._as_bool(raw), want)
check("_normalize_stage('2')", ConsultationSession._normalize_stage("2", 9), 2)
check("_normalize_stage(None, 3)", ConsultationSession._normalize_stage(None, 3), 3)

# --- 3. 同步链路：收到 true 必须推进阶段 ----------------------------------
print("\n[3] 同步 process_user_input 阶段推进")
ConsultationSession._retrieve_references = lambda self, q: (None, None)
ConsultationSession._remember_turn = lambda self, u, r: None
ConsultationSession._query_patient_history = lambda self, name: None

consultation.llm_client.chat = lambda **kw: reply_with(True, 2)
_sync_sess = ConsultationSession(session_id="t-sync")
_sync_sess.process_user_input("我叫周敏，女，28岁，胃疼")
check("stage 推进到 2", _sync_sess.stage, 2)
check("patient_age 转为 int 28", _sync_sess.patient_age, 28)

# --- 4. 流式链路：同样必须推进阶段 ----------------------------------------
print("\n[4] 流式 process_user_input_stream 阶段推进")


async def fake_stream(*args, **kwargs):
    yield reply_with(True, 4)


consultation.llm_client.chat_stream = fake_stream
_stream_sess = ConsultationSession(session_id="t-stream")
_stream_sess.conversation_history.append({"role": "user", "content": "既往体健"})


async def drain():
    async for _ev in _stream_sess.process_user_input_stream("既往体健"):
        pass


asyncio.run(drain())
check("stage 推进到 4", _stream_sess.stage, 4)
check("流式也写入 patient_age", _stream_sess.patient_age, 28)

# --- 5. 信息不齐 + stage_complete=false 时不得推进 ------------------------
print("\n[5] 信息未收齐时不推进")
consultation.llm_client.chat = lambda **kw: reply_with(
    False, 1, patient_name="", patient_gender="", patient_age=0, chief_complaint="")
_no_sess = ConsultationSession(session_id="t-no")
_no_sess.process_user_input("嗯")
check("stage 保持 1", _no_sess.stage, 1)

# --- 6. 模型完全不输出 JSON 时的兜底推进（本次故障主因）------------------
print("\n[6] 无 JSON 块时的确定性兜底")


async def no_json_stream(*args, **kwargs):
    yield "好的，还有什么不舒服吗？"   # 完全不带 JSON


consultation.llm_client.chat_stream = no_json_stream
_nojson = ConsultationSession(session_id="t-nojson")
# 模拟首轮已收集齐基本信息
_nojson.patient_name, _nojson.patient_gender = "周敏", "女"
_nojson.patient_age, _nojson.chief_complaint = 28, "上腹隐痛"


async def drain2():
    async for _ev in _nojson.process_user_input_stream("就这些"):
        pass


asyncio.run(drain2())
check("无 JSON 仍推进到 stage 2", _nojson.stage, 2)

# --- 7. 数据长期不齐时按最大回合数强制推进（防死锁）----------------------
print("\n[7] 超过最大回合数强制推进")
_stuck = ConsultationSession(session_id="t-stuck")
_stuck.stage = 3  # 既往史：用户始终答不上来
_advanced = False
for i in range(4):
    _advanced = _stuck._fallback_stage_advance()
    if _advanced:
        break
check("stage 3 在 4 回合内被推进", _stuck.stage, 4)
check("返回值为 True", _advanced, True)

# --- 8. QA（question）轮次也计入阶段推进（2026-09-22 二次修复）------------
print("\n[8] 问答分支计入推进计数")


async def qa_stream(*args, **kwargs):
    yield "头疼有很多可能原因，您最近睡眠怎么样？"


consultation.llm_client.chat_stream = qa_stream

_qa_sess = ConsultationSession(session_id="t-qa")
# 第一阶段基本信息已在先前轮次收齐(stage 1 -> 数据 ready, MIN_TURNS=1)
_qa_sess.patient_name, _qa_sess.patient_gender = "小明", "男"
_qa_sess.patient_age, _qa_sess.chief_complaint = 18, "头疼"


async def drain_qa():
    # 连续 2 轮纯提问输入(都会被意图路由判为 question)
    for _ in range(2):
        async for _ev in _qa_sess.process_user_input_stream("头疼是怎么回事？"):
            pass


asyncio.run(drain_qa())
check("QA 轮次使 stage 推进(1->2)", _qa_sess.stage, 2)

# --- 9. QA 轮推进到终末阶段: is_complete + 后台报告任务 -------------------
print("\n[9] QA 推进到 COMPLETE 触发后台报告")


async def fake_report_stream(*args, **kwargs):
    yield "## 测试报告正文"


consultation.report_generator.generate_report_stream = fake_report_stream


async def qa_final_stream(*args, **kwargs):
    # 收尾轮:模型不再提问(原用例回复带问号,在「提问必须等回答」规则下应被拦截,
    # 正是 2026-09-26 修复的「第五步提问后报告提前生成」的旧断言)
    yield "好的，您的症状与病史我已经充分了解，信息收集完成。"


consultation.llm_client.chat_stream = qa_final_stream

_done_sess = ConsultationSession(session_id="t-done")
_done_sess.stage = 4  # 系统回顾阶段
_done_sess._stage_turns = 0
# 数据齐备(满足 _can_finalize):用户已回答完最后一问,本轮模型只做收尾陈述
_done_sess.patient_name, _done_sess.patient_gender = "小明", "男"
_done_sess.patient_age, _done_sess.chief_complaint = 18, "头疼"
_done_sess.present_illness = "头疼三天，阵发性加重"
_done_sess.system_review = "无特殊异常"


async def drain_done():
    async for _ev in _done_sess.process_user_input_stream("头不疼了？还有别的要问吗？"):
        pass
    # 等待后台报告任务完成
    if _done_sess._report_task is not None:
        await _done_sess._report_task


asyncio.run(drain_done())
check("QA 轮推进到 STAGE_COMPLETE", _done_sess.stage, 5)
check("is_complete 置真", _done_sess.is_complete, True)
check("报告后台生成成功", _done_sess.report_status, "done")
check("报告正文已保存", _done_sess.report.startswith("## 测试报告正文") or "测试报告正文" in _done_sess.report, True)
check("报告已追加进对话历史", _done_sess.conversation_history[-1]["content"].startswith("## "), True)

# --- 10. maybe_start_report_task 幂等 ------------------------------------
print("\n[10] maybe_start_report_task 幂等")


async def idem():
    s = ConsultationSession(session_id="t-idem")
    s.is_complete = True
    first = s.maybe_start_report_task()
    second = s.maybe_start_report_task()  # 任务未完成,不得重复启动
    if s._report_task is not None:
        s._report_task.cancel()
    return first, second, s.report_status


_f, _s2, _st = asyncio.run(idem())
check("首次启动成功", _f, True)
check("重复调用被拒绝", _s2, False)
check("状态进入生成流程", _st in ("pending", "running", "done"), True)

# --- 11. from_dict 旧数据兼容（无 report_status 字段）--------------------
print("\n[11] report_status 反序列化兼容")
_old_done = ConsultationSession.from_dict({"report": "旧报告", "is_complete": True})
check("有报告 -> done", _old_done.report_status, "done")
_old_complete = ConsultationSession.from_dict({"report": "", "is_complete": True})
check("已完成无报告 -> pending(可重触发)", _old_complete.report_status, "pending")
_old_new = ConsultationSession.from_dict({"report": "", "is_complete": False})
check("未完成 -> none", _old_new.report_status, "none")

# --- 12. 第五步:模型提问未获回答时,报告不得提前生成（2026-09-26 修复）-----
# 场景复现:问句在句中、句号结尾(「……是否有其他症状？这些信息有助于我们进行系统回顾。」),
# 旧实现只判末尾字符 → 漏判 → stage 直跳 5,报告在患者作答前开跑。
print("\n[12] 问句在句中(句号结尾)时拦截过早完结")
import json as _mj

_midq_payload = {
    "patient_name": "周敏", "patient_gender": "女", "patient_age": 28,
    "chief_complaint": "上腹隐痛", "present_illness": "上腹隐痛三天，餐后加重",
    "past_history": "", "personal_history": "", "family_history": "家族中无遗传病",
    "system_review": "暂无特殊",
    "stage_complete": True, "next_stage": 5,
}
_midq_reply = (
    "您提到家族中没有遗传病。请问您是否有其他系统的症状，比如消化系统不适、"
    "呼吸困难或肌肉疼痛？这些信息有助于我们进行系统回顾。\n\n【JSON块】\n"
    + _mj.dumps(_midq_payload, ensure_ascii=False)
)


async def midq_stream(*args, **kwargs):
    yield _midq_reply


consultation.llm_client.chat_stream = midq_stream
_midq_sess = ConsultationSession(session_id="t-midq")
_midq_sess.stage = 4
_midq_sess.patient_name, _midq_sess.patient_gender = "周敏", "女"
_midq_sess.patient_age, _midq_sess.chief_complaint = 28, "上腹隐痛"
_midq_sess.present_illness = "上腹隐痛三天，餐后加重"
_midq_sess.system_review = "暂无特殊"


async def drain_midq():
    _end = None
    async for _ev in _midq_sess.process_user_input_stream("没有遗传病"):
        if _ev.get("event") == "end":
            _end = _ev
    return _end


_end_midq = asyncio.run(drain_midq())
check("问句未答 stage 保持 4", _midq_sess.stage, 4)
check("is_complete 仍为 False", _midq_sess.is_complete, False)
check("报告未启动", _midq_sess.report_status, "none")
check("未追加完成提示语", "✅ 问诊信息收集完成" in _end_midq["data"], False)

# --- 13. 同样数据、回复无问句(用户已作答) → 正常进入报告 ------------------
print("\n[13] 无问句时正常完结并触发报告")


async def fin_stream(*args, **kwargs):
    yield "好的，信息已经收集完整。\n\n【JSON块】\n" + _mj.dumps(_midq_payload, ensure_ascii=False)


consultation.llm_client.chat_stream = fin_stream
_fin_sess = ConsultationSession(session_id="t-fin")
_fin_sess.stage = 4
_fin_sess.patient_name, _fin_sess.patient_gender = "周敏", "女"
_fin_sess.patient_age, _fin_sess.chief_complaint = 28, "上腹隐痛"
_fin_sess.present_illness = "上腹隐痛三天，餐后加重"
_fin_sess.system_review = "暂无特殊"


async def drain_fin():
    async for _ev in _fin_sess.process_user_input_stream("没有其他症状了"):
        pass
    if _fin_sess._report_task is not None:
        await _fin_sess._report_task


asyncio.run(drain_fin())
check("stage 推进到 5", _fin_sess.stage, 5)
check("is_complete 置真", _fin_sess.is_complete, True)
check("报告生成完成", _fin_sess.report_status, "done")

print("\n" + "=" * 56)
print(f"结果: {PASS} passed, {FAIL} failed")

# --- 还原全局替换,避免污染同进程内后续被收集的测试模块 ---
consultation.report_generator.generate_report_stream = _ORIG_GENERATE_REPORT_STREAM
llm_client.chat_stream = _ORIG_CHAT_STREAM

# 用 pytest 收集时不退出，避免 SystemExit 打断整个测试会话
if __name__ == "__main__":
    sys.exit(1 if FAIL else 0)

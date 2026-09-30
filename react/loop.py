"""ReAct 受控循环编排

循环形态:Thought(Planner) -> Action(工具白名单) -> Observation(工具真实返回) -> ... -> 终答

设计要点(针对本项目约束):
1. Planner 用结构化 JSON 协议,不用自由文本 ReAct 协议 —— 7B 小模型遵循不住自由文本;
2. Observation 只来自工具真实返回值,模型无法编造;
3. 步数预算 + 时间预算(默认 8s 作用于编排阶段)双闸,超限立即终答;
4. Planner 连续 2 次非法输出即降级,降级后回退到「现有单次 LLM 流程」;
5. Planner 与终答统一复用 config.CONSULT_MODEL_NAME,不新增模型标识;
6. 本模块只 yield 与 _stream_direct_qa 同格式的事件字典,路由层零改动。

本模块不依赖 consultation 模块级作用域(仅在函数内按需导入,避免循环 import)。
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import replace
from typing import AsyncIterator, List, Optional

import config
import llm_client
from react.tools import (
    TOOL_ASK_USER, TOOL_FINISH, TOOL_WHITELIST, ToolContext, describe_tools, execute_tool,
)
from react.types import (
    REF_KNOWLEDGE, STATUS_ERROR, STATUS_OK, STATUS_TIMEOUT, STEP_ACTION, STEP_FALLBACK,
    STEP_FINAL, STEP_NOTE, STEP_OBSERVATION, STEP_THOUGHT, Trace, Step, build_sentence_trace,
    now_iso, strip_undefined_cites,
)

logger = logging.getLogger("react")

# Planner 最大重试次数:连续失败到此次数即降级(防止小模型空转)
_MAX_PLANNER_FAILS = 2

_PLANNER_SYSTEM = """你是一个受控推理引擎，服务于医学健康咨询场景的「直接问答」分支。

工作方式：
1. 先思考回答这个问题需要哪些信息（thought）；
2. 需要外部信息时调用工具（action），工具会返回真实结果（observation）；
3. 信息足够后结束推理，由作答阶段生成最终回答。

严格输出如下 JSON，不要输出任何额外文字、不要 Markdown 代码块：
{{"thought": "一句话说明下一步要做什么", "action": {{"name": "工具名", "args": {{}}}}, "final_answer": null}}

信息足够时：
{{"thought": "已掌握足够信息，可以作答", "action": {{"name": "finish", "args": {{}}}}, "final_answer": "留空，作答阶段会自行生成"}}

可用工具：
{tools}

规则：
1. 只输出 JSON，禁止代码块与解释性文字；
2. 工具最多调用 {max_steps} 次，超预算会强制作答；
3. 无效工具名或参数会导致本轮降级，优先使用 kb_search；
4. thought 保持一句话，不要复述用户输入。
"""

# 终答阶段的引用约束(追加在 DIRECT_QA_SYSTEM 之后)
_CITATION_HINT = """
【引用书写要求 —— 必须遵守】
- 正文每一句事实性陈述（病因、症状、用药、护理、判断等）后面紧跟引用编号，形如：……退烧药对乙酰氨基酚[int]……。
- 多个来源用同一组方括号，形如 [1][3] 或 [1,3]。
- 只允许使用上方【可用引用】中给出的编号，禁止编造编号。
- 完全通用、无需出处的过渡句可以不标注。
"""


# C 期:明显不属于健康科普范畴的话题线索。只在「知识库零命中」时才启用判定 ——
# 有依据时正常作答,零命中时才区分「知识未覆盖」与「话题超出范围」两种兜底话术。
_OUT_OF_SCOPE_HINTS = (
    "写诗", "写一首", "翻译", "编程", "代码", "写作文", "读后感", "情书",
    "数学题", "算一下", "股票", "基金", "投资", "彩票", "招聘", "简历", "面试",
    "法律", "离婚", "合同条款", "自我介绍", "物理题", "化学", "历史题",
    "政治题", "地球", "天文", "动物", "植物",
)


def _is_out_of_scope(user_input: str) -> bool:
    """粗判问题是否超出「用药/症状/疾病/护理」健康科普范围(零命中时才调用)。"""
    text = (user_input or "").lower()
    return any(h.lower() in text for h in _OUT_OF_SCOPE_HINTS)


def _score_floor() -> float:
    """证据门槛(老部署没有该配置时退化为 0,即不额外过滤)。"""
    try:
        return float(getattr(config, "REACT_MIN_SCORE", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _strong_kb_refs(refs: list) -> list:
    """
    取真正可作为医学依据的引用:kind=kb 且分数达到证据门槛。

    tools.kb_search 已按门槛过滤过一遍,这里再兜一层 —— 防止别处注入的低分片段
    绕过门槛,变成模型的「证据」。

    例外:strong_hit(片段里写着用户问的那味药/那个症状)属精确命中,
    在 tools 侧已豁免门槛,这里必须认同一把尺子,否则引用池会变成
    「只留泛泛相关的、把对症的挤掉」。
    """
    floor = _score_floor()
    picked: dict = {}
    for r in refs:
        if r.kind != REF_KNOWLEDGE:
            continue
        if r.score < floor and not r.strong_hit:
            continue
        # 同一片段会被预检索与各轮 kb_search 重复返回,不去重会让 [n] 里塞满重复条目:
        # 实测一轮终答 12 条引用中,只有 3 个不同片段,其余是重复项。
        prev = picked.get(r.doc_id)
        if prev is None or r.score > prev.score:
            picked[r.doc_id] = r
    # 精确命中优先,其次按相关度降序:编号从「最对症」那条开始,
    # 用户顺着 [1] 点开就该看到药名片段,而不是同样分量的泛泛段落。
    return sorted(picked.values(), key=lambda r: (not r.strong_hit, -r.score))


# 记忆 / 就诊记录观察块自带的 [n] 编号,会与知识库引用池的编号成对撞。
# 留着它有反效果:模型照着写 [1],句子就被绑到知识库 [1] 上 —— 那是**错误归因**,
# 比「不标来源」更糟(用户会以为这句话出自医学文献)。故拼提示词时一律抹掉,只留事实内容。
_OBSCITE_RE = re.compile(r"^\[\d+\]\s*\(\s*(?:来源|时间)\s*:[^)]*\)\s*", re.M)


def _strip_obscite_marks(text: str) -> str:
    """抹掉观察块中「个人史」片段自带的 [n] 编号。"""
    return _OBSCITE_RE.sub("", text or "")


def _extract_json_object(text: str) -> Optional[dict]:
    """
    从模型输出里稳健提取 JSON 对象。

    小模型常有「思维链包裹 / 前后加解释 / 带 Markdown 围栏」等问题，
    这里按 ①直接解析 ②去围栏 ③首尾括号回溯 三级降级，
    与 consultation._parse_llm_response 的容错思路保持一致。
    """
    if not text:
        return None
    s = text.strip()
    # 剥离推理模型的思维链(若模型仍输出 <think>)
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.S).strip()
    # 去 Markdown 围栏
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.S).strip()
    for candidate in (s,):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, TypeError):
            pass
    # 括号回溯:取最后一个 { 到最后一个 }
    start, end = s.rfind("{"), s.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(s[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, TypeError):
            pass
    return None


async def stream_qa_with_react(
    session,
    user_input: str,
    emergency_msg: str,
    turn_index: int,
    qa_system: str,
) -> AsyncIterator[dict]:
    """
    在「直接问答」分支上跑受控 ReAct 循环，产出与 _stream_direct_qa 同格式的事件。

    Yields:
      {"event": "step",    "data": <step JSON>}   推理过程(可折叠时间线)
      {"event": "reply",   "data": str}           最终回答片段
    """
    from consultation import _VisibleStreamFilter  # 函数内导入,避免与 consultation 循环 import

    user_id = getattr(session, "user_id", 0)
    ctx = ToolContext(
        user_id=user_id,
        chief_complaint=getattr(session, "chief_complaint", ""),
        session_id=getattr(session, "session_id", ""),
    )

    trace = Trace(
        trace_id=f"{getattr(session, 'session_id', '')}#{turn_index}",
        session_id=getattr(session, "session_id", ""),
        turn_index=turn_index,
        enabled=True,
        branch="direct_qa",
    )
    # 落库需要的轨迹挂在会话对象上,由 consultation 层统一持久化(不污染 to_dict/from_dict)
    session._last_trace = trace

    t_start = time.perf_counter()
    seq = 0
    last_stamp = 0

    def _elapsed_ms() -> int:
        return int((time.perf_counter() - t_start) * 1000)

    def _emit(step: Step):
        """
        登记步骤并按开关下发 step 事件(老前端不认识该事件会自动忽略)。

        elapsed_ms 记的是「本步自身耗时」(当前累计耗时 - 上一步累计耗时),
        因此各步 elapsed_ms 之和 ≈ trace.total_ms,便于前端做耗时对齐校验。
        """
        nonlocal seq, last_stamp
        now_total = _elapsed_ms()
        step.elapsed_ms = max(0, now_total - last_stamp)
        last_stamp = now_total
        step.seq = seq
        step.ts = now_iso()
        trace.steps.append(step)
        seq += 1
        if config.REACT_SHOW_STEPS:
            yield {"event": "step", "data": json.dumps(step.to_dict(), ensure_ascii=False)}

    # ---------- 第 0 步:确定性步骤(零 LLM,解释"为什么走这条分支") ----------
    for ev in _emit(Step(
        type=STEP_NOTE,
        text="意图判定：question（命中直接问答分支，不套用 5 阶段问诊）",
    )):
        yield ev

    if emergency_msg:
        for ev in _emit(Step(
            type=STEP_NOTE,
            text="命中紧急症状关键词，回答前置就医提醒。",
        )):
            yield ev

    refs: List = []          # 累积引用(预检索 + 工具调用)
    observations: List[str] = []  # 累积观察文本

    # ---------- 预检索:调用真实工具,同时兼顾"零延迟起步"与"工具可被调用" ----------
    try:
        kb_task = asyncio.create_task(_safe_tool("kb_search",
                                                 {"query": user_input, "top_k": 3}, ctx))
        mem_task = asyncio.create_task(_safe_tool("memory_search",
                                                  {"query": user_input, "top_k": 2}, ctx))
        kb_res, mem_res = await asyncio.gather(kb_task, mem_task)
        for r in (kb_res, mem_res):
            if r and r.refs:
                refs.extend(r.refs)
            if r and r.text:
                observations.append(r.text)
    except Exception as e:
        logger.warning(f"[react] 预检索异常,继续作答: {e}")

    if refs or observations:
        hit = len(refs)
        for ev in _emit(Step(
            type=STEP_OBSERVATION,
            status=STATUS_OK,
            tool="kb_search+memory_search",
            text=f"预检索完成，命中 {hit} 条可引用片段。",
            refs=list(refs),
        )):
            yield ev
    else:
        for ev in _emit(Step(
            type=STEP_OBSERVATION,
            status=STATUS_OK,
            tool="kb_search+memory_search",
            text="预检索无命中（知识库/记忆为空或相关度不足），将依据通用医学常识作答。",
        )):
            yield ev

    # ---------- 证据门槛:知识库零命中时的确定性兜底(防幻觉) ----------
    # 零命中 = 没有任何达到证据门槛的医学片段。此时若继续让 Planner 推理,
    # 模型盯着一堆「相关性不足」的资料,很容易顺手补一段医学常识 —— 那就是幻觉。
    # 处置:不生成、不推测,直接给确定性话术(话题超范围时给引导)。
    no_evidence = not _strong_kb_refs(refs)
    out_of_scope = no_evidence and _is_out_of_scope(user_input)
    if no_evidence:
        head = (config.REACT_OUT_OF_SCOPE_REPLY if out_of_scope
                else config.REACT_NO_EVIDENCE_REPLY)
        for ev in _emit(Step(
            type=STEP_NOTE,
            text=("该问题超出本助手健康科普范围。" if out_of_scope
                  else f"知识库无可用依据(相关度均低于证据门槛 "
                       f"{getattr(config, 'REACT_MIN_SCORE', 0.0)})。"),
        )):
            yield ev
        for ev in _emit(Step(
            type=STEP_OBSERVATION,
            tool="kb_search",
            text=head,
        )):
            yield ev

    # ---------- Planner 循环 ----------
    asks_user = False
    planner_fails = 0
    max_steps = max(1, config.REACT_MAX_STEPS)
    # 零命中 + 严格模式:没有依据可规划,跳过规划直接进终答,
    # 既避免一次必然诱发推测的调用,也省下几十秒等待。
    planner_active = not (no_evidence and config.REACT_NO_EVIDENCE_STRICT)

    for _ in range(max_steps if planner_active else 0):
        if _elapsed_ms() > config.REACT_BUDGET_MS:
            logger.info(f"[react] 达到时间预算 {config.REACT_BUDGET_MS}ms,直接进入终答")
            trace.fallback_reason = "budget_exceeded"
            break

        plan = await _call_planner(user_input, ctx, refs, observations, max_steps,
                                   no_evidence=no_evidence)
        if plan is None:
            planner_fails += 1
            logger.warning(f"[react] Planner 第 {planner_fails} 次输出无法解析")
            if planner_fails >= _MAX_PLANNER_FAILS:
                for ev in _emit(Step(
                    type=STEP_FALLBACK,
                    status=STATUS_ERROR,
                    text="规划模型连续输出异常，已回退为单次问答流程。",
                    error="planner_parse_failed",
                )):
                    yield ev
                trace.fallback_reason = "planner_parse_failed"
                break
            continue

        thought = str(plan.get("thought") or "").strip()
        if thought:
            for ev in _emit(Step(type=STEP_THOUGHT, text=thought)):
                yield ev

        action = plan.get("action") or {}
        name = str(action.get("name") or "").strip()
        args = action.get("args") or {}

        if not name or name not in TOOL_WHITELIST:
            planner_fails += 1
            logger.warning(f"[react] 非法工具名: {name!r}")
            if planner_fails >= _MAX_PLANNER_FAILS:
                for ev in _emit(Step(
                    type=STEP_FALLBACK,
                    status=STATUS_ERROR,
                    text=f"规划模型请求了未授权的工具（{name or '空'}），已回退为单次问答流程。",
                    error="tool_not_allowed",
                )):
                    yield ev
                trace.fallback_reason = "tool_not_allowed"
                break
            continue

        if name in (TOOL_FINISH, TOOL_ASK_USER):
            if name == TOOL_ASK_USER:
                asks_user = True
            for ev in _emit(Step(
                type=STEP_ACTION,
                tool=name,
                text=("向患者追问缺失信息。" if asks_user else "信息已足够，进入作答。"),
            )):
                yield ev
            break

        # 真实工具调用:观察结果完全来自返回值,不由模型撰写
        step_tool_start = time.perf_counter()
        res = await _safe_tool(name, args, ctx)
        cost_ms = int((time.perf_counter() - step_tool_start) * 1000)
        if res and res.refs:
            refs.extend(res.refs)
        if res and res.text:
            observations.append(res.text)

        status = STATUS_OK if (res is not None and res.ok) else STATUS_ERROR
        for ev in _emit(Step(
            type=STEP_ACTION,
            status=status,
            tool=name,
            args=_safe_args(args),
            text=f"调用 {name}",
        )):
            yield ev

        if res is None:
            for ev in _emit(Step(
                type=STEP_OBSERVATION,
                status=STATUS_TIMEOUT,
                text="工具超时未返回，按空结果继续推理。",
                error="tool_timeout",
            )):
                yield ev
            continue

        for ev in _emit(Step(
            type=STEP_OBSERVATION,
            status=status,
            tool=name,
            text=_observation_summary(res.text),
            refs=list(res.refs),
            error=res.error,
        )):
            yield ev

    trace.total_ms = _elapsed_ms()

    # ---------- 终答(流式;全程不受 8s 编排预算约束) ----------
    async for ev in _stream_final_answer(
        session=session,
        user_input=user_input,
        emergency_msg=emergency_msg,
        qa_system=qa_system,
        refs=refs,
        observations=observations,
        asks_user=asks_user,
        trace=trace,
        filter_cls=_VisibleStreamFilter,
        no_evidence=no_evidence,
        out_of_scope=out_of_scope,
    ):
        yield ev


# ==================== 内部辅助 ====================

async def _safe_tool(name: str, args: dict, ctx: ToolContext):
    """工具执行:线程外执行 + 超时约束,异常收敛为 None(不向上抛)。"""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(execute_tool, name, args, ctx),
            timeout=config.REACT_TOOL_TIMEOUT_MS / 1000.0,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[react] 工具 {name} 超过 {config.REACT_TOOL_TIMEOUT_MS}ms 未返回")
        return None
    except Exception as e:
        logger.warning(f"[react] 工具 {name} 执行异常: {e}")
        return None


def _planner_timeout_ms() -> int:
    """
    单次 Planner 调用超时。

    实测(qwen2.5:7b-instruct):首次冷启动约 5700ms,之后预热可降到 1.3s。
    这里封顶 6000ms —— 若沿用旧的 4000ms,冷启动的那一次规划会被判超时丢弃,
    用户看到的首轮推理过程里一个 thought 都没有(白等一次 5.7s 且没有反馈)。
    8s 预算下取 0.75 倍即 6000ms,仍为第二次规划留出约 2s 重试窗口。
    """
    return min(6000, max(1500, int(config.REACT_BUDGET_MS * 0.75)))


async def _call_planner(user_input: str, ctx: ToolContext, refs: list,
                        observations: list, max_steps: int,
                        no_evidence: bool = False) -> Optional[dict]:
    """调用 Planner(复用 CONSULT_MODEL_NAME),返回解析后的 JSON 或 None。"""
    known = "\n".join(
        f"[{r.n}] {r.source}{'#' + str(r.chunk_index) if r.chunk_index is not None else ''}"
        for r in refs
    ) or "(暂无)"
    obs_text = "\n---\n".join(observations[-3:]) or "(暂无观察结果)"

    system = _PLANNER_SYSTEM.format(tools=describe_tools(), max_steps=max_steps)
    user = (
        f"【本轮已检索到的片段】\n{known}\n\n"
        f"【最近一次观察结果】\n{obs_text}\n\n"
        f"【待回答的用户问题】\n{user_input}\n\n"
        "请按协议输出 JSON。"
    )
    if no_evidence:
        # 严格模式下 Planner 已被跳过,这里只服务非严格模式(回滚选项)
        user += ("\n\n【证据状态】知识库未命中任何可用依据。不要推测、不要用通用常识补全，"
                 "直接以 finish 结束推理，由作答阶段告知用户知识未覆盖。")
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(
                llm_client.chat,
                system_prompt=system,
                user_prompt=user,
                history=None,
                temperature=0.1,
                model=config.CONSULT_MODEL_NAME,   # 显式指定:不传会静默回退默认推理模型
                max_tokens=600,
            ),
            # 单次 Planner 超时必须显著小于整轮预算:用满 8s 的话,「预检索 + 一次
            # Planner」就已经吃光预算,第二次规划还没开始就被强制作答,推理过程里
            # 一个 thought 都没有。这里按预算的 0.75 倍(8s→6s)封顶,既容得下冷启动,
            # 又给第二次规划留出重试窗口(取值见 _planner_timeout_ms 的实测说明)。
            timeout=_planner_timeout_ms() / 1000.0,
        )
    except Exception as e:
        logger.warning(f"[react] Planner 调用失败: {e}")
        return None
    return _extract_json_object(raw or "")


def _safe_args(args: dict) -> dict:
    """action 参数脱敏后下发前端(避免把完整原文透出)。"""
    out = {}
    for k, v in (args or {}).items():
        s = str(v)
        out[str(k)] = s[:60] + ("…" if len(s) > 60 else "")
    return out


def _observation_summary(text: str, limit: int = 160) -> str:
    """观察结果摘要(落库/展示用,不整段回显)。"""
    t = (text or "").strip()
    if not t:
        return "(空结果)"
    first_nl = t.find("\n")
    head = t[:first_nl] if 0 < first_nl < 120 else t
    return head[:limit] + ("…" if len(head) > limit else "")


async def _stream_final_answer(session, user_input: str, emergency_msg: str,
                               qa_system: str, refs: list, observations: list,
                               asks_user: bool, trace: Trace, filter_cls,
                               no_evidence: bool = False,
                               out_of_scope: bool = False) -> AsyncIterator[dict]:
    """
    终答流式输出 + 句子级引用绑定。

    引用绑定发生在正文之后(正文已逐字下发),因此这里只做「编号回校验 + 句子切分」,
    不再改写已经流式发出的正文,避免出现前后不一致。

    no_evidence=True 时走零命中兜底:不生成、不推测,直接给确定性话术(见 B 期防幻觉)。
    """
    from consultation import DIRECT_QA_SYSTEM  # 常量来自 consultation,避免模块级循环 import

    prefix = (emergency_msg + "\n\n") if emergency_msg else ""
    system = qa_system or DIRECT_QA_SYSTEM

    # ---------- 零命中兜底(防幻觉):确定性话术,不调模型 ----------
    if no_evidence:
        fallback = (config.REACT_OUT_OF_SCOPE_REPLY if out_of_scope
                    else config.REACT_NO_EVIDENCE_REPLY)
        yield {"event": "reply", "data": (prefix + fallback) if prefix else fallback}
        final_step = Step(
            seq=len(trace.steps),
            ts=now_iso(),
            type=STEP_FINAL,
            text=("话题超出覆盖范围：" + fallback) if out_of_scope else ("零命中兜底：" + fallback),
            refs=[],
            sentences=[],
            error="out_of_scope" if out_of_scope else "no_evidence",
        )
        trace.steps.append(final_step)
        if config.REACT_SHOW_STEPS:
            yield {"event": "step", "data": json.dumps(final_step.to_dict(), ensure_ascii=False)}
        return

    # ---------- 引用池只保留知识库片段,并重新编号 ----------
    # 记忆(既往对话)与就诊记录属于「个人史」,不是「医学依据」。让它们占 [n]
    # 有两点坏处:① [n] 语义混乱,用户以为医疗建议有知识出处;
    # ② 句子被标成 cited=True,把「没有知识依据」这个事实掩盖掉。
    # 因此这里把 kb 片段单独抽出、按 1..n 重新排列,编号与最终 refs 严格一一对应。
    citation_refs = [replace(r, n=i) for i, r in enumerate(_strong_kb_refs(refs), 1)]

    # 引用块:只下发真实命中的片段,[n] 与 step.refs 的 n 一一对应
    citation_block = ""
    if citation_refs:
        lines = []
        for r in citation_refs:
            loc = f"#{r.chunk_index}" if r.chunk_index is not None else ""
            lines.append(f"[{r.n}] {r.source}{loc}（相关度 {r.score}）：{r.quote}")
        citation_block = "\n【可用引用】\n" + "\n".join(lines) + "\n"

    enriched = f"用户问题：{user_input}"
    if observations:
        enriched += ("\n\n【检索到的资料】(事实性内容，可用于作答)\n"
                     + "\n---\n".join(_strip_obscite_marks(o) for o in observations[-4:]))
    if citation_block:
        enriched += "\n" + citation_block
    if config.REACT_SENTENCE_CITATION:
        enriched += _CITATION_HINT
    if no_evidence and not config.REACT_NO_EVIDENCE_STRICT:
        # 非严格模式(回滚开关):仍生成,但把资料清空并钉死话术,
        # 生成后再做一次后置校验,防止模型自作主张写医学内容。
        refs, observations = [], []
        want = (config.REACT_OUT_OF_SCOPE_REPLY if out_of_scope
                else config.REACT_NO_EVIDENCE_REPLY)
        enriched += (f"\n\n【证据状态】知识库未命中任何可用依据，禁止推测、禁止补充医学常识。"
                     f"必须原样输出这句话：{want}")
    if asks_user:
        enriched += "\n\n【本轮任务】信息不足，需要向患者追问关键信息后再作答，只问最必要的一两项。"

    streamed: list = []
    text_filter = filter_cls()
    think_state = {"in_think": False, "buf": ""}
    first = True
    try:
        async for raw in llm_client.chat_stream(
            system_prompt=system,
            user_prompt=enriched,
            # 与问诊主链路共用同一窗口(默认 12 条 ≈ 6 轮):ReAct 终答同样需要看到
            # 用户在前面几轮提供的背景,否则会重复追问已回答过的问题。
            history=session.history_window(),
            model=config.CONSULT_MODEL_NAME,   # 显式指定,避免静默回退默认推理模型
            max_tokens=config.CONSULT_MAX_TOKENS,
            return_raw=True,
        ):
            for kind, txt in llm_client._split_think_stream(raw, think_state):
                if kind == "think":
                    # 终答阶段模型自发的思维链(A 期可见性):与降级路径 _stream_direct_qa
                    # 保持一致,以 thinking 事件下发,由前端「💭 思考过程」块承接。
                    # 此前是直接 continue 丢弃,导致走 ReAct 反而比降级路径更看不到思考过程。
                    if config.SHOW_THINKING and txt:
                        yield {"event": "thinking", "data": txt}
                    continue  # 思维链不进正文,只作为可解释信息透出
                visible = text_filter.feed(txt)
                if not visible:
                    continue
                if first and prefix:
                    visible = prefix + visible
                first = False
                streamed.append(visible)
                yield {"event": "reply", "data": visible}

        tail = text_filter.flush()
        if tail:
            streamed.append(tail)
            yield {"event": "reply", "data": tail}
    except Exception as e:
        logger.warning(f"[react] 终答流式异常: {e}")
        if not streamed:
            yield {
                "event": "reply",
                "data": prefix + "抱歉，回答生成失败，请重试。",
            }

    reply = "".join(streamed)

    # ---------- 零命中后置校验(仅非严格模式) ----------
    # 正文已逐字下发,不做整段替换(会造成前后不一致),只在末尾补一句兜底提示。
    if no_evidence and not config.REACT_NO_EVIDENCE_STRICT:
        want = (config.REACT_OUT_OF_SCOPE_REPLY if out_of_scope
                else config.REACT_NO_EVIDENCE_REPLY)
        if want not in reply:
            logger.warning("[react] 零命中兜底话术未出现在本轮生成结果中,已追加")
            yield {"event": "reply", "data": "\n\n" + want}
            reply = reply + "\n\n" + want

    # ---------- 句子级溯源 ----------
    sentences: list = []
    undefined: list = []
    if config.REACT_SENTENCE_CITATION and reply:
        # 绑定用的就是模型看到的那一套编号(citation_refs),不是聚合后的全部 refs
        # —— 否则模型按 citation_block 写的 [1] 会被拿去和记忆片段的编号对号入座。
        sentences = build_sentence_trace(reply, citation_refs)
        if config.REACT_CITATION_CHECK:
            body, removed = _strip_undefined(reply, {r.n for r in citation_refs})
            if removed:
                undefined = removed
                logger.warning(f"[react] 正文存在未定义引用编号 {removed},已回校验")
                sentences = build_sentence_trace(body, citation_refs)

    # seq/ts 交给本函数自行登记(此处拿不到 _emit 的 nonlocal seq,改用轨迹长度对齐,
    # 保证前端按 seq 排序后仍与线下顺序完全一致)
    # 溯源结论必须自解释:只丢一个「0 句带知识来源」的数字,用户无从判断
    # 是检索没命中、还是模型没标注,容易误以为溯源坏了。这里按三种情形如实说明。
    cited_cnt = sum(1 for s in sentences if s.get("cited"))
    infer_cnt = sum(1 for s in sentences if s.get("inferred"))
    if cited_cnt:
        detail = f"共 {len(sentences)} 句，{cited_cnt} 句显式引用知识片段"
        if infer_cnt:
            detail += f"，另 {infer_cnt} 句为系统推断绑定（非模型显式引用）"
    elif citation_refs:
        detail = (f"共 {len(sentences)} 句，本轮回答未标注知识来源 —— "
                  f"知识库有 {len(citation_refs)} 条相关片段但未被引用，属模型自由作答，请谨慎采纳")
    else:
        detail = f"共 {len(sentences)} 句，知识库无可用依据，未作医学推测"

    final_step = Step(
        seq=len(trace.steps),
        ts=now_iso(),
        type=STEP_FINAL,
        text="作答完成，" + detail
             + (f"；已剥离未定义编号 {undefined}。" if undefined else "。"),
        refs=list(citation_refs),
        sentences=sentences,
        error="citation_undefined" if undefined else None,
    )
    trace.steps.append(final_step)
    if config.REACT_SHOW_STEPS:
        yield {"event": "step", "data": json.dumps(final_step.to_dict(), ensure_ascii=False)}


def _strip_undefined(text: str, valid: set) -> tuple:
    """剥离正文里未定义的引用编号,返回 (清洗后文本, 被剥离编号列表)。"""
    return strip_undefined_cites(text, valid)

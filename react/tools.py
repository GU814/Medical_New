"""ReAct 工具集(Planner 可调用的动作白名单)

全部工具均为同步实现,由 loop 层通过 asyncio.to_thread 投放执行 + wait_for 超时控制。

工具清单(全部启用):
- kb_search        : 知识库语义检索,返回带溯源标识的医学片段
- memory_search    : 该用户跨会话长记忆检索
- patient_history  : 患者历史就诊记录查询(按 user_id 作用域隔离)
- finish           : 信息足够,进入终答
- ask_user         : 信息不足,需要向用户追问(终止动作)

约定:工具只能返回系统真实产生的内容,禁止模型自行编造 Observation。
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

import config
import database
import knowledge_base
import memory_store
from react.types import REF_KNOWLEDGE, REF_MEMORY, Ref

logger = logging.getLogger("react")

TOOL_KB_SEARCH = "kb_search"
TOOL_MEMORY_SEARCH = "memory_search"
TOOL_PATIENT_HISTORY = "patient_history"
TOOL_FINISH = "finish"
TOOL_ASK_USER = "ask_user"

# Planner 可用工具白名单:不在名单内的 action 视为非法,直接降级
TOOL_WHITELIST = {
    TOOL_KB_SEARCH: "kb_search: 检索医学知识库(query:检索词, top_k:返回条数)",
    TOOL_MEMORY_SEARCH: "memory_search: 检索该患者跨会话记忆(query:检索词, top_k:返回条数)",
    TOOL_PATIENT_HISTORY: "patient_history: 查询该患者既往就诊记录(name:患者姓名)",
    TOOL_FINISH: "finish: 信息已足够,直接作答(不再调用其他工具)",
    TOOL_ASK_USER: "ask_user: 信息不足,需要向患者追问(结束本轮)",
}


@dataclass
class ToolResult:
    """工具执行结果。text 供模型继续推理,sources 供前端溯源展示。"""

    ok: bool = True
    text: str = ""
    refs: List[Ref] = field(default_factory=list)
    error: Optional[str] = None
    finished: bool = False   # finish/ask_user 为终止动作
    asks_user: bool = False


@dataclass
class ToolContext:
    """工具执行上下文(由 loop 注入,避免工具直接依赖 session 内部状态)"""

    user_id: int = 0
    chief_complaint: str = ""
    session_id: str = ""


def _ref_from_kb(item: dict, n: int) -> Ref:
    """知识库检索结果 -> Ref(保留稳定片段标识,供历史回放定位)"""
    text = item.get("text") or ""
    return Ref(
        n=n,
        doc_id=item.get("id") or "",
        source=item.get("source") or "未知来源",
        chunk_index=item.get("chunk_index"),
        score=float(item.get("relevance_score") or 0.0),
        quote=text[:200],
        kind=REF_KNOWLEDGE,
        strong_hit=bool(item.get("strong_hit")),
    )


def _ref_from_memory(item: dict, n: int) -> Ref:
    """记忆检索结果 -> Ref(doc_id 形如 {session_id}_t{turn_index},可回溯到具体历史轮次)"""
    return Ref(
        n=n,
        doc_id=item.get("id") or "",
        source=f"历史记忆({item.get('kind', 'turn')} · {item.get('ts', '')})",
        chunk_index=None,
        score=float(item.get("relevance_score") or 0.0),
        quote=(item.get("text") or "")[:200],
        kind=REF_MEMORY,
        session_id=item.get("session_id") or "",
    )


def _wide_consultation_search(query: str, n_results: int) -> list:
    """
    绕过 Chroma 侧 relevance_threshold 的宽召回,结构对齐 search_for_consultation 的
    return_raw 列表,供上层统一重排。

    为什么不用 search_for_consultation:它在内部先按 RELEVANCE_THRESHOLD(0.6) 砍一刀、
    再截断到 top_k。实测问「发烧能不能吃对乙酰氨基酚」时,真正含该药名的片段语义分只有
    0.49,会在砍掉的那批里 —— 后续重排再怎么加分也救不回一个没进候选的片段。
    这里直接查 collection,只开窗口、不做阈值过滤,门槛由本模块自己的证据闸控制。
    """
    col = knowledge_base.get_collection()
    if col is None:
        return []
    count = col.count()
    if not count:
        return []
    try:
        res = col.query(
            query_texts=[query],
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:  # noqa: BLE001 —— 宽召回失败不应影响主流程
        logger.warning(f"[react] 宽召回异常: {e}")
        return []

    docs = (res or {}).get("documents") or [[]]
    if not docs or not docs[0]:
        return []
    out = []
    for text, meta, dist in zip(docs[0], res["metadatas"][0], res["distances"][0]):
        meta = meta or {}
        out.append({
            "text": text,
            "source": meta.get("source", "unknown"),
            "distance": dist,
            "relevance_score": round(1 - dist, 4),
            "id": knowledge_base._derive_doc_id(meta),
            "chunk_index": meta.get("chunk_index"),
            "metadata": meta,
        })
    return out


def _kb_search_resilient(query: str, top_k: int, ctx: ToolContext, wide_n: int = 0) -> list:
    """
    kb_search 的降级重试包装。

    ChromaDB 持久化客户端在多进程(后端服务 + 脚本/测试)共用同一 data/chroma_db 时,
    偶发抛 "Could not connect to tenant default_tenant"。这类异常属于 Verbindungs状态
    问题而非知识库没数据,直接放弃会让整轮失去引用、句子级溯源全空 —— 与可解释性目标相悖。
    这里做一次「重建客户端后重试」,仍失败才返回空。

    wide_n>0 时改走 _wide_consultation_search(不受阈值影响的宽召回),用于需要
    把含关键实体(药名等)的低分片段也捞进候选的场景。
    """
    def _once() -> list:
        if wide_n:
            return _wide_consultation_search(query, wide_n)
        return knowledge_base.search_for_consultation(
            symptoms=query, chief_complaint=ctx.chief_complaint,
            top_k=top_k, return_raw=True,
        ) or []

    try:
        return _once()
    except Exception as e:
        logger.warning(f"[react] kb_search 首次检索异常,尝试重建检索客户端: {e}")
        try:
            knowledge_base.init_knowledge_base()
            return _once()
        except Exception as e2:
            logger.warning(f"[react] kb_search 重建后仍失败,本轮放弃引用: {e2}")
            return []


_CJK_SEG = re.compile(r"[\u4e00-\u9fff]+")


def _query_phrases(query: str, min_len: int) -> set:
    """
    从查询里抽出「较长的中文短语」(药名、症状名、检查项目名)。

    实测缺陷:纯向量检索在中文药名上会漏召 —— 问「发烧能不能吃对乙酰氨基酚」,
    《常用药物与用药安全》里明明写着该药名,语义排序却把它排到 top-10 之外,
    结果引用池里只剩普通感冒与痛风片段,模型只能凭常识作答。
    这里把查询中较长的中文连续片段抽出来,供检索后做精确短语加成。
    """
    phrases = set()
    for seg in _CJK_SEG.findall(query or ""):
        for i in range(len(seg) - min_len + 1):
            p = seg[i:i + min_len]
            # 滤掉「提问结构」产生的碎片:不含这些虚词的 5 字片段,
            # 大概率是药名/症状名/检查项,才配得上「精确命中」的待遇。
            if any(bad in p for bad in _PHRASE_STOPWORDS):
                continue
            phrases.add(p)
    return phrases


# 提问里高频出现、但不能作为实体依据的虚词/疑问成分
_PHRASE_STOPWORDS = (
    "可以", "什么", "怎么", "怎样", "多少", "为什么", "是否", "能否", "会不会",
    "吗", "呢", "吧", "啊", "了", "的", "是", "有", "在", "和", "与", "或", "等",
    "请问", "麻烦", "谢谢", "一下", "比较", "比较", "还是", "以及",
)


def _phrase_bonus(text: str, pid4: set, pid5: set) -> tuple:
    """
    片段文本里命中查询短语时返回 (排序加分, 是否强命中)。

    强命中 = 命中 pid5,即片段里真的写着用户问的那个实体(药名、症状名)。
    这类片段的语义分常常偏低(实测含「对乙酰氨基酚」的那条只有 0.48),
    若死守语义门槛,就会「精确的那条被拦下、沾边的那条反而入选」。
    故强命中在排序加分的同时豁免语义门槛(见 _filter_by_score 的 exact 参数)。

    pid4(4 字)命中只给小加成,不豁免 —— 实测查询里的虚词碎片(如「可以吃对」)
    也会命中不相干片段,若一并豁免,等于把门槛拱手让出。
    """
    body = text or ""
    if len(pid5) and any(p in body for p in pid5):
        return 0.20, True
    if len(pid4) and any(p in body for p in pid4):
        return 0.12, False
    return 0.0, False


def _filter_by_score(results: list, exact: set = None) -> tuple:
    """
    按相关度门槛过滤片段,返回 (达标列表, 被过滤条数)。

    防幻觉的一道闸:Chroma 侧 threshold=0.6 只挡掉了明显无关的结果,
    剩下的往往是「沾边」片段(实测最高分约 0.70),让模型拿这些当证据等于开门揖盗。

    exact: 命中查询关键词的片段 id 集合。这些片段是「精确命中」而非「语义接近」,
    实测它们的语义分反而偏低(含「对乙酰氨基酚」那条只有 0.48),
    若与沾边片段用同一把尺子量,就会出现「精确的那条被拦、沾边的那条入选」。
    故对精确命中豁免语义门槛。
    """
    if not results:
        return [], 0
    floor = getattr(config, "REACT_MIN_SCORE", 0.0)
    # 一律转成 set 再判定:生成器被第一次 in 消费完就空了,会导致后续判断全部失真。
    exact = set(exact) if exact else set()
    kept = []
    for r in results:
        if r.get("id") in exact:
            kept.append(r)
            continue
        try:
            score = float(r.get("relevance_score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        if score >= floor:
            kept.append(r)
    return kept, len(results) - len(kept)


def _kb_search(query: str, top_k: int, ctx: ToolContext) -> ToolResult:
    """知识库检索。查询词缺省时回退为主诉,保证总有可用上下文。"""
    q = (query or "").strip() or ctx.chief_complaint
    if not q:
        return ToolResult(ok=False, text="", error="empty_query")

    # 取更宽的候选集再做重排:纯向量检索会漏掉含药名/症状名的片段
    # (实测 top_k=3 时《常用药物与用药安全》排不进结果),宽召回 + 短语加成即可捞回。
    # 实测:117 片段的库里,命中「对乙酰氨基酚」的那条语义分只有 0.49,
    # 会被 search() 的 0.6 阈值挡在候选之外 —— 重排救不回没进候选的片段。
    # 所以这里走宽召回窗口,门槛仍交给下面的 _filter_by_score 决定。
    # 窗口大小按「库有多大」而不是「要几条」来定:重排只能重排已进候选的片段,
    # 实测 104 片段的库里含药名的片段排在 top-40 之外,窗口开 40 等于没捞。
    # 小体量库(本项目百级)直接全量取,成本只是一次查询,换来确定性召回。
    probe_n = max(top_k * 6, 100)
    candidates = _kb_search_resilient(q, probe_n, ctx, wide_n=probe_n) or []
    if not candidates:
        return ToolResult(ok=True, text="未命中相关医学知识片段。", refs=[])

    pid5 = _query_phrases(q, 5)
    pid4 = _query_phrases(q, 4)
    scored = []
    for r in candidates:
        bonus, strong_hit = _phrase_bonus(r.get("text") or "", pid4, pid5)
        r["strong_hit"] = strong_hit
        scored.append((float(r.get("relevance_score") or 0.0) + bonus, r))
    # 强命中(片段里真的写着用户问的实体)直接置顶,再按综合分排 ——
    # 「精确命中」是确定性事实,不该被一个 0.75 的语义分压过去。
    scored.sort(key=lambda pair: (not pair[1].get("strong_hit"), -pair[0]))
    results = [r for _, r in scored[:top_k]]

    # 必须传 set 而不是生成器:生成器被第一次 `in` 消费到末尾后即耗尽,
    # 后续判定会全部落到「不在集合里」的分支(实测只有第 3 条通过过滤)。
    kept, weak = _filter_by_score(
        results,
        exact={r.get("id") for r in results if r.get("strong_hit")},
    )
    if not kept:
        # 命中了但全都太弱:必须如实告知模型「没有可用依据」,否则它会拿片段当证据
        return ToolResult(
            ok=True,
            text=(f"命中 {len(results)} 条片段，但相关度均低于证据门槛 "
                  f"{getattr(config, 'REACT_MIN_SCORE', 0.0)}，均不作为作答依据。"),
            refs=[],
        )

    refs = [_ref_from_kb(r, i) for i, r in enumerate(kept, 1)]
    lines = []
    for r in refs:
        loc = f"#{r.chunk_index}" if r.chunk_index is not None else ""
        lines.append(
            f"[{r.n}] (来源: {r.source}{loc}, 相关度: {r.score})\n{r.quote}"
        )
    if weak:
        lines.append(f"（另有 {weak} 条低相关片段已按证据门槛过滤，未纳入依据。）")
    return ToolResult(ok=True, text="\n\n".join(lines), refs=refs)


def _memory_search(query: str, top_k: int, ctx: ToolContext) -> ToolResult:
    """跨会话记忆检索。受 ENABLE_LONG_MEMORY 开关约束,关闭时明确告知模型不可用。"""
    if not config.ENABLE_LONG_MEMORY:
        return ToolResult(ok=False, text="", error="memory_disabled")
    q = (query or "").strip() or ctx.chief_complaint
    if not q:
        return ToolResult(ok=False, text="", error="empty_query")

    results = memory_store.search_memories(
        user_id=ctx.user_id,
        query=q,
        top_k=top_k,
        exclude_session_id=ctx.session_id,
    )
    if not results:
        return ToolResult(ok=True, text="未检索到该患者的相关历史记忆。", refs=[])

    refs = [_ref_from_memory(r, i) for i, r in enumerate(results, 1)]
    lines = [
        f"[{r.n}] (时间: {r.session_id} · 相关度: {r.score})\n{r.quote}" for r in refs
    ]
    return ToolResult(ok=True, text="\n\n".join(lines), refs=refs)


def _patient_history(name: str, ctx: ToolContext) -> ToolResult:
    """既往就诊记录查询。属敏感数据,仅展示摘要,不整段回显。"""
    n = (name or "").strip()
    if not n:
        return ToolResult(ok=False, text="", error="empty_name")
    try:
        records = database.query_patient(n, user_id=ctx.user_id)
    except Exception as e:  # 查询失败不得中断主流程
        logger.warning(f"[react] patient_history 查询失败: {e}")
        return ToolResult(ok=False, text="", error="query_failed")

    if not records:
        return ToolResult(ok=True, text=f"未查到患者「{n}」的历史就诊记录。", refs=[])

    lines = []
    for i, rec in enumerate(records[:5], 1):
        visit = rec.get("visit_date") or rec.get("created_at") or "时间未知"
        complaint = rec.get("chief_complaint") or ""
        diagnosis = rec.get("diagnosis") or ""
        # 仅回显必要字段,病史详情不整段透出(与既有加密策略一致)
        lines.append(f"[{i}] {visit} 主诉: {complaint[:40]} 诊断: {diagnosis[:40]}")
    return ToolResult(ok=True, text="\n\n".join(lines), refs=[])


# ==================== 统一入口 ====================

def execute_tool(name: str, args: dict, ctx: ToolContext) -> ToolResult:
    """
    执行工具。白名单外的工具名一律拒绝(防止 Planner 臆造动作)。
    任何异常都收敛为 ToolResult(ok=False),由 loop 层降级处理。
    """
    args = args or {}
    try:
        if name == TOOL_KB_SEARCH:
            return _kb_search(args.get("query", ""), int(args.get("top_k", 3) or 3), ctx)
        if name == TOOL_MEMORY_SEARCH:
            return _memory_search(args.get("query", ""), int(args.get("top_k", 3) or 3), ctx)
        if name == TOOL_PATIENT_HISTORY:
            return _patient_history(args.get("name", ""), ctx)
        if name == TOOL_FINISH:
            return ToolResult(finished=True, text="信息已收集完毕,准备作答。")
        if name == TOOL_ASK_USER:
            return ToolResult(finished=True, asks_user=True, text="需要向患者追问更多信息。")
    except Exception as e:
        logger.warning(f"[react] 工具 {name} 执行异常: {e}")
        return ToolResult(ok=False, text="", error=str(e)[:200])
    return ToolResult(ok=False, text="", error=f"unknown_tool:{name}")


def describe_tools() -> str:
    """给 Planner 的工具清单描述(供提示词使用)。"""
    return "\n".join(f"- {v}" for v in TOOL_WHITELIST.values())

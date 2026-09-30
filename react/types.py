"""ReAct 推理过程的数据结构与溯源解析

对齐项目既有风格:dataclass + 中文注释 + 字段全部可选以便向后兼容。
"""

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional


# 单次推理步骤的类型
STEP_THOUGHT = "thought"        # Planner 的思考
STEP_ACTION = "action"          # 执行的动作
STEP_OBSERVATION = "observation"  # 工具真实返回
STEP_FINAL = "final"            # 终答开始/结束
STEP_FALLBACK = "fallback"      # 降级说明(例如 Planner 解析失败)
STEP_NOTE = "note"              # 系统提示步骤(分支说明、缺失原因)

# 步骤状态
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_TIMEOUT = "timeout"
STATUS_SKIPPED = "skipped"

# 引用来源类型
REF_KNOWLEDGE = "kb"
REF_MEMORY = "memory"


@dataclass
class Ref:
    """知识溯源引用:一个被引用的知识片段(或记忆片段)"""

    n: int                      # 本轮序号 [n]
    doc_id: str                 # 稳定片段标识:知识库为 {文件名}_chunk_{i},记忆为 {session_id}_t{n}
    source: str                 # 来源文件名 / 记忆所属会话标识
    chunk_index: Optional[int] = None   # 文件内片段序号
    score: float = 0.0          # 相似度
    quote: str = ""             # 前 200 字摘录(仅展示用,不落全文)
    kind: str = REF_KNOWLEDGE   # kb / memory
    session_id: str = ""        # 仅记忆引用时有值(用于回溯到具体历史会话)
    # 命中了查询里的关键实体(药名/症状名)。这类片段语义分往往偏低却最对症，
    # 在 tools 侧已豁免证据门槛,这里带上以便 loop 的引用池也认同一把尺子。
    strong_hit: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Step:
    """推理过程的一步。seq 由执行层单调递增发放,保证顺序可追溯。"""

    type: str
    # seq 由执行层(_emit)单调递增发放;给默认值是为了「任何一步构造失败都不得拖垮整轮推理」
    seq: int = 0
    text: str = ""
    ts: str = ""                # 系统时间 ISO8601(禁止模型生成时间)
    elapsed_ms: int = 0         # 本步耗时
    status: str = STATUS_OK
    tool: Optional[str] = None  # action 步骤的工具名
    args: Optional[dict] = None  # action 参数(脱敏后)
    refs: List[Ref] = field(default_factory=list)  # 本步引用的知识片段
    sentences: Optional[list] = None  # 终答步骤的句子级溯源结果
    error: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["refs"] = [r.to_dict() for r in self.refs]
        return d


@dataclass
class Trace:
    """一轮问答的完整推理轨迹"""

    trace_id: str               # {session_id}#{turn_index}
    session_id: str
    turn_index: int
    steps: List[Step] = field(default_factory=list)
    total_ms: int = 0
    enabled: bool = False       # 是否真的走了 ReAct(false = 降级/未启用)
    branch: str = "direct_qa"   # direct_qa / intake / emergency
    fallback_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "turn_index": self.turn_index,
            "steps": [s.to_dict() for s in self.steps],
            "total_ms": self.total_ms,
            "enabled": self.enabled,
            "branch": self.branch,
            "fallback_reason": self.fallback_reason,
        }


# ==================== 时间工具 ====================

def now_iso() -> str:
    """系统时间 ISO8601(带时区)。沿用项目「日期时间一律来自系统、不得由模型生成」的铁律。"""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


# ==================== 句子级溯源解析 ====================

# 中英文句号/问号/感叹号/分号/换行处切句,保留标点
_SENT_SPLIT_RE = re.compile(r"(?<=[。！？!?；;\n])")
# 引用标记,如 [1] [2,3] [1][2]
_CITE_RE = re.compile(r"\[(\d+)(?:[,，、](\d+))*\]")


def split_sentences(text: str) -> List[str]:
    """把正文切成句子(保留句尾标点),用于句子级溯源绑定。"""
    if not text:
        return []
    parts = _SENT_SPLIT_RE.split(text)
    out = []
    for p in parts:
        s = p.strip()
        if s:
            out.append(s)
    return out


def extract_cites(sentence: str) -> List[int]:
    """抽取句子里引用的编号 [n],返回升序去重列表。"""
    nums = []
    for m in _CITE_RE.finditer(sentence):
        for g in m.groups():
            if g:
                try:
                    nums.append(int(g))
                except ValueError:
                    continue
    return sorted({n for n in nums if n > 0})


def strip_undefined_cites(text: str, valid_nums: set) -> tuple:
    """
    剥离正文里未定义的引用编号,返回 ( cleaned_text, 被剥离的编号列表 )。
    用于防止小模型乱标 [9] 这类不存在来源的编号。
    """
    removed = []

    def _repl(m):
        found = []
        for g in m.groups():
            if g:
                try:
                    found.append(int(g))
                except ValueError:
                    pass
        if any(n in valid_nums for n in found):
            return m.group(0)
        removed.extend(found)
        return ""

    cleaned = _CITE_RE.sub(_repl, text)
    return cleaned, sorted({n for n in removed if n > 0})


def build_sentence_trace(reply: str, refs: List[Ref]) -> list:
    """
    句子级溯源:把终答正文逐句拆开,绑定每句引用的片段。

    返回的每一项:
      {"text": 原句(已剥离未定义编号), "refs": [Ref...], "cited": 是否引用了知识片段,
       "inferred": 来源是否为系统按字面重合度推断绑定(非模型显式引用)}
    未引用任何片段的句子 cited=False,前端显示为「无直接来源」而不是丢弃,
    这样保证"不丢内容",用户也能看出哪些句子是通用表述。
    """
    # 只有知识库片段算「医学依据」。记忆(既往对话)与就诊记录属于个人史,
    # 它们不是医学出处,却同样会占 [n] 编号 —— 混进来等于把个人史伪装成有知识出处,
    # 是防幻觉的缺口(实测:记忆引用让终答显示 0 句带知识来源,但用户以为有出处)。
    evidence = [r for r in refs if r.kind == REF_KNOWLEDGE]
    valid = {r.n for r in evidence}
    body, _ = strip_undefined_cites(reply, valid)
    out = []
    for sent in split_sentences(body):
        nums = extract_cites(sent)
        bound = [r for r in evidence if r.n in nums]
        out.append({
            "text": sent,
            "refs": [r.to_dict() for r in bound],
            "cited": bool(bound),
        })
    if not out and body.strip():
        out.append({"text": body.strip(), "refs": [], "cited": False})

    # 兜底绑定:模型漏写 [n] 时(实测 qwen2.5:7b 高发),按「句↔片段字面重合度」
    # 就近挂源,保证句子级溯源不为空 —— 溯源是可解释性的硬要求,不能依赖模型自觉。
    #
    # 但它是「推断」不是「引用」:模型并没有声明出自该片段。若照旧标 cited=True,
    # 等于把通用表述伪造成有知识出处,与防幻觉目标直接冲突。因此这里改为:
    # 挂上来源(用户仍可查证) + cited=False(不算作有依据) + inferred=True(标明推断)。
    if evidence and not any(s.get("cited") for s in out):
        for s in out:
            hit = _match_ref_by_overlap(s["text"], evidence)
            if hit:
                s["refs"] = [hit.to_dict()]
                s["cited"] = False
                s["inferred"] = True
    return out


# 兜底绑定的重合度阈值:低于此值视为「通用表述」,不给挂源,避免出现伪溯源
_OVERLAP_MIN_RATIO = 0.30
_OVERLAP_MIN_SHARED = 3


def _tokens(text: str) -> set:
    """中文按字符二元切分,英文/数字按词切分,用于重合度计算。"""
    text = re.sub(r"[\[\]()（）《》「」、，。！？；：\s]+", "", text or "")
    cn = re.findall(r"[\u4e00-\u9fff]+", text)
    toks = set()
    for seg in cn:
        if len(seg) == 1:
            toks.add(seg)
        else:
            toks.update(seg[i:i + 2] for i in range(len(seg) - 1))
    toks.update(w.lower() for w in re.findall(r"[A-Za-z]+|\d+", text))
    # 单字中文 token 太宽泛(如"之""的"),只作为补充权重来源剔除,避免误判
    toks.difference_update({"的", "了", "是", "在", "和", "对", "与", "为", "可"})
    return toks


def _match_ref_by_overlap(sentence: str, refs: List[Ref]) -> Optional[Ref]:
    """
    用字面重合度给单句找一个来源片段:命中片段的 quote 与句子共有的 token 占比
    达到阈值即认为该句出自该片段。取重合度最高的那个引用。
    """
    stok = _tokens(sentence)
    if not stok:
        return None
    best, best_score = None, 0.0
    for r in refs:
        rtok = _tokens(r.quote)
        if not rtok:
            continue
        shared = stok & rtok
        if len(shared) < _OVERLAP_MIN_SHARED:
            continue
        # 双向取小,防止短片段被长句子轻易"命中"
        score = len(shared) / min(len(stok), len(rtok))
        if score >= _OVERLAP_MIN_RATIO and score > best_score:
            best, best_score = r, score
    return best

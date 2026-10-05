"""
问诊逻辑模块 - 医学问诊智能体
实现5阶段状态机的多轮问诊流程

优化：将3次LLM调用合并为1次，大幅降低延迟
"""

import asyncio
import json
import logging
import re
import threading
from typing import Optional

import config
import database
import llm_client
import knowledge_base
import memory_store
import report_generator
from react import loop as react_loop

logger = logging.getLogger(__name__)


# ==================== 流式可见文本过滤器 ====================

class _VisibleStreamFilter:
    """
    流式输出过滤器：只把「用户应该看到的正文」逐字透出给前端。

    解决的问题：
    1. deepseek-r1 等推理模型会把 <think>...</think> 思维链混在正文里；
    2. 问诊提示词要求模型在回复末尾附【JSON块】{...} 结构化数据，
       若原样流式转发，用户会看到一堆 JSON 代码。

    实现要点：
    - 逐字符状态机，跨 chunk 边界也不会漏判（标记可能被切成两半）
    - 命中隐藏标记后进入隐藏态，直到标记对应的结束条件满足才恢复
    - 未确定是否为标记前缀的尾部字符会暂存在缓冲区，避免提前吐出半个标记
    """

    _THINK_OPEN = "<think>"
    _THINK_CLOSE = "</think>"
    _FENCE = "```"
    # 中文/变体 JSON 块标记（提示词约定 JSON 放在回复最末尾）
    _JSON_MARKERS = ("【JSON块】", "【JSON】", "【json块】", "[JSON]", "【结构化数据】")

    _MAX_HOLD = max(
        len(_THINK_OPEN), len(_THINK_CLOSE), len(_FENCE),
        max(len(m) for m in _JSON_MARKERS)
    )

    def __init__(self):
        self._pending = ""      # 暂存区（可能是标记前缀）
        self._state = "text"    # text | think | fence | json
        self._depth = 0         # json 态下的花括号深度
        self._brace_seen = False
        self._skip_nl = False   # 代码块闭合后吞掉紧随的一个换行，避免多出空行
        self._cand_at = None    # 疑似 JSON 起始位置（裸 { 无标记时的候选态）
        self._CAND_MAX = 64     # 候选态最长观望长度，超过则判定为普通文本

    # --- 内部工具 ---
    def _markers(self):
        return tuple(self._JSON_MARKERS) + (self._THINK_OPEN, self._FENCE)

    def _flush_safe(self) -> str:
        """输出不可能再构成任何标记前缀的前半部分，尾巴留在暂存区"""
        if not self._pending:
            return ""
        hold = 0
        upper = min(len(self._pending), self._MAX_HOLD)
        for k in range(upper, 0, -1):
            tail = self._pending[-k:]
            if any(m.startswith(tail) for m in self._markers()):
                hold = k
                break
        if hold:
            safe = self._pending[:-hold]
            self._pending = self._pending[-hold:]
        else:
            safe = self._pending
            self._pending = ""
        return safe

    def _tail_keep(self, text: str, keep: str) -> None:
        """隐藏态下的尾部裁剪：只保留可能构成结束标记的后缀长度"""
        self._pending += text
        if len(self._pending) > len(keep):
            self._pending = self._pending[-len(keep):]

    # --- 对外接口 ---
    def feed(self, chunk: str) -> str:
        """喂入一段流式文本，返回应当展示给用户的部分"""
        if not chunk:
            return ""
        out = []
        for ch in chunk:
            if self._state == "think":
                self._tail_keep(ch, self._THINK_CLOSE)
                if self._pending.endswith(self._THINK_CLOSE):
                    self._pending = ""
                    self._state = "text"
                continue

            if self._state == "fence":
                self._tail_keep(ch, self._FENCE)
                if self._pending.endswith(self._FENCE):
                    self._pending = ""
                    self._state = "text"
                    self._skip_nl = True
                continue

            if self._state == "json":
                # 等待 JSON 对象的花括号闭合，闭合后恢复正常文本
                if ch == "{":
                    self._depth += 1
                    self._brace_seen = True
                elif ch == "}":
                    self._depth -= 1
                    if self._brace_seen and self._depth <= 0:
                        self._state = "text"
                        self._pending = ""
                        self._depth = 0
                        self._brace_seen = False
                continue

            # state == candidate：看到裸 { 后短暂观望，判断是否为 JSON 对象
            if self._state == "candidate":
                self._pending += ch
                if ch in " \t\r\n":
                    # 空白不提供信息，继续观望（但设上限，避免长段文本被卡住）
                    if len(self._pending) - self._cand_at > self._CAND_MAX:
                        self._state = "text"
                        self._cand_at = None
                    continue
                if ch == '"' or ch == '}' or ch == '“':
                    # 确认是 JSON 对象（首字符为键名引号或空对象），丢弃候选片段进入隐藏态
                    self._pending = self._pending[:self._cand_at]
                    self._cand_at = None
                    if ch == '}':
                        self._state = "text"   # 空对象 {}, 直接结束
                    else:
                        self._state = "json"
                        self._depth = 1
                        self._brace_seen = True
                    continue
                # 不是 JSON（如正文里出现的普通花括号），恢复普通文本
                self._state = "text"
                self._cand_at = None
                continue

            # state == text
            if self._skip_nl:
                self._skip_nl = False
                if ch == "\n":
                    continue
            self._pending += ch
            if ch == "{":
                # 裸 {：进入候选态观望，判断后面是不是 JSON 对象的键名
                self._state = "candidate"
                self._cand_at = len(self._pending) - 1
                continue
            if any(self._pending.endswith(m) for m in self._JSON_MARKERS):
                self._pending = ""
                self._state = "json"
                self._depth = 0
                self._brace_seen = False
                continue
            if self._pending.endswith(self._THINK_OPEN):
                self._pending = ""
                self._state = "think"
                continue
            if self._pending.endswith(self._FENCE):
                self._pending = ""
                self._state = "fence"
                continue
            out.append(self._flush_safe())
        return "".join(out)

    def flush(self) -> str:
        """流结束时把暂存区剩余文本吐出（同时清理残留标记）"""
        tail = self._pending if self._state in ("text", "candidate") else ""
        self._pending = ""
        if not tail:
            return ""
        tail = re.sub(r"【JSON[块]?】\s*", "", tail)
        tail = re.sub(r"\[JSON\]\s*", "", tail)
        return tail

    @property
    def hidden(self) -> bool:
        """当前是否处于隐藏态（供调用方判断是否已开始输出正文）"""
        return self._state != "text"


class ConsultationState:
    """问诊阶段常量"""
    STAGE_BASIC_INFO = 1       # 收集基本信息（姓名、性别、年龄、初步主诉）
    STAGE_CHIEF_COMPLAINT = 2  # 主诉和现病史
    STAGE_HISTORY = 3          # 既往史/个人史/家族史
    STAGE_REVIEW = 4           # 系统回顾
    STAGE_COMPLETE = 5         # 问诊完成，生成报告

    # ---- 阶段推进兜底参数 ----
    # 实测 qwen2.5:7b-instruct 存在两类行为：① 某些轮次完全不输出 JSON 块；
    # ② 信息已收齐仍持续返回 stage_complete=false。纯 LLM 驱动的状态机会因此
    # 永久卡死在 stage 1 —— 问诊永远出不了报告，「记录」页永远为空。
    # 故附加确定性规则：满足条件即推进，超过上限无条件推进。
    STAGE_MIN_TURNS = {1: 1, 2: 2, 3: 1, 4: 1}   # 达到该回合数才允许按「字段已齐」推进
    STAGE_MAX_TURNS = {1: 4, 2: 5, 3: 4, 4: 3}   # 达到该回合数无条件推进（防死锁）


# ==================== 合并后的统一提示词 ====================

SYSTEM_PROMPT_GLOBAL = """你是一位专业的医学问诊AI助手。你的任务是通过友好的对话，系统性地收集患者的健康信息，为后续诊断提供完整依据。

核心原则：
1. 一次只问1-2个问题，不要一次问太多
2. 语气温和专业，像一位耐心的医生
3. 根据患者回答灵活追问，不要机械地照本宣科
4. 如果患者提到紧急症状（胸痛、呼吸困难、意识丧失、大出血等），立即提醒就医
5. 不要给出明确诊断，只收集信息
6. 用中文交流
7. 当你判断某个阶段的信息已经充分时，主动过渡到下一阶段
8. 【铁律·禁止重复询问】上下文里标注为「已收集」「已确认」的信息，患者已经回答过了。
   除非患者本人明确更正，否则**绝不允许**再次询问、复述确认或换个说法再问一遍。
   这是最高优先级约束 —— 重复问同一个问题会让患者认为你没在听他说话。
   你应当基于已有信息继续推进到尚未了解的内容。

【重要】你必须在回复的最末尾附上一个JSON块，格式如下：
```json
{
    "patient_name": "患者姓名（如未提及则为空字符串）",
    "patient_gender": "性别（如未提及则为空字符串）",
    "patient_age": "年龄（如未提及则为0）",
    "chief_complaint": "主诉（简洁概括）",
    "present_illness": "现病史详情",
    "past_history": "既往史（如未提及则为空字符串）",
    "personal_history": "个人史（如未提及则为空字符串）",
    "family_history": "家族史（如未提及则为空字符串）",
    "system_review": "系统回顾（如未提及则为空字符串）",
    "stage_complete": false,
    "next_stage": 1
}
```
其中：
- stage_complete: 当前阶段信息是否已收集充分（true/false）
- next_stage: 建议的下一阶段编号（1=基本信息 2=主诉现病史 3=既往史 4=系统回顾 5=完成）
- 只提取对话中明确提到的信息，不要推测或编造
- JSON块必须放在回复的最末尾
"""

SYSTEM_PROMPT_STAGE_1 = SYSTEM_PROMPT_GLOBAL + """
【当前阶段：收集基本信息】
你需要收集以下信息：
- 患者姓名
- 性别
- 年龄
- 初步主诉（来看什么问题）

请以友好的方式开始问诊。首次问候时，先自我介绍，然后请对方提供姓名和来诊原因。
如果患者一次提供了多个信息，确认后直接进入下一阶段。
当姓名、性别、年龄、初步主诉都收集完毕后，将 stage_complete 设为 true，next_stage 设为 2。
"""

SYSTEM_PROMPT_STAGE_2 = SYSTEM_PROMPT_GLOBAL + """
【当前阶段：主诉和现病史】
患者基本信息已收集。现在你需要深入了解主诉和现病史，包括：
- 症状的具体部位
- 症状的性质（如疼痛是钝痛、刺痛、烧灼痛等）
- 发作时间和频率（什么时候开始的、持续多久、是否反复发作）
- 可能的诱因（什么情况下会加重或诱发）
- 伴随症状（除了主要症状还有什么不舒服）
- 缓解因素（什么情况下会好转）
- 是否曾就诊或用药，效果如何

注意：
1. 根据患者的初步主诉有针对性地提问
2. 不要一次问所有问题，分2-3轮逐步了解
3. 追问细节，比如疼痛的程度（1-10分）、部位是否转移等
4. 当你认为现病史信息足够详细时，将 stage_complete 设为 true，next_stage 设为 3
"""

SYSTEM_PROMPT_STAGE_3 = SYSTEM_PROMPT_GLOBAL + """
【当前阶段：既往史/个人史/家族史】
现病史已收集完毕。现在需要了解与主诉相关的既往史、个人史和家族史：

既往史需要了解：
- 以前是否有过类似的症状或疾病
- 是否有慢性疾病（如高血压、糖尿病、心脏病等）
- 手术史、外伤史
- 药物过敏史

个人史需要了解（只问与主诉相关的）：
- 吸烟、饮酒情况
- 职业暴露
- 生活习惯

家族史需要了解（只问与主诉相关的）：
- 家族中是否有类似疾病
- 家族中是否有遗传性疾病

重要原则：只问与当前主诉可能相关的内容，不要问无关问题。
如果患者主诉是感冒，就不需要详细问家族史。
当相关病史信息收集完毕后，将 stage_complete 设为 true，next_stage 设为 4。
"""

SYSTEM_PROMPT_STAGE_4 = SYSTEM_PROMPT_GLOBAL + """
【当前阶段：系统回顾】
既往史已收集。现在需要进行针对性的系统回顾。

只问与主诉相关的身体系统，例如：
- 如果是呼吸系统主诉→问呼吸系统相关症状
- 如果是消化系统主诉→问消化系统相关症状
- 如果是心血管系统主诉→问心血管系统相关症状

不要对所有系统都做回顾，只针对2-3个最相关的系统简要询问。
每个系统只问1-2个关键问题。

当你认为系统回顾信息已经充分时，将 stage_complete 设为 true，next_stage 设为 5。
"""


# ==================== 直接问答（意图识别命中时）====================
# 用于用户提出具体医学问题（用药/症状/疾病咨询）时，直接回答而非机械追问。

DIRECT_QA_SYSTEM = """你是一位严谨的医学健康咨询助手。用户正在问诊过程中提出了一个具体的医学问题（如用药、症状、疾病、护理等），请直接、有针对性地回答，不要反问、不要套用问诊流程。

要求：
1. 直接回应用户的问题，给出清晰、可操作的科普性建议。
2. 涉及具体药物时，只说明常见非处方药的大致用途与注意事项；明确拒绝开具具体处方或剂量方案，处方药必须建议就医由医生决定。
3. 不提供明确诊断，提醒用户最终以医生面诊为准。
4. 如问题涉及紧急/严重情况，提示立即就医。
5. 回答简洁（3-6 句），用中文，语气温和专业。
6. 文末附一句：⚠️ 以上为健康科普，不能替代医生诊断。
7. 【铁律·依据优先】只能依据上文「【检索到的资料】」作答。资料未覆盖的内容，一律不得推测，也不得用通用医学常识自行补全。
8. 【铁律·零命中拒答】若没有任何可用资料，必须原样输出「知识库未覆盖，建议就医。」，不得改写、不得增减。
9. 【铁律·范围边界】本助手只覆盖用药、症状、疾病、日常护理等健康科普；问题超出该范围时，先说明边界，再建议用户描述具体健康问题或及时就医。
"""

# 意图分类用关键词（规则优先，零额外 LLM 开销）
_QA_INTERROGATIVES = [
    "什么", "怎么", "如何", "哪些", "为什么", "能否", "可以吗", "应该",
    "是不是", "是否", "多少", "哪个", "哪种", "怎么办", "有何", "哪里",
]
_QA_KEYWORDS = [
    "药物", "用药", "吃什么药", "吃什么", "退烧", "止痛", "缓解", "治疗",
    "症状", "疾病", "偏方", "剂量", "副作用", "能不能吃", "可以吃",
    "注意事项", "食疗", "护理",
]


class ConsultationSession:
    """
    问诊会话类 - 管理5阶段问诊的状态和流程
    优化：每次用户输入只调用1次LLM，而非3次
    """

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.user_id = 0          # 小程序模式:归属用户(0=未鉴权/桌面模式)
        self.stage = ConsultationState.STAGE_BASIC_INFO
        self.patient_name = ""
        self.patient_gender = ""
        self.patient_age = 0
        self.chief_complaint = ""
        self.present_illness = ""
        self.past_history = ""
        self.personal_history = ""
        self.family_history = ""
        self.system_review = ""
        self.diagnosis = ""
        self.conversation_history = []  # [{"role": "user/assistant", "content": "..."}]
        self.is_complete = False
        self.history_data = None  # 从数据库查到的历史记录
        self.report = ""          # 最终报告
        # 报告生成状态机: none(未触发)/pending(已排队)/running(生成中)/done/failed。
        # 报告由后台任务生成(见 maybe_start_report_task),不随 SSE 断开而中断。
        self.report_status = "none"
        self._greeted = False     # 是否已打过招呼
        self._remember_task = None  # 后台记忆写入任务(避免被 GC)
        self._report_task = None    # 后台报告生成任务(避免被 GC)
        self._stage_turns = 0     # 当前阶段已进行的回合数(供阶段推进兜底判定)
        # 是否从登录资料预填了性别/年龄(仅影响提示词,不参与序列化)
        self.profile_prefilled = False

    # ==================== 序列化(供会话持久化)====================
    def to_dict(self) -> dict:
        """序列化为 dict(明文,供 session_service 加密后落库)"""
        return {
            "stage": self.stage,
            "patient_name": self.patient_name,
            "patient_gender": self.patient_gender,
            "patient_age": self.patient_age,
            "chief_complaint": self.chief_complaint,
            "present_illness": self.present_illness,
            "past_history": self.past_history,
            "personal_history": self.personal_history,
            "family_history": self.family_history,
            "system_review": self.system_review,
            "diagnosis": self.diagnosis,
            "conversation_history": json.dumps(self.conversation_history, ensure_ascii=False),
            "is_complete": self.is_complete,
            "report": self.report,
            "report_status": self.report_status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConsultationSession":
        """从 dict 反序列化(解密后的明文,供 session_service 恢复)"""
        session = cls(session_id=d.get("session_id", "default"))
        session.user_id = d.get("user_id", 0)
        session.stage = d.get("stage", ConsultationState.STAGE_BASIC_INFO)
        session.patient_name = d.get("patient_name", "") or ""
        session.patient_gender = d.get("patient_gender", "") or ""
        session.patient_age = d.get("patient_age", 0) or 0
        session.chief_complaint = d.get("chief_complaint", "") or ""
        session.present_illness = d.get("present_illness", "") or ""
        session.past_history = d.get("past_history", "") or ""
        session.personal_history = d.get("personal_history", "") or ""
        session.family_history = d.get("family_history", "") or ""
        session.system_review = d.get("system_review", "") or ""
        session.diagnosis = d.get("diagnosis", "") or ""
        session.conversation_history = d.get("conversation_history") or []
        session.is_complete = bool(d.get("is_complete", False))
        session.report = d.get("report", "") or ""
        # 兼容旧数据:无 report_status 字段时,按 report 是否已存在推导
        # (有报告=done;无报告且已完成=pending 交由 maybe_start_report_task 重触发)
        if "report_status" in d and d.get("report_status"):
            session.report_status = d["report_status"]
        elif session.report:
            session.report_status = "done"
        elif session.is_complete:
            session.report_status = "pending"
        else:
            session.report_status = "none"
        session._greeted = True  # 恢复的会话视为已打招呼
        return session

    def _get_system_prompt(self) -> str:
        """根据当前阶段获取系统提示词"""
        stage_prompts = {
            ConsultationState.STAGE_BASIC_INFO: SYSTEM_PROMPT_STAGE_1,
            ConsultationState.STAGE_CHIEF_COMPLAINT: SYSTEM_PROMPT_STAGE_2,
            ConsultationState.STAGE_HISTORY: SYSTEM_PROMPT_STAGE_3,
            ConsultationState.STAGE_REVIEW: SYSTEM_PROMPT_STAGE_4,
            ConsultationState.STAGE_COMPLETE: SYSTEM_PROMPT_GLOBAL + "问诊已完成，等待生成报告。",
        }
        return stage_prompts.get(self.stage, SYSTEM_PROMPT_GLOBAL)

    def _check_emergency(self, text: str) -> Optional[str]:
        """
        检查用户输入中是否包含紧急症状关键词
        Returns:
            紧急提醒文本，如无紧急症状则返回 None
        """
        for keyword in config.EMERGENCY_KEYWORDS:
            if keyword in text:
                return (
                    f"⚠️ 紧急提醒：您提到了「{keyword}」，这可能需要紧急医疗处理！\n"
                    "如果您或您身边的人正在经历这些症状，请立即拨打120急救电话或前往最近的急诊！\n"
                    "生命安全第一，请先确保得到及时的医疗救助。\n\n"
                    "在确保安全的前提下，我可以继续帮您记录症状信息。"
                )
        return None

    async def _notify_family_emergency(self, emergency_text: str):
        """(协程)触发家庭成员紧急推送,异常隔离,不污染问诊主流程。"""
        try:
            from app.services import family_service
            await family_service.notify_emergency(self.user_id, emergency_text)
        except Exception as e:  # 推送失败绝不能影响问诊回复
            logger.error(f"[family] 紧急推送失败: {e}")

    def _fire_family_emergency(self, emergency_text: str):
        """
        非阻塞地触发家庭成员紧急推送。
        在异步上下文(流式问诊)用 create_task;在纯同步上下文(遗留桌面分支)
        起守护线程跑独立事件循环,均不阻塞问诊回复。
        """
        if self.user_id in (0, None):
            return  # 未鉴权 / 桌面模式(无归属用户)不推送
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._notify_family_emergency(emergency_text))
                return
        except RuntimeError:
            pass
        threading.Thread(
            target=lambda: asyncio.run(self._notify_family_emergency(emergency_text)),
            daemon=True,
        ).start()

    def _parse_llm_response(self, raw_response: str) -> tuple:
        """
        从LLM回复中分离出：对话文本 和 结构化JSON数据
        Returns:
            (display_text, extracted_info)
        """
        display_text = raw_response
        extracted_info = {}

        # 尝试从回复末尾提取JSON块
        # 匹配多种格式：```json ... ```、``` ... ```、【JSON块】... 等
        json_patterns = [
            r'```json\s*\n(.*?)\n\s*```',
            r'```\s*\n(.*?)\n\s*```',
        ]

        json_str = None
        json_start_pos = -1  # JSON块在原文中的起始位置，用于截断显示文本

        for pattern in json_patterns:
            matches = list(re.finditer(pattern, raw_response, re.DOTALL))
            if matches:
                last_match = matches[-1]
                json_str = last_match.group(1)
                json_start_pos = last_match.start()
                break

        # 尝试匹配 【JSON块】 或 【JSON】 等中文标记格式
        if json_str is None:
            cn_patterns = [
                r'【JSON[块]?】\s*\n?',
                r'\[JSON\]\s*\n?',
            ]
            for cn_pat in cn_patterns:
                match = re.search(cn_pat, raw_response)
                if match:
                    json_start_pos = match.start()
                    remaining = raw_response[match.end():]
                    # 从剩余文本中找 { ... }
                    brace_pos = remaining.find('{')
                    if brace_pos != -1:
                        depth = 0
                        for i in range(brace_pos, len(remaining)):
                            if remaining[i] == '{':
                                depth += 1
                            elif remaining[i] == '}':
                                depth -= 1
                                if depth == 0:
                                    json_str = remaining[brace_pos:i+1]
                                    break
                    break

        # 如果没找到代码块格式，尝试找最后一个 { ... } 块
        if json_str is None:
            last_brace = raw_response.rfind('{')
            if last_brace != -1:
                depth = 0
                for i in range(last_brace, len(raw_response)):
                    if raw_response[i] == '{':
                        depth += 1
                    elif raw_response[i] == '}':
                        depth -= 1
                        if depth == 0:
                            json_str = raw_response[last_brace:i+1]
                            json_start_pos = last_brace
                            break

        if json_str:
            try:
                extracted_info = json.loads(json_str)
                # 从显示文本中移除JSON块
                if json_start_pos > 0:
                    display_text = raw_response[:json_start_pos].rstrip()
                else:
                    for pattern in json_patterns:
                        display_text = re.sub(pattern, '', display_text, flags=re.DOTALL)
                # 清理残留的中文标记
                display_text = re.sub(r'【JSON[块]?】\s*', '', display_text)
                display_text = re.sub(r'\[JSON\]\s*', '', display_text)
                display_text = display_text.strip()
                # 清理末尾的 <think>...</think> 标签（deepseek-r1 推理模型特有）
                display_text = re.sub(r'<think>.*?</think>', '', display_text, flags=re.DOTALL)
                display_text = display_text.strip()
            except json.JSONDecodeError:
                logger.debug("LLM回复中的JSON解析失败，忽略结构化数据")

        # 清理 deepseek-r1 的 <think> 标签（无论JSON是否解析成功）
        display_text = re.sub(r'<think>.*?</think>', '', display_text, flags=re.DOTALL)
        display_text = display_text.strip()

        return display_text, extracted_info

    @staticmethod
    def _normalize_age(value) -> int:
        """
        归一化年龄为 int。

        提示词 JSON 模板里 patient_age 写在引号内（"年龄（如未提及则为0）"），
        模型会照抄模板输出字符串 "35"；个别模型还会输出 "35岁"。
        原实现 `info["patient_age"] > 0` 会让 str 与 int 比较直接抛 TypeError。
        """
        if value is None:
            return 0
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        matched = re.search(r"\d+", str(value))
        return int(matched.group()) if matched else 0

    @staticmethod
    def _as_bool(value) -> bool:
        """
        归一化布尔字段。字符串 "false" 在 Python 里是真值，直接 truthy 判断会让
        尚未收集齐的阶段被误判为完成。
        """
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in ("true", "yes", "y", "1", "是")

    @staticmethod
    def _normalize_stage(value, default: int) -> int:
        """归一化阶段号为 int（模型可能输出 "2" 这类带引号的数字）。"""
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
            return value
        matched = re.search(r"\d+", str(value)) if value is not None else None
        return int(matched.group()) if matched else default

    def _stage_data_ready(self) -> bool:
        """判断当前阶段的必填信息是否已收集齐（用于推进兜底）"""
        stage = self.stage
        if stage == ConsultationState.STAGE_BASIC_INFO:
            return bool(self.patient_name and self.patient_gender
                        and self.patient_age and self.chief_complaint)
        if stage == ConsultationState.STAGE_CHIEF_COMPLAINT:
            return len(self.present_illness or "") >= 15
        if stage == ConsultationState.STAGE_HISTORY:
            return bool(self.past_history or self.personal_history or self.family_history)
        if stage == ConsultationState.STAGE_REVIEW:
            return bool(self.system_review)
        return False

    def _fallback_stage_advance(self, display_text: str = "") -> bool:
        """
        LLM 未给出有效阶段判定时的确定性推进兜底。

        触发场景（实测高频）：
          1) 模型某轮完全没输出 JSON 块 → extracted_info 为空；
          2) 模型持续返回 stage_complete=false，即使本阶段信息已收集齐。
        两者都会让 stage 长期停在 1 → is_complete 永不为真 → 报告与「记录」永不生成。

        Returns: 是否发生了推进
        """
        if not getattr(config, "ENABLE_STAGE_GUARD", True):
            return False

        stage = self.stage
        if stage >= ConsultationState.STAGE_COMPLETE:
            return False

        self._stage_turns += 1
        min_turns = ConsultationState.STAGE_MIN_TURNS.get(stage, 2)
        max_turns = ConsultationState.STAGE_MAX_TURNS.get(stage, 4)
        ready = self._stage_data_ready()
        overdue = self._stage_turns >= max_turns

        if not ((ready and self._stage_turns >= min_turns) or overdue):
            return False

        target = min(stage + 1, ConsultationState.STAGE_COMPLETE)
        # 进入终末阶段(=触发报告生成)门槛更高:数据齐备 且 本轮没有再向患者提问。
        # 超时兜底只允许推进到 STAGE_REVIEW,不能在信息缺失或问题未回答时强行完结,
        # 否则会出现「患者还没回答完就出报告」。
        if target >= ConsultationState.STAGE_COMPLETE and not self._ready_to_finalize(display_text):
            logger.info(
                f"兜底推进暂不进入终末阶段: 报告所需数据未收齐或仍在提问 "
                f"session={self.session_id} stage={stage}"
            )
            return False

        self.stage = target
        self._stage_turns = 0
        logger.info(
            f"阶段兜底推进: {stage} -> {self.stage} "
            f"(数据齐全={ready}, 已超时={overdue})"
        )
        return True

    def _can_finalize(self) -> bool:
        """
        是否具备生成报告所需的最低数据条件。

        核心四要素:姓名 / 性别 / 年龄 / 主诉 / 现病史 —— 这几项是医学报告必需的,
        缺失时报告必然是残缺的,必须收齐。

        2026-10-05 修复(缺陷2·报告不自动生成):
        原实现强制要求「系统回顾(system_review)」,但第4阶段系统回顾在实测中
        常常未被收集(qwen2.5:7b 容易跳过或用户未提供),导致 is_complete 几乎
        永不为真 → maybe_start_report_task() 永不触发 → 报告只能靠用户手动说
        「帮我生成报告」。系统回顾属于「锦上添花」而非报告必需项,故从硬性门槛中
        移除;保留现病史为必需,避免拿到主诉就草草出报告的另一种极端。
        """
        return bool(
            self.patient_name and self.patient_gender and self.patient_age
            and self.chief_complaint and self.present_illness
        )

    def _reply_asks_question(self, display_text: str) -> bool:
        """本条回复是否仍在向患者提问(回复中含任何待回答的问句)。

        实测模型会一边追问「是否还有其他症状?」一边输出 stage_complete=true,
        若不拦截,报告会在患者还没回答时就开始生成。

        2026-09-26 修复:原实现只看末尾字符,但模型常在问句后补一句陈述
        (如「……是否有其他症状？这些信息有助于我们进行系统回顾。」),
        问号在中间、句号结尾 → 漏判 → 第五步提问后报告提前开跑(线上实测)。
        只要本轮回复里存在任何问句,就必须等用户作答,因此改为全文扫描。
        """
        text = (display_text or "").rstrip()
        if not text:
            return False
        return ("？" in text) or ("?" in text)

    def _ready_to_finalize(self, display_text: str = "") -> bool:
        """能否进入 STAGE_COMPLETE:数据齐备 且 模型本轮没有再向患者提问"""
        if not self._can_finalize():
            return False
        if self._reply_asks_question(display_text):
            return False
        return True

    def _apply_stage_transition(self, extracted_info: dict, display_text: str) -> str:
        """
        统一处理阶段转换(流式与非流式共用),返回需追加到回复末尾的提示语(可能为空)。

        关键点:把「跳到 STAGE_COMPLETE」单独设门槛 —— 未满足条件时最多推进到
        STAGE_REVIEW,既不误触发报告,也不会因信息缺失卡在早期阶段。
        """
        if extracted_info and self._as_bool(extracted_info.get("stage_complete")):
            next_stage = self._normalize_stage(extracted_info.get("next_stage"), self.stage + 1)
            if next_stage > self.stage:
                target = min(next_stage, ConsultationState.STAGE_COMPLETE)
                if target >= ConsultationState.STAGE_COMPLETE and not self._ready_to_finalize(display_text):
                    logger.info(
                        f"拦截过早完结: 数据未收齐或模型仍在提问 session={self.session_id} "
                        f"stage={self.stage} data_ready={self._can_finalize()}"
                    )
                    target = ConsultationState.STAGE_REVIEW
                if target > self.stage:
                    self.stage = target
                    self._stage_turns = 0
                    logger.info(f"阶段转换: -> {self.stage}")
                    return self._finalize_stage_advance()
        elif self._fallback_stage_advance(display_text):
            return self._finalize_stage_advance()
        return ""

    def _finalize_stage_advance(self) -> str:
        """阶段推进后的收尾：到达终末阶段则标记完成。返回需追加到回复的提示语"""
        if self.stage >= ConsultationState.STAGE_COMPLETE:
            self.is_complete = True
            return "\n\n✅ 问诊信息收集完成，报告正在后台生成，完成后会自动展示；您也可以离开本页稍后回来查看。"
        return ""

    # ==================== 后台报告生成(脱离 SSE 请求生命周期) ====================
    def maybe_start_report_task(self):
        """
        触发后台报告生成(幂等)。
        - 仅当问诊完成、报告尚未生成且未在生成中时启动;
        - report_status=failed 时需先由 /report/retry 接口重置为 pending 才会再触发;
        - 任务引用保存在 self._report_task 上防止被 GC。
        """
        if not (self.is_complete and not self.report):
            return False
        if self.report_status in ("running", "done"):
            return False
        if self._report_task is not None and not self._report_task.done():
            return False
        self.report_status = "pending"
        self._report_task = asyncio.create_task(self.run_report_generation())
        logger.info(f"后台报告生成任务已启动 session={self.session_id}")
        return True

    async def _collect_report_once(self) -> str:
        """消费一次 report_generator.generate_report_stream,返回完整报告文本。
        落库由 report_generator 内部 _save_to_database 负责(唯一落库点),此处不重复存。"""
        chunks = []
        async for chunk in report_generator.generate_report_stream(
            self.get_patient_data(), user_id=self.user_id
        ):
            chunks.append(chunk)
        return "".join(chunks)

    async def run_report_generation(self):
        """
        后台生成报告:带超时与重试,状态全程落库。
        成功后报告正文追加进 conversation_history(以 ## 开头,前端据此渲染报告气泡),
        用户断线/切后台/重进页面均可通过 /sessions/{id}/report 拿到结果。
        """
        import app.services.session_service as session_service

        self.report_status = "running"
        session_service.persist(self)

        last_err = None
        for attempt in range(1, max(1, config.REPORT_MAX_ATTEMPTS) + 1):
            try:
                report_text = await asyncio.wait_for(
                    self._collect_report_once(), timeout=config.REPORT_GEN_TIMEOUT
                )
                if report_text and report_text.strip():
                    self.report = report_text
                    # 追加进对话历史:前端 loadHistory 按 "##" 前缀识别报告气泡
                    self.conversation_history.append(
                        {"role": "assistant", "content": f"## {report_text}"}
                    )
                    # 仅负责会话级长记忆摘要(records 落库在 report_generator 内完成)
                    self._save_completed_record(report_text)
                    self.report_status = "done"
                    logger.info(f"后台报告生成成功 session={self.session_id} 长度={len(report_text)}")
                    break
                raise RuntimeError("报告生成返回空内容")
            except Exception as e:
                last_err = e
                logger.warning(
                    f"后台报告生成失败(第 {attempt}/{config.REPORT_MAX_ATTEMPTS} 次): {e}"
                )
                if attempt < config.REPORT_MAX_ATTEMPTS:
                    await asyncio.sleep(2)

        if self.report_status != "done":
            self.report_status = "failed"
            logger.error(f"后台报告生成最终失败 session={self.session_id}: {last_err}")

        session_service.persist(self)

    # ---------- 字段累积合并与确定性兜底提取 ----------
    # 「患者说了但模型没用上」「反复问同一个问题」两大现象的共同断点:
    # ① 原实现每轮整体覆盖自由文本字段,模型只写本轮内容时前几轮的细节被顶掉;
    # ② 模型漏输出 JSON 的那一轮,信息没有任何其他通道能补回来。
    # 下面两个方法是这两个断点的补丁。

    # 亲属/他人指代:出现这些词时"XX岁"说的多半不是患者本人,禁止抽年龄
    _KIN_WORDS_RE = re.compile(r"(孩子|女儿|儿子|宝宝|小孩|婴幼儿|孙子|外孙|孙女|"
                               r"朋友|同事|同学|家人|母亲|父亲|妈妈|爸爸|老婆|老公|患者家属)")

    @staticmethod
    def _merge_text_field(old: str, new: str) -> str:
        """
        自由文本字段累积合并:保留旧值,把新值中「旧值没有的句子」追加在后面。

        为什么不能直接赋值(旧行为):
        提示词要求「只提取对话中明确提到的信息」,7b 模型往往只写**本轮**提到的内容。
        直接赋值会让上一轮采集的完整描述被这一轮更短的摘要顶掉 ——
        上下文里的"已收集-现病史"随之缩水,模型判定信息不足,于是把问过的问题再问一遍。
        """
        old = (old or "").strip()
        new = (new or "").strip()
        if not new:
            return old
        if not old:
            return new
        if new in old:
            return old          # 模型复述了已收集内容,不重复追加
        if old in new:
            return new          # 新值是旧值的超集(模型补全了),取更完整的

        # 以句为单位去重追加,避免同一句话反复堆砌
        sep_re = re.compile(r"[。！？；;]")
        old_sents = [s.strip() for s in sep_re.split(old) if s.strip()]
        have = set(old_sents)
        for s in sep_re.split(new):
            s = s.strip()
            if not s:
                continue
            # 子串级去重:模型改写过的近似句不重复计入
            if s not in have and not any(s in o or o in s for o in old_sents if abs(len(s) - len(o)) < 12):
                old_sents.append(s)
                have.add(s)
        merged = "。".join(old_sents)
        if not merged.endswith(("。", "！", "？")):
            merged += "。"
        limit = getattr(config, "CONSULT_FIELD_MAX_LEN", 600) or 600
        if len(merged) > limit:
            # 超长时优先保留较新的内容(尾部),旧细节已被报告消费过
            merged = "…" + merged[-limit:]
        return merged

    @classmethod
    def _regex_extract_basics(cls, text: str) -> dict:
        """
        从用户原话确定性补抽年龄/性别。

        只在结构化字段为空时用于补位(见 _update_patient_info),**不覆盖模型已给的值**。
        这是「字段校验仅判空」的补丁:模型漏输出 JSON 的那一轮,用户信息原本会永久丢失。
        规则刻意保守 —— 宁漏勿错,抽错的性别/年龄会直接写进报告。
        """
        out: dict = {}
        t = (text or "").strip()
        if not t:
            return out

        # 年龄:数字 + (周岁|岁)。出现亲属词时跳过,那通常说的是别人
        if not cls._KIN_WORDS_RE.search(t):
            m = re.search(r"(\d{1,3})\s*(?:周?岁|years?\s*old)", t)
            if m:
                age = int(m.group(1))
                if 0 < age <= 120:
                    out["patient_age"] = age

        # 性别:只在「我是男/女」「性别:男」「35岁，男」这类明确表述时抽取
        gender_patterns = (
            r"性别\s*[:：]?\s*(男|女)",
            r"(?:我是|本人)\s*(男|女)(?:性|的|人)?",
            r"\d{1,3}\s*(?:周?岁)?\s*[，,、]?\s*(男|女)(?:性|的)?(?:[，,。！？]|$)",
        )
        for pat in gender_patterns:
            gm = re.search(pat, t)
            if gm:
                out["patient_gender"] = gm.group(1)
                break
        return out

    def _update_patient_info(self, info: dict, user_text: str = ""):
        """
        根据提取的信息更新患者数据（字段类型统一做容错，见 _normalize_age）

        user_text: 本轮用户原话,用于模型漏提取时的确定性补抽(见 _regex_extract_basics)。
        """
        info = dict(info or {})

        # 兜底补抽:仅填「模型没给且当前也为空」的字段,绝不覆盖已确认的值
        if getattr(config, "CONSULT_REGEX_FALLBACK", True) and user_text:
            for key, val in self._regex_extract_basics(user_text).items():
                if info.get(key) in (None, "", 0):
                    info[key] = val
                    logger.info(f"兜底提取命中 {key}={val!r}（模型未输出该字段）")

        # 姓名/性别/年龄属于「定长标量」,直接覆盖(患者更正时以最新为准)
        if info.get("patient_name"):
            self.patient_name = info["patient_name"]
        if info.get("patient_gender"):
            self.patient_gender = info["patient_gender"]
        age = self._normalize_age(info.get("patient_age"))
        if age > 0:
            self.patient_age = age

        # 主诉:取更完整的那条(模型有时会先写"头痛",后写"头痛三天伴恶心")
        new_cc = (info.get("chief_complaint") or "").strip()
        if new_cc and len(new_cc) > len(self.chief_complaint or ""):
            self.chief_complaint = new_cc

        # 自由文本字段:累积合并(旧行为是覆盖,会丢前面几轮的细节)
        merge = getattr(config, "CONSULT_FIELDS_MERGE", True)
        for attr, key in (
            ("present_illness", "present_illness"),
            ("past_history", "past_history"),
            ("personal_history", "personal_history"),
            ("family_history", "family_history"),
            ("system_review", "system_review"),
        ):
            new_val = (info.get(key) or "").strip()
            if not new_val:
                continue
            setattr(self, attr,
                    self._merge_text_field(getattr(self, attr, ""), new_val) if merge else new_val)

    def _query_patient_history(self, name: str):
        """查询患者历史记录(小程序模式按 user_id 限定作用域,桌面模式 user_id=0 兼容旧逻辑)"""
        try:
            records = database.query_patient(name, user_id=self.user_id)
            if records:
                self.history_data = records
                logger.info(f"找到患者 '{name}' 的 {len(records)} 条历史记录")
            else:
                self.history_data = None
                logger.info(f"未找到患者 '{name}' 的历史记录")
        except Exception as e:
            logger.error(f"查询患者历史记录失败: {e}")
            self.history_data = None

    def process_user_input(self, user_input: str) -> str:
        """
        处理用户输入，返回Bot回复
        优化：只调用1次LLM，在回复中同时完成对话+信息提取+阶段判断
        """
        if not user_input.strip():
            return "您好，请告诉我您的症状或问题。"

        # 1. 紧急症状检查（纯本地关键词匹配，无需LLM）
        emergency_msg = self._check_emergency(user_input)
        if emergency_msg:
            self.conversation_history.append({"role": "user", "content": user_input})
            self._fire_family_emergency(emergency_msg)

        # 2. 如果是首次对话，标记已打招呼
        if not self._greeted:
            self._greeted = True

        # 记录用户输入到对话历史
        if not emergency_msg:
            self.conversation_history.append({"role": "user", "content": user_input})

        # 3. 如果问诊已完成，不再处理
        if self.is_complete:
            return "问诊已完成。如需重新开始，请点击重置按钮。"

        # 4. 检索知识库医学参考 + 历史对话记忆（双检索）
        kb_reference, memory_reference = self._retrieve_references(user_input)

        # 5. 调用 LLM 获取回复（仅1次调用！）
        system_prompt = self._get_system_prompt()
        context = self._build_context()
        enriched_input = f"{context}\n\n患者说：{user_input}"

        # 注入历史对话记忆（跨会话长记忆）
        if memory_reference:
            enriched_input += (
                f"\n\n【历史对话记忆】（该患者既往与系统的对话片段，仅供辅助理解其情况，"
                f"不要直接提及\"记忆\"或原文引用）\n{memory_reference}"
            )

        # 如果有知识库参考，注入到用户输入中
        if kb_reference:
            enriched_input += f"\n\n【知识库参考信息】\n{kb_reference}\n请参考以上医学知识辅助问诊，但不要直接向患者引用知识库原文。"
        # 禁止重复询问的紧凑提示:紧邻用户消息与 JSON 要求,对抗长提示开头的指令衰减
        hint = self._no_repeat_hint()
        if hint:
            enriched_input += f"\n\n{hint}"
        # 同流式分支:把 JSON 格式要求压到用户消息末尾,提高多轮后的结构化抽取命中率
        if config.CONSULT_JSON_REMINDER:
            enriched_input += f"\n\n{config.CONSULT_JSON_REMINDER}"

        raw_reply = llm_client.chat(
            system_prompt=system_prompt,
            user_prompt=enriched_input,
            history=self.history_window(),
        )

        # 6. 从回复中分离对话文本和结构化JSON
        display_text, extracted_info = self._parse_llm_response(raw_reply)

        # 7. 更新患者信息（容错同上，异常不得中断阶段推进）
        #    注意:这里**不能**只在 extracted_info 非空时调用。模型漏输出 JSON 的那一轮,
        #    唯一能救回信息的就是 _update_patient_info 里的确定性兜底提取(年龄/性别),
        #    被 if 挡掉等于让这一轮的用户陈述永久丢失(旧实现在此丢失信息)。
        try:
            self._update_patient_info(extracted_info, user_input)
        except Exception as e:
            logger.warning(f"更新患者信息失败(已忽略,不影响阶段推进): {e}")

        # 8. 处理阶段转换(终端/桌面共用 _apply_stage_transition,含过早完结拦截)
        display_text += self._apply_stage_transition(extracted_info, display_text)

        # 8.5 确定性兜底:剔除针对已收集项的纯重复提问(与流式分支一致)
        display_text = self._suppress_repeat_question(display_text)

        # 9. 在阶段1收集到姓名后查询历史记录
        if self.stage == ConsultationState.STAGE_BASIC_INFO and self.patient_name and self.history_data is None:
            self._query_patient_history(self.patient_name)
            if self.history_data:
                last_visit = self.history_data[0]
                history_notice = (
                    f"\n\n📋 我查到您之前在我这里有过就诊记录"
                    f"（最近一次：{last_visit.get('visit_date', '未知时间')}，"
                    f"主诉：{last_visit.get('chief_complaint', '未知')}）。"
                    f"\n请问这次是复查还是新的问题？"
                )
                display_text += history_notice

        # 10. 记录 Bot 回复到对话历史（用显示文本，不含JSON）
        self.conversation_history.append({"role": "assistant", "content": display_text})

        # 10.5 写入跨会话长记忆(脱敏患者姓名,失败不影响主流程)
        self._remember_turn(user_input, display_text)

        # 11. 如果有紧急提醒，追加到回复前
        if emergency_msg:
            display_text = emergency_msg + "\n\n" + display_text

        return display_text

    # ==================== 意图识别与直接问答（新增）====================

    def _classify_intent(self, text: str) -> str:
        """
        轻量规则意图分类：判断用户输入是「医学问题（直接问答）」还是「问诊信息采集」。
        零额外 LLM 开销，毫秒级响应。
        Returns:
            "question" 或 "intake"
        """
        t = text.strip()
        if not t:
            return "intake"

        # 规则0(后加):短答复几乎都是对上一轮问题的**回答**,不是新提问。
        # 旧实现没有这条,"男"、"35岁"、"没有"、"三天了"这类答复一旦沾上
        # 疑问词或问号就会被引到问答分支,采集流程随之漏采本轮信息。
        if len(t) <= 10 and not any(w in t for w in _QA_KEYWORDS):
            return "intake"

        # 规则1：显式问号
        if "？" in t or "?" in t:
            return "question"

        # 规则2：疑问词 + 一定长度（避免把"男""32岁"这类短答复误判为问题）
        if len(t) >= 4 and any(w in t for w in _QA_INTERROGATIVES):
            return "question"

        # 规则3：明确的知识咨询类关键词
        if any(w in t for w in _QA_KEYWORDS):
            return "question"

        return "intake"

    def _retrieve_kb(self, user_input: str) -> str:
        """检索知识库（供问诊与直接问答共用），异常安全。"""
        try:
            search_query = user_input
            if self.chief_complaint:
                search_query = f"{self.chief_complaint} {user_input}"
            return knowledge_base.search_for_consultation(
                symptoms=search_query,
                chief_complaint=self.chief_complaint,
                top_k=2,
            )
        except Exception as e:
            # 同上:检索失败会让本轮变成「零命中」进而触发拒答话术,必须可见。
            logger.warning(f"知识库检索失败（不影响主流程）: {e}")
            return ""

    def _retrieve_memory(self, user_input: str) -> str:
        """
        语义检索该用户的历史对话记忆(跨会话长记忆),返回格式化参考文本。
        排除当前会话(其内容已在滑动窗口内),按 user_id 作用域隔离。
        异常安全:记忆功能故障不影响问诊主流程。
        """
        if not config.ENABLE_LONG_MEMORY:
            return ""
        try:
            search_query = user_input
            if self.chief_complaint:
                search_query = f"{self.chief_complaint} {user_input}"
            results = memory_store.search_memories(
                user_id=self.user_id,
                query=search_query,
                top_k=config.MEMORY_TOP_K,
                exclude_session_id=self.session_id,
            )
            if not results:
                return ""
            refs = []
            for i, r in enumerate(results, 1):
                refs.append(f"[记忆{i}] (时间: {r.get('ts', '')}, 类型: {r.get('kind', '')})\n{r['text']}")
            return "\n\n".join(refs)
        except Exception as e:
            # 从 debug 提到 warning:记忆检索异常此前完全不可见,排查「用户说过的信息
            # 没被用上」时无法判断是检索失败还是根本没写入。失败仍需不阻断主流程。
            logger.warning(f"记忆检索失败（不影响主流程）: {e}")
            return ""

    def _no_repeat_hint(self) -> str:
        """
        紧凑的「已收集项，严禁重复询问」提示。

        为什么需要它:_build_context 生成的"已收集"清单位于 enriched_input 的**最前面**,
        而用户消息在最后面,中间隔着历史记忆和知识库检索结果 —— qwen2.5:7b 对长提示开头的
        指令遵循度明显偏低,清单写了也常常照问不误。因此再生成一份极简版本,
        贴在靠近用户消息的位置复述一次(成本只有几十字)。
        """
        if not getattr(config, "CONSULT_NO_REPEAT_HINT", True):
            return ""
        got = [label for label, val in (
            ("姓名", self.patient_name),
            ("性别", self.patient_gender),
            ("年龄", self.patient_age),
            ("主诉", self.chief_complaint),
            ("现病史", self.present_illness),
            ("既往史", self.past_history),
            ("个人史", self.personal_history),
            ("家族史", self.family_history),
            ("系统回顾", self.system_review),
        ) if val]
        if not got:
            return ""
        return ("【已确认信息-严禁重复询问】" + "、".join(got)
                + " 已在前面收集完毕，除非患者主动更正，本轮不得再次询问这些内容。")

    def history_window(self) -> list:
        """
        注入 LLM 的历史消息窗口(条数由 CONSULT_HISTORY_TURNS 控制,默认 12 条 ≈ 6 轮)。

        原实现在四处硬编码 `[-6:]`(≈3 轮):早期轮次提供的背景信息(过敏史、既往就诊等)
        如果当时没被模型提取进结构化字段,3 轮后就从模型视野里彻底消失 ——
        而长期记忆检索又刻意排除了当前会话(见 _retrieve_memory 的 exclude_session_id),
        等于没有任何通道能把它找回来,于是表现为「答非所问」「重复问已问过的问题」。
        """
        n = getattr(config, "CONSULT_HISTORY_TURNS", 12)
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = 12
        if n <= 0:
            return list(self.conversation_history)
        return self.conversation_history[-n:]

    def _retrieve_references(self, user_input: str) -> tuple:
        """一次性完成知识库+记忆双检索(供后台线程单次调度,减少线程切换)"""
        return self._retrieve_kb(user_input), self._retrieve_memory(user_input)

    def _remember_turn(self, user_input: str, display_text: str):
        """将本轮对话片段写入长记忆(脱敏患者姓名),异常安全。"""
        if not config.ENABLE_LONG_MEMORY:
            return
        try:
            turn_index = len(self.conversation_history) // 2
            memory_store.remember_turn(
                user_id=self.user_id,
                session_id=self.session_id,
                stage=self.stage,
                user_text=user_input,
                assistant_text=display_text,
                patient_name=self.patient_name,
                turn_index=turn_index,
            )
        except Exception as e:
            logger.debug(f"对话记忆写入失败（不影响主流程）: {e}")

    def _persist_trace_async(self):
        """把本轮 ReAct 轨迹丢到后台落库(异常安全,不阻塞 end 事件)。"""
        trace = getattr(self, "_last_trace", None)
        if not trace or not config.REACT_PERSIST:
            return
        try:
            from app.services import session_service
            asyncio.create_task(
                asyncio.to_thread(session_service.persist_session_trace, self, trace)
            )
        except Exception as e:
            logger.debug(f"推理过程落库调度失败(不影响主流程): {e}")

    def _finalize_direct_qa(self, user_input: str, reply_text: str) -> str:
        """
        直接问答收尾(单次流程与 ReAct 流程共用):阶段兜底推进 → 历史追加 → 长记忆写入。

        抽成独立方法是为了避免两条分支各写一遍收尾逻辑而走偏。
        """
        # ------------------------------------------------------------------
        # QA 轮同样要做确定性补抽(仍零 LLM 成本)。
        # 旧实现注释写着「QA 分支不做字段抽取」—— 于是用户在提问时顺带交代的背景
        # ("我对青霉素过敏,能吃头孢吗?"、"我今年 40 岁,血压高能吃这个吗?")
        # 永远不会进入结构化字段。几轮之后滑出对话窗口,信息就彻底消失了,
        # 表现为「明明说过,后面回答却完全没用上」。
        # 这里只走规则兜底提取(年龄/性别),不解析 JSON —— QA 提示词本就不要求输出 JSON。
        # 必须放在阶段推进判定之前,否则补到的字段对本轮的推进判定不起作用。
        try:
            self._update_patient_info({}, user_input)
        except Exception as e:
            logger.warning(f"QA 轮字段补抽失败(已忽略): {e}")

        # 问答轮次同样计入阶段推进兜底计数:否则用户连续提问会让 _stage_turns
        # 永不增长、stage 永久卡住、报告永不触发(实测高频停滞场景)。
        if self._fallback_stage_advance(reply_text):
            reply_text += self._finalize_stage_advance()
            # 推进到终末阶段:立即触发后台报告生成
            self.maybe_start_report_task()
        # 记录到对话历史（含紧急前缀），保持上下文连贯
        self.conversation_history.append({"role": "assistant", "content": reply_text})
        # 写入跨会话长记忆(内部已异常安全,失败只记日志不抛错)
        self._remember_turn(user_input, reply_text)
        return reply_text

    async def _stream_direct_qa(self, user_input: str, emergency_msg: str):
        """
        直接问答分支：RAG + 安全护栏，流式回答，不推进 5 阶段状态机。
        Yields: {"event": "step"|"reply"|"end", "data": str}

        当 ENABLE_REACT=true 时，先走 react.loop 的受控 ReAct 循环
        (Thought/Action/Observation + 句子级引用),异常或降级则回退下方单次 LLM 流程。
        """
        # 与问诊主链路一致:追加简洁性约束以压缩输出 token(本机约 16 tokens/s)
        qa_system = DIRECT_QA_SYSTEM
        if config.CONSULT_BRIEF_OUTPUT and config.DIRECT_QA_BRIEF_HINT:
            qa_system = f"{DIRECT_QA_SYSTEM}\n{config.DIRECT_QA_BRIEF_HINT}"

        turn_index = len(self.conversation_history) // 2

        # ==================== ReAct 受控循环(可解释推理过程) ====================
        # 仅接管本分支;采集态(5 阶段)、报告生成、路由层均不受影响。
        if config.ENABLE_REACT:
            streamed: list = []
            try:
                react_system = qa_system
                async for ev in react_loop.stream_qa_with_react(
                    session=self,
                    user_input=user_input,
                    emergency_msg=emergency_msg,
                    turn_index=turn_index,
                    qa_system=react_system,
                ):
                    if ev.get("event") == "reply":
                        streamed.append(ev.get("data") or "")
                    yield ev
                reply_text = "".join(streamed)
                # 推理过程落库(后台执行,失败不影响回答与 end 事件)
                self._persist_trace_async()
                self._finalize_direct_qa(user_input, reply_text)
                yield {
                    "event": "end",
                    "data": json.dumps({
                        "session_id": self.session_id,
                        "stage": self.stage,
                        "is_complete": self.is_complete,
                        "reply_clean": reply_text,
                        "report_status": self.report_status,
                        # 前端可据此判断当前会话是否具备推理过程数据,决定回放时如何提示
                        "react_enabled": bool(config.ENABLE_REACT),
                    }, ensure_ascii=False),
                }
                return
            except Exception as e:
                # 降级:ReAct 任何异常都不应让用户拿不到回答,退回原单次流程重跑
                logger.warning(f"ReAct 流程异常,降级为单次问答: {e}")
                react_reason = str(e)

        # ==================== 原单次问答流程(默认路径 / 降级路径) ====================
        # 知识库 + 历史记忆 双检索并发执行(两次 embedding 并行,降低首字前等待)
        kb_reference, memory_reference = await asyncio.gather(
            asyncio.to_thread(self._retrieve_kb, user_input),
            asyncio.to_thread(self._retrieve_memory, user_input),
        )

        enriched = f"用户问题：{user_input}"
        if memory_reference:
            enriched += (
                f"\n\n【历史对话记忆】（该用户既往与系统的对话片段，仅供辅助理解其情况，"
                f"不要直接提及\"记忆\"或原文引用）\n{memory_reference}"
            )
        if kb_reference:
            enriched += f"\n\n【知识库参考信息】\n{kb_reference}\n请参考以上医学知识回答，但不要直接引用知识库原文。"

        # 问答分支同样需要:避免回答时把已采集的姓名/年龄/主诉再问一遍
        hint = self._no_repeat_hint()
        if hint:
            enriched += f"\n\n{hint}"

        prefix = (emergency_msg + "\n\n") if emergency_msg else ""
        streamed = []
        first = True
        # 流式过滤器：剥离末尾 JSON 结构块，只透出可见正文
        # 思维链走 return_raw 原样透出,由 _split_think_stream 拆分为 thinking/正文
        text_filter = _VisibleStreamFilter()
        think_state = {"in_think": False, "buf": ""}
        async for raw in llm_client.chat_stream(
            system_prompt=qa_system,
            user_prompt=enriched,
            history=self.history_window(),
            model=config.CONSULT_MODEL_NAME,
            max_tokens=config.CONSULT_MAX_TOKENS,
            return_raw=True,
        ):
            for kind, txt in llm_client._split_think_stream(raw, think_state):
                if kind == "think":
                    if config.SHOW_THINKING and txt:
                        yield {"event": "thinking", "data": txt}
                else:
                    visible = text_filter.feed(txt)
                    if not visible:
                        continue
                    if first and prefix:
                        visible = prefix + visible
                    first = False
                    streamed.append(visible)
                    yield {"event": "reply", "data": visible}

        # 思维链残尾兜底(模型未正常闭合 </think> 时)
        if think_state["in_think"] and think_state["buf"]:
            if config.SHOW_THINKING:
                yield {"event": "thinking", "data": think_state["buf"]}

        tail = text_filter.flush()
        if tail:
            streamed.append(tail)
            yield {"event": "reply", "data": tail}

        reply_text = "".join(streamed)
        # 收尾:阶段兜底推进 → 历史追加 → 长记忆写入(与 ReAct 分支同一实现)
        reply_text = self._finalize_direct_qa(user_input, reply_text)
        # 直接问答不改变采集阶段
        yield {
            "event": "end",
            "data": json.dumps({
                "session_id": self.session_id,
                "stage": self.stage,
                "is_complete": self.is_complete,
                "reply_clean": reply_text,
                "report_status": self.report_status,
            }, ensure_ascii=False),
        }

    async def process_user_input_stream(self, user_input: str):
        """
        处理用户输入并以 SSE 事件流形式产出结果（流式输出主入口）。
        Yields 事件字典：{"event": "reply"|"report"|"end"|"report_done"|"error", "data": str}
        """
        if not user_input.strip():
            yield {"event": "reply", "data": "您好，请告诉我您的症状或问题。"}
            yield {"event": "end", "data": json.dumps({
                "session_id": self.session_id,
                "stage": self.stage,
                "is_complete": self.is_complete,
                "reply_clean": "您好，请告诉我您的症状或问题。",
                "report_status": self.report_status,
            }, ensure_ascii=False)}
            return

        # 1. 紧急症状检查（纯本地关键词匹配，无需 LLM）
        emergency_msg = self._check_emergency(user_input)
        if emergency_msg:
            self._fire_family_emergency(emergency_msg)
        if not self._greeted:
            self._greeted = True
        if not emergency_msg:
            # 去重保护:小程序路由会在调用前先落一次用户消息(防崩溃丢失),此处避免重复追加
            last = self.conversation_history[-1] if self.conversation_history else None
            is_dup = (last is not None and last.get("role") == "user"
                      and last.get("content") == user_input)
            if not is_dup:
                self.conversation_history.append({"role": "user", "content": user_input})

        # 2. 问诊已完成则不再处理
        if self.is_complete:
            msg = "问诊已完成。如需重新开始，请点击右上角「新建对话」。"
            yield {"event": "reply", "data": msg}
            yield {"event": "end", "data": json.dumps({
                "session_id": self.session_id,
                "stage": self.stage,
                "is_complete": True,
                "reply_clean": msg,
                "report_status": self.report_status,
            }, ensure_ascii=False)}
            return

        # 3. 意图路由：命中"直接问答"则走 QA 分支（不再机械套用 5 阶段）
        intent = self._classify_intent(user_input) if config.ENABLE_DIRECT_QA else "intake"
        if intent == "question":
            async for ev in self._stream_direct_qa(user_input, emergency_msg):
                yield ev
            return

        # 4. 常规 5 阶段采集流程（流式）
        # 知识库 + 历史对话记忆 双检索(单次后台线程调度)
        # 知识库 + 历史记忆 双检索并发执行(两次 embedding 并行,降低首字前等待)
        kb_reference, memory_reference = await asyncio.gather(
            asyncio.to_thread(self._retrieve_kb, user_input),
            asyncio.to_thread(self._retrieve_memory, user_input),
        )
        system_prompt = self._get_system_prompt()
        # 响应速度优先:追加简洁性约束,压缩输出 token 数。
        # 本机实测生成速度约 16 tokens/s,单次耗时几乎完全由「输出 token 数」决定
        # (推理内容与正文共用 max_tokens 预算),因此缩短输出是最直接的加速手段。
        if config.CONSULT_BRIEF_OUTPUT and config.CONSULT_BRIEF_HINT:
            system_prompt = f"{system_prompt}\n{config.CONSULT_BRIEF_HINT}"
            # 简洁约束会把「末尾输出 JSON 块」挤到中间导致模型漏输出,故再压一句提醒在最后
            if config.CONSULT_JSON_REMINDER:
                system_prompt = f"{system_prompt}\n{config.CONSULT_JSON_REMINDER}"
        context = self._build_context()
        enriched_input = f"{context}\n\n患者说：{user_input}"
        if memory_reference:
            enriched_input += (
                f"\n\n【历史对话记忆】（该患者既往与系统的对话片段，仅供辅助理解其情况，"
                f"不要直接提及\"记忆\"或原文引用）\n{memory_reference}"
            )
        if kb_reference:
            enriched_input += (
                f"\n\n【知识库参考信息】\n{kb_reference}\n"
                "请参考以上医学知识辅助问诊，但不要直接向患者引用知识库原文。"
            )
        # 同非流式分支:紧凑的「已收集项不得重复询问」提示,贴在最靠近生成起点的位置
        hint = self._no_repeat_hint()
        if hint:
            enriched_input += f"\n\n{hint}"
        # 多轮后模型会逐渐不再输出 JSON(历史里它看到的自己的回复都被剥离了 JSON,
        # 于是模仿自身历史而省略结构化数据)。把格式要求再压到用户消息末尾通常
        # 比 system 提示更被遵守,用于稳定抽取率 —— 否则 present_illness 等字段
        # 长期为空,生成的报告内容会残缺。
        if config.CONSULT_JSON_REMINDER:
            enriched_input += f"\n\n{config.CONSULT_JSON_REMINDER}"

        # 流式获取 LLM 回复（逐段 yield）
        # 注意：不能直接把模型原始输出转发给前端——
        # ① 推理模型的 <think> 思维链需作为「思考过程」单独透出(可配置 SHOW_THINKING)；
        # ② 提示词要求末尾附【JSON块】{...}，原样转发会让用户看到一堆代码，
        #    因此可见正文仍经 _VisibleStreamFilter 剥离 JSON 结构块。
        # 这里用 return_raw 原样拿到模型输出,自行拆分为 thinking/reply 两类事件。
        full_reply = []
        visible_reply = []
        text_filter = _VisibleStreamFilter()
        think_state = {"in_think": False, "buf": ""}
        async for raw in llm_client.chat_stream(
            system_prompt=system_prompt,
            user_prompt=enriched_input,
            history=self.history_window(),
            model=config.CONSULT_MODEL_NAME,
            max_tokens=config.CONSULT_MAX_TOKENS,
            return_raw=True,
        ):
            full_reply.append(raw)
            for kind, txt in llm_client._split_think_stream(raw, think_state):
                if kind == "think":
                    if config.SHOW_THINKING and txt:
                        yield {"event": "thinking", "data": txt}
                else:
                    visible = text_filter.feed(txt)
                    if visible:
                        visible_reply.append(visible)
                        yield {"event": "reply", "data": visible}

        # 思维链残尾兜底(模型未正常闭合 </think> 时)
        if think_state["in_think"] and think_state["buf"]:
            if config.SHOW_THINKING:
                yield {"event": "thinking", "data": think_state["buf"]}

        tail = text_filter.flush()
        if tail:
            visible_reply.append(tail)
            yield {"event": "reply", "data": tail}

        raw_reply = "".join(full_reply)
        display_text, extracted_info = self._parse_llm_response(raw_reply)

        # 5. 更新患者信息
        #    包裹异常：字段结构异常不得中断本轮后续处理(阶段推进/历史追加/会话落库)，
        #    否则会出现"回答正常但 stage 卡死、报告永不出炉"的隐性故障。
        #    同非流式分支:不能只在 extracted_info 非空时调用,否则模型漏输出 JSON
        #    那一轮的用户陈述无法通过兜底提取补回(本轮信息永久丢失)。
        try:
            self._update_patient_info(extracted_info, user_input)
        except Exception as e:
            logger.warning(f"更新患者信息失败(已忽略,不影响阶段推进): {e}")

        # 6. 处理阶段转换(含过早完结拦截:数据未齐或本轮仍在提问时不进 STAGE_COMPLETE)
        display_text += self._apply_stage_transition(extracted_info, display_text)

        # 6.5 确定性兜底:剔除针对已收集项的纯重复提问(缓解「重复问已答过的问题」)
        display_text = self._suppress_repeat_question(display_text)

        # 7. 阶段1收集到姓名后查询历史记录
        if self.stage == ConsultationState.STAGE_BASIC_INFO and self.patient_name and self.history_data is None:
            self._query_patient_history(self.patient_name)
            if self.history_data:
                last_visit = self.history_data[0]
                history_notice = (
                    f"\n\n📋 我查到您之前在我这里有过就诊记录"
                    f"（最近一次：{last_visit.get('visit_date', '未知时间')}，"
                    f"主诉：{last_visit.get('chief_complaint', '未知')}）。"
                    f"\n请问这次是复查还是新的问题？"
                )
                display_text += history_notice

        # 8. 记录 Bot 回复到对话历史（用显示文本，不含 JSON）
        self.conversation_history.append({"role": "assistant", "content": display_text})

        # 8.5 写入跨会话长记忆:改为后台任务(不 await),避免把 embedding/落盘成本
        #     计入本轮用户的等待——end 事件可更早透出,回复定稿对用户更早可见。
        #     ENABLE_LONG_MEMORY 关闭时 _remember_turn 内部直接返回,此处无副作用。
        self._remember_task = asyncio.create_task(
            asyncio.to_thread(self._remember_turn, user_input, display_text)
        )

        # 9. 紧急提醒前置
        if emergency_msg:
            display_text = emergency_msg + "\n\n" + display_text

        # 10. 若尚未完成，直接收尾
        if not self.is_complete:
            yield {"event": "end", "data": json.dumps({
                "session_id": self.session_id,
                "stage": self.stage,
                "is_complete": False,
                "reply_clean": display_text,
                "report_status": self.report_status,
            }, ensure_ascii=False)}
            return

        # 11. 阶段完成：报告改为后台任务生成(不随 SSE 断开而中断)。
        #     SSE 以 end 事件收尾并携带 report_status,前端据此轮询
        #     GET /sessions/{id}/report 拿取结果(断点续传)。
        self.maybe_start_report_task()
        yield {"event": "end", "data": json.dumps({
            "session_id": self.session_id,
            "stage": self.stage,
            "is_complete": True,
            "reply_clean": display_text,
            "report_status": self.report_status,
        }, ensure_ascii=False)}

    def _save_completed_record(self, report_text: str):
        """
        报告完成后的收尾。

        注意：患者记录落库由 report_generator._save_to_database 统一负责
        （generate_report_stream 内部已调用），这里**不得**再存一次，
        否则每次问诊会在 patients_info 里写入两条一模一样的记录。
        """
        # 写入会话级长记忆摘要(供跨会话语义检索,主诉/现病史等要点)
        if config.ENABLE_LONG_MEMORY:
            try:
                memory_store.remember_episode(
                    user_id=self.user_id,
                    session_id=self.session_id,
                    patient_data=self.get_patient_data(),
                    patient_name=self.patient_name,
                )
            except Exception as e:
                logger.debug(f"会话记忆写入失败（不影响主流程）: {e}")

    def _build_context(self) -> str:
        """
        构建当前问诊状态的上下文信息，帮助 LLM 了解已收集的信息
        """
        context_parts = []

        context_parts.append(f"【当前问诊阶段: {self.stage}】")

        # 登录资料预填项:明确告知模型这些项已由用户提供,不得重复询问
        if self.profile_prefilled:
            context_parts.append(
                "【用户登录资料】以下基本信息来自用户注册时填写的资料:"
                + ("性别" if self.patient_gender else "")
                + ("、年龄" if self.patient_age else "")
                + "已带入本次问诊，除非患者本人明确更正，否则不要再询问这些内容。"
            )

        if self.patient_name:
            context_parts.append(f"已收集 - 姓名: {self.patient_name}")
        if self.patient_gender:
            context_parts.append(f"已收集 - 性别: {self.patient_gender}")
        if self.patient_age:
            context_parts.append(f"已收集 - 年龄: {self.patient_age}")
        if self.chief_complaint:
            context_parts.append(f"已收集 - 主诉: {self.chief_complaint}")
        if self.present_illness:
            context_parts.append(f"已收集 - 现病史: {self.present_illness[:200]}")
        if self.past_history:
            context_parts.append(f"已收集 - 既往史: {self.past_history[:200]}")
        if self.personal_history:
            context_parts.append(f"已收集 - 个人史: {self.personal_history[:200]}")
        if self.family_history:
            context_parts.append(f"已收集 - 家族史: {self.family_history[:200]}")
        if self.system_review:
            context_parts.append(f"已收集 - 系统回顾: {self.system_review[:200]}")

        if self.history_data:
            last_visit = self.history_data[0]
            context_parts.append(
                f"历史就诊: 最近一次 {last_visit.get('visit_date', '')}，"
                f"主诉: {last_visit.get('chief_complaint', '')}，"
                f"诊断: {last_visit.get('diagnosis', '')}"
            )

        # 给出当前阶段「尚未收集」的明确目标,从根源减少重复询问:
        # 模型有了具体目标,就不会凭空再问一遍已收集项。
        pending = self._pending_hint()
        if pending:
            context_parts.append(pending)

        return "\n".join(context_parts)

    # 字段 <-> 关键词映射,用于识别「针对已收集项的重复提问」
    _REASK_FIELD_KEYWORDS = {
        "patient_name": ["姓名", "叫什么", "怎么称呼", "尊姓", "名字"],
        "patient_gender": ["性别", "男还是女", "是男是女", "男女"],
        "patient_age": ["年龄", "多大", "几岁", "年纪", "贵庚", "岁数"],
        "chief_complaint": ["主诉", "哪里不舒服", "怎么了", "什么症状",
                            "来看什么", "什么问题", "不舒服"],
        "present_illness": ["现病史", "什么时候开始", "持续多久", "诱因",
                            "伴随症状", "缓解"],
        "past_history": ["既往史", "手术史", "过敏史", "慢性病", "以前得"],
        "personal_history": ["个人史", "吸烟", "喝酒", "职业"],
        "family_history": ["家族史", "家族中"],
        "system_review": ["系统回顾", "各个系统"],
    }
    # 提问句中常见修饰/礼貌套话,判定「纯重复提问」时从残留中剔除
    _REASK_FILLER = [
        "请问", "您", "你", "的", "是", "多少", "呢", "麻烦", "可以告诉我",
        "能说一下", "方便告知", "吗", "呀", "啊", "再", "一下", "大概",
        "左右", "具体", "能", "说说", "告诉", "我", "我们", "关于", "方面",
    ]

    def _pending_hint(self) -> str:
        """列出当前阶段「尚未收集」的要点,给模型一个明确提问目标。

        配合 _no_repeat_hint(已收集项严禁重复)使用:一面封死已问过的,
        一面指明还没问的,双管齐下缓解 qwen2.5:7b 偶发的「重复问已答过的问题」。
        """
        if not getattr(config, "CONSULT_PENDING_HINT", True):
            return ""
        stage = self.stage
        need: list = []
        if stage == ConsultationState.STAGE_BASIC_INFO:
            if not self.patient_name:
                need.append("姓名")
            if not self.patient_gender:
                need.append("性别")
            if not self.patient_age:
                need.append("年龄")
            if not self.chief_complaint:
                need.append("初步主诉")
        elif stage == ConsultationState.STAGE_CHIEF_COMPLAINT:
            if not self.chief_complaint:
                need.append("主诉")
            if not self.present_illness:
                need.append("现病史(部位/性质/时长/诱因/伴随)")
        elif stage == ConsultationState.STAGE_HISTORY:
            if not (self.past_history or self.personal_history or self.family_history):
                need.append("相关既往史/个人史/家族史(与主诉相关的即可)")
        elif stage == ConsultationState.STAGE_REVIEW:
            if not self.system_review:
                need.append("系统回顾(2-3 个相关系统)")
        else:
            return ""
        if not need:
            return ("【本轮目标】当前阶段信息已基本收集,请直接给出 stage_complete=true "
                    "进入下一阶段,不要重复询问已收集项。")
        return ("【本轮待了解】" + "、".join(need)
                + "。请只针对以上待了解项提问,已收集项严禁重复询问或换种说法再问。")

    def _suppress_repeat_question(self, display_text: str) -> str:
        """确定性兜底:剔除回复里针对「已收集项」的纯重复提问句。

        为什么:即使有 _no_repeat_hint / _pending_hint,qwen2.5:7b 仍偶发把已答过的
        问题换个说法再问一遍,患者体验极差。这里不依赖模型,直接把「纯重复提问」
        那一句删掉(连同标点)。

        判定很保守:仅当某问句在剔除字段关键词与礼貌套话后几乎不剩内容(<=2 字),
        且对应字段确已收集,才视为纯重复提问。任何包含实质新信息的问句
        (如「症状什么时候开始的」)都保留,绝不误删。
        """
        if not getattr(config, "CONSULT_DEDUPE_QUESTION", True):
            return display_text
        if not display_text:
            return display_text
        parts = re.split(r'([。！？!?])', display_text)
        sentences: list = []
        for k in range(0, len(parts), 2):
            seg = parts[k]
            sep = parts[k + 1] if k + 1 < len(parts) else ""
            sentences.append((seg, sep))
        out: list = []
        for seg, sep in sentences:
            is_question = sep in ("？", "?", "！", "!")
            if "？" in seg or "?" in seg:
                is_question = True
            if is_question:
                hit_field = None
                for field, kws in self._REASK_FIELD_KEYWORDS.items():
                    if any(kw in seg for kw in kws) and getattr(self, field, None):
                        hit_field = field
                        break
                if hit_field:
                    leftover = seg
                    for kw in self._REASK_FIELD_KEYWORDS[hit_field]:
                        leftover = leftover.replace(kw, "")
                    for f in self._REASK_FILLER:
                        leftover = leftover.replace(f, "")
                    leftover = re.sub(r"\s+", "", leftover)
                    if len(leftover) <= 2:
                        # 纯重复提问:丢弃该句
                        logger.info(
                            f"剔除针对已收集项({hit_field})的纯重复提问: {seg}{sep}"
                        )
                        continue
            out.append(seg + sep)
        result = "".join(out)
        # 若整段都被剔除(整轮都在重复问),退回原文,避免空气泡
        return result if result.strip() else display_text

    def get_patient_data(self) -> dict:
        """获取完整的患者数据字典"""
        return {
            "patient_name": self.patient_name,
            "patient_gender": self.patient_gender,
            "patient_age": self.patient_age,
            "chief_complaint": self.chief_complaint,
            "present_illness": self.present_illness,
            "past_history": self.past_history,
            "personal_history": self.personal_history,
            "family_history": self.family_history,
            "system_review": self.system_review,
            "diagnosis": self.diagnosis,
        }

    def get_history_for_display(self) -> list:
        """获取对话历史用于前端展示"""
        return self.conversation_history.copy()

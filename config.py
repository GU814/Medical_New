"""
配置文件 - 医学问诊智能体
所有配置项均支持环境变量覆盖，优先使用环境变量
"""

import os
import sys
import json

# ==================== 路径基础 ====================
# 打包后数据应存放在 EXE 同级目录，而非临时解压目录
if getattr(sys, 'frozen', False):
    _app_dir = os.path.dirname(sys.executable)
else:
    _app_dir = os.path.dirname(os.path.abspath(__file__))

# ==================== .env 加载 ====================
# 之前的坑：项目里装了 python-dotenv，但代码从未调用 load_dotenv()，
# 导致 .env 中配置的 MASTER_KEY / SECRET_KEY / WX_* 全部不生效。
# 这里显式加载（已存在的真实环境变量优先，不覆盖）。
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(_app_dir, ".env"), override=False)
except Exception:
    # python-dotenv 未安装时静默跳过，完全依赖真实环境变量
    pass

# ==================== LLM 配置 ====================
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:11434/v1")

API_KEY = os.environ.get("API_KEY", "ollama")

MODEL_NAME = os.environ.get("MODEL_NAME", "deepseek-r1:8b")

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")

EMBEDDING_DIMENSION = int(os.environ.get("EMBEDDING_DIMENSION", "768"))

# 嵌入模型服务地址（可选）。默认复用对话模型的 API_BASE_URL（即 Ollama）。
# 当使用自训嵌入模型 + serve_embed.py 时，设为该服务地址，例如 http://127.0.0.1:8002/v1
EMBEDDING_API_BASE_URL = os.environ.get("EMBEDDING_API_BASE_URL", API_BASE_URL)

MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "4096"))

DEFAULT_TEMPERATURE = float(os.environ.get("DEFAULT_TEMPERATURE", "0.3"))

# ==================== 双模型 / 性能优化配置 ====================
# 问诊与直接问答使用轻量「指令模型」，延迟更低、不会输出冗长思维链；
# 报告深度分析仍可保留「推理模型」（如 deepseek-r1）以获得更严谨的分析。
# 若留空则回退到 MODEL_NAME。
CONSULT_MODEL_NAME = os.environ.get("CONSULT_MODEL_NAME", MODEL_NAME)
REPORT_MODEL_NAME = os.environ.get("REPORT_MODEL_NAME", MODEL_NAME)

# 问诊/问答的单次回复 token 上限。
# 注意：deepseek-r1 等「推理模型」会先把额度消耗在思维链上，只有思维链结束后才输出正文。
# 额度过小（如 1200）时会出现「整段只有思考、正文为空」的情况，因此给足预算。
CONSULT_MAX_TOKENS = int(os.environ.get("CONSULT_MAX_TOKENS", "2048"))

# ==================== 响应速度优化（简洁输出）====================
# 本地实测：deepseek-r1:8b 在本机约 16 tokens/s，耗时几乎完全由「输出 token 数」决定
# （推理内容 + 正文都在 max_tokens 预算内）。因此缩短输出是最直接的加速手段。
# 追加到系统提示词的简洁性约束；置空字符串可关闭。注意措辞必须强调「末尾 JSON 块照常输出」，
# 否则模型会为了省字而省略结构化数据，导致阶段无法推进。
CONSULT_BRIEF_OUTPUT = os.environ.get("CONSULT_BRIEF_OUTPUT", "true").strip().lower() in ("1", "true", "yes", "on")

CONSULT_BRIEF_HINT = os.environ.get(
    "CONSULT_BRIEF_HINT",
    "【响应速度要求】先用最简短的方式想清楚(思考过程不要超过 100 字),"
    "然后直接给出回复。正文控制在 120 字以内,一次只问最关键的 1 个问题,"
    "不要罗列条目、不要重复已确认的信息。"
    "注意:正文之后末尾的 JSON 块必须照常完整输出。",
)

DIRECT_QA_BRIEF_HINT = os.environ.get(
    "DIRECT_QA_BRIEF_HINT",
    "【响应速度要求】请直接给出结论与最关键的 1-3 条建议,控制在 200 字以内,"
    "不要展开罗列、不要复述问题。分析过程请尽量简短。",
)

# 简洁性约束会把「末尾必须输出 JSON 块」这条要求挤到提示词中间,模型随即开始漏输出 JSON
# (实测:JSON 要求在前时命中率 0/9,压在最末尾时 9/9)。故追加简洁约束后必须再补一句提醒,
# 保证结构化数据不丢 —— 否则问诊阶段永远无法推进、报告也生成不了。
CONSULT_JSON_REMINDER = os.environ.get(
    "CONSULT_JSON_REMINDER",
    "【重要-必须遵守】上述简洁要求不影响结构化输出:正文之后,仍必须在回复的最末尾\n"
    "附上 JSON 块(含 patient_name/patient_gender/patient_age/chief_complaint/present_illness/\n"
    "past_history/personal_history/family_history/system_review/stage_complete/next_stage 字段)。\n"
    "只提取对话中明确提到的信息,JSON 块不得省略。",
)

# ==================== 阶段推进兜底 ====================
# 问诊状态机原完全依赖模型返回的 stage_complete。实测某些轮次模型会完全不输出
# JSON 块(或未收齐信息也持续 false),状态机随即永久卡在 stage 1 —— 问诊永远出
# 不了报告、"记录"页永远为空。开启后由确定性规则兜底推进(见 consultation
# .ConsultationSession._fallback_stage_advance)。置 false 可退回纯 LLM 判定。
ENABLE_STAGE_GUARD = os.environ.get(
    "ENABLE_STAGE_GUARD", "true").strip().lower() in ("1", "true", "yes", "on")

# ==================== 输出与交互开关 ====================
# 流式输出：true 时 /chat 走 SSE 逐段返回，体验更友好；false 时回退到一次性 JSON。
STREAMING_OUTPUT = os.environ.get("STREAMING_OUTPUT", "true").strip().lower() in ("1", "true", "yes", "on")

# 直接问答路由：true 时启用轻量意图识别，对「用药/疾病咨询」类问题直接回答，
# 不再机械套用 5 阶段采集流程；false 时维持原 5 阶段行为。
ENABLE_DIRECT_QA = os.environ.get("ENABLE_DIRECT_QA", "true").strip().lower() in ("1", "true", "yes", "on")

# 思维链(思考过程)透出：true 时向后端实时转发推理模型的「思考过程」(thinking 事件),
# 前端以可折叠的「💭 思考过程」块展示,降低长思维链带来的"空等"感并提升可解释性。
# 仅当使用推理模型(如 deepseek-r1)时才有内容;使用非推理指令模型或关闭时静默(无 thinking 事件)。
# 关闭可进一步缩短首字前的等待,但会失去可解释性。
SHOW_THINKING = os.environ.get("SHOW_THINKING", "true").strip().lower() in ("1", "true", "yes", "on")

# ==================== ReAct 推理过程(可解释性)配置 ====================
# 在「直接问答」分支启用 ReAct 受控循环:Thought/Action 由 Planner 产出,
# Observation 只来自工具真实返回值(不由模型编造),并把完整推理步骤下发给前端。
# Planner 与终答均复用 CONSULT_MODEL_NAME(不引入新模型标识)。
ENABLE_REACT = os.environ.get("ENABLE_REACT", "false").strip().lower() in ("1", "true", "yes", "on")

# Planner 最大步数(含第 0 步确定性步骤):超过即强制进入终答
REACT_MAX_STEPS = int(os.environ.get("REACT_MAX_STEPS", "3"))

# 单轮推理编排预算(毫秒)。作用于「Planner 循环 + 工具调用」阶段,
# 超限立即进入终答(终答全程流式,不再受此预算约束)。
REACT_BUDGET_MS = int(os.environ.get("REACT_BUDGET_MS", "8000"))

# 单个工具调用超时(毫秒),超时按空观察处理并降级,不中断整轮
REACT_TOOL_TIMEOUT_MS = int(os.environ.get("REACT_TOOL_TIMEOUT_MS", "4000"))

# 是否向前端下发 step 事件(false 时仅落库供追溯)
REACT_SHOW_STEPS = os.environ.get("REACT_SHOW_STEPS", "true").strip().lower() in ("1", "true", "yes", "on")

# 是否把推理步骤落库到 session_steps 表
REACT_PERSIST = os.environ.get("REACT_PERSIST", "true").strip().lower() in ("1", "true", "yes", "on")

# 终答句子级溯源:解析正文每句携带的 [n] 引用编号,回校验后绑定到知识片段
REACT_SENTENCE_CITATION = os.environ.get("REACT_SENTENCE_CITATION", "true").strip().lower() in ("1", "true", "yes", "on")

# 引用编号回校验:剥离正文里未定义的 [n](防止小模型乱标)
REACT_CITATION_CHECK = os.environ.get("REACT_CITATION_CHECK", "true").strip().lower() in ("1", "true", "yes", "on")

# ==================== 防幻觉:证据门槛与零命中兜底 ====================
# kb_search 片段的相关度下限(0~1,score = 1 - cosine_distance)。
# 低于该值的片段不进引用池、不作为作答依据 —— 避免「沾边段落」被当成医学证据。
REACT_MIN_SCORE = float(os.environ.get("REACT_MIN_SCORE", "0.50"))

# 零命中(经 REACT_MIN_SCORE 过滤后无任何可引用片段)时的确定作答语。
# 语义是「不推测、不编造」,直接把就医建议给用户。
REACT_NO_EVIDENCE_REPLY = os.environ.get("REACT_NO_EVIDENCE_REPLY", "知识库未覆盖，建议就医。")

# True(默认):零命中时直接以上述话术作答,跳过终答 LLM —— 结果 100% 可预期,
#   也省掉一次几十秒的无效生成(没有任何依据时,生成得越好越危险)。
# False:仍生成,但会用后置校验强制话术,未命中则整段替换(保留回滚空间)。
REACT_NO_EVIDENCE_STRICT = os.environ.get(
    "REACT_NO_EVIDENCE_STRICT", "true").strip().lower() in ("1", "true", "yes", "on")

# 话题明显超出健康科普范围时的二级兜底引导(C 期)。
REACT_OUT_OF_SCOPE_REPLY = os.environ.get(
    "REACT_OUT_OF_SCOPE_REPLY",
    "本助手的知识库目前只覆盖用药、症状、疾病与日常护理等健康科普内容，"
    "这个问题超出了我的覆盖范围。建议直接描述你的具体健康问题（如症状、用药、护理），"
    "或及时就医询问。",
)

# ==================== 数据库配置 ====================
DB_PATH = os.environ.get("DB_PATH", os.path.join(_app_dir, "data", "medical.db"))

# ==================== 知识库配置 ====================
CHROMA_PATH = os.environ.get("CHROMA_PATH", os.path.join(_app_dir, "data", "chroma_db"))

KNOWLEDGE_DIR = os.environ.get("KNOWLEDGE_DIR", os.path.join(_app_dir, "data", "knowledge"))

CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "500"))

CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "100"))

# 分块策略。"heading"(默认):按 Markdown 的 ## 标题层级切分,一个块 = 一个 ## 主题
#   (标题行 + 其下直到下一个 ## 之前的全部内容,含 ### 子标题、正文与代码块);
#   第一个 ## 之前的 # 级标题与引言单独成块。
#   "legacy":回退到旧的「标题优先 + 贪心装箱到 CHUNK_SIZE」行为。
# 实测本库 11 篇文档按 ## 切分后最大块 1337 字,主题纯度显著高于装箱方案
#   (旧方案 114/117 块跨多个标题)。
CHUNK_STRATEGY = os.environ.get("CHUNK_STRATEGY", "heading").strip().lower()

# 单个 ## 块超过该长度时才二次切分(先在 ### 处断开,再按字符+重叠兜底)。
# 设得足够大,是为了让「一个 ## 主题 = 一个块」成为常态,二次切分只作安全阀。
CHUNK_H2_MAX_SIZE = int(os.environ.get("CHUNK_H2_MAX_SIZE", "2000"))

# 低于该长度的块不写入向量库(切分时仍会产出,只是不参与检索)。
# 起因:按 ## 切分后,12 个文档的引言块只剩一行 H1 标题(11~16 字)。这类块
#   没有任何可用信息,但短文本的余弦相似度会虚高 —— 实测一个 14 字的标题行
#   对「发烧能不能吃对乙酰氨基酚」拿到 0.77 分,把真正含药名的片段挤出 Top-K。
# 本库内容块最短 76 字,取 40 可安全分离。置 0 可关闭该过滤。
CHUNK_MIN_INDEX_LEN = int(os.environ.get("CHUNK_MIN_INDEX_LEN", "40"))

SEARCH_TOP_K = int(os.environ.get("SEARCH_TOP_K", "5"))

# ==================== 长记忆配置 ====================
# 跨会话对话记忆:每轮对话片段/会话摘要写入独立 Chroma 集合(consultation_memory),
# 问诊与直接问答时按语义检索既往对话并注入上下文。关闭后回退纯滑动窗口行为。
ENABLE_LONG_MEMORY = os.environ.get("ENABLE_LONG_MEMORY", "true").strip().lower() in ("1", "true", "yes", "on")

# 每次注入上下文的历史记忆条数
MEMORY_TOP_K = int(os.environ.get("MEMORY_TOP_K", "3"))

# 写入记忆的最小片段长度(过短的"是/否"类答复不写入,降低噪声)
MEMORY_MIN_LEN = int(os.environ.get("MEMORY_MIN_LEN", "8"))

# ==================== 问诊上下文与字段提取 ====================
# 注入 LLM 的历史消息条数(user+assistant 各算 1 条,12 条 ≈ 最近 6 轮)。
# 原实现四处硬编码 [-6:](≈3 轮):早期轮次提供的背景信息(用药过敏史、既往就诊等)
# 若当时没被 LLM 提取进结构化字段,3 轮后就从模型视野里彻底消失 ——
# 表现为「答非所问 / 重复问已问过的问题」。长期记忆又刻意排除当前会话
# (见 consultation._retrieve_memory 的 exclude_session_id),没有其他通道能把它找回来。
# 故把窗口放宽到 6 轮;本地 7b 模型 32k 上下文,这点增量对首字延迟影响可忽略。
CONSULT_HISTORY_TURNS = int(os.environ.get("CONSULT_HISTORY_TURNS", "12"))

# 自由文本字段(现病史/既往史/个人史/家族史/系统回顾)采用累积合并而非覆盖。
# 关闭则退回旧的「每轮整体覆盖」行为(实测会让前几轮采集的细节被更短的新值顶掉)。
CONSULT_FIELDS_MERGE = os.environ.get("CONSULT_FIELDS_MERGE", "true").strip().lower() in (
    "1", "true", "yes", "on")

# 单个自由文本字段合并后的最大长度(超出则保留尾部新内容,避免越攒越长拖慢生成)
CONSULT_FIELD_MAX_LEN = int(os.environ.get("CONSULT_FIELD_MAX_LEN", "600"))

# 在用户消息附近复述一份极简的「已收集项,禁止重复询问」提示。
# 上下文里完整的"已收集"清单在最前面,7b 模型对长提示开头的指令遵循度偏低,
# 光靠它压不住重复提问,故再贴一份紧凑版在靠近生成起点的位置(成本仅几十字)。
CONSULT_NO_REPEAT_HINT = os.environ.get("CONSULT_NO_REPEAT_HINT", "true").strip().lower() in (
    "1", "true", "yes", "on")

# 确定性兜底提取:LLM 未输出 JSON / 字段为空时,用规则从用户原话里补抽年龄与性别。
# 这是「字段校验仅判空」的补丁 —— 没有它,模型漏输出 JSON 的那一轮信息就永久丢失。
CONSULT_REGEX_FALLBACK = os.environ.get("CONSULT_REGEX_FALLBACK", "true").strip().lower() in (
    "1", "true", "yes", "on")

# ==================== 多模态输入(语音/图片识别)配置 ====================
# 语音识别(ASR):基于 OpenAI 兼容的 /v1/audio/transcriptions 接口。
# 本地 Ollama 需先 `ollama pull whisper`;OpenAI 则直接用 whisper-1。
# 默认关闭,避免在未配置语音模型时影响现有问诊流程。
ASR_ENABLED = os.environ.get("ASR_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
# 语音后端:ollama(OpenAI 兼容,需 Ollama 提供 whisper 模型) |
#           openai(OpenAI 云 whisper-1) | local(进程内 faster-whisper,完全离线)
# 注意:Ollama 官方库已下架 whisper 模型,本地离线方案请设 ASR_BACKEND=local
ASR_BACKEND = os.environ.get("ASR_BACKEND", "ollama").strip().lower()
ASR_MODEL = os.environ.get("ASR_MODEL", "whisper")
# local 后端专用:faster-whisper 模型尺寸 / 设备 / 精度
ASR_MODEL_SIZE = os.environ.get("ASR_MODEL_SIZE", "base")
ASR_DEVICE = os.environ.get("ASR_DEVICE", "cpu")
ASR_COMPUTE_TYPE = os.environ.get("ASR_COMPUTE_TYPE", "int8")
ASR_API_BASE_URL = os.environ.get("ASR_API_BASE_URL", API_BASE_URL)
ASR_API_KEY = os.environ.get("ASR_API_KEY", API_KEY)
ASR_MAX_SIZE_MB = int(os.environ.get("ASR_MAX_SIZE_MB", "10"))
ASR_SUPPORTED_FORMATS = tuple(
    o.strip().lower() for o in os.environ.get("ASR_SUPPORTED_FORMATS", "mp3,wav,m4a,amr,pcm").split(",") if o.strip()
)
# local 后端:预先下载到本地的权重目录(绝对路径)。设置后完全离线从本地目录加载,
# 不走 HuggingFace Hub,避免国内网络拉取权重失败。留空则兜底走 HF 镜像按需下载。
ASR_LOCAL_MODEL_DIR = os.environ.get("ASR_LOCAL_MODEL_DIR", "").strip()
# local 后端:识别语言。留空=自动检测;医疗问诊场景建议固定 zh(更快且避免误判为英语/日语)
ASR_LANGUAGE = os.environ.get("ASR_LANGUAGE", "zh").strip()
# local 后端:初始提示词(给解码器一点领域先验,能提升医学术语准确率),留空则不使用
ASR_INITIAL_PROMPT = os.environ.get("ASR_INITIAL_PROMPT", "以下是一段中文医疗问诊对话。").strip()

# 图片识别(Vision):基于 OpenAI 兼容多模态 chat(消息内含 image_url)。
# 需多模态模型:本地 Ollama 可 `ollama pull llava` 或 `qwen2.5vl`;OpenAI 用 gpt-4o-mini 等。
# 默认关闭,避免用非多模态主模型去识别图片导致失败。
VISION_ENABLED = os.environ.get("VISION_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
VISION_MODEL = os.environ.get("VISION_MODEL", MODEL_NAME)
VISION_API_BASE_URL = os.environ.get("VISION_API_BASE_URL", API_BASE_URL)
VISION_API_KEY = os.environ.get("VISION_API_KEY", API_KEY)
VISION_MAX_SIZE_MB = int(os.environ.get("VISION_MAX_SIZE_MB", "10"))
VISION_MAX_TOKENS = int(os.environ.get("VISION_MAX_TOKENS", "1500"))
VISION_SUPPORTED_FORMATS = tuple(
    o.strip().lower() for o in os.environ.get("VISION_SUPPORTED_FORMATS", "jpg,jpeg,png,webp,bmp,gif").split(",") if o.strip()
)

# ==================== 服务配置 ====================
# DESKTOP_MODE=True 时保留单机桌面行为(旧 /chat 等路由 + Ollama 自动安装 + 自动开浏览器)
# DESKTOP_MODE=False 时作为小程序后端 API 服务器,启用 app/ 包的路由与中间件
DESKTOP_MODE = os.environ.get("DESKTOP_MODE", "false").strip().lower() in ("1", "true", "yes", "on")

# 桌面模式默认绑定本地回环;小程序/API 模式默认监听 0.0.0.0 以便云端部署
SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1" if DESKTOP_MODE else "0.0.0.0")

SERVER_PORT = int(os.environ.get("SERVER_PORT", "8000"))

LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "300"))

LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "3"))

# ==================== 后台报告生成配置 ====================
# 报告改为 asyncio.create_task 后台生成(不随 SSE 断开而中断)。
# REPORT_GEN_TIMEOUT: 单次尝试的整体超时(asyncio.wait_for,秒)。
# REPORT_MAX_ATTEMPTS: 最大尝试次数(失败自动重试 1 次)。
REPORT_GEN_TIMEOUT = int(os.environ.get("REPORT_GEN_TIMEOUT", "300"))
REPORT_MAX_ATTEMPTS = int(os.environ.get("REPORT_MAX_ATTEMPTS", "2"))

# ==================== 安全与认证配置 ====================
# JWT 签名密钥(必填,启动时校验非空;生产务必通过环境变量注入)
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-secret-key-change-in-prod")
JWT_ALG = os.environ.get("JWT_ALG", "HS256")
JWT_TTL_DAYS = int(os.environ.get("JWT_TTL_DAYS", "7"))

# 字段加密主密钥(32 字节 base64,KEK 派生源;生产务必通过环境变量/KMS 注入,绝不入仓入日志)
MASTER_KEY = os.environ.get("MASTER_KEY", "")  # 为空时 dev 模式自动生成(仅开发,重启失效)

# ==================== 微信小程序配置 ====================
WX_APPID = os.environ.get("WX_APPID", "")
WX_SECRET = os.environ.get("WX_SECRET", "")

# code2session 调用基础地址
WX_API_BASE = os.environ.get("WX_API_BASE", "https://api.weixin.qq.com")

# 订阅消息模板:场景 -> 模板 ID,JSON 字符串注入(如 '{"consult_done":"TplIdxxx"}')
# 留空则进入 dev 降级(发信用 mock 返回,不触网)
WX_SUBSCRIBE_TEMPLATES = {}
_WX_SUB_RAW = os.environ.get("WX_SUBSCRIBE_TEMPLATES", "{}")
try:
    WX_SUBSCRIBE_TEMPLATES = json.loads(_WX_SUB_RAW) if isinstance(_WX_SUB_RAW, str) else _WX_SUB_RAW
except Exception:
    WX_SUBSCRIBE_TEMPLATES = {}

# 小程序码默认落地页(仅 page 路径,不带 query)
WXACODE_DEFAULT_PAGE = os.environ.get("WXACODE_DEFAULT_PAGE", "pages/index/index")

# ==================== CORS 配置 ====================
# 小程序无 CORS 限制,但分享落地页/Web 调试需要;逗号分隔多域名
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

# ==================== 限流配置 ====================
# code2session 登录限流:同一 IP 每分钟最大次数
LOGIN_RATE_LIMIT = int(os.environ.get("LOGIN_RATE_LIMIT", "10"))

# session_key 缓存 TTL(秒),用于解密手机号等 encrypted_data
SESSION_KEY_TTL = int(os.environ.get("SESSION_KEY_TTL", "300"))

# ==================== 紧急症状关键词 ====================
EMERGENCY_KEYWORDS = [
    "胸痛", "胸闷", "呼吸困难", "意识丧失", "昏迷", "大出血",
    "剧烈头痛", "持续高热", "抽搐", "窒息", "心脏骤停",
    "休克", "过敏性休克", "严重创伤", "中毒"
]
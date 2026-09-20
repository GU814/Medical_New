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
CONSULT_MAX_TOKENS = int(os.environ.get("CONSULT_MAX_TOKENS", "4096"))

# ==================== 输出与交互开关 ====================
# 流式输出：true 时 /chat 走 SSE 逐段返回，体验更友好；false 时回退到一次性 JSON。
STREAMING_OUTPUT = os.environ.get("STREAMING_OUTPUT", "true").strip().lower() in ("1", "true", "yes", "on")

# 直接问答路由：true 时启用轻量意图识别，对「用药/疾病咨询」类问题直接回答，
# 不再机械套用 5 阶段采集流程；false 时维持原 5 阶段行为。
ENABLE_DIRECT_QA = os.environ.get("ENABLE_DIRECT_QA", "true").strip().lower() in ("1", "true", "yes", "on")

# ==================== 数据库配置 ====================
DB_PATH = os.environ.get("DB_PATH", os.path.join(_app_dir, "data", "medical.db"))

# ==================== 知识库配置 ====================
CHROMA_PATH = os.environ.get("CHROMA_PATH", os.path.join(_app_dir, "data", "chroma_db"))

KNOWLEDGE_DIR = os.environ.get("KNOWLEDGE_DIR", os.path.join(_app_dir, "data", "knowledge"))

CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "500"))

CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "100"))

SEARCH_TOP_K = int(os.environ.get("SEARCH_TOP_K", "5"))

# ==================== 长记忆配置 ====================
# 跨会话对话记忆:每轮对话片段/会话摘要写入独立 Chroma 集合(consultation_memory),
# 问诊与直接问答时按语义检索既往对话并注入上下文。关闭后回退纯滑动窗口行为。
ENABLE_LONG_MEMORY = os.environ.get("ENABLE_LONG_MEMORY", "true").strip().lower() in ("1", "true", "yes", "on")

# 每次注入上下文的历史记忆条数
MEMORY_TOP_K = int(os.environ.get("MEMORY_TOP_K", "3"))

# 写入记忆的最小片段长度(过短的"是/否"类答复不写入,降低噪声)
MEMORY_MIN_LEN = int(os.environ.get("MEMORY_MIN_LEN", "8"))

# ==================== 服务配置 ====================
# DESKTOP_MODE=True 时保留单机桌面行为(旧 /chat 等路由 + Ollama 自动安装 + 自动开浏览器)
# DESKTOP_MODE=False 时作为小程序后端 API 服务器,启用 app/ 包的路由与中间件
DESKTOP_MODE = os.environ.get("DESKTOP_MODE", "false").strip().lower() in ("1", "true", "yes", "on")

# 桌面模式默认绑定本地回环;小程序/API 模式默认监听 0.0.0.0 以便云端部署
SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1" if DESKTOP_MODE else "0.0.0.0")

SERVER_PORT = int(os.environ.get("SERVER_PORT", "8000"))

LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "300"))

LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "3"))

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
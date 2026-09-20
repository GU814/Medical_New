"""
语音识别服务(ASR) - 语音输入 -> 文本

通过 OpenAI 兼容的 /v1/audio/transcriptions 接口完成语音转写。
- 本地 Ollama:需先 `ollama pull whisper`,ASR_MODEL 设为 whisper
- OpenAI:ASR_MODEL 设为 whisper-1,ASR_API_BASE_URL 指向 https://api.openai.com/v1

设计要点:
- 未启用(ASR_ENABLED=false)时抛 NotImplementedError,由路由转成 501,前端给出友好提示
- 与问诊主 LLM 共用 "OpenAI 兼容" 协议,但允许独立配置地址/模型/密钥
- 异常安全:任何底层异常都向上抛出,由路由统一转成 502,不污染问诊主流程
"""

import logging

import config

logger = logging.getLogger(__name__)

# 懒加载的同步客户端(语音转写是一次性请求,用同步客户端放线程池即可)
_client = None


def _get_client():
    """获取 ASR 专用 OpenAI 兼容客户端(懒加载单例)"""
    global _client
    if _client is not None:
        return _client
    from openai import OpenAI

    try:
        import httpx
        try:
            http_client = httpx.Client(proxy=None)
        except TypeError:
            http_client = httpx.Client(proxies=None)
        _client = OpenAI(
            api_key=config.ASR_API_KEY if config.ASR_API_KEY else "not-needed",
            base_url=config.ASR_API_BASE_URL,
            timeout=config.LLM_TIMEOUT,
            http_client=http_client,
        )
    except Exception as e:
        logger.error(f"ASR 客户端初始化失败: {e}")
        raise
    return _client


def transcribe(audio_bytes: bytes, filename: str | None = None) -> str:
    """
    将音频字节转写为文本。

    Args:
        audio_bytes: 完整音频文件的二进制内容
        filename: 原始文件名(用于推断扩展名,便于后端按格式处理)
    Returns:
        识别出的纯文本(已 strip)
    Raises:
        NotImplementedError: ASR 未启用
        Exception: 转写失败(网络/模型不可用/不支持格式等)
    """
    if not config.ASR_ENABLED:
        raise NotImplementedError(
            "语音识别未启用:请在 .env 设置 ASR_ENABLED=true 并配置 ASR_MODEL"
            "(本地 Ollama 需先 `ollama pull whisper`)。"
        )

    if not audio_bytes:
        raise ValueError("音频内容为空")

    ext = (filename or "audio.mp3").rsplit(".", 1)[-1].lower() or "mp3"
    # OpenAI SDK 的 file 参数支持 (filename, content) 元组
    file_tuple = (f"speech.{ext}", audio_bytes)

    client = _get_client()
    try:
        resp = client.audio.transcriptions.create(
            model=config.ASR_MODEL,
            file=file_tuple,
        )
    except Exception as e:
        # 常见:Ollama 未拉取 whisper -> 404/模型不存在;把根因透出便于排障
        logger.error(f"语音转写调用失败: {e}")
        raise

    text = (getattr(resp, "text", None) or "").strip()
    return text

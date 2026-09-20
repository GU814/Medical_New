"""
图片识别服务(Vision) - 图片输入 -> 文本

通过 OpenAI 兼容的多模态 chat 接口完成图片理解:消息中含 image_url(data URL),
由多模态模型返回对图片中信息的结构化文字描述(检查报告/化验单/处方/病历/症状照片等)。

- 本地 Ollama:需 `ollama pull llava`(或 qwen2.5vl),VISION_MODEL 设为对应模型名
- OpenAI:VISION_MODEL 设为 gpt-4o-mini 等多模态模型

设计要点:
- 未启用(VISION_ENABLED=false)时抛 NotImplementedError -> 路由转 501
- 图片以 base64 data URL 内联,避免临时落盘与额外存储
- 异常安全:底层异常向上抛出,由路由统一转 502
"""

import base64
import logging
import mimetypes

import config

logger = logging.getLogger(__name__)

# 懒加载的同步客户端(图片识别为一次性请求,放线程池即可)
_client = None

# 识别系统提示词:聚焦医学场景,客观提取、不编造
VISION_SYSTEM_PROMPT = """你是一位医学辅助信息识别助手。用户会上传一张图片,可能是检查报告、化验单、处方、病历、皮肤/伤口照片或药物包装。

请遵守:
1. 用中文、结构化地提取图片中的关键信息(患者信息、检查/检验项目与数值、诊断、用药、可见的症状或体征描述等);
2. 若图片与医学无关,如实说明"图片中未看到明确的医学信息";
3. 绝不编造图中不存在的信息;无法辨认的内容标注"看不清";
4. 输出简洁、客观,便于后续问诊助手据此继续提问与采集信息。"""


def _get_client():
    """获取 Vision 专用 OpenAI 兼容客户端(懒加载单例)"""
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
            api_key=config.VISION_API_KEY if config.VISION_API_KEY else "not-needed",
            base_url=config.VISION_API_BASE_URL,
            timeout=config.LLM_TIMEOUT,
            http_client=http_client,
        )
    except Exception as e:
        logger.error(f"Vision 客户端初始化失败: {e}")
        raise
    return _client


def _guess_mime(filename: str | None) -> str:
    """根据文件名推断 MIME,未知回退为 png"""
    if filename:
        mime, _ = mimetypes.guess_type(filename)
        if mime:
            return mime
    return "image/png"


def recognize(
    image_bytes: bytes,
    filename: str | None = None,
    prompt: str | None = None,
) -> str:
    """
    识别图片内容,返回文字描述。

    Args:
        image_bytes: 完整图片文件的二进制内容
        filename: 原始文件名(用于推断 MIME)
        prompt: 可选的识别指令(默认提取要点)
    Returns:
        模型返回的文字描述(已 strip)
    Raises:
        NotImplementedError: 图片识别未启用
        Exception: 识别失败
    """
    if not config.VISION_ENABLED:
        raise NotImplementedError(
            "图片识别未启用:请在 .env 设置 VISION_ENABLED=true 并配置 VISION_MODEL"
            "(需多模态模型,本地 Ollama 可 `ollama pull llava` 或 qwen2.5vl)。"
        )

    if not image_bytes:
        raise ValueError("图片内容为空")

    mime = _guess_mime(filename)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    user_text = prompt or "请识别这张图片中的信息并提取要点。"
    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model=config.VISION_MODEL,
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            max_tokens=config.VISION_MAX_TOKENS,
            temperature=0,
        )
    except Exception as e:
        logger.error(f"图片识别调用失败: {e}")
        raise

    text = (resp.choices[0].message.content or "").strip()
    return text

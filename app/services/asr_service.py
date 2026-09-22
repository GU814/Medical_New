"""
语音识别服务(ASR) - 语音输入 -> 文本

通过 OpenAI 兼容的 /v1/audio/transcriptions 接口完成语音转写。
- 本地 Ollama:需先 `ollama pull whisper`,ASR_MODEL 设为 whisper(注意:Ollama 官方库已下架 whisper 模型)
- OpenAI:ASR_MODEL 设为 whisper-1,ASR_API_BASE_URL 指向 https://api.openai.com/v1
- 本地 faster-whisper(推荐,完全离线、无需密钥):ASR_BACKEND=local,ASR_MODEL 设为模型尺寸
  (base/small/medium/large-v3),权重经 HF 镜像(hf-mirror.com)下载

设计要点:
- 未启用(ASR_ENABLED=false)时抛 NotImplementedError,由路由转成 501,前端给出友好提示
- 与问诊主 LLM 共用 "OpenAI 兼容" 协议,但允许独立配置地址/模型/密钥
- 异常安全:任何底层异常都向上抛出,由路由统一转成 502,不污染问诊主流程
"""

import logging
import os
import tempfile

import config

logger = logging.getLogger(__name__)

# 懒加载的同步客户端(语音转写是一次性请求,用同步客户端放线程池即可)
_client = None

# 懒加载的本地 faster-whisper 模型(进程内常驻,首次转写时下载权重)
_fw_model = None


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

    # 后端选择:local=进程内 faster-whisper(离线);其余走 OpenAI 兼容接口(Ollama/OpenAI)
    backend = (getattr(config, "ASR_BACKEND", "ollama") or "ollama").lower()
    if backend == "local":
        return _transcribe_local(audio_bytes, filename)

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


def _transcribe_local(audio_bytes: bytes, filename: str | None) -> str:
    """
    本地 faster-whisper 后端:进程内离线转写,无需 Ollama 或外部 API。

    模型权重经 HF 镜像(hf-mirror.com)按需下载并缓存到本地;首次调用会触发下载。
    依赖已在 venv 安装:faster-whisper / av(PyAV,用于解码 mp3 等格式)。
    """
    from faster_whisper import WhisperModel

    model_size = getattr(config, "ASR_MODEL_SIZE", None) or getattr(config, "ASR_MODEL", "base") or "base"
    device = getattr(config, "ASR_DEVICE", "cpu") or "cpu"
    compute_type = getattr(config, "ASR_COMPUTE_TYPE", "int8") or "int8"

    # 优先使用预先下载到本地的权重目录(完全离线,绝不走 HuggingFace Hub)
    local_dir = getattr(config, "ASR_LOCAL_MODEL_DIR", None) or ""
    if local_dir and os.path.isdir(local_dir) and os.path.exists(os.path.join(local_dir, "model.bin")):
        model_path = local_dir
        # 彻底禁止任何网络回退,确保离线运行
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        logger.info("使用本地权重目录加载 faster-whisper: %s (%s/%s)", model_path, device, compute_type)
    else:
        # 兜底:经 HF 镜像按需下载(默认 hf-mirror.com,可在环境变量覆盖)
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        os.environ.setdefault("HF_HUB_DISABLE_PROXY", "1")
        os.environ.setdefault("no_proxy", f"hf-mirror.com,{os.environ.get('no_proxy', '')}")
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
        os.environ.setdefault("HF_DOWNLOAD_TIMEOUT", "600")
        model_path = model_size
        logger.info("本地权重目录未配置/不存在,改为经 HF 镜像下载: %s (%s/%s)", model_path, device, compute_type)

    global _fw_model
    if _fw_model is None:
        _fw_model = WhisperModel(model_path, device=device, compute_type=compute_type)

    ext = (filename or "audio.mp3").rsplit(".", 1)[-1].lower() or "mp3"
    with tempfile.NamedTemporaryFile(suffix="." + ext, delete=False) as tf:
        tf.write(audio_bytes)
        tmp_path = tf.name
    try:
        language = getattr(config, "ASR_LANGUAGE", None)
        language = (language or "").strip() or None  # 空串 -> 交给模型自动检测
        initial_prompt = getattr(config, "ASR_INITIAL_PROMPT", None)
        initial_prompt = (initial_prompt or "").strip() or None
        segments, _info = _fw_model.transcribe(
            tmp_path,
            beam_size=5,
            language=language,
            initial_prompt=initial_prompt,
            # 医疗口述常出现自纠正,关闭上文条件可显著降低"滚句子/重复"概率
            condition_on_previous_text=False,
        )
        text = "".join(seg.text for seg in segments).strip()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return text

"""
LLM 调用封装模块 - 医学问诊智能体
使用 OpenAI 兼容 API 格式，支持 DeepSeek / Ollama / 其他兼容 API
"""

import json
import logging
import time
from typing import Optional

from openai import OpenAI, AsyncOpenAI

import config

logger = logging.getLogger(__name__)

# 全局 LLM 客户端（懒加载）
_client = None

# 全局异步 LLM 客户端（流式输出用，懒加载）
_async_client = None


def _get_client() -> OpenAI:
    """获取 OpenAI 兼容 API 客户端（懒加载单例）"""
    global _client
    if _client is not None:
        return _client

    try:
        import httpx
        try:
            http_client = httpx.Client(proxy=None)
        except TypeError:
            http_client = httpx.Client(proxies=None)

        _client = OpenAI(
            api_key=config.API_KEY if config.API_KEY else "not-needed",
            base_url=config.API_BASE_URL,
            timeout=config.LLM_TIMEOUT,
            http_client=http_client,
        )
        logger.info(f"LLM 客户端已初始化，地址: {config.API_BASE_URL}，模型: {config.MODEL_NAME}")
        return _client
    except Exception as e:
        logger.error(f"LLM 客户端初始化失败: {e}")
        try:
            _client = OpenAI(
                api_key=config.API_KEY if config.API_KEY else "not-needed",
                base_url=config.API_BASE_URL,
                timeout=config.LLM_TIMEOUT,
            )
            logger.info(f"LLM 客户端已初始化（无自定义HTTP），地址: {config.API_BASE_URL}")
            return _client
        except Exception as e2:
            logger.error(f"LLM 客户端初始化最终失败: {e2}")
            raise


def _get_async_client() -> AsyncOpenAI:
    """获取 OpenAI 兼容异步 API 客户端（懒加载单例，用于流式输出）"""
    global _async_client
    if _async_client is not None:
        return _async_client

    try:
        import httpx
        try:
            http_client = httpx.AsyncClient(proxy=None)
        except TypeError:
            http_client = httpx.AsyncClient(proxies=None)

        _async_client = AsyncOpenAI(
            api_key=config.API_KEY if config.API_KEY else "not-needed",
            base_url=config.API_BASE_URL,
            timeout=config.LLM_TIMEOUT,
            http_client=http_client,
        )
        logger.info(f"异步 LLM 客户端已初始化，地址: {config.API_BASE_URL}")
        return _async_client
    except Exception as e:
        logger.warning(f"异步 LLM 客户端（自定义HTTP）初始化失败，尝试默认: {e}")
        try:
            _async_client = AsyncOpenAI(
                api_key=config.API_KEY if config.API_KEY else "not-needed",
                base_url=config.API_BASE_URL,
                timeout=config.LLM_TIMEOUT,
            )
            logger.info(f"异步 LLM 客户端已初始化（无自定义HTTP），地址: {config.API_BASE_URL}")
            return _async_client
        except Exception as e2:
            logger.error(f"异步 LLM 客户端初始化最终失败: {e2}")
            raise


def chat(
    system_prompt: str,
    user_prompt: str,
    history: list = None,
    temperature: float = None,
) -> str:
    """
    调用 LLM 进行对话，返回回复文本
    Args:
        system_prompt: 系统提示词
        user_prompt: 用户消息
        history: 对话历史（可选），格式: [{"role": "user/assistant", "content": "..."}]
        temperature: 温度参数（可选）
    Returns:
        LLM 回复的文本内容
    """
    temperature = temperature if temperature is not None else config.DEFAULT_TEMPERATURE
    client = _get_client()

    # 构建消息列表
    messages = [{"role": "system", "content": system_prompt}]

    # 添加对话历史
    if history:
        messages.extend(history)

    # 添加当前用户消息
    messages.append({"role": "user", "content": user_prompt})

    # 重试逻辑
    for attempt in range(1, config.LLM_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=config.MODEL_NAME,
                messages=messages,
                temperature=temperature,
                max_tokens=config.MAX_TOKENS,
            )
            result = response.choices[0].message.content.strip()
            logger.debug(f"LLM 调用成功（第 {attempt} 次），回复长度: {len(result)}")
            return result

        except Exception as e:
            logger.warning(f"LLM 调用失败（第 {attempt}/{config.LLM_MAX_RETRIES} 次）: {e}")
            if attempt < config.LLM_MAX_RETRIES:
                wait_time = attempt * 2  # 递增等待时间
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                logger.error(f"LLM 调用最终失败，已重试 {config.LLM_MAX_RETRIES} 次")
                if "connection" in str(e).lower() or "timeout" in str(e).lower():
                    return "抱歉，无法连接到 AI 服务。请检查 Ollama 是否已安装并运行，或运行 setup_offline.py 设置离线环境。"
                else:
                    return "抱歉，AI 服务暂时不可用，请稍后再试。"


def chat_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = None,
) -> dict:
    """
    调用 LLM 并要求返回 JSON 格式结果
    Args:
        system_prompt: 系统提示词
        user_prompt: 用户消息
        temperature: 温度参数（可选）
    Returns:
        解析后的 JSON 字典；解析失败返回空字典
    """
    temperature = temperature if temperature is not None else 0.1  # JSON 输出用低温度

    # 在系统提示词中追加 JSON 格式要求
    json_system_prompt = system_prompt + "\n\n请严格按照 JSON 格式输出，不要输出任何其他内容。"

    client = _get_client()

    messages = [
        {"role": "system", "content": json_system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 重试逻辑
    for attempt in range(1, config.LLM_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=config.MODEL_NAME,
                messages=messages,
                temperature=temperature,
                max_tokens=config.MAX_TOKENS,
            )
            raw_content = response.choices[0].message.content.strip()

            # 尝试从 markdown 代码块中提取 JSON
            if "```json" in raw_content:
                json_str = raw_content.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_content:
                json_str = raw_content.split("```")[1].split("```")[0].strip()
            else:
                json_str = raw_content

            result = json.loads(json_str)
            logger.debug(f"LLM JSON 调用成功（第 {attempt} 次）")
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"LLM JSON 解析失败（第 {attempt} 次）: {e}")
            logger.debug(f"原始返回内容: {raw_content[:500]}")
            if attempt < config.LLM_MAX_RETRIES:
                time.sleep(attempt * 2)
            else:
                logger.error("LLM JSON 输出解析最终失败")
                return {}

        except Exception as e:
            logger.warning(f"LLM JSON 调用失败（第 {attempt} 次）: {e}")
            if attempt < config.LLM_MAX_RETRIES:
                time.sleep(attempt * 2)
            else:
                logger.error(f"LLM JSON 调用最终失败: {e}")
                return {}


def _strip_think_stream(delta: str, state: dict) -> str:
    """
    增量剥离 deepseek-r1 等推理模型的 <think>...</think> 思维链。
    支持标签被分片（跨多次 delta）的情况，仅在闭合标签之后才输出正文。
    Args:
        delta: 本次新增的文本片段
        state: 调用方需在多次调用间复用的状态字典，初始为 {"in_think": False, "buf": ""}
    Returns:
        应当对外输出的文本片段（已剔除思维链）
    """
    out = ""
    text = state["buf"] + delta
    i = 0
    while i < len(text):
        if state["in_think"]:
            end = text.find("</think>", i)
            if end == -1:
                # 思维链尚未闭合，缓存剩余内容等待后续
                state["buf"] = text[i:]
                break
            i = end + len("</think>")
            state["in_think"] = False
        else:
            start = text.find("<think>", i)
            if start == -1:
                # 剩余无思维链起始标签，全部输出
                out += text[i:]
                state["buf"] = ""
                break
            # 输出思维链之前的正文，进入思维链状态
            out += text[i:start]
            i = start + len("<think>")
            state["in_think"] = True
    return out


async def chat_stream(
    system_prompt: str,
    user_prompt: str,
    history: list = None,
    temperature: float = None,
    model: str = None,
    max_tokens: int = None,
) -> str:
    """
    异步流式调用 LLM，作为异步生成器逐段 yield 文本片段。
    自动剥离 <think> 思维链（推理模型），对外部只暴露最终回答正文。
    Args:
        system_prompt: 系统提示词
        user_prompt: 用户消息
        history: 对话历史（可选）
        temperature: 温度参数（可选）
        model: 指定模型名（可选，默认用 config.CONSULT_MODEL_NAME）
        max_tokens: 单次生成上限（可选，默认用 config.CONSULT_MAX_TOKENS）
    Yields:
        文本片段（str）
    """
    temperature = temperature if temperature is not None else config.DEFAULT_TEMPERATURE
    model = model or config.CONSULT_MODEL_NAME
    max_tokens = max_tokens or config.CONSULT_MAX_TOKENS
    client = _get_async_client()

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    think_state = {"in_think": False, "buf": ""}
    emitted_any = False

    for attempt in range(1, config.LLM_MAX_RETRIES + 1):
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue
                out = _strip_think_stream(delta, think_state)
                if out:
                    emitted_any = True
                    yield out

            # 若整段都在思维链中（无正文），给出一个兜底提示
            if not emitted_any:
                yield "（模型未返回可见内容，请稍后重试或调整模型配置。）"
            return

        except Exception as e:
            logger.warning(f"流式 LLM 调用失败（第 {attempt}/{config.LLM_MAX_RETRIES} 次）: {e}")
            if attempt < config.LLM_MAX_RETRIES:
                wait_time = attempt * 2
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                logger.error(f"流式 LLM 调用最终失败，已重试 {config.LLM_MAX_RETRIES} 次")
                if "connection" in str(e).lower() or "timeout" in str(e).lower():
                    yield "抱歉，无法连接到 AI 服务。请检查 Ollama 是否已安装并运行，或运行 setup_offline.py 设置离线环境。"
                else:
                    yield "抱歉，AI 服务暂时不可用，请稍后再试。"

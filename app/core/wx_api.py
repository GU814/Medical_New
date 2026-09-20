"""
微信开放接口公共底座 - access_token 统一封装

设计要点(对齐项目既有「dev 降级」思路,如 auth_service 的 code="dev"):
- access_token 内存缓存,过期前 300s 主动刷新,避免频繁请求
- asyncio.Lock 防并发击穿(多请求同时发现过期只真实请求 1 次)
- 调微信接口失败一律返回 None / {"mock": True},**绝不向上抛 500**
- WX_APPID/WX_SECRET 缺失时进入 dev 模式:返回 mock token,下游可本地跑通链路

下游复用方:订阅消息(wxacode.getUnlimited)、小程序码、客服接口、内容安全。
"""

import asyncio
import logging
import time

import httpx

import config

logger = logging.getLogger(__name__)

# 内存缓存(单进程内有效;多副本部署可换 Redis,本项目规模够用)
_token_cache: dict = {"access_token": None, "expires_at": 0.0}
_token_lock = asyncio.Lock()


def _is_dev() -> bool:
    """无 AppID/Secret 视为 dev 模式,走 mock,不触网"""
    return not (config.WX_APPID and config.WX_SECRET)


async def get_access_token() -> str | None:
    """
    获取 access_token(带缓存 + 锁)。
    dev 模式返回固定 mock token;真实模式失败返回 None(调用方降级)。
    """
    if _is_dev():
        return "dev-mock-access-token"

    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"] - 300:
        return _token_cache["access_token"]

    async with _token_lock:
        # 双重检查:锁等待期间可能已被其他协程刷新
        if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 300:
            return _token_cache["access_token"]
        try:
            url = (
                f"{config.WX_API_BASE}/cgi-bin/token"
                f"?grant_type=client_credential&appid={config.WX_APPID}&secret={config.WX_SECRET}"
            )
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url)
                data = resp.json()
            if "access_token" not in data:
                logger.warning(f"[wx_api] 获取 access_token 失败: {data}")
                return None
            _token_cache["access_token"] = data["access_token"]
            _token_cache["expires_at"] = time.time() + float(data.get("expires_in", 7200))
            logger.info("[wx_api] access_token 已刷新")
            return _token_cache["access_token"]
        except Exception as e:
            logger.warning(f"[wx_api] 获取 access_token 异常: {e}")
            return None


async def wx_request(
    method: str,
    path: str,
    json: dict | None = None,
    params: dict | None = None,
) -> dict | None:
    """
    带 access_token 调用微信开放接口(非 token 端点)。
    token 以 query 参数 ?access_token= 注入(订阅消息/小程序码/客服接口的规范用法)。
    dev 模式返回 {"mock": True};失败返回 None。
    """
    token = await get_access_token()
    if not token:
        return None
    if token == "dev-mock-access-token":
        logger.info(f"[wx_api] dev mock,跳过真实调用 {method} {path}")
        return {"mock": True}

    q = dict(params or {})
    q["access_token"] = token
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.request(method, f"{config.WX_API_BASE}{path}", json=json, params=q)
            return resp.json()
    except Exception as e:
        logger.warning(f"[wx_api] 调用 {method} {path} 异常: {e}")
        return None


async def wx_get_bytes(method: str, path: str, json: dict | None = None) -> tuple:
    """
    同 wx_request,但返回原始二进制(用于小程序码等图片接口)。
    Returns: (content_bytes, content_type) | (None, None)
    """
    token = await get_access_token()
    if not token:
        return None, None
    if token == "dev-mock-access-token":
        return None, "mock"

    q = {"access_token": token}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.request(method, f"{config.WX_API_BASE}{path}", json=json, params=q)
            return resp.content, resp.headers.get("content-type", "image/png")
    except Exception as e:
        logger.warning(f"[wx_api] 二进制调用 {method} {path} 异常: {e}")
        return None, None

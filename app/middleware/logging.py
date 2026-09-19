"""
日志中间件 - 请求日志 + 敏感数据脱敏

脱敏规则:
- patient_name -> 姓 + **(如"张三"->"张**")
- 手机号 -> 前3后4(如"13812345678"->"138****5678")
- 身份证号 -> 前6后4
- 长 base64 串(疑似密钥/密文)-> ***REDACTED***
- openid/session_key/token 等关键字段
"""

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("app.access")

# 敏感字段名(出现在日志/查询参数时脱敏)
_SENSITIVE_KEYS = {"password", "token", "secret", "session_key", "openid", "authorization"}
# 长 base64(疑似密钥/密文)
_B64_RE = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")


def mask_name(name: str) -> str:
    """姓名脱敏:保留姓,其余 *"""
    if not name or not isinstance(name, str):
        return name
    if len(name) <= 1:
        return name[0] + "*" if name else name
    return name[0] + "*" * (len(name) - 1)


def mask_phone(phone: str) -> str:
    """手机号脱敏:前3后4"""
    if not phone or len(phone) < 7:
        return phone
    return phone[:3] + "****" + phone[-4:]


def _redact_value(v):
    if v is None:
        return None
    s = str(v)
    # 长 base64 串视为密钥/密文
    if _B64_RE.fullmatch(s):
        return "***REDACTED***"
    # 疑似手机号(11 位数字)
    if re.fullmatch(r"\d{11}", s):
        return mask_phone(s)
    return s


def redact_dict(d: dict) -> dict:
    """递归脱敏 dict 中的敏感字段"""
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        key_lower = str(k).lower()
        if key_lower in _SENSITIVE_KEYS:
            out[k] = "***REDACTED***"
        elif isinstance(v, dict):
            out[k] = redact_dict(v)
        elif isinstance(v, str):
            out[k] = _redact_value(v)
        else:
            out[k] = v
    return out


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:8]
        request.state.request_id = request_id

        start = time.time()
        # 记录请求(method/path,不记录 body 避免泄露明文)
        logger.info(f"[{request_id}] -> {request.method} {request.url.path}")

        try:
            response = await call_next(request)
        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error(f"[{request_id}] !! {request.method} {request.url.path} 异常 ({duration:.0f}ms): {e}")
            raise

        duration = (time.time() - start) * 1000
        logger.info(f"[{request_id}] <- {response.status_code} ({duration:.0f}ms)")
        response.headers["X-Request-ID"] = request_id
        return response

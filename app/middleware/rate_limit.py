"""
限流中间件 - 基于 IP 的滑动窗口限流

当前仅对登录端点 /auth/wx-login 限流(防 code2session 刷量)。
实现:进程内滑动窗口(单机部署足够;多实例需换 Redis)。
"""

import logging
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

import config

logger = logging.getLogger(__name__)

# ip -> [timestamps]
_login_hits: dict = defaultdict(deque)
_WINDOW = 60  # 60 秒窗口


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 仅对登录端点限流
        if path == "/auth/wx-login":
            ip = request.client.host if request.client else "unknown"
            now = time.time()
            hits = _login_hits[ip]
            # 清理过期
            while hits and hits[0] < now - _WINDOW:
                hits.popleft()
            if len(hits) >= config.LOGIN_RATE_LIMIT:
                logger.warning(f"登录限流触发 IP={ip}")
                return JSONResponse(
                    {"detail": "登录尝试过于频繁,请稍后再试"},
                    status_code=429,
                    headers={"Retry-After": str(_WINDOW)},
                )
            hits.append(now)

        return await call_next(request)

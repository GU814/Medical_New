"""
认证中间件 - JWT 校验,注入 request.state.user_id

白名单:/auth/wx-login、/api/share/{token}、/healthz、/、/static、旧桌面路由(桌面模式)
白名单路径之外的请求必须携带合法 Authorization: Bearer <token>
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

import config
from app.core.security import decode_access_token

logger = logging.getLogger(__name__)

# 无需认证的路径前缀/精确匹配
PUBLIC_PATHS = (
    "/auth/wx-login",
    "/api/share/",          # 分享公开访问(脱敏)
    "/healthz",
    "/favicon.ico",
    "/static/",
    "/docs",
    "/openapi.json",
    "/redoc",
)
# 桌面模式旧路由也放行(由旧逻辑自处理)
DESKTOP_PUBLIC_PATHS = ("/chat", "/reset", "/history")


def _is_public(path: str) -> bool:
    # 根路径仅精确匹配放行(仅重定向到 /docs,无敏感数据);
    # 不能放进 PUBLIC_PATHS 做前缀匹配,否则 "/" 前缀会放行所有路径
    if path == "/":
        return True
    if any(path == p or path.startswith(p) for p in PUBLIC_PATHS):
        return True
    if config.DESKTOP_MODE and path in DESKTOP_PUBLIC_PATHS:
        return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 白名单放行
        if _is_public(path):
            return await call_next(request)

        # 提取 JWT
        auth = request.headers.get("authorization", "")
        if not auth:
            return JSONResponse(
                {"detail": "未登录"}, status_code=401
            )
        parts = auth.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return JSONResponse({"detail": "认证格式错误"}, status_code=401)

        try:
            payload = decode_access_token(parts[1].strip())
            user_id = int(payload.get("sub"))
        except Exception as e:
            logger.info(f"认证失败 {path}: {e}")
            return JSONResponse({"detail": "登录已过期,请重新登录"}, status_code=401)

        # 注入 user_id,后续路由可通过 request.state.user_id 或 Depends(get_current_user) 取得
        request.state.user_id = user_id
        return await call_next(request)

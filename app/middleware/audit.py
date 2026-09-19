"""
审计中间件 - 记录敏感数据访问行为到 audit_logs

仅记录敏感操作(读记录/导出/分享创建/会话详情),非敏感请求不落库以减少噪声。
成功/拒绝均记录,便于合规留痕与异常追溯。
"""

import logging
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.db.connection import get_conn

logger = logging.getLogger(__name__)

# 需审计的路径前缀(读/导出/分享 等敏感操作)
_AUDITED_PREFIXES = (
    "/api/records/",
    "/api/share",
    "/api/sessions/",   # 会话详情含患者数据
    "/api/admin",
)


def _is_audited(path: str) -> bool:
    return any(path.startswith(p) for p in _AUDITED_PREFIXES)


def _infer_action(method: str, path: str) -> tuple:
    """从方法+路径推断 (action, resource_type)"""
    if path.startswith("/api/records/"):
        if path.endswith("/export"):
            return "export_pdf", "record"
        if path.endswith("/report"):
            return "read_report", "record"
        return f"read_{method.lower()}", "record"
    if path.startswith("/api/share"):
        if method == "POST":
            return "share_create", "record"
        return "share_view", "record"
    if path.startswith("/api/sessions/"):
        if path.endswith("/history"):
            return "read_session_history", "session"
        return "read_session", "session"
    if path.startswith("/api/admin"):
        return f"admin_{method.lower()}", "knowledge"
    return method.lower(), None


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        response = await call_next(request)

        if not _is_audited(path):
            return response

        user_id = getattr(request.state, "user_id", None)
        action, resource_type = _infer_action(request.method, path)
        # 从路径提取 resource_id(records/123 -> 123;share/{token} -> token)
        parts = path.strip("/").split("/")
        resource_id = parts[-1] if len(parts) >= 2 else None

        status = "success" if response.status_code < 400 else "denied"
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")

        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO audit_logs(user_id, action, resource_type, resource_id, ip, ua, status, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, action, resource_type, resource_id, ip, ua, status,
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"审计日志写入失败: {e}")

        return response

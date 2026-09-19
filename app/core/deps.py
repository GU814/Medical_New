"""
FastAPI 依赖注入 - 提供认证与归属校验依赖

用法:
    @router.get("/me")
    async def me(user: int = Depends(get_current_user)):
        ...
"""

import logging

from fastapi import Depends, Header, HTTPException, status

from app.core.security import decode_access_token

logger = logging.getLogger(__name__)


def get_current_user(authorization: str = Header(None)) -> int:
    """
    从 Authorization: Bearer <token> 提取并校验 JWT,返回 user_id。
    Raises: 401 未携带/格式错误/过期/无效
    """
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证格式错误")

    token = parts[1].strip()
    try:
        payload = decode_access_token(token)
    except Exception as e:
        logger.info(f"JWT 校验失败: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期,请重新登录")

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录凭证")

    return user_id


def get_optional_user(authorization: str = Header(None)):
    """可选认证:有合法 token 返回 user_id,否则返回 None(用于公开端点的可选鉴权)"""
    if not authorization:
        return None
    try:
        return get_current_user(authorization)
    except HTTPException:
        return None

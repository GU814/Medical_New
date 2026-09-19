"""
认证服务 - 微信登录 + 用户管理

流程:code2session -> upsert users -> 生成 DEK -> 签发 JWT
"""

import logging

from app.core import crypto, security
from app.db import repositories

logger = logging.getLogger(__name__)


def wx_login(code: str) -> dict:
    """
    微信授权登录核心流程。
    Returns: {token, expires_in, user_id, is_new}
    Raises: ValueError(微信侧错误)
    """
    # 1. code 换 openid/session_key
    session_info = security.code2session(code)
    openid = session_info["openid"]
    union_id = session_info.get("unionid")

    # 2. upsert 用户
    user_id, is_new = repositories.upsert_user_by_openid(openid, union_id)
    logger.info(f"微信登录成功 user_id={user_id} is_new={is_new}")

    # 3. 首次登录生成 DEK(显式触发,确保 user_keys 有记录)
    if is_new:
        crypto._get_or_create_dek(user_id)

    # 4. 签发 JWT
    token, expires_in = security.create_access_token(user_id, openid)

    return {
        "token": token,
        "expires_in": expires_in,
        "user_id": user_id,
        "is_new": is_new,
    }


def get_profile(user_id: int) -> dict:
    """获取当前用户信息(脱敏 openid/phone)"""
    user = repositories.get_user(user_id)
    if not user:
        return {}
    from app.middleware.logging import mask_phone
    # phone 加密存储,这里解密后脱敏展示
    phone_plain = crypto.decrypt_field(user_id, user.get("phone")) if user.get("phone") else None
    return {
        "user_id": user["user_id"],
        "openid_masked": (user["openid"][:4] + "***") if user.get("openid") else None,
        "nickname": user.get("nickname"),
        "avatar_url": user.get("avatar_url"),
        "phone_masked": mask_phone(phone_plain) if phone_plain else None,
        "created_at": user.get("created_at"),
    }


def update_profile(user_id: int, nickname: str = None, avatar_url: str = None, phone: str = None):
    """更新资料;phone 加密后存储"""
    phone_enc = crypto.encrypt_field(user_id, phone) if phone else None
    # phone_enc 为 None 时不更新(保留原值);为空串表示清空
    repositories.update_user_profile(
        user_id,
        nickname=nickname,
        avatar_url=avatar_url,
        phone=phone_enc if phone is not None else None,
    )

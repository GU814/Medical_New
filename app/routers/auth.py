"""认证路由 - 微信授权登录 + 用户资料"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.models.schemas import ProfileUpdate, WxLoginRequest, WxLoginResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["认证"])
logger = logging.getLogger(__name__)


@router.post("/wx-login", response_model=WxLoginResponse)
async def wx_login(req: WxLoginRequest):
    """微信授权登录:用 code 换 openid -> 签发 JWT"""
    try:
        result = auth_service.wx_login(req.code)
        return WxLoginResponse(**result)
    except ValueError as e:
        logger.warning(f"微信登录失败: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"微信登录异常: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="登录服务异常")


@router.get("/me")
async def me(user_id: int = Depends(get_current_user)):
    """获取当前登录用户信息(脱敏)"""
    profile = auth_service.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return profile


@router.put("/profile")
async def update_profile(
    req: ProfileUpdate,
    user_id: int = Depends(get_current_user),
):
    """更新用户资料(phone 加密存储)"""
    auth_service.update_profile(
        user_id,
        nickname=req.nickname,
        avatar_url=req.avatar_url,
        phone=req.phone,
    )
    return {"ok": True}

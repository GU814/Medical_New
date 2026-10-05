"""家庭成员路由 - 绑定 / 状态共享 / 紧急推送。

端点说明:
  GET    /api/family                  主用户查看已绑定的家庭成员列表
  POST   /api/family                  主用户添加成员(生成待绑定邀请)
  PUT    /api/family/{member_id}      主用户修改成员配置(开关/称呼等)
  DELETE /api/family/{member_id}      主用户移除成员
  POST   /api/family/accept           家庭成员接受邀请(绑定其微信号/账号)
  GET    /api/family/status/{token}   家庭成员凭邀请令牌查看主用户状态摘要
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.db import repositories
from app.models.schemas import FamilyMemberAdd, FamilyMemberUpdate, FamilyAcceptInvite
from app.services import family_service

router = APIRouter(prefix="/api/family", tags=["家庭成员"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_members(user_id: int = Depends(get_current_user)):
    return family_service.list_members(user_id)


@router.post("")
async def add_member(req: FamilyMemberAdd, user_id: int = Depends(get_current_user)):
    return family_service.create_invite(user_id, req)


@router.put("/{member_id}")
async def update_member(
    member_id: int, req: FamilyMemberUpdate, user_id: int = Depends(get_current_user)
):
    member = family_service.update_member(member_id, user_id, req)
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成员不存在")
    return member


@router.delete("/{member_id}")
async def delete_member(member_id: int, user_id: int = Depends(get_current_user)):
    family_service.delete_member(member_id, user_id)
    return {"ok": True}


@router.post("/accept")
async def accept_invite(req: FamilyAcceptInvite, user_id: int = Depends(get_current_user)):
    """
    家庭成员接受邀请。

    接受者即当前登录用户,优先采用其账号信息:
      - member_user_id 缺省取当前登录用户;
      - member_openid 缺省由当前用户反查(openid 是推送目标)。
    """
    member_user_id = req.member_user_id if req.member_user_id is not None else user_id
    member_openid = req.member_openid
    if not member_openid:
        u = repositories.get_user(member_user_id) or {}
        member_openid = u.get("openid") or ""
    member = family_service.accept_invite(req.token, member_openid, member_user_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="邀请无效或已失效"
        )
    return member


@router.get("/status/{token}")
async def member_view_status(token: str):
    """家庭成员凭邀请令牌查看主用户状态摘要(点击分享链接进入,无需重复登录)。"""
    status_data = family_service.get_status_by_token(token)
    if status_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="邀请无效或尚未绑定"
        )
    if "error" in status_data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=status_data["error"])
    return status_data

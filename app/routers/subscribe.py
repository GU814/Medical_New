"""订阅消息路由 - 授权记录 / 提醒创建与查询 / 单次发送(测试用)"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.db import repositories
from app.models.schemas import ReminderCreate, ReminderItem, SubscribeAuthorize
from app.services import subscribe_service

router = APIRouter(prefix="/api/subscribe", tags=["订阅消息"])
logger = logging.getLogger(__name__)


@router.post("/authorize")
async def authorize(req: SubscribeAuthorize, user_id: int = Depends(get_current_user)):
    subscribe_service.record_authorize(user_id, req.template_id, req.scene)
    return {"ok": True}


@router.post("/reminders", status_code=status.HTTP_201_CREATED)
async def create_reminder(req: ReminderCreate, user_id: int = Depends(get_current_user)):
    rid = await subscribe_service.create_reminder(
        user_id, req.template_id, req.data, req.scheduled_at
    )
    return {"id": rid}


@router.get("/reminders", response_model=list[ReminderItem])
async def list_reminders(user_id: int = Depends(get_current_user)):
    rows = repositories.list_reminders(user_id)
    return [
        {
            "id": r["id"],
            "template_id": r["template_id"],
            "data": json.loads(r["data_json"]),
            "status": r["status"],
            "scheduled_at": r["scheduled_at"],
            "sent_at": r["sent_at"],
            "fail_reason": r["fail_reason"],
        }
        for r in rows
    ]


@router.post("/send")
async def send_now(req: ReminderCreate, user_id: int = Depends(get_current_user)):
    """手动触发一次订阅消息(常用于联调/验证)"""
    res = await subscribe_service.send_subscribe(user_id, req.template_id, req.data)
    if res is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="订阅消息发送失败(微信侧错误)")
    return res

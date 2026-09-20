"""
订阅消息服务 - 记录授权 + 发送订阅消息 + 提醒建/发

发送走 app.core.wx_api(access_token 底座);dev 降级返回 {"mock":True},不触网、不抛异常。
"""

import json
import logging
from datetime import datetime

from app.core import wx_api
from app.db import repositories

logger = logging.getLogger(__name__)


def record_authorize(user_id: int, template_id: str, scene: str = None):
    """记录用户在某场景下授权了某模板(幂等 upsert)"""
    repositories.upsert_subscription(user_id, template_id, scene)


def _openid_of(user_id: int):
    user = repositories.get_user(user_id)
    return user.get("openid") if user else None


async def send_subscribe(user_id: int, template_id: str, data: dict) -> dict | None:
    """
    发送一次订阅消息。
    Returns: 微信响应 dict(含 errcode) / {"mock":True} / None(失败)
    """
    openid = _openid_of(user_id)
    if not openid:
        logger.warning("[subscribe] 发送失败:缺少 openid")
        return None
    payload = {"touser": openid, "template_id": template_id, "data": data}
    res = await wx_api.wx_request("POST", "/cgi-bin/message/subscribe/send", json=payload)
    if res is None:
        return None
    if res.get("mock"):
        return {"mock": True}
    if res.get("errcode", 0) != 0:
        logger.warning(f"[subscribe] 发送失败: {res}")
        return None
    return res


async def create_reminder(user_id: int, template_id: str, data: dict, scheduled_at: str = None) -> int:
    """创建提醒;若计划时间<=当前则立即下发"""
    data_json = json.dumps(data, ensure_ascii=False)
    if not scheduled_at:
        scheduled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rid = repositories.create_reminder(user_id, template_id, data_json, scheduled_at)

    sched = datetime.strptime(scheduled_at, "%Y-%m-%d %H:%M:%S")
    if sched <= datetime.now():
        await _dispatch(rid, user_id, template_id, data)
    return rid


async def _dispatch(rid: int, user_id: int, template_id: str, data: dict):
    res = await send_subscribe(user_id, template_id, data)
    if res is None:
        repositories.mark_reminder_failed(rid, "send_returned_none")
    elif res.get("mock"):
        repositories.mark_reminder_sent(rid)
    elif res.get("errcode", 0) == 0:
        repositories.mark_reminder_sent(rid)
    else:
        repositories.mark_reminder_failed(rid, str(res))

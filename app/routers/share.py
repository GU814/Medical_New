"""分享路由 - 生成带签名的分享链接 + 公开脱敏访问"""

import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.db import repositories
from app.db.connection import get_conn
from app.models.schemas import ShareCreateRequest
from app.services import record_service

router = APIRouter(prefix="/api/share", tags=["分享"])
logger = logging.getLogger(__name__)


@router.post("")
async def create_share(req: ShareCreateRequest, user_id: int = Depends(get_current_user)):
    """创建分享链接(校验记录归属)"""
    detail = record_service.get_record_detail(req.record_id, user_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在或无权访问")

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(hours=req.ttl_hours)).strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO share_links(token, record_id, user_id, expires_at, max_views, view_count, created_at) "
            "VALUES (?, ?, ?, ?, 0, 0, ?)",
            (token, req.record_id, user_id, expires_at, now),
        )
        conn.commit()

    return {"token": token, "expires_at": expires_at}


@router.get("/{token}")
async def view_share(token: str):
    """公开访问分享(脱敏:无姓名,仅报告)"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM share_links WHERE token=?", (token,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享链接不存在")
        if row["expires_at"] < now:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="分享链接已过期")

        # 增加访问计数
        conn.execute(
            "UPDATE share_links SET view_count = view_count + 1 WHERE token=?", (token,)
        )
        conn.commit()

        # 取记录(用创建者 user_id 解密)
        record = repositories.get_record(row["record_id"], row["user_id"])
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")

    from app.core import crypto
    dec = crypto.decrypt_record(row["user_id"], record, crypto.PATIENT_SENSITIVE_FIELDS)

    return {
        "patient_age": dec.get("patient_age"),
        "patient_gender": dec.get("patient_gender"),
        "report": dec.get("full_report", ""),
        "visit_date": dec.get("visit_date"),
        "disclaimer": "本报告由AI医学问诊助手生成,仅供参考,不能替代医生面诊。请务必咨询专业医疗人员。",
    }

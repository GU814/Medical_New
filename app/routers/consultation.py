"""问诊会话路由 - 创建/恢复/对话/重置/历史

核心:POST /api/chat 沿用现有 SSE 协议(event: reply/report/end/report_done),
小程序端用 onChunkReceived 接收。
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

import config
from app.core.deps import get_current_user
from app.models.schemas import ChatRequest
from app.services import session_service
from consultation import ConsultationSession

router = APIRouter(prefix="/api", tags=["问诊"])
logger = logging.getLogger(__name__)


def _sse(event: str, data) -> bytes:
    """格式化 SSE 事件块"""
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


@router.post("/sessions")
async def create_session(user_id: int = Depends(get_current_user)):
    """新建问诊会话"""
    session = session_service.create_session(user_id, ConsultationSession)
    return {"session_id": session.session_id, "stage": session.stage}


@router.get("/sessions")
async def list_sessions(limit: int = 20, user_id: int = Depends(get_current_user)):
    """
    会话列表(最近更新优先)。
    与 POST /sessions(新建)同路径不同方法:新建不会删除旧会话,故这里能列出全部历史会话。
    """
    return {"items": session_service.list_sessions(user_id, limit=limit)}


@router.get("/sessions/latest")
async def get_latest_session(user_id: int = Depends(get_current_user)):
    """
    获取「最近一条」会话用于复用。

    原实现只取 is_complete=0 的未完成会话,导致上一轮问诊一旦完成,
    再次进入问诊页就会因查不到而新建空会话,历史记录看起来被清空。
    这里改为不论完成与否都返回最近一条,由前端直接复用并加载其历史。
    """
    session = session_service.get_latest_any(user_id, ConsultationSession)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="无未完成会话")
    return {
        "session_id": session.session_id,
        "stage": session.stage,
        "is_complete": session.is_complete,
        "has_report": bool(session.report),
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user_id: int = Depends(get_current_user)):
    """获取会话状态(不含完整明细)"""
    row = session_service.get_history(session_id, user_id, cursor=0, size=0)
    if not row["items"] and row["next_cursor"] is None:
        # 尝试获取会话基本信息
        from app.db import repositories
        sess = repositories.get_session(session_id, user_id)
        if not sess:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
        return {
            "session_id": session_id,
            "stage": sess.get("stage"),
            "is_complete": bool(sess.get("is_complete")),
            "patient_gender": sess.get("patient_gender"),
            "patient_age": sess.get("patient_age", 0),
            "created_at": sess.get("created_at"),
        }
    return {"session_id": session_id, "stage": None}


@router.get("/sessions/{session_id}/history")
async def get_session_history(
    session_id: str,
    cursor: int = 0,
    size: int = 20,
    user_id: int = Depends(get_current_user),
):
    """分页获取对话历史"""
    result = session_service.get_history(session_id, user_id, cursor=cursor, size=size)
    return result


@router.get("/sessions/{session_id}/report")
async def get_session_report(session_id: str, user_id: int = Depends(get_current_user)):
    """
    查询会话报告状态与内容(供前端轮询/断线续传)。
    - report_status: none/pending/running/done/failed
    - report 全文仅在 done 时返回;running/pending 时前端继续轮询,
      failed 时可调 POST /sessions/{id}/report/retry 重触发。
    """
    session = session_service.get_or_create(session_id, user_id, ConsultationSession)
    return {
        "session_id": session.session_id,
        "report_status": session.report_status,
        "report": session.report if session.report_status == "done" else "",
        "stage": session.stage,
        "is_complete": session.is_complete,
    }


@router.post("/sessions/{session_id}/report/retry")
async def retry_session_report(session_id: str, user_id: int = Depends(get_current_user)):
    """
    重试后台报告生成。仅 failed 状态可重触发;
    其余状态原样返回(避免并发重复生成)。
    """
    session = session_service.get_or_create(session_id, user_id, ConsultationSession)
    if session.report_status == "failed":
        session.report_status = "pending"
        session_service.persist(session)
        session.maybe_start_report_task()
    return {
        "session_id": session.session_id,
        "report_status": session.report_status,
    }


@router.post("/sessions/{session_id}/reset")
async def reset_session(session_id: str, user_id: int = Depends(get_current_user)):
    """重置会话(删除旧会话,新建)"""
    new_session = session_service.reset_session(session_id, user_id, ConsultationSession)
    return {"session_id": new_session.session_id, "stage": new_session.stage}


@router.post("/chat")
async def chat(
    req: ChatRequest,
    request: Request,
    user_id: int = Depends(get_current_user),
):
    """
    问诊对话(流式 SSE)。
    响应 Content-Type: text/event-stream,事件:
      - reply: 医生回复片段
      - report: 报告片段(阶段5)
      - end: 单轮结束(含 session_id/stage/is_complete)
      - report_done: 报告生成完成
      - error: 错误
    """
    # 获取或恢复会话(支持断点续诊:req.session_id 为空时自动恢复最近未完成会话)
    if req.session_id:
        session = session_service.get_or_create(req.session_id, user_id, ConsultationSession)
    else:
        # 无指定会话:优先恢复最近未完成,否则新建
        session = session_service.get_latest_unfinished(user_id, ConsultationSession)
        if not session:
            session = session_service.create_session(user_id, ConsultationSession)

    async def event_stream():
        try:
            # 记录用户输入到对话历史
            session.conversation_history.append({"role": "user", "content": req.message})

            # 持久化用户输入(立即落库,防止丢失)
            session_service.persist(session)

            # 流式问诊(复用现有 process_user_input_stream)
            async for ev in session.process_user_input_stream(req.message):
                yield _sse(ev["event"], ev["data"])

            # 兜底:任何路径推进到问诊完成但未触发后台报告时,在此补触发
            session.maybe_start_report_task()

            # 会话状态变更后持久化
            session_service.persist(session)
        except Exception as e:
            logger.error(f"问诊流式异常: {e}")
            yield _sse("error", {"detail": str(e)})

    media_type = "text/event-stream; charset=utf-8"
    return StreamingResponse(event_stream(), media_type=media_type)

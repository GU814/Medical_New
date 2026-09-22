"""
会话服务 - 长对话记忆/持久化/恢复

职责:
- 内存缓存(LRU)+ DB 持久化双轨
- ConsultationSession <-> DB 序列化(经加密)
- 断点续诊:加载用户最近未完成会话
- 对话历史分页

ConsultationSession 的 to_dict/from_dict 在 consultation.py 改造中实现,
本服务负责在序列化 dict 与 DB 行之间做加密/解密转换。
"""

import json
import logging
import threading
import uuid
from datetime import datetime
from typing import Optional

from app.core import crypto
from app.db import repositories

logger = logging.getLogger(__name__)

# 内存缓存:session_id -> ConsultationSession(热数据)
_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 200  # 最多缓存 200 个活跃会话


def _gen_session_id() -> str:
    return str(uuid.uuid4())[:8]


def create_session(user_id: int, session_cls):
    """新建问诊会话(内存 + DB 占位)"""
    session_id = _gen_session_id()
    session = session_cls(session_id=session_id)
    session.user_id = user_id
    persist(session)
    with _cache_lock:
        _evict_if_needed()
        _cache[session_id] = session
    logger.info(f"创建会话 session_id={session_id} user_id={user_id}")
    return session


def get_or_create(session_id: Optional[str], user_id: int, session_cls):
    """
    获取或创建会话:
    1. 内存缓存命中 -> 直接返回(校验 user_id)
    2. DB 命中 -> 反序列化(解密)回内存
    3. 否则新建
    """
    if session_id:
        with _cache_lock:
            cached = _cache.get(session_id)
        if cached is not None and getattr(cached, "user_id", None) == user_id:
            return cached

        # 从 DB 恢复
        row = repositories.get_session(session_id, user_id)
        if row:
            session = _row_to_session(row, user_id, session_cls)
            with _cache_lock:
                _evict_if_needed()
                _cache[session_id] = session
            logger.info(f"从 DB 恢复会话 session_id={session_id}")
            return session

    # 新建
    return create_session(user_id, session_cls)


def persist(session):
    """将会话序列化(加密)后落库"""
    user_id = getattr(session, "user_id", None)
    if not user_id:
        logger.warning("会话无 user_id,跳过持久化")
        return

    data = session.to_dict()
    # 加密敏感字段
    enc = crypto.encrypt_record(user_id, data, crypto.SESSION_SENSITIVE_FIELDS)
    repositories.save_session(session.session_id, user_id, enc)


def get_latest_unfinished(user_id: int, session_cls):
    """断点续诊:获取用户最近未完成会话"""
    row = repositories.get_latest_session(user_id)
    if not row:
        return None
    return _row_to_session(row, user_id, session_cls)


def get_latest_any(user_id: int, session_cls):
    """
    获取用户最近一条会话(不论是否完成)。
    进入问诊页时用它复用已有会话,避免"上一条已完成 -> 新建空会话 -> 历史看似丢失"。
    """
    row = repositories.get_latest_any_session(user_id)
    if not row:
        return None
    return _row_to_session(row, user_id, session_cls)


def list_sessions(user_id: int, limit: int = 20) -> list:
    """
    会话列表(供历史会话切换)。返回轻量摘要,解密 conversation_history 取出首条
    用户消息作为标题预览;单条解密失败不影响其余条目。
    """
    rows = repositories.list_sessions(user_id, limit=limit)
    items = []
    for row in rows:
        title = ""
        msg_count = 0
        try:
            dec = crypto.decrypt_record(user_id, row, crypto.SESSION_SENSITIVE_FIELDS)
            history_raw = dec.get("conversation_history") or ""
            history = json.loads(history_raw) if history_raw else []
        except Exception:
            history = []
        if isinstance(history, list):
            msg_count = len(history)
            for m in history:
                if isinstance(m, dict) and m.get("role") == "user" and m.get("content"):
                    title = str(m["content"]).strip().replace("\n", " ")
                    break
        items.append({
            "session_id": row.get("session_id"),
            "stage": row.get("stage"),
            "is_complete": bool(row.get("is_complete")),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "message_count": msg_count,
            "title": title[:40] if title else "",
        })
    return items


def _row_to_session(row: dict, user_id: int, session_cls):
    """DB 行(含密文)解密后还原为 ConsultationSession"""
    dec = crypto.decrypt_record(user_id, row, crypto.SESSION_SENSITIVE_FIELDS)
    # conversation_history 是 JSON 字符串,需解析
    if dec.get("conversation_history"):
        try:
            dec["conversation_history"] = json.loads(dec["conversation_history"])
        except (json.JSONDecodeError, TypeError):
            dec["conversation_history"] = []
    else:
        dec["conversation_history"] = []
    dec["user_id"] = user_id
    dec["is_complete"] = bool(dec.get("is_complete"))
    return session_cls.from_dict(dec)


def reset_session(session_id: str, user_id: int, session_cls):
    """重置会话:删除旧会话(内存+DB),新建"""
    with _cache_lock:
        _cache.pop(session_id, None)
    repositories.delete_session(session_id, user_id)
    return create_session(user_id, session_cls)


def get_history(session_id: str, user_id: int, cursor: int = 0, size: int = 20):
    """
    分页获取对话历史。

    注意:conversation_history 在落库时是密文(见 persist -> crypto.encrypt_record),
    这里必须先按用户密钥解密再 json.loads。之前直接对密文 json.loads 必然抛
    JSONDecodeError,被下面的 except 吞掉后返回空列表 —— 表现为"历史记录查不出来"。
    """
    row = repositories.get_session(session_id, user_id)
    if not row:
        return {"items": [], "next_cursor": None}
    try:
        dec = crypto.decrypt_record(user_id, row, crypto.SESSION_SENSITIVE_FIELDS)
        raw = dec.get("conversation_history") or ""
    except Exception:
        logger.warning("会话历史解密失败,回退为原始字段 session_id=%s", session_id)
        raw = row.get("conversation_history") or ""
    try:
        history = json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        history = []
    if not isinstance(history, list):
        history = []
    total = len(history)
    end = min(cursor + size, total)
    items = history[cursor:end]
    next_cursor = end if end < total else None
    return {"items": items, "next_cursor": next_cursor}


def _evict_if_needed():
    """LRU 淘汰:超过上限移除最早的(简单实现,非严格 LRU)"""
    if len(_cache) > _CACHE_MAX:
        oldest = next(iter(_cache))
        _cache.pop(oldest, None)

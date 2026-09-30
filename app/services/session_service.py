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

import config
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
    _apply_user_profile(session, user_id)
    persist(session)
    with _cache_lock:
        _evict_if_needed()
        _cache[session_id] = session
    logger.info(f"创建会话 session_id={session_id} user_id={user_id}")
    return session


def _apply_user_profile(session, user_id: int):
    """
    把登录资料(profile_age/profile_gender)预填进新会话。

    用户在登录界面录入过年龄/性别时,新开对话直接带入,
    模型不再跨会话重复询问(会话内患者主动陈述的值始终优先,这里只在为空时填)。
    """
    try:
        user = repositories.get_user(user_id) or {}
        gender = (user.get("profile_gender") or "").strip()
        age = user.get("profile_age") or 0
        prefilled = False
        if gender and not session.patient_gender:
            session.patient_gender = gender
            prefilled = True
        if age and not session.patient_age:
            session.patient_age = int(age)
            prefilled = True
        session.profile_prefilled = prefilled
        if prefilled:
            logger.info(f"已预填登录资料 session_id={session.session_id} "
                        f"gender={session.patient_gender} age={session.patient_age}")
    except Exception as e:
        logger.warning(f"预填用户资料失败(不影响会话创建): {e}")


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
    # 推理步骤是随会话产生的附属数据,会话删除时一并清理,避免孤儿记录
    repositories.delete_session_steps(session_id, user_id)
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


# ==================== 推理过程(session_steps) ====================


def persist_session_trace(session, trace) -> bool:
    """
    落库一轮的推理过程(步骤 + 知识引用)。

    - text/refs/sentences/args 走列级加密(与会话历史同一套密钥体系);
    - 失败只记日志,绝不向上抛 —— 推理过程属于增强能力,不能影响回答本身。
    """
    user_id = getattr(session, "user_id", 0)
    if not config.REACT_PERSIST:
        return False
    # 桌面模式 user_id=0 也照样落库:否则桌面端产生的推理过程永远查不到,
    # 历史回放只能给出「为什么没有」的兜底文案,与可解释性的目标相悖。
    if not user_id:
        logger.debug("ReAct 轨迹以 user_id=0 落库(桌面模式)")
    steps = []
    try:
        for s in trace.steps:
            payload = {
                "seq": s.seq,
                "step_type": s.type,
                "status": s.status,
                "tool": s.tool,
                "args": json.dumps(s.args or {}, ensure_ascii=False) if s.args else None,
                "text": s.text or None,
                "refs": json.dumps([r.to_dict() for r in s.refs], ensure_ascii=False) if s.refs else None,
                "sentences": json.dumps(s.sentences, ensure_ascii=False) if s.sentences else None,
                "elapsed_ms": s.elapsed_ms,
                "ts": s.ts,
            }
            steps.append(crypto.encrypt_record(user_id, payload, crypto.STEP_SENSITIVE_FIELDS))
        repositories.save_session_steps(
            user_id, trace.session_id, trace.turn_index, steps,
            branch=trace.branch, fallback_reason=trace.fallback_reason,
        )
        return True
    except Exception as e:
        # 带堆栈:曾经出现过只报「FOREIGN KEY constraint failed」却无从定位的情况
        logger.warning(f"推理过程落库失败(不影响回答): {e}", exc_info=True)
        return False


def get_session_steps(session_id: str, user_id: int, turn_index: int = None) -> dict:
    """
    读取推理过程供历史回放。

    返回:
      {"session_id", "turns": [{"turn_index", "branch", "fallback_reason", "steps": [...]}],
       "missing_reason": 整个会话一条记录都没有时的说明文案}

    注意:历史回放不允许出现「暂无推理过程」这类空态文案,缺数据时必须给出
    「为什么缺」的具体原因(见 _missing_reason),前端据此渲染提示。
    """
    rows = repositories.get_session_steps(session_id, user_id, turn_index)
    if not rows:
        return {
            "session_id": session_id,
            "turns": [],
            "missing_reason": _missing_reason(session_id, user_id, turn_index, rows),
        }

    by_turn: dict = {}
    branch = ""
    fallback_reason = None
    for r in rows:
        ti = r.get("turn_index")
        branch = r.get("branch") or branch
        fallback_reason = r.get("fallback_reason") or fallback_reason
        try:
            dec = crypto.decrypt_record(user_id, r, crypto.STEP_SENSITIVE_FIELDS)
        except Exception:
            dec = {k: r.get(k) for k in
                   ("seq", "step_type", "status", "tool", "elapsed_ms", "ts")}
        step = {
            "seq": dec.get("seq"),
            "type": dec.get("step_type"),
            "status": dec.get("status"),
            "tool": dec.get("tool"),
            "text": dec.get("text") or "",
            "elapsed_ms": dec.get("elapsed_ms") or 0,
            "ts": dec.get("ts"),
        }
        refs_raw = dec.get("refs")
        if refs_raw:
            try:
                step["refs"] = json.loads(refs_raw)
            except (json.JSONDecodeError, TypeError):
                step["refs"] = []
        else:
            step["refs"] = []
        sentences_raw = dec.get("sentences")
        if sentences_raw:
            try:
                step["sentences"] = json.loads(sentences_raw)
            except (json.JSONDecodeError, TypeError):
                step["sentences"] = None
        by_turn.setdefault(ti, []).append(step)

    turns = []
    for ti in sorted(by_turn.keys()):
        steps = sorted(by_turn[ti], key=lambda x: (x.get("seq") or 0))
        turns.append({
            "turn_index": ti,
            "branch": branch,
            "fallback_reason": fallback_reason,
            "steps": steps,
            "total_ms": sum(s.get("elapsed_ms") or 0 for s in steps),
        })
    # 指定轮次但无记录时,给出该轮缺失原因(同样不允许空态)
    if turn_index is not None and not any(t["turn_index"] == turn_index for t in turns):
        return {
            "session_id": session_id,
            "turns": [],
            "missing_reason": _missing_reason(session_id, user_id, turn_index, rows),
        }
    return {"session_id": session_id, "turns": turns, "missing_reason": None}


def _missing_reason(session_id: str, user_id: int, turn_index, rows: list) -> str:
    """解释「为什么这段历史没有推理过程」,供前端直接展示,避免空文案。"""
    if turn_index is not None:
        return (
            f"第 {turn_index + 1} 轮问答未记录推理过程。"
            f"可能原因:该轮由「推理过程」功能上线前的版本产生,或当时该轮未命中直接问答分支。"
        )
    if not config.ENABLE_REACT:
        return "当前服务未启用推理过程记录(ENABLE_REACT=false),因此本会话的历史对话不含推理步骤。"
    return (
        "本会话的对话早于「推理过程」功能上线,当时未记录推理步骤;"
        "如需查看推理过程,请开启 ENABLE_REACT 后重新发起一轮问答。"
    )


def _evict_if_needed():
    """LRU 淘汰:超过上限移除最早的(简单实现,非严格 LRU)"""
    if len(_cache) > _CACHE_MAX:
        oldest = next(iter(_cache))
        _cache.pop(oldest, None)

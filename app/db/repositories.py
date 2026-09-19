"""
仓储层 - 各表 DAO,统一 user_id 作用域

所有患者数据查询均强制 user_id 过滤,从根上解决同名串档与越权。
"""

import logging
from datetime import datetime
from typing import Optional

from app.db.connection import get_conn

logger = logging.getLogger(__name__)


# ==================== users ====================

def upsert_user_by_openid(openid: str, union_id: str = None) -> tuple:
    """
    按 openid 新增或更新用户登录时间。
    Returns: (user_id, is_new)
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute("SELECT user_id FROM users WHERE openid=?", (openid,))
        row = cur.fetchone()
        if row:
            conn.execute(
                "UPDATE users SET last_login_at=? WHERE user_id=?", (now, row["user_id"])
            )
            conn.commit()
            return row["user_id"], False
        # 新用户
        cur = conn.execute(
            "INSERT INTO users(openid, union_id, created_at, last_login_at) VALUES (?, ?, ?, ?)",
            (openid, union_id, now, now),
        )
        conn.commit()
        return cur.lastrowid, True


def get_user(user_id: int) -> Optional[dict]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_user_profile(user_id: int, nickname: str = None, avatar_url: str = None, phone: str = None):
    """更新用户资料(仅更新非空字段)"""
    fields, params = [], []
    if nickname is not None:
        fields.append("nickname=?"); params.append(nickname)
    if avatar_url is not None:
        fields.append("avatar_url=?"); params.append(avatar_url)
    if phone is not None:
        fields.append("phone=?"); params.append(phone)
    if not fields:
        return
    params.append(user_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE user_id=?", params)
        conn.commit()


# ==================== consultation_sessions ====================

def save_session(session_id: str, user_id: int, data: dict):
    """upsert 问诊会话(密文由调用方在 service 层加密后传入)"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO consultation_sessions(
                session_id, user_id, stage, patient_name, patient_gender, patient_age,
                chief_complaint, present_illness, past_history, personal_history,
                family_history, system_review, diagnosis, conversation_history,
                is_complete, report, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                stage=excluded.stage, patient_name=excluded.patient_name,
                patient_gender=excluded.patient_gender, patient_age=excluded.patient_age,
                chief_complaint=excluded.chief_complaint, present_illness=excluded.present_illness,
                past_history=excluded.past_history, personal_history=excluded.personal_history,
                family_history=excluded.family_history, system_review=excluded.system_review,
                diagnosis=excluded.diagnosis, conversation_history=excluded.conversation_history,
                is_complete=excluded.is_complete, report=excluded.report, updated_at=excluded.updated_at
            """,
            (session_id, user_id, data.get("stage", 1),
             data.get("patient_name"), data.get("patient_gender"), data.get("patient_age", 0),
             data.get("chief_complaint"), data.get("present_illness"), data.get("past_history"),
             data.get("personal_history"), data.get("family_history"), data.get("system_review"),
             data.get("diagnosis"), data.get("conversation_history"),
             1 if data.get("is_complete") else 0, data.get("report"),
             data.get("created_at", now), now),
        )
        conn.commit()


def get_session(session_id: str, user_id: int) -> Optional[dict]:
    """获取会话(强制 user_id 作用域)"""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM consultation_sessions WHERE session_id=? AND user_id=?",
            (session_id, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_latest_session(user_id: int) -> Optional[dict]:
    """获取用户最近未完成会话(用于断点续诊)"""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM consultation_sessions WHERE user_id=? AND is_complete=0 "
            "ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def delete_session(session_id: str, user_id: int):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM consultation_sessions WHERE session_id=? AND user_id=?",
            (session_id, user_id),
        )
        conn.commit()


# ==================== patients_info(历史就诊记录) ====================

def save_patient_record(user_id: int, data: dict) -> Optional[int]:
    """
    保存患者问诊记录(密文 + preview 由 service 层处理)。
    Returns: 新记录 id
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 计算就诊次数
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT COUNT(*) AS c FROM patients_info WHERE user_id=? AND patient_name=?",
            (user_id, data.get("patient_name_enc")),
        )
        visit_count = cur.fetchone()["c"] + 1

        cur = conn.execute(
            """
            INSERT INTO patients_info(
                user_id, patient_name, patient_gender, patient_age,
                chief_complaint, present_illness, past_history, system_review,
                personal_history, family_history, diagnosis, full_report,
                visit_date, visit_count, chief_complaint_preview
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, data.get("patient_name_enc"), data.get("patient_gender"),
             data.get("patient_age", 0), data.get("chief_complaint_enc"),
             data.get("present_illness_enc"), data.get("past_history_enc"),
             data.get("system_review_enc"), data.get("personal_history_enc"),
             data.get("family_history_enc"), data.get("diagnosis_enc"),
             data.get("full_report_enc"), now, visit_count,
             data.get("chief_complaint_preview")),
        )
        conn.commit()
        return cur.lastrowid


def query_patient_records(user_id: int, name_enc: str = None) -> list:
    """查询患者历史记录(强制 user_id 作用域;name 为密文,精确匹配)"""
    with get_conn() as conn:
        if name_enc:
            cur = conn.execute(
                "SELECT * FROM patients_info WHERE user_id=? AND patient_name=? ORDER BY visit_date DESC",
                (user_id, name_enc),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM patients_info WHERE user_id=? ORDER BY visit_date DESC",
                (user_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def list_records(user_id: int, page: int = 1, size: int = 10,
                 start: str = None, end: str = None) -> tuple:
    """
    分页列表(强制 user_id 作用域,按时间倒序)。
    Returns: (items, total)
    """
    where = ["user_id=?"]
    params: list = [user_id]
    if start:
        where.append("visit_date>=?"); params.append(start)
    if end:
        where.append("visit_date<=?"); params.append(end)
    where_sql = " AND ".join(where)
    offset = (page - 1) * size
    with get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM patients_info WHERE {where_sql}", params
        ).fetchone()["c"]
        cur = conn.execute(
            f"SELECT id, visit_date, visit_count, chief_complaint_preview "
            f"FROM patients_info WHERE {where_sql} ORDER BY visit_date DESC LIMIT ? OFFSET ?",
            params + [size, offset],
        )
        items = [dict(r) for r in cur.fetchall()]
    return items, total


def get_record(record_id: int, user_id: int) -> Optional[dict]:
    """获取单条记录(强制 user_id 作用域,防越权)"""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM patients_info WHERE id=? AND user_id=?", (record_id, user_id)
        )
        row = cur.fetchone()
        return dict(row) if row else None

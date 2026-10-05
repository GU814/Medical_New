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


def update_user_profile(user_id: int, nickname: str = None, avatar_url: str = None,
                        phone: str = None, age: int = None, gender: str = None):
    """更新用户资料(仅更新非空字段)"""
    fields, params = [], []
    if nickname is not None:
        fields.append("nickname=?"); params.append(nickname)
    if avatar_url is not None:
        fields.append("avatar_url=?"); params.append(avatar_url)
    if phone is not None:
        fields.append("phone=?"); params.append(phone)
    if age is not None:
        fields.append("profile_age=?"); params.append(int(age))
    if gender is not None:
        fields.append("profile_gender=?"); params.append(gender)
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


# ==================== session_steps(推理过程 / 知识溯源) ====================
# 说明:调用方(service 层)负责列级加密,这里只做落库与读取。
#       user_id / session_id / turn_index / seq 保持明文,便于统计与排序。

def save_session_steps(user_id: int, session_id: str, turn_index: int, steps: list,
                       branch: str = "", fallback_reason: str = None):
    """批量写入一轮的推理步骤(幂等:同 session/turn/seq 已存在时先删后插)。

    steps 元素需为 dict,且 text/refs/sentences/args 已由调用方加密。
    """
    if not steps:
        return 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM session_steps WHERE session_id=? AND turn_index=?",
            (session_id, turn_index),
        )
        conn.executemany(
            """
            INSERT INTO session_steps(
                user_id, session_id, turn_index, seq, step_type, status, branch,
                tool, args_json, text, refs_json, sentences_json,
                elapsed_ms, ts, fallback_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    user_id, session_id, turn_index,
                    int(s.get("seq", 0)),
                    s.get("step_type", ""),
                    s.get("status"),
                    branch,
                    s.get("tool"),
                    s.get("args"),
                    s.get("text"),
                    s.get("refs"),
                    s.get("sentences"),
                    int(s.get("elapsed_ms") or 0),
                    s.get("ts"),
                    fallback_reason,
                    now,
                )
                for s in steps
            ],
        )
        conn.commit()
    return len(steps)


def get_session_steps(session_id: str, user_id: int, turn_index: int = None) -> list:
    """读取推理步骤。turn_index 为空时返回该会话全部轮次,按轮次/序号升序。"""
    with get_conn() as conn:
        if turn_index is None:
            cur = conn.execute(
                "SELECT * FROM session_steps WHERE session_id=? AND user_id=? "
                "ORDER BY turn_index ASC, seq ASC",
                (session_id, user_id),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM session_steps WHERE session_id=? AND user_id=? AND turn_index=? "
                "ORDER BY seq ASC",
                (session_id, user_id, turn_index),
            )
        return [dict(r) for r in cur.fetchall()]


def delete_session_steps(session_id: str, user_id: int):
    """会话重置时一并清理推理步骤(与 delete_session 对应)。"""
    with get_conn() as conn:
        conn.execute("DELETE FROM session_steps WHERE session_id=? AND user_id=?",
                     (session_id, user_id))
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


def get_latest_any_session(user_id: int) -> Optional[dict]:
    """
    获取用户「最近一条」会话(不论是否已完成)。

    用于进入问诊页时复用已有会话,而不是因为「上一条已完成」就新建一个空会话,
    导致用户看不到历史消息。
    """
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM consultation_sessions WHERE user_id=? "
            "ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_sessions(user_id: int, limit: int = 20) -> list:
    """会话列表(最近更新优先),不含明细,供前端做历史会话切换。"""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT session_id, stage, is_complete, chief_complaint, "
            "conversation_history, created_at, updated_at "
            "FROM consultation_sessions WHERE user_id=? "
            "ORDER BY updated_at DESC LIMIT ?",
            (user_id, max(1, min(int(limit or 20), 100))),
        )
        return [dict(r) for r in cur.fetchall()]


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


# ==================== user_locations(地理位置) ====================

def add_location(user_id: int, name: str, address: str = None,
                 latitude: float = None, longitude: float = None, is_default: bool = False) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        if is_default:
            conn.execute("UPDATE user_locations SET is_default=0 WHERE user_id=?", (user_id,))
        cur = conn.execute(
            "INSERT INTO user_locations(user_id, name, address, latitude, longitude, is_default, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, address, latitude, longitude, 1 if is_default else 0, now),
        )
        conn.commit()
        return cur.lastrowid


def list_locations(user_id: int) -> list:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM user_locations WHERE user_id=? "
            "ORDER BY is_default DESC, created_at DESC",
            (user_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def delete_location(loc_id: int, user_id: int):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM user_locations WHERE id=? AND user_id=?", (loc_id, user_id)
        )
        conn.commit()


def set_default_location(loc_id: int, user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE user_locations SET is_default=0 WHERE user_id=?", (user_id,))
        conn.execute(
            "UPDATE user_locations SET is_default=1 WHERE id=? AND user_id=?", (loc_id, user_id)
        )
        conn.commit()


# ==================== user_subscriptions(订阅授权) ====================

def upsert_subscription(user_id: int, template_id: str, scene: str = None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO user_subscriptions(user_id, template_id, scene, authorized_at, status) "
            "VALUES (?, ?, ?, ?, 'authorized') "
            "ON CONFLICT(user_id, template_id) DO UPDATE SET "
            "scene=excluded.scene, authorized_at=excluded.authorized_at, status='authorized'",
            (user_id, template_id, scene, now),
        )
        conn.commit()


# ==================== reminders(提醒) ====================

def create_reminder(user_id: int, template_id: str, data_json: str, scheduled_at: str) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO reminders(user_id, template_id, data_json, status, scheduled_at, created_at) "
            "VALUES (?, ?, ?, 'scheduled', ?, ?)",
            (user_id, template_id, data_json, scheduled_at, now),
        )
        conn.commit()
        return cur.lastrowid


def list_reminders(user_id: int) -> list:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM reminders WHERE user_id=? ORDER BY scheduled_at DESC", (user_id,)
        )
        return [dict(r) for r in cur.fetchall()]


def mark_reminder_sent(reminder_id: int):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "UPDATE reminders SET status='sent', sent_at=? WHERE id=?", (now, reminder_id)
        )
        conn.commit()


def mark_reminder_failed(reminder_id: int, reason: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE reminders SET status='failed', fail_reason=? WHERE id=?", (reason, reminder_id)
        )
        conn.commit()


# ==================== family_members(家庭成员) ====================
# 业务字段由迁移 v9 补充:member_openid / member_user_id / phone / can_view_status /
# emergency_contact / notify_on_emergency / address_shared / invite_token /
# invite_status / bound_at / updated_at。

def add_family_member(user_id: int, member_name: str, relationship: str = None,
                      gender: str = None, birth_date: str = None, phone: str = None,
                      member_openid: str = None, member_user_id: int = None,
                      can_view_status: bool = True, emergency_contact: bool = False,
                      notify_on_emergency: bool = True, address_shared: bool = True,
                      invite_token: str = None, invite_status: str = "pending") -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO family_members("
            "user_id, member_name, relationship, gender, birth_date, phone, "
            "member_openid, member_user_id, can_view_status, emergency_contact, "
            "notify_on_emergency, address_shared, invite_token, invite_status, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id, member_name, relationship, gender, birth_date, phone,
                member_openid, member_user_id,
                1 if can_view_status else 0,
                1 if emergency_contact else 0,
                1 if notify_on_emergency else 0,
                1 if address_shared else 0,
                invite_token, invite_status, now, now,
            ),
        )
        conn.commit()
        return cur.lastrowid


def list_family_members(user_id: int) -> list:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM family_members WHERE user_id=? ORDER BY emergency_contact DESC, created_at ASC",
            (user_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_family_member(member_id: int, user_id: int) -> Optional[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM family_members WHERE id=? AND user_id=?", (member_id, user_id)
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_family_member_by_token(token: str) -> Optional[dict]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM family_members WHERE invite_token=?", (token,)
        )
        row = cur.fetchone()
        return dict(row) if row else None


def update_family_member(member_id: int, user_id: int, **fields) -> bool:
    allowed = {
        "member_name", "relationship", "gender", "birth_date", "phone",
        "member_openid", "member_user_id", "can_view_status", "emergency_contact",
        "notify_on_emergency", "address_shared", "invite_status",
    }
    sets, params = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ("can_view_status", "emergency_contact", "notify_on_emergency", "address_shared"):
            v = 1 if v else 0
        sets.append(f"{k}=?")
        params.append(v)
    if not sets:
        return False
    params.append(member_id)
    params.append(user_id)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            f"UPDATE family_members SET {', '.join(sets)}, updated_at=? "
            f"WHERE id=? AND user_id=?",
            [now, *params],
        )
        conn.commit()
    return True


def bind_family_member(token: str, member_openid: str, member_user_id: int = None) -> Optional[dict]:
    """家庭成员接受邀请:把其微信号/账号绑定到邀请记录,状态置为 bound。"""
    member = get_family_member_by_token(token)
    if not member:
        return None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        conn.execute(
            "UPDATE family_members SET member_openid=?, member_user_id=?, "
            "invite_status='bound', bound_at=?, updated_at=? WHERE invite_token=?",
            (member_openid, member_user_id, now, now, token),
        )
        conn.commit()
    return get_family_member_by_token(token)


def delete_family_member(member_id: int, user_id: int):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM family_members WHERE id=? AND user_id=?", (member_id, user_id)
        )
        conn.commit()


def list_emergency_contacts(user_id: int) -> list:
    """该用户勾选「重大情况推送」的家庭成员(推送目标)。"""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM family_members WHERE user_id=? AND notify_on_emergency=1",
            (user_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_latest_record(user_id: int) -> Optional[dict]:
    """用户最近一条就诊记录(供家庭成员查看用户状态)。"""
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT visit_date, chief_complaint_preview, diagnosis, full_report, created_at "
            "FROM patients_info WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

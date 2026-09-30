"""
数据库迁移模块 - 版本化 schema 管理

设计:
- schema_migrations 表记录已执行迁移版本
- 每个 migrate_vN() 幂等(CREATE TABLE IF NOT EXISTS / ALTER TABLE ADD COLUMN 前检查)
- patients_info 现有表通过 ALTER TABLE 增量加列,保留旧数据

迁移版本说明:
- v1: 新建 users / consultation_sessions / user_keys / audit_logs / share_links
- v2: patients_info 增加 user_id 外键 + chief_complaint_preview
- v3: family_members / feedback(P2 预留表,空实现)
- v5: 全新库补建 patients_info(v2 全新库会跳过,故单独兜底)
- v6: 修复 v5 建表缺陷 —— created_at 缺 DEFAULT,而 repositories 的 INSERT 不含该列,
      每次保存必现 NOT NULL 约束失败(报告在聊天可见但「就诊记录」永远为空),重建表补默认值
- v7: users 增加登录资料列 profile_age / profile_gender(供新会话预填,避免跨会话重复询问)
"""

import logging
import sqlite3

from app.db.connection import get_conn, ensure_db_dir

logger = logging.getLogger(__name__)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """检查表中是否已存在某列(ALTER TABLE ADD COLUMN 前的幂等检查)"""
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def _ensure_migrations_table(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _applied_versions(conn: sqlite3.Connection) -> set:
    _ensure_migrations_table(conn)
    cur = conn.execute("SELECT version FROM schema_migrations")
    return {row[0] for row in cur.fetchall()}


def _mark_applied(conn: sqlite3.Connection, version: int):
    from datetime import datetime
    conn.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (version, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()


# ==================== 迁移实现 ====================

def migrate_v1(conn: sqlite3.Connection):
    """新建核心表:users / consultation_sessions / user_keys / audit_logs / share_links"""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            openid TEXT UNIQUE NOT NULL,
            union_id TEXT,
            nickname TEXT,
            avatar_url TEXT,
            phone TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            last_login_at TEXT
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_openid ON users(openid)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS consultation_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            stage INTEGER NOT NULL DEFAULT 1,
            patient_name TEXT,
            patient_gender TEXT,
            patient_age INTEGER,
            chief_complaint TEXT,
            present_illness TEXT,
            past_history TEXT,
            personal_history TEXT,
            family_history TEXT,
            system_review TEXT,
            diagnosis TEXT,
            conversation_history TEXT,
            is_complete INTEGER NOT NULL DEFAULT 0,
            report TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_user_updated "
        "ON consultation_sessions(user_id, updated_at DESC)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_keys (
            user_id INTEGER PRIMARY KEY,
            encrypted_dek TEXT NOT NULL,
            kek_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            rotated_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            ip TEXT,
            ua TEXT,
            status TEXT,
            timestamp TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_user_time "
        "ON audit_logs(user_id, timestamp DESC)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS share_links (
            token TEXT PRIMARY KEY,
            record_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            max_views INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(record_id) REFERENCES patients_info(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_share_record ON share_links(record_id)"
    )
    conn.commit()


def migrate_v2(conn: sqlite3.Connection):
    """patients_info 增加 user_id 外键 + chief_complaint_preview 列(增量,保留旧数据)"""

    if not _table_exists(conn, "patients_info"):
        logger.info("patients_info 表不存在(全新库),跳过 v2 增量改造")
        return

    if not _column_exists(conn, "patients_info", "user_id"):
        # 旧表无 user_id,新增列(默认 0,后续归属到迁移用户或保留为遗留数据)
        conn.execute("ALTER TABLE patients_info ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0")
        logger.info("patients_info 已增加 user_id 列")

    if not _column_exists(conn, "patients_info", "chief_complaint_preview"):
        # 非密文前 20 字,供列表展示/搜索(密文无法 SQL LIKE)
        conn.execute("ALTER TABLE patients_info ADD COLUMN chief_complaint_preview TEXT")
        logger.info("patients_info 已增加 chief_complaint_preview 列")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_records_user_date "
        "ON patients_info(user_id, visit_date DESC)"
    )
    conn.commit()


def migrate_v3(conn: sqlite3.Connection):
    """P2 预留表:family_members / feedback"""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS family_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            member_name TEXT NOT NULL,
            relationship TEXT,
            gender TEXT,
            birth_date TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id TEXT,
            content TEXT,
            rating INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()


def migrate_v4(conn: sqlite3.Connection):
    """P2/P3 业务表:user_locations(地理位置) / user_subscriptions(订阅授权) / reminders(提醒)"""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            address TEXT,
            latitude REAL,
            longitude REAL,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_loc_user ON user_locations(user_id)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            template_id TEXT NOT NULL,
            scene TEXT,
            authorized_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'authorized',
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sub_user_tpl ON "
        "user_subscriptions(user_id, template_id)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            template_id TEXT NOT NULL,
            data_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'scheduled',
            scheduled_at TEXT NOT NULL,
            sent_at TEXT,
            fail_reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminder_status ON reminders(status, scheduled_at)"
    )
    conn.commit()


def migrate_v5(conn: sqlite3.Connection):
    """全新库补建 patients_info(历史就诊记录主表)

    v2 只做增量 ALTER,全新库(表不存在)时直接跳过,导致 patients_info 永远缺失,
    而 repositories 对它的读写不受迁移保护 → 新增本迁移兜底建表。
    """

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS patients_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            patient_name TEXT,
            patient_gender TEXT,
            patient_age INTEGER DEFAULT 0,
            chief_complaint TEXT,
            present_illness TEXT,
            past_history TEXT,
            system_review TEXT,
            personal_history TEXT,
            family_history TEXT,
            diagnosis TEXT,
            full_report TEXT,
            visit_date TEXT NOT NULL,
            visit_count INTEGER NOT NULL DEFAULT 1,
            chief_complaint_preview TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_records_user_date "
        "ON patients_info(user_id, visit_date DESC)"
    )
    conn.commit()


def migrate_v6(conn: sqlite3.Connection):
    """修复 v5 建表缺陷:patients_info.created_at 缺 DEFAULT

    repositories.save_patient_record 的 INSERT 不包含 created_at,
    若该列 NOT NULL 且无默认值,每次保存都抛 IntegrityError(被上层吞掉),
    表现为:报告在对话里能看到,但「就诊记录」页永远查不到。
    SQLite 不支持修改列默认值,故按标准流程重建表(保留已有数据)。
    """

    if not _table_exists(conn, "patients_info"):
        return

    # 已有默认值则无需处理(全新库由修正后的 v5 直接建对)
    cur = conn.execute("PRAGMA table_info(patients_info)")
    for row in cur.fetchall():
        if row[1] == "created_at" and row[4]:  # row[4] = dflt_value
            return

    logger.info("patients_info.created_at 缺少默认值,重建表修复 ...")

    # 重建期间关闭外键(share_links 引用本表;DDL 在 autocommit 下执行,无未决事务)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute(
        """
        CREATE TABLE patients_info_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            patient_name TEXT,
            patient_gender TEXT,
            patient_age INTEGER DEFAULT 0,
            chief_complaint TEXT,
            present_illness TEXT,
            past_history TEXT,
            system_review TEXT,
            personal_history TEXT,
            family_history TEXT,
            diagnosis TEXT,
            full_report TEXT,
            visit_date TEXT NOT NULL,
            visit_count INTEGER NOT NULL DEFAULT 1,
            chief_complaint_preview TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        INSERT INTO patients_info_new(
            id, user_id, patient_name, patient_gender, patient_age,
            chief_complaint, present_illness, past_history, system_review,
            personal_history, family_history, diagnosis, full_report,
            visit_date, visit_count, chief_complaint_preview, created_at
        )
        SELECT
            id, user_id, patient_name, patient_gender, patient_age,
            chief_complaint, present_illness, past_history, system_review,
            personal_history, family_history, diagnosis, full_report,
            visit_date, visit_count, chief_complaint_preview, created_at
        FROM patients_info
        """
    )
    conn.execute("DROP TABLE patients_info")
    conn.execute("ALTER TABLE patients_info_new RENAME TO patients_info")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_records_user_date "
        "ON patients_info(user_id, visit_date DESC)"
    )
    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()
    logger.info("patients_info 重建完成,created_at 已补默认值")


def migrate_v7(conn: sqlite3.Connection):
    """users 增加登录资料列:profile_age / profile_gender

    登录界面录入的基本信息存到这里;新会话创建时预填进 ConsultationSession,
    使模型不再跨会话重复询问年龄/性别。
    """
    if not _column_exists(conn, "users", "profile_age"):
        conn.execute("ALTER TABLE users ADD COLUMN profile_age INTEGER")
        logger.info("users 已增加 profile_age 列")
    if not _column_exists(conn, "users", "profile_gender"):
        conn.execute("ALTER TABLE users ADD COLUMN profile_gender TEXT")
        logger.info("users 已增加 profile_gender 列")
    conn.commit()


def migrate_v8(conn: sqlite3.Connection):
    """新增 session_steps:保存每一轮问答的推理过程(Thought/Action/Observation)与知识溯源引用。

    独立建表,不改动 consultation_sessions 的既有字段与关联关系;
    text/refs/sentences/args 含患者原话与病史片段,由 service 层加密后写入。
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_steps (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            session_id    TEXT NOT NULL,
            turn_index    INTEGER NOT NULL,
            seq           INTEGER NOT NULL,
            step_type     TEXT NOT NULL,          -- note/thought/action/observation/final/fallback
            status        TEXT,                   -- ok/error/timeout/skipped
            branch        TEXT,                   -- direct_qa / intake
            tool          TEXT,
            args_json     TEXT,                   -- 加密(action 参数)
            text          TEXT,                   -- 加密(步骤正文/摘要)
            refs_json     TEXT,                   -- 加密(知识溯源引用)
            sentences_json TEXT,                  -- 加密(句子级溯源结果)
            elapsed_ms    INTEGER,
            ts            TEXT,
            fallback_reason TEXT,
            created_at    TEXT NOT NULL,
            UNIQUE(session_id, turn_index, seq)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_steps_session "
        "ON session_steps(session_id, turn_index)"
    )
    conn.commit()


# 迁移注册表:(version, function)
_MIGRATIONS = [
    (1, migrate_v1),
    (2, migrate_v2),
    (3, migrate_v3),
    (4, migrate_v4),
    (5, migrate_v5),
    (6, migrate_v6),
    (7, migrate_v7),
    (8, migrate_v8),
]


def run_migrations():
    """执行所有未应用的迁移"""
    ensure_db_dir()
    with get_conn() as conn:
        applied = _applied_versions(conn)
        for version, func in _MIGRATIONS:
            if version in applied:
                continue
            logger.info(f"执行数据库迁移 v{version} ...")
            func(conn)
            _mark_applied(conn, version)
            logger.info(f"数据库迁移 v{version} 完成")
    logger.info(f"数据库迁移完成,已应用版本: {sorted(applied | {v for v, _ in _MIGRATIONS})}")

"""
数据库操作模块 - 医学问诊智能体
使用 SQLite 存储患者问诊记录，零配置开箱即用
"""

import sqlite3
import logging
from datetime import datetime
from typing import Optional

import config

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """获取 SQLite 数据库连接"""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row  # 让查询结果可以用列名访问
    return conn


def init_database():
    """
    初始化数据库，创建 patients_info 表
    如果表已存在则不会重复创建
    """
    # 确保数据目录存在
    import os
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patients_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_name TEXT NOT NULL,
                patient_gender TEXT,
                patient_age INTEGER,
                chief_complaint TEXT,
                present_illness TEXT,
                past_history TEXT,
                system_review TEXT,
                personal_history TEXT,
                family_history TEXT,
                diagnosis TEXT,
                full_report TEXT,
                visit_date TEXT,
                visit_count INTEGER DEFAULT 1
            )
        """)
        conn.commit()
        logger.info("数据库初始化成功，patients_info 表已就绪")
    except sqlite3.Error as e:
        logger.error(f"数据库初始化失败: {e}")
        raise
    finally:
        conn.close()


def query_patient(name: str, user_id: int = 0) -> list:
    """
    按姓名查询患者历史记录
    Args:
        name: 患者姓名
        user_id: 用户标识(小程序模式>0 时限定作用域,防同名串档;=0 时桌面模式查全部)
    Returns:
        患者记录列表，每条记录为字典格式；无结果返回空列表

    注意:小程序模式下 name 为密文(user_keys 加密),精确匹配即可;
    桌面模式 user_id=0 时 name 为明文,按旧逻辑匹配。
    """
    if not name or not name.strip():
        logger.warning("查询患者时姓名为空")
        return []

    conn = get_connection()
    try:
        cursor = conn.cursor()
        if user_id and user_id > 0:
            # 小程序模式:限定 user_id 作用域(防同名串档)
            cursor.execute(
                """
                SELECT id, patient_name, patient_gender, patient_age,
                       chief_complaint, present_illness, past_history,
                       system_review, personal_history, family_history,
                       diagnosis, full_report, visit_date, visit_count
                FROM patients_info
                WHERE patient_name = ? AND user_id = ?
                ORDER BY visit_date DESC
                """,
                (name.strip(), user_id)
            )
        else:
            # 桌面模式:保持旧逻辑(全部记录按姓名匹配)
            cursor.execute(
                """
                SELECT id, patient_name, patient_gender, patient_age,
                       chief_complaint, present_illness, past_history,
                       system_review, personal_history, family_history,
                       diagnosis, full_report, visit_date, visit_count
                FROM patients_info
                WHERE patient_name = ?
                ORDER BY visit_date DESC
                """,
                (name.strip(),)
            )
        rows = cursor.fetchall()
        # 将 Row 对象转为字典列表
        results = [dict(row) for row in rows]
        logger.info(f"查询患者 '{name}'，找到 {len(results)} 条记录")
        return results
    except sqlite3.Error as e:
        logger.error(f"查询患者 '{name}' 失败: {e}")
        return []
    finally:
        conn.close()


def save_patient(data: dict) -> Optional[int]:
    """
    保存患者问诊记录到数据库
    Args:
        data: 患者数据字典，包含以下字段：
            - patient_name: 姓名（必填）
            - patient_gender: 性别
            - patient_age: 年龄
            - chief_complaint: 主诉
            - present_illness: 现病史
            - past_history: 既往史
            - system_review: 系统回顾
            - personal_history: 个人史
            - family_history: 家族史
            - diagnosis: 诊断
            - full_report: 完整报告
    Returns:
        新记录的 ID，失败返回 None
    """
    required_fields = ["patient_name"]
    for field in required_fields:
        if field not in data or not data[field]:
            logger.error(f"保存患者记录失败：缺少必填字段 '{field}'")
            return None

    # 查询该患者是否已有记录，以确定 visit_count
    existing = query_patient(data["patient_name"])
    visit_count = len(existing) + 1

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO patients_info (
                patient_name, patient_gender, patient_age,
                chief_complaint, present_illness, past_history,
                system_review, personal_history, family_history,
                diagnosis, full_report, visit_date, visit_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("patient_name", ""),
                data.get("patient_gender", ""),
                data.get("patient_age", 0),
                data.get("chief_complaint", ""),
                data.get("present_illness", ""),
                data.get("past_history", ""),
                data.get("system_review", ""),
                data.get("personal_history", ""),
                data.get("family_history", ""),
                data.get("diagnosis", ""),
                data.get("full_report", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                visit_count,
            )
        )
        conn.commit()
        record_id = cursor.lastrowid
        logger.info(f"患者 '{data['patient_name']}' 的记录已保存，ID={record_id}，第 {visit_count} 次就诊")
        return record_id
    except sqlite3.Error as e:
        logger.error(f"保存患者记录失败: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

"""
数据库连接模块 - 医学问诊智能体小程序后端

特性:
- SQLite WAL 模式,缓解并发读写单写锁
- 开启外键约束
- 统一 row_factory,结果可按列名访问
- 连接上下文管理,确保释放
"""

import logging
import sqlite3
from contextlib import contextmanager

import config

logger = logging.getLogger(__name__)

# 连接级 PRAGMA,WAL 下安全且更快
_PRAGMAS = [
    "PRAGMA journal_mode=WAL;",
    "PRAGMA foreign_keys=ON;",
    "PRAGMA synchronous=NORMAL;",
]


def _apply_pragmas(conn: sqlite3.Connection):
    """对单个连接应用 PRAGMA"""
    cur = conn.cursor()
    for p in _PRAGMAS:
        cur.execute(p)
    conn.commit()


@contextmanager
def get_conn():
    """
    获取数据库连接的上下文管理器。
    自动应用 PRAGMA,异常时回滚,结束时关闭。
    用法:
        with get_conn() as conn:
            conn.execute(...)
    """
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        _apply_pragmas(conn)
        yield conn
    except sqlite3.Error:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_db_dir():
    """确保数据库目录存在"""
    import os
    db_dir = os.path.dirname(config.DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

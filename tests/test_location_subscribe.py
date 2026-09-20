"""
地理位置 / 订阅 / 提醒 仓库层单测 - 不触网

运行: .venv/Scripts/pytest.exe tests/test_location_subscribe.py -q
"""

import asyncio
import tempfile

import config
from app.db import migrations, repositories
from app.services import subscribe_service


def _setup() -> int:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    config.DB_PATH = f.name
    migrations.run_migrations()
    uid, _ = repositories.upsert_user_by_openid("openid_loc_test")
    return uid


def test_location_crud_and_default():
    uid = _setup()
    lid = repositories.add_location(uid, "市第一医院", "XX路1号", 31.2, 121.4, is_default=True)
    assert lid > 0
    rows = repositories.list_locations(uid)
    assert len(rows) == 1 and rows[0]["is_default"] == 1

    lid2 = repositories.add_location(uid, "市中医院", is_default=True)
    rows = repositories.list_locations(uid)
    defaults = [r for r in rows if r["is_default"] == 1]
    assert len(defaults) == 1 and defaults[0]["id"] == lid2

    repositories.delete_location(lid, uid)
    assert len(repositories.list_locations(uid)) == 1


def test_subscription_and_reminder_flow():
    uid = _setup()
    repositories.upsert_subscription(uid, "tpl_1", "consult_done")
    # 计划时间在过去 -> 立即下发;dev 模式走 mock -> 标记 sent
    rid = asyncio.run(
        subscribe_service.create_reminder(
            uid, "tpl_1", {"thing1": {"value": "复诊提醒"}}, scheduled_at="2000-01-01 00:00:00"
        )
    )
    assert rid > 0
    rows = repositories.list_reminders(uid)
    assert rows[0]["status"] == "sent"

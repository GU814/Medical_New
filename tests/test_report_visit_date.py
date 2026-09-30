"""
回归测试：报告中的"就诊日期"必须来自系统时间，不得由模型编造。

背景：REPORT_GENERATION_PROMPT 里"- 就诊日期："原本留空让 LLM 自行填写，
模型按训练语料习惯生成了"2023年10月1日"这类固定旧日期（与真实时间无关）。
修复：提示词注入系统时间 + 生成后 _enforce_visit_date 兜底校正。

本测试不依赖 Ollama，用假 LLM 模拟模型仍写旧日期的情况。
"""
import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import report_generator as rg  # noqa: E402

# 假 LLM 输出：故意编造 2023 年的旧日期
FAKE_REPORT = """# 完整病历

## 基本信息
- 姓名：患者
- 性别：男
- 年龄：21
- 就诊日期：2023年10月1日

## 主诉
肚子痛

⚠️ 免责声明
"""


def _visit_date(report: str) -> str:
    m = re.search(r"就诊日期[：:]\s*([^\n]+)", report)
    return m.group(1).strip() if m else ""


def test_current_time_str_matches_system():
    """时间取自系统，格式为 YYYY-MM-DD HH:MM:SS"""
    now = rg.current_time_str()
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", now)
    assert now[:13] == datetime.now().strftime("%Y-%m-%d %H")


def test_prompt_injects_visit_date():
    """提示词模板必须注入系统时间，且带禁止编造规则"""
    now = rg.current_time_str()
    prompt = rg.REPORT_GENERATION_PROMPT.format(
        patient_name="张三", patient_gender="男", patient_age="21",
        chief_complaint="腹痛", present_illness="x", past_history="x",
        personal_history="x", family_history="x", system_review="x",
        deep_analysis="分析", history_reference="无", visit_date=now,
    )
    assert f"- 就诊日期：{now}" in prompt
    assert "严禁自行填写" in prompt


def test_enforce_replaces_old_date():
    fixed = rg._enforce_visit_date(FAKE_REPORT, "2026-09-27 18:00:00")
    assert _visit_date(fixed) == "2026-09-27 18:00:00"


def test_enforce_adds_missing_field():
    """模型漏写就诊日期时，在"## 基本信息"下补一行"""
    no_date = "## 基本信息\n- 姓名：患者\n\n## 主诉\n腹痛\n"
    fixed = rg._enforce_visit_date(no_date, "2026-09-27 18:00:00")
    assert _visit_date(fixed) == "2026-09-27 18:00:00"


def test_enforce_is_idempotent():
    once = rg._enforce_visit_date(FAKE_REPORT, "2026-09-27 18:00:00")
    twice = rg._enforce_visit_date(once, "2026-09-27 18:00:00")
    assert twice.count("就诊日期") == 1


def test_sync_path_uses_system_time(monkeypatch):
    saved = {}
    monkeypatch.setattr(rg.llm_client, "chat", lambda **kw: FAKE_REPORT)
    monkeypatch.setattr(
        rg, "_save_to_database", lambda pd, rep, da, user_id=0: saved.update(rep=rep)
    )
    report = rg.generate_report({"patient_name": "测试", "chief_complaint": "腹痛"})
    got = _visit_date(report)
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", got)
    assert "2023" not in got
    # 落库内容同样被纠正
    assert not _visit_date(saved["rep"]).startswith("2023")


def test_stream_path_uses_system_time(monkeypatch):
    async def fake_stream(**kw):
        # 按 12 字切块，模拟"半行"到达的情况
        for i in range(0, len(FAKE_REPORT), 12):
            yield FAKE_REPORT[i:i + 12]

    saved = {}
    monkeypatch.setattr(rg.llm_client, "chat_stream", fake_stream)
    monkeypatch.setattr(
        rg, "_save_to_database", lambda pd, rep, da, user_id=0: saved.update(rep=rep)
    )

    def run():
        chunks = []
        # 注意：环境未装 pytest-asyncio，这里显式用 asyncio.run 驱动
        async def collect():
            async for c in rg.generate_report_stream(
                {"patient_name": "测试", "chief_complaint": "腹痛"}
            ):
                chunks.append(c)
        asyncio.run(collect())
        return "".join(chunks)

    streamed = run()

    got = _visit_date(streamed)
    # 关键：不能出现"2026-09-27 18:51:1323年10月1日"这种半行拼接残留
    assert "2023" not in got
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", got)
    assert not _visit_date(saved["rep"]).startswith("2023")

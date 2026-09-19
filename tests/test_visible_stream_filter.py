# -*- coding: utf-8 -*-
"""
流式可见文本过滤器回归测试（consultation._VisibleStreamFilter）

背景：deepseek-r1 等推理模型会把 <think> 思维链混入正文，且问诊提示词要求
模型在回复末尾附带结构化 JSON（可能带【JSON块】标记，也可能是裸 { ... }）。
若原样流式转发给前端，用户会看到一堆思考过程和 JSON 代码。

运行：python tests/test_visible_stream_filter.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from consultation import _VisibleStreamFilter  # noqa: E402

CASES = [
    (
        "中文JSON块",
        "您好，您提到最近有咳嗽和低烧。\n首先，能告诉我您的姓名吗？\n\n【JSON块】\n"
        '{\n    "patient_name": "",\n    "chief_complaint": "咳嗽伴低烧",\n'
        '    "stage_complete": false,\n    "next_stage": 1\n}',
        "您好，您提到最近有咳嗽和低烧。\n首先，能告诉我您的姓名吗？",
    ),
    (
        "think思维链",
        "<think>我在思考要不要问年龄...</think>请问您今年多大年纪了？\n\n【JSON块】\n{\"patient_age\": 0}",
        "请问您今年多大年纪了？",
    ),
    (
        "代码围栏",
        "这是回答。\n\n```json\n{\"a\": 1}\n```\n希望有帮助。",
        "这是回答。\n\n希望有帮助。",
    ),
    (
        "裸JSON无标记",
        "您好，您提到最近有咳嗽和低烧。\n\n请告诉我您的姓名。\n\n"
        "{\n    \"patient_name\": \"\",\n    \"chief_complaint\": \"咳嗽伴低烧\",\n"
        "    \"stage_complete\": false\n}",
        "您好，您提到最近有咳嗽和低烧。\n\n请告诉我您的姓名。",
    ),
    (
        "正文花括号不误判",
        "体温范围 {36.5-37.2} 属于低热区间，请注意观察。",
        "体温范围 {36.5-37.2} 属于低热区间，请注意观察。",
    ),
]

# 逐字符 / 细粒度分块最容易暴露跨 chunk 边界漏判，必须全部覆盖
CHUNK_SIZES = (1, 2, 3, 5, 7, 13, 64, 4096)


def run(raw: str, size: int) -> str:
    f = _VisibleStreamFilter()
    out = []
    for i in range(0, len(raw), size):
        out.append(f.feed(raw[i:i + size]))
    out.append(f.flush())
    return "".join(out).strip()


def main() -> int:
    failed = 0
    for name, raw, expect in CASES:
        for size in CHUNK_SIZES:
            got = run(raw, size)
            if got != expect:
                failed += 1
                print(f"[FAIL] {name} chunk={size}\n  期望: {expect!r}\n  实际: {got!r}")
        print(f"[{'OK' if failed == 0 else '..'}] {name}")
    print("\n全部通过 ✅" if failed == 0 else f"\n失败 {failed} 项 ❌")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

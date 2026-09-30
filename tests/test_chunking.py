"""
分块策略回归(CHUNK_STRATEGY=heading)。

锁定的是「一个块 = 一个 ## 主题」这条契约:
引言单独成块、子标题不拆、内容不遗漏、顺序不乱、超长才有安全阀。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import knowledge_base as kb  # noqa: E402

DOC = """# 医学知识库

本库用于健康科普参考。

## 高血压

### 概述
高血压是最常见的慢性病。

### 分级
- 1 级：140-159 / 90-99
- 2 级：160-179 / 100-109

## 糖尿病

### 分型
1 型与 2 型。

### 监测
空腹血糖与糖化血红蛋白。
"""


def test_preamble_is_its_own_chunk():
    """第一个 ## 之前的 # 级标题与引言单独成块。"""
    ann = kb._split_text_annotated(DOC)
    assert ann[0]["section"] == "", f"引言块的 section 应为空串, 实际 {ann[0]['section']!r}"
    assert ann[0]["text"].startswith("# 医学知识库")
    assert "本库用于健康科普参考。" in ann[0]["text"]
    assert "## 高血压" not in ann[0]["text"]


def test_one_h2_theme_per_chunk():
    """每个块只含一个 ## 标题 —— 旧装箱方案的病正是「114/117 块跨多个标题」。"""
    ann = kb._split_text_annotated(DOC)
    for item in ann[1:]:
        n_h2 = sum(1 for line in item["text"].split("\n")
                   if kb._H2_RE.match(line))
        assert n_h2 == 1, f"块 {item['section']!r} 含 {n_h2} 个 ## 标题"


def test_section_names_and_order():
    ann = kb._split_text_annotated(DOC)
    assert [c["section"] for c in ann] == ["", "高血压", "糖尿病"]
    assert ann[1]["text"].startswith("## 高血压")
    assert ann[2]["text"].startswith("## 糖尿病")


def test_sub_headings_stay_with_their_theme():
    """同一 ## 主题下的 ### 子标题与正文不得被拆到别的块。"""
    ann = kb._split_text_annotated(DOC)
    hypertension = ann[1]["text"]
    assert "### 概述" in hypertension and "### 分级" in hypertension
    assert "- 1 级：140-159 / 90-99" in hypertension
    diabetes = ann[2]["text"]
    assert "### 分型" in diabetes and "### 监测" in diabetes


def test_no_content_loss_and_order_preserved():
    """逐行核对:原文每个非空行都出现在块内,且块顺序与原文一致。"""
    ann = kb._split_text_annotated(DOC)
    joined = "\n".join(c["text"] for c in ann)
    for line in DOC.split("\n"):
        if line.strip():
            assert line.strip() in joined, f"内容丢失: {line!r}"
    # 顺序:后出现的行在拼接串中的位置不得早于先出现的行
    pos = -1
    for line in DOC.split("\n"):
        if not line.strip():
            continue
        cur = joined.find(line.strip())
        assert cur >= pos, f"顺序被打乱: {line!r}"
        pos = cur


def test_document_without_h2_is_single_chunk():
    plain = "阿司匹林用于解热镇痛。\n长期服用需注意胃肠道反应。"
    ann = kb._split_text_annotated(plain)
    assert len(ann) == 1, f"无 ## 结构时应整篇一块, 实际 {len(ann)} 块"
    assert ann[0]["text"] == plain.strip()


def test_oversize_theme_splits_at_h3(monkeypatch):
    """超过安全阈才二次切分:在 ### 处断开,且每片都保留 ## 标题行。"""
    monkeypatch.setattr(config, "CHUNK_H2_MAX_SIZE", 200)
    long_doc = "## 大主题\n" + "\n".join(
        f"### 子主题{i}\n" + ("内容" * 60) for i in range(1, 5)
    )
    ann = kb._split_text_annotated(long_doc)
    assert len(ann) > 1, "超长主题应触发安全阀"
    for item in ann:
        assert item["section"] == "大主题"
        assert item["text"].startswith("## 大主题"), "分片必须带上 ## 标题行做上下文"
    assert ann[0]["total_parts"] == len(ann)


def test_legacy_strategy_rolls_back(monkeypatch):
    """CHUNK_STRATEGY=legacy 时必须回到旧的装箱实现,保证可一键回滚。"""
    monkeypatch.setattr(config, "CHUNK_STRATEGY", "legacy")
    out = kb._split_text(DOC, 500, 100)
    assert out and all(isinstance(x, str) for x in out)
    # 旧实现的特征:会把多个 ## 标题装箱进同一块
    merged = [c for c in out if sum(1 for l in c.split("\n") if kb._H2_RE.match(l)) > 1]
    assert merged, "legacy 分支未生效(应出现跨主题装箱块)"


def test_min_len_filter_skips_title_only_chunks(monkeypatch):
    """纯标题块不入库(短文本余弦虚高会抢占 Top-K),但切分结果仍保留它。"""
    monkeypatch.setattr(config, "CHUNK_MIN_INDEX_LEN", 40)
    title_only = "## 只有标题\n"
    with_intro = "## 有正文\n" + "内容" * 30
    ann = kb._split_text_annotated("# 标题\n\n" + title_only + with_intro)
    picked = kb.indexable_chunks(ann)
    assert len(picked) == 1, f"应只保留有正文的块, 实际 {len(picked)}"
    idx, item = picked[0]
    assert item["section"] == "有正文"
    # 原始下标保留,doc_id 因此不会因过滤而错位
    assert idx == ann.index(item)


def test_add_documents_writes_section_metadata(tmp_path, monkeypatch):
    """入库元数据必须带 section,否则溯源只能定位到文件、定位不到章节。"""
    monkeypatch.setattr(config, "CHUNK_MIN_INDEX_LEN", 0)  # 关闭下限,取全部块
    d = tmp_path
    (d / "t.md").write_text(DOC, encoding="utf-8")

    captured = {}

    class FakeCol:
        def upsert(self, ids, documents, metadatas):
            captured["ids"] = ids
            captured["metadatas"] = metadatas

    monkeypatch.setattr(kb, "get_collection", lambda: FakeCol())
    kb.add_documents(str(d))

    metas = captured["metadatas"]
    assert metas, "未写入任何片段"
    assert [m["section"] for m in metas] == ["", "高血压", "糖尿病"]
    assert metas[0]["doc_id"] == "t.md_chunk_0"
    assert metas[1]["doc_id"] == "t.md_chunk_1"
    assert all(m["chunk_index"] == i for i, m in enumerate(metas))

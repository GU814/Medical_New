"""
导出知识库的分块结果，便于人工核对切分是否符合预期。

用法:
    python export_knowledge_chunks.py [输出文件路径]

默认输出到 docs/knowledge-chunks.md。
分块逻辑与入库完全一致(都走 knowledge_base._split_text_annotated)，
所以这里看到的就是实际进向量库的片段。
"""
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config  # noqa: E402
import knowledge_base as kb  # noqa: E402

DEFAULT_OUT = os.path.join(ROOT, "docs", "knowledge-chunks.md")
KNOWLEDGE_DIR = config.KNOWLEDGE_DIR if hasattr(config, "KNOWLEDGE_DIR") else os.path.join(ROOT, "data", "knowledge")
SUPPORTED = (".md", ".txt")


def main(out_path: str = DEFAULT_OUT):
    files = [f for f in sorted(os.listdir(KNOWLEDGE_DIR))
             if os.path.splitext(f)[1].lower() in SUPPORTED]
    if not files:
        print(f"目录为空: {KNOWLEDGE_DIR}")
        return 1

    blocks_total = 0
    buf = []
    buf.append("# 知识库分块结果（按 ## 主题切分）\n")
    buf.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    buf.append(f"- 分块策略：`CHUNK_STRATEGY={getattr(config, 'CHUNK_STRATEGY', 'heading')}`"
               f"（一个块 = 一个 ## 主题；首个 ## 之前的 # 级标题与引言单独成块）")
    buf.append(f"- 安全阈：`CHUNK_H2_MAX_SIZE={getattr(config, 'CHUNK_H2_MAX_SIZE', 2000)}`"
               f"（超过才在 ### 处二次切分，本库未触发）")
    buf.append(f"- 文档目录：`{KNOWLEDGE_DIR}`\n")

    for filename in files:
        raw = open(os.path.join(KNOWLEDGE_DIR, filename), encoding="utf-8").read()
        annotated = kb._split_text_annotated(raw)
        blocks_total += len(annotated)

        buf.append("---\n")
        buf.append(f"## 文件：{filename}  \n共 {len(annotated)} 块\n")

        for i, item in enumerate(annotated, 1):
            section = item.get("section") or "引言（# 级标题与前言）"
            part = item.get("part", 1)
            total_parts = item.get("total_parts", 1)
            tail = f" 第 {part}/{total_parts} 片" if total_parts > 1 else ""
            buf.append("---\n")
            buf.append(f"**块 {i} / {len(annotated)}** · `## 主题：{section}` · "
                       f"{len(item['text'])} 字符{tail}\n")
            buf.append(item["text"].strip())
            buf.append("")

    buf.append("---\n")
    buf.append(f"**合计：{len(files)} 篇文档，{blocks_total} 个分块**")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(buf))

    print(f"已导出 {len(files)} 篇文档 / {blocks_total} 个分块 -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT))

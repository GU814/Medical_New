"""
重建知识库索引（幂等）

用法（在项目根执行）：
    .venv\\Scripts\\python.exe reindex_knowledge.py

说明：
- 读取 data/knowledge 下全部 .md/.txt/.pdf，按当前 CHUNK_STRATEGY 分块后 upsert 进 Chroma。
  默认策略 heading：一个块 = 一个 ## 主题（首个 ## 之前的 # 级标题与引言单独成块）。
- 片段主键是确定的 `{文件名}_chunk_{i}`，因此重复执行只会覆盖同名片段，**不会**重复堆积。
- 新增或删除文档后重新执行即可让生效范围与磁盘内容对齐。
- ⚠️ 仅 upsert 无法处理「块数变少」：切换切分策略后旧片段的 id 会落在新的编号范围之外，
  残留在库里会被检索召回（陈旧内容 + 旧切分边界）。因此本脚本在导入后会**按预期主键集合
  清理陈旧片段**，保证库内片段与磁盘严格一一对应。
- 注意：导入耗时主要在 embedding（nomic-embed-text 为 768 维），文档多时请预留时间。
"""

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# config._app_dir 在 venv 下会被 sys.executable 带偏，这里直接定位真实工程目录
ROOT = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_DIR = os.path.join(ROOT, "data", "knowledge")


def main() -> int:
    if not os.path.isdir(KNOWLEDGE_DIR):
        print(f"知识库目录不存在: {KNOWLEDGE_DIR}")
        return 1

    import config
    import knowledge_base

    # 路径写死，避免 _app_dir 漂移
    knowledge_base.config.CHROMA_PATH = config.CHROMA_PATH

    docs = [f for f in os.listdir(KNOWLEDGE_DIR)
            if os.path.splitext(f)[1].lower() in (".md", ".txt", ".pdf")]
    print(f"待导入文档 {len(docs)} 个 -> {KNOWLEDGE_DIR}")

    # 导入前先记录库内已有主键,导入后用于清理陈旧片段
    try:
        before_ids = set(knowledge_base.get_collection().get()["ids"] or [])
    except Exception as e:
        print(f"读取已有主键失败(跳过陈旧清理): {e}")
        before_ids = set()

    knowledge_base.add_documents(KNOWLEDGE_DIR)

    # 预期主键集合:与 add_documents 的命名约定严格一致
    expected = set()
    for name in docs:
        path = os.path.join(KNOWLEDGE_DIR, name)
        try:
            if name.lower().endswith(".pdf"):
                text = knowledge_base._extract_text_from_pdf(path)
            else:
                text = open(path, "r", encoding="utf-8").read()
        except Exception as e:
            print(f"重算分块数失败,跳过 {name}: {e}")
            continue
        # 与 add_documents 用同一套过滤,否则会把「已跳过的纯标题块」误判为陈旧片段而删除
        annotated = knowledge_base._split_text_annotated(text)
        for i, _ in knowledge_base.indexable_chunks(annotated):
            expected.add(f"{name}_chunk_{i}")

    try:
        col = knowledge_base.get_collection()
        stale = before_ids - expected
        if stale:
            col.delete(ids=sorted(stale))
            print(f"已清理陈旧片段 {len(stale)} 条(切分策略变更/文档删除产生的残留)")
        print(f"导入完成，集合当前片段数: {col.count()}（预期 {len(expected)}）")
    except Exception as e:  # 取计数失败不阻塞，导入本身通常已成功
        print(f"导入完成，但读取片段数失败: {e}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

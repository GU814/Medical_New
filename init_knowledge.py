"""
知识库初始化脚本 - 医学问诊智能体
读取 data/knowledge/ 目录下的文档，分块并添加到 ChromaDB
支持 .txt / .md / .pdf 格式
"""

import logging
import sys
import os

# 确保可以导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import knowledge_base
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def init_knowledge():
    """初始化知识库"""
    # 初始化 ChromaDB
    knowledge_base.init_knowledge_base()
    logger.info("ChromaDB 已初始化")

    # 读取文档目录
    knowledge_dir = config.KNOWLEDGE_DIR
    if not os.path.isdir(knowledge_dir):
        logger.warning(f"知识库文档目录不存在: {knowledge_dir}")
        logger.info("正在创建目录...")
        os.makedirs(knowledge_dir, exist_ok=True)
        logger.info(f"目录已创建: {knowledge_dir}")
        logger.info("请将医学知识文档（.txt/.md/.pdf 格式）放入该目录后重新运行此脚本")
        return

    # 检查目录下是否有文档（支持 .txt/.md/.pdf）
    supported_extensions = ('.txt', '.md', '.pdf')
    files = [f for f in os.listdir(knowledge_dir)
             if os.path.isfile(os.path.join(knowledge_dir, f))
             and f.lower().endswith(supported_extensions)]

    if not files:
        logger.warning(f"知识库文档目录为空: {knowledge_dir}")
        logger.info("请将医学知识文档（.txt/.md/.pdf 格式）放入该目录后重新运行此脚本")
        return

    # 列出找到的文件
    logger.info(f"发现 {len(files)} 个文档文件:")
    for f in files:
        size = os.path.getsize(os.path.join(knowledge_dir, f))
        logger.info(f"  - {f} ({size} 字节)")

    # 添加文档到知识库
    knowledge_base.add_documents(knowledge_dir)

    # 显示结果
    collection = knowledge_base.get_collection()
    count = collection.count()
    logger.info(f"知识库初始化完成，共 {count} 条文档片段")
    
    if count == 0:
        logger.warning("知识库仍为空！请检查文档内容是否为空或格式是否正确")


if __name__ == "__main__":
    init_knowledge()

"""
本地知识库初始化脚本 - 无需 Ollama
使用 TF-IDF + 余弦相似度代替神经网络 Embedding
适合在 Ollama 未安装/未启动时完成知识库初始化
"""

import os
import sys
import re
import json
import logging
import shutil
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# 确保可以导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# ==================== 配置 ====================

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "knowledge")
INDEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "knowledge_index")
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
RELEVANCE_THRESHOLD = 0.15  # TF-IDF 余弦相似度阈值（比向量 embedding 低）


# ==================== 文本处理 ====================

def split_text(text: str) -> list:
    """将文本按语义段落分块"""
    if len(text) <= CHUNK_SIZE:
        return [text]

    sections = re.split(r'\n(?=##|# )', text)
    chunks = []
    current_chunk = ""

    for section in sections:
        if not section.strip():
            continue
        if len(section) > CHUNK_SIZE:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            start = 0
            while start < len(section):
                end = start + CHUNK_SIZE
                chunks.append(section[start:end].strip())
                start += CHUNK_SIZE - CHUNK_OVERLAP
        elif len(current_chunk) + len(section) > CHUNK_SIZE:
            chunks.append(current_chunk.strip())
            current_chunk = section
        else:
            current_chunk += "\n" + section

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return [c for c in chunks if c.strip()]


def extract_pdf_text(filepath: str) -> str:
    """从 PDF 提取文本"""
    for lib_name, lib_import in [
        ("PyMuPDF", "import fitz"),
        ("pdfplumber", "import pdfplumber"),
        ("PyPDF2", "from PyPDF2 import PdfReader"),
    ]:
        try:
            if lib_name == "PyMuPDF":
                import fitz
                doc = fitz.open(filepath)
                text = "".join(page.get_text() for page in doc)
                doc.close()
                if text.strip():
                    return text
            elif lib_name == "pdfplumber":
                import pdfplumber
                with pdfplumber.open(filepath) as pdf:
                    text = "".join((page.extract_text() or "") + "\n" for page in pdf.pages)
                    if text.strip():
                        return text
            elif lib_name == "PyPDF2":
                from PyPDF2 import PdfReader
                reader = PdfReader(filepath)
                text = "".join((page.extract_text() or "") + "\n" for page in reader.pages)
                if text.strip():
                    return text
        except ImportError:
            continue
        except Exception as e:
            logger.debug(f"{lib_name} 提取 PDF 失败: {e}")
    logger.warning(f"无法提取 PDF（缺少 PDF 库）: {os.path.basename(filepath)}")
    return ""


# ==================== 知识库构建 ====================

def load_documents(knowledge_dir: str) -> list:
    """加载所有知识文档"""
    supported = {".txt", ".md", ".pdf"}
    documents = []

    if not os.path.isdir(knowledge_dir):
        logger.error(f"目录不存在: {knowledge_dir}")
        return documents

    for filename in sorted(os.listdir(knowledge_dir)):
        filepath = os.path.join(knowledge_dir, filename)
        if not os.path.isfile(filepath):
            continue

        ext = os.path.splitext(filename)[1].lower()
        if ext not in supported:
            continue

        try:
            if ext == ".pdf":
                content = extract_pdf_text(filepath)
                if not content.strip():
                    continue
            else:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()

            if not content.strip():
                continue

            chunks = split_text(content)
            for i, chunk in enumerate(chunks):
                documents.append({
                    "id": f"{filename}_chunk_{i}",
                    "text": chunk,
                    "source": filename,
                    "chunk_index": i,
                    "file_type": ext.lstrip("."),
                })

            logger.info(f"  {filename}: {len(chunks)} 个文档块")

        except Exception as e:
            logger.error(f"  {filename}: 处理失败 - {e}")

    return documents


def build_index(documents: list) -> dict:
    """构建 TF-IDF 索引"""
    texts = [doc["text"] for doc in documents]

    logger.info("正在构建 TF-IDF 向量索引...")
    vectorizer = TfidfVectorizer(
        max_features=10000,
        ngram_range=(1, 2),
        token_pattern=r'(?u)\b\w+\b',  # 支持中文单字
    )
    tfidf_matrix = vectorizer.fit_transform(texts)
    logger.info(f"TF-IDF 矩阵: {tfidf_matrix.shape[0]} 文档 × {tfidf_matrix.shape[1]} 特征")

    return {
        "vectorizer": vectorizer,
        "tfidf_matrix": tfidf_matrix,
    }


def save_index(documents: list, index: dict, index_dir: str):
    """保存索引到磁盘"""
    os.makedirs(index_dir, exist_ok=True)

    import pickle

    # 保存文档元数据
    with open(os.path.join(index_dir, "documents.json"), "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)

    # 保存 TF-IDF 模型和矩阵
    with open(os.path.join(index_dir, "tfidf_index.pkl"), "wb") as f:
        pickle.dump({
            "vectorizer": index["vectorizer"],
            "tfidf_matrix": index["tfidf_matrix"],
        }, f)

    # 保存配置
    config = {
        "num_documents": len(documents),
        "relevance_threshold": RELEVANCE_THRESHOLD,
        "index_type": "tfidf",
    }
    with open(os.path.join(index_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    logger.info(f"索引已保存到: {index_dir}")


# ==================== 主流程 ====================

def main():
    logger.info("=" * 50)
    logger.info("本地知识库初始化（TF-IDF 模式，无需 Ollama）")
    logger.info("=" * 50)

    # 1. 加载文档
    logger.info(f"\n正在加载文档: {KNOWLEDGE_DIR}")
    documents = load_documents(KNOWLEDGE_DIR)

    if not documents:
        logger.error("未加载到任何文档，退出")
        return

    logger.info(f"\n共加载 {len(documents)} 个文档块")

    # 统计信息
    sources = set(doc["source"] for doc in documents)
    logger.info(f"来源文件: {len(sources)} 个")
    for src in sorted(sources):
        count = sum(1 for d in documents if d["source"] == src)
        logger.info(f"  - {src}: {count} 块")

    # 2. 构建索引
    index = build_index(documents)

    # 3. 保存索引
    save_index(documents, index, INDEX_DIR)

    # 4. 快速测试搜索
    logger.info("\n" + "=" * 50)
    logger.info("搜索功能测试")
    logger.info("=" * 50)

    test_queries = ["头痛", "胃痛", "胸闷", "腰痛", "咳嗽"]
    for query in test_queries:
        query_vec = index["vectorizer"].transform([query])
        scores = cosine_similarity(query_vec, index["tfidf_matrix"]).flatten()
        top_idx = scores.argsort()[-3:][::-1]
        top_score = scores[top_idx[0]]
        top_source = documents[top_idx[0]]["source"]
        top_text = documents[top_idx[0]]["text"][:80]
        logger.info(f"  '{query}' -> 最佳匹配: {top_source} (相似度={top_score:.4f}) \"{top_text}...\"")

    logger.info("\n" + "=" * 50)
    logger.info(f"初始化完成！共 {len(documents)} 条文档片段已入库")
    logger.info(f"索引目录: {INDEX_DIR}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()

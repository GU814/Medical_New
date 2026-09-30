"""
知识库操作模块 - 医学问诊智能体
使用 ChromaDB 实现文档存储和语义检索

增强功能：
- 支持 .txt / .md / .pdf 三种格式
- search() 增加相关性阈值过滤
- 搜索结果按相关度排序
"""
# 关闭 chroma 遥测（彻底解决报错）
import os
os.environ["CHROMA_TELEMETRY"] = "False"
import json
import logging
import re
from typing import Optional, List, Union

import chromadb
from chromadb.utils import embedding_functions

import config

logger = logging.getLogger(__name__)

# 全局 ChromaDB 客户端和集合（懒加载）
_chroma_client = None
_collection = None
_embedding_fn = None

# 相关性阈值：cosine distance > 此值的结果被过滤掉（越小越相似，0=完全相同）
RELEVANCE_THRESHOLD = 0.6

# ## 级标题(二级)。用 (?!#) 排除 ###/####,避免子标题被误判为主题边界。
_H2_RE = re.compile(r"^##(?!#)\s*(.+?)\s*$")
# ### 级标题(三级)——仅在超长安全阀切分时作为断开点。
_SUB_RE = re.compile(r"^#{3,6}\s*(.+?)\s*$")


def _get_embedding_function():
    """获取 Embedding 函数，使用 OpenAI 兼容 API 格式"""
    global _embedding_fn
    if _embedding_fn is not None:
        return _embedding_fn

    api_key = config.API_KEY if config.API_KEY else "not-needed"
    api_base = config.EMBEDDING_API_BASE_URL
    model_name = config.EMBEDDING_MODEL

    init_attempts = [
        {"api_key": api_key, "api_base": api_base, "model_name": model_name},
        {"api_key": api_key, "api_base": api_base},
        {"api_key": api_key},
    ]

    for i, kwargs in enumerate(init_attempts, 1):
        try:
            _embedding_fn = embedding_functions.OpenAIEmbeddingFunction(**kwargs)
            logger.info(f"Embedding 函数已初始化（方法{i}），模型: {model_name}")
            return _embedding_fn
        except TypeError as e:
            logger.debug(f"Embedding 初始化方法{i}失败: {e}")
            continue
        except Exception as e:
            logger.debug(f"Embedding 初始化方法{i}异常: {e}")
            continue

    try:
        import httpx
        try:
            http_client = httpx.Client(proxy=None)
        except TypeError:
            http_client = httpx.Client(proxies=None)

        _embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            http_client=http_client,
        )
        logger.info(f"Embedding 函数已初始化（自定义HTTP客户端），模型: {model_name}")
        return _embedding_fn
    except Exception as e:
        logger.debug(f"Embedding 自定义HTTP客户端初始化失败: {e}")

    logger.warning("所有 Embedding 初始化方法都失败，将使用 Ollama 原生 API 作为 fallback")

    class OllamaEmbeddingFunction:
        def __init__(self):
            self._api_base = config.EMBEDDING_API_BASE_URL.replace("/v1", "")
            self._model = config.EMBEDDING_MODEL

        def __call__(self, input):
            import requests as req
            if isinstance(input, str):
                input = [input]
            results = []
            for text in input:
                try:
                    resp = req.post(
                        f"{self._api_base}/api/embeddings",
                        json={"model": self._model, "prompt": text},
                        timeout=30,
                    )
                    if resp.status_code == 200:
                        results.append(resp.json().get("embedding", []))
                    else:
                        import numpy as np
                        results.append(np.random.rand(config.EMBEDDING_DIMENSION).tolist())
                except Exception:
                    import numpy as np
                    results.append(np.random.rand(config.EMBEDDING_DIMENSION).tolist())
            return results

    _embedding_fn = OllamaEmbeddingFunction()
    return _embedding_fn


def init_knowledge_base():
    """
    初始化 ChromaDB 知识库
    创建持久化客户端和集合
    """
    global _chroma_client, _collection

    # 确保目录存在
    os.makedirs(config.CHROMA_PATH, exist_ok=True)

    # 使用持久化客户端
    _chroma_client = chromadb.PersistentClient(path=config.CHROMA_PATH)

    # 获取或创建集合
    _collection = _chroma_client.get_or_create_collection(
        name="medical_knowledge",
        embedding_function=_get_embedding_function(),
        metadata={"hnsw:space": "cosine"}
    )
    count = _collection.count()
    logger.info(f"知识库已初始化，当前包含 {count} 条文档片段")


def get_collection():
    """获取知识库集合（如果未初始化则自动初始化）"""
    global _collection
    if _collection is None:
        init_knowledge_base()
    return _collection


def get_chroma_client():
    """
    获取共享的 ChromaDB 持久化客户端（公共接口）。
    供 memory_store 等模块在同一 Chroma 实例上创建其他集合，
    避免同一路径重复创建客户端导致的锁冲突。
    """
    global _chroma_client
    if _chroma_client is None:
        init_knowledge_base()
    return _chroma_client


def get_embedding_function():
    """获取共享的嵌入函数（公共接口，供 memory_store 等模块复用）"""
    return _get_embedding_function()


def _split_text_legacy(text: str, chunk_size: int, chunk_overlap: int) -> list:
    """
    旧的分块实现：「标题优先 + 贪心装箱到 CHUNK_SIZE」。

    保留它是因为 CHUNK_STRATEGY=legacy 可一键回滚。已知缺陷(勿再当作默认):
    标题只是候选边界,装箱时会被合并 —— 实测 114/117 个块跨多个标题。
    """
    if len(text) <= chunk_size:
        return [text]

    import re as _re
    sections = _re.split(r'\n(?=##|# )', text)

    chunks = []
    current_chunk = ""

    for section in sections:
        if not section.strip():
            continue
        if len(section) > chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            start = 0
            while start < len(section):
                end = start + chunk_size
                chunks.append(section[start:end].strip())
                start += chunk_size - chunk_overlap
                if len(section) - start < chunk_size // 3:
                    if start < len(section):
                        chunks.append(section[start:].strip())
                    break
        elif len(current_chunk) + len(section) > chunk_size:
            chunks.append(current_chunk.strip())
            current_chunk = section
        else:
            current_chunk += "\n" + section

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return [c for c in chunks if c.strip()]


def _split_text_annotated(text: str, chunk_size: int = None,
                          chunk_overlap: int = None) -> list:
    """
    按 Markdown 的 ## 标题层级切分,返回带主题标注的块列表。

    规则:
      1. 一个块 = 一个 ## 标题 + 其下直到下一个 ## 之前的全部内容
         (含 ###/#### 子标题、正文、列表与代码块),原文照搬,不改写不摘要;
      2. 第一个 ## 之前的 # 级标题与引言单独成块(section 为空串);
      3. 同一 ## 主题的正文与子标题绝不被拆到不同块 —— 这是与旧装箱方案的本质区别;
      4. 仅当某块超过 CHUNK_H2_MAX_SIZE(安全阈,默认 2000)时才二次切分:
         先在 ### 处断开,仍过长才按字符 + 重叠兜底,每片都保留 ## 标题行做上下文。

    实测本库 11 篇文档按此规则得 104 块,最大 1337 字,无一触发二次切分。

    Returns: [{"text": str, "section": str, "part": int, "total_parts": int}, ...]
    """
    chunk_size = chunk_size or config.CHUNK_SIZE
    chunk_overlap = chunk_overlap or config.CHUNK_OVERLAP
    max_size = getattr(config, "CHUNK_H2_MAX_SIZE", 0) or 0

    body = text or ""
    if not body.strip():
        return []

    lines = body.split("\n")
    starts = [i for i, line in enumerate(lines) if _H2_RE.match(line)]

    # 无 ## 结构(纯文本/无标题文档):整篇一块,过长走字符切分
    if not starts:
        pieces = ([body.strip()] if len(body) <= max_size
                  else _char_split(body.strip(), chunk_size, chunk_overlap))
        return [{"text": p, "section": "", "part": i + 1, "total_parts": len(pieces)}
                for i, p in enumerate(pieces)]

    out = []

    def _push(section: str, content: str):
        """按安全阈决定是否二次切分,保持 part/total_parts 可溯源。"""
        content = content.strip()
        if not content:
            return
        if max_size and len(content) > max_size:
            pieces = _split_oversize(section, content, chunk_size, chunk_overlap)
            for i, p in enumerate(pieces):
                out.append({"text": p, "section": section,
                            "part": i + 1, "total_parts": len(pieces)})
        else:
            out.append({"text": content, "section": section,
                        "part": 1, "total_parts": 1})

    # 引言块:第一个 ## 之前的全部内容(通常含 # 级标题)
    preamble = "\n".join(lines[:starts[0]]).strip()
    _push("", preamble)

    # 逐 ## 主题成块,边界取「下一个 ## 之前」,子标题不动
    for j, start in enumerate(starts):
        end = starts[j + 1] if j + 1 < len(starts) else len(lines)
        title = _H2_RE.match(lines[start]).group(1).strip()
        _push(title, "\n".join(lines[start:end]))

    return out


def _split_oversize(section: str, content: str, chunk_size: int,
                    chunk_overlap: int) -> list:
    """
    超过安全阈的 ## 主题:先在 ### 处断开,每片都带上 ## 标题行保留上下文;
    单个 ### 仍过长才按字符切分(此时 chunk_overlap 才真正生效)。
    """
    lines = content.split("\n")
    head = lines[0]                       # ## 标题行
    body_lines = lines[1:]

    sub_idx = [i for i, l in enumerate(body_lines) if _SUB_RE.match(l)]
    if sub_idx:
        pieces = []
        for j, s in enumerate(sub_idx):
            e = sub_idx[j + 1] if j + 1 < len(sub_idx) else len(body_lines)
            piece = "\n".join([head] + body_lines[s:e]).strip()
            if not piece:
                continue
            if len(piece) > chunk_size:
                pieces.extend(_char_split(piece, chunk_size, chunk_overlap))
            else:
                pieces.append(piece)
        return [p for p in pieces if p.strip()]

    return _char_split(content, chunk_size, chunk_overlap)


def _char_split(text: str, chunk_size: int, chunk_overlap: int) -> list:
    """按固定字符数切分,带重叠窗口(兜底路径,这也是 overlap 唯一生效的地方)。"""
    if len(text) <= chunk_size:
        return [text]
    out = []
    start = 0
    step = max(1, chunk_size - chunk_overlap)
    while start < len(text):
        out.append(text[start:start + chunk_size].strip())
        start += step
        if len(text) - start < chunk_size // 3:
            if start < len(text):
                out.append(text[start:].strip())
            break
    return [c for c in out if c.strip()]


def _min_index_len() -> int:
    """入库下限(见 config.CHUNK_MIN_INDEX_LEN)。"""
    try:
        return int(getattr(config, "CHUNK_MIN_INDEX_LEN", 0) or 0)
    except (TypeError, ValueError):
        return 0


def indexable_chunks(annotated: list) -> list:
    """
    返回 [(原始下标, 块), ...]，过滤掉低于入库下限的块。

    切分与入库在这里分家:切分结果必须完整(引言块也是块),但只剩标题行、
    没有任何可用信息的块不该进向量库 —— 它们无法作为医学依据,却会因为
    短文本余弦虚高抢占 Top-K。下标保持原始序号,doc_id 因此可稳定溯源。
    """
    floor = _min_index_len()
    return [(i, c) for i, c in enumerate(annotated)
            if len((c.get("text") or "").strip()) >= floor]


def _split_text(text: str, chunk_size: int = None, chunk_overlap: int = None) -> list:
    """
    将文本分块(对外保持原有的 list[str] 契约)。

    默认走 CHUNK_STRATEGY=heading(按 ## 主题切分);
    置为 legacy 则回退到旧的装箱实现。需要主题标注请用 _split_text_annotated。
    """
    chunk_size = chunk_size or config.CHUNK_SIZE
    chunk_overlap = chunk_overlap or config.CHUNK_OVERLAP

    if getattr(config, "CHUNK_STRATEGY", "heading") != "heading":
        chunks = _split_text_legacy(text, chunk_size, chunk_overlap)
    else:
        chunks = [c["text"] for c in _split_text_annotated(text, chunk_size, chunk_overlap)]

    logger.debug(f"文本分块完成，总长 {len(text or '')} 字符，分为 {len(chunks)} 块")
    return chunks


def _extract_text_from_pdf(filepath: str) -> str:
    """
    从 PDF 文件中提取文本
    优先使用 PyMuPDF (fitz)，其次使用 pdfplumber，最后使用 PyPDF2
    """
    # 方法1: PyMuPDF (fitz)
    try:
        import fitz
        doc = fitz.open(filepath)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        if text.strip():
            return text
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"PyMuPDF 提取 PDF 失败: {e}")

    # 方法2: pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            if text.strip():
                return text
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"pdfplumber 提取 PDF 失败: {e}")

    # 方法3: PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        if text.strip():
            return text
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"PyPDF2 提取 PDF 失败: {e}")

    logger.warning(f"无法提取 PDF 文本（缺少 PDF 库），请安装: pip install PyMuPDF 或 pip install pdfplumber")
    return ""


def add_documents(directory: str):
    """
    从目录读取文档并添加到知识库
    支持 .txt、.md 和 .pdf 文件
    """
    collection = get_collection()

    if not os.path.isdir(directory):
        logger.error(f"文档目录不存在: {directory}")
        return

    supported_extensions = {".txt", ".md", ".pdf"}
    total_chunks = 0
    file_count = 0

    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if not os.path.isfile(filepath):
            continue

        ext = os.path.splitext(filename)[1].lower()
        if ext not in supported_extensions:
            logger.debug(f"跳过不支持的文件类型: {filename}")
            continue

        try:
            if ext == ".pdf":
                content = _extract_text_from_pdf(filepath)
                if not content.strip():
                    logger.warning(f"PDF 文件提取为空，跳过: {filename}")
                    continue
            else:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()

            if not content.strip():
                logger.warning(f"文件为空，跳过: {filename}")
                continue

            # 分块(带 ## 主题标注)
            annotated = _split_text_annotated(content)
            if not annotated:
                logger.warning(f"文件切分为空，跳过: {filename}")
                continue

            # 入库前过滤掉纯标题块,但保留原始下标,使 doc_id 与切分结果一一对应
            picked = indexable_chunks(annotated)
            skipped = len(annotated) - len(picked)
            if skipped:
                logger.info(f"{filename}: {skipped} 个块低于入库下限"
                            f"({_min_index_len()} 字)，已跳过（切分结果仍保留）")
            chunks = [c["text"] for _, c in picked]

            # 为每个块生成唯一 ID 和元数据(下标用原始的 i,编号不会因过滤而错位)
            ids = [f"{filename}_chunk_{i}" for i, _ in picked]
            # doc_id 一并写进元数据:检索侧 include 取不到 ids(ChromaDB 会抛错),
            # 只能从元数据反推,这里显式落一份,保证以后改主键格式也不会丢溯源
            metadatas = [
                {
                    "source": filename,
                    "chunk_index": i,
                    "file_type": ext.lstrip("."),
                    "doc_id": f"{filename}_chunk_{i}",
                    # 所属 ## 主题(引言块为空串)。有了它,溯源能精确到章节,
                    # 检索结果也能显示"出自哪一节",而不只是"出自哪个文件"。
                    "section": (item.get("section") or ""),
                    "part": item.get("part", 1),
                    "total_parts": item.get("total_parts", 1),
                }
                for i, item in picked
            ]

            # 添加到 ChromaDB
            collection.upsert(
                ids=ids,
                documents=chunks,
                metadatas=metadatas
            )

            total_chunks += len(chunks)
            file_count += 1
            logger.info(f"已处理文件: {filename}，生成 {len(chunks)} 个文档块")

        except Exception as e:
            logger.error(f"处理文件 {filename} 失败: {e}")
            continue

    logger.info(f"知识库文档添加完成，共处理 {file_count} 个文件，生成 {total_chunks} 个文档块")


def _try_load_local_index():
    """
    尝试加载 TF-IDF 本地索引（init_knowledge_local.py 生成的）
    当 ChromaDB 为空但本地索引存在时使用
    Returns: (documents, vectorizer, tfidf_matrix) 或 None
    """
    try:
        import pickle
        local_index_dir = os.path.join(os.path.dirname(config.CHROMA_PATH), "knowledge_index")
        doc_path = os.path.join(local_index_dir, "documents.json")
        index_path = os.path.join(local_index_dir, "tfidf_index.pkl")

        if not os.path.exists(doc_path) or not os.path.exists(index_path):
            return None

        with open(doc_path, "r", encoding="utf-8") as f:
            documents = json.load(f)

        with open(index_path, "rb") as f:
            index_data = pickle.load(f)

        logger.info(f"已加载本地 TF-IDF 索引，{len(documents)} 条文档片段")
        return documents, index_data["vectorizer"], index_data["tfidf_matrix"]

    except Exception as e:
        logger.debug(f"加载本地索引失败: {e}")
        return None


# 全局本地索引缓存
_local_index_cache = None


def _search_local_index(query: str, top_k: int = 3, relevance_threshold: float = 0.15) -> list:
    """
    使用本地 TF-IDF 索引搜索（Ollama 不可用时的 fallback）
    """
    global _local_index_cache

    if _local_index_cache is None:
        result = _try_load_local_index()
        if result is None:
            return []
        _local_index_cache = result

    documents, vectorizer, tfidf_matrix = _local_index_cache

    try:
        from sklearn.metrics.pairwise import cosine_similarity
        query_vec = vectorizer.transform([query])
        scores = cosine_similarity(query_vec, tfidf_matrix).flatten()

        # 获取排序后的索引
        sorted_indices = scores.argsort()[::-1]

        results = []
        for idx in sorted_indices:
            score = float(scores[idx])
            if score < relevance_threshold:
                break
            results.append({
                "text": documents[idx]["text"],
                "source": documents[idx]["source"],
                "distance": 1 - score,  # 转换为 distance 格式
                "relevance_score": round(score, 4),
                # 溯源标识(与 ChromaDB 路径字段对齐):本地索引无独立主键,
                # 用「索引名+序号」构造稳定可复现的 id,便于历史回放定位来源
                "id": f"__local_index__#{idx}",
                "chunk_index": idx,
            })
            if len(results) >= top_k:
                break

        return results

    except Exception as e:
        logger.error(f"本地索引搜索失败: {e}")
        return []


def _derive_doc_id(metadata: dict) -> str:
    """
    从元数据反推 Chroma 主键,替代 include=["ids"](ChromaDB 当前版本会因此抛错)。

    入库约定见 add_documents:主键 = f"{文件名}_chunk_{i}",
    元数据里的 source + chunk_index 与之一一对应,
    所以存量 collection 不重新导入也能拿到可回溯的片段标识。
    """
    meta = metadata or {}
    src = meta.get("source")
    ci = meta.get("chunk_index")
    if src is not None and ci is not None:
        return f"{src}_chunk_{ci}"
    # 新写入路径会在元数据里直接落下 doc_id(优先级最高)
    return str(meta.get("doc_id") or "")


def search(query: str, top_k: int = None, relevance_threshold: float = None) -> list:
    """
    语义搜索知识库，带相关性阈值过滤
    Args:
        query: 查询文本
        top_k: 返回最相关的 top_k 条结果
        relevance_threshold: 相关性阈值（cosine distance），大于此值的结果被过滤。
                              默认使用模块常量 RELEVANCE_THRESHOLD=0.6
    Returns:
        搜索结果列表，每项包含 text、source、distance、relevance_score
    """
    top_k = top_k or config.SEARCH_TOP_K
    threshold = relevance_threshold if relevance_threshold is not None else RELEVANCE_THRESHOLD
    collection = get_collection()

    try:
        count = collection.count()
        if count == 0:
            # ChromaDB 为空，尝试使用本地 TF-IDF 索引
            logger.info(f"ChromaDB 为空，尝试使用本地 TF-IDF 索引搜索 '{query}'")
            local_results = _search_local_index(query, top_k=top_k, relevance_threshold=0.05)
            if local_results:
                logger.info(f"本地索引搜索 '{query}'，返回 {len(local_results)} 条结果")
                return local_results
            logger.info(f"知识库搜索 '{query}' 无结果")
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(top_k * 2, count),  # 多取一些，阈值过滤后可能不足 top_k
            # 注意:include 里加 "ids" 会让 ChromaDB 直接抛
            # "Expected include item to be one of documents/embeddings/metadatas/
            #  distances/uris/data",整个检索被异常吞掉、溯源全丢。
            # 改为从元数据按入库约定反推主键(见 _derive_doc_id),存量 collection 无需重导。
            include=["documents", "metadatas", "distances"]
        )

        if not results or not results["documents"] or not results["documents"][0]:
            logger.info(f"知识库搜索 '{query}' 无结果")
            return []

        # 整理结果格式 + 相关性阈值过滤
        search_results = []
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 1.0
            
            # cosine distance 越小越相似，超过阈值则过滤
            if distance > threshold:
                continue
            
            # 转换为相似度分数 (1 - distance)，1=完全相同，0=无关联
            relevance_score = round(1 - distance, 4)
            
            search_results.append({
                "text": doc,
                "source": metadata.get("source", "unknown"),
                "distance": distance,
                "relevance_score": relevance_score,
                # ── 溯源字段(纯新增,旧调用方不受影响) ──
                "id": _derive_doc_id(metadata),                    # 稳定片段主键,如 消化系统疾病.md_chunk_12
                "chunk_index": metadata.get("chunk_index"),        # 文件内片段序号
                "metadata": metadata,                              # 透传原始元数据,便于将来加标题/页码
            })

        # 按相关度降序排列
        search_results.sort(key=lambda x: x["relevance_score"], reverse=True)

        # 截断到 top_k
        search_results = search_results[:top_k]

        logger.info(f"知识库搜索 '{query}'，返回 {len(search_results)} 条结果（阈值={threshold}）")
        return search_results

    except Exception as e:
        logger.error(f"知识库搜索失败: {e}")
        return []


def search_for_consultation(symptoms: str, chief_complaint: str = "", top_k: int = 3,
                            return_raw: bool = False) -> Union[str, list]:
    """
    为问诊流程检索知识库，返回格式化的参考文本
    供 consultation.py 各阶段调用
    Args:
        symptoms: 症状描述
        chief_complaint: 主诉（可选，用于组合查询）
        top_k: 返回结果数
        return_raw: True 时返回结构化结果列表(保留 id/chunk_index/metadata 供溯源),
                    False(默认)保持原有「返回格式字符串」行为,保证旧调用方零影响
    Returns:
        默认返回格式化的知识库参考文本(无结果为空字符串);
        return_raw=True 时返回 search() 的原始结果列表
    """
    # 组合查询：主诉 + 症状
    query_parts = []
    if chief_complaint:
        query_parts.append(chief_complaint)
    if symptoms:
        query_parts.append(symptoms)
    query = " ".join(query_parts) if query_parts else symptoms

    if not query.strip():
        return [] if return_raw else ""

    results = search(query, top_k=top_k)
    if not results:
        return [] if return_raw else ""
    if return_raw:
        return results

    references = []
    for i, result in enumerate(results, 1):
        references.append(
            f"[参考{i}] (来源: {result['source']}, 相关度: {result['relevance_score']})\n{result['text']}"
        )

    return "\n\n".join(references)

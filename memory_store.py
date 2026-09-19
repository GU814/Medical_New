"""
长记忆存储模块 - 医学问诊智能体
将问诊对话的关键片段与会话摘要写入独立的 ChromaDB 集合(consultation_memory),
跨会话按语义检索既往对话记忆,注入问诊/直接问答的上下文。

设计要点:
- 复用 knowledge_base 的 Chroma 客户端与嵌入函数(同库不同集合),零新增依赖
- 按 user_id 隔离作用域(桌面模式 user_id=0 全局共享,小程序模式每用户独立)
- 写入两类记忆:
  * turn   : 每轮对话的「患者-医生」片段(写入前剥离患者姓名)
  * episode: 问诊完成时的会话摘要(主诉/现病史/既往史/系统回顾要点)
- 检索时排除当前会话(其内容已在滑动窗口内),按 cosine 距离阈值过滤
- 所有操作异常安全:记忆功能故障只记日志,绝不阻断问诊主流程

安全说明(明文折中):
向量检索必须在明文上计算嵌入,因此本集合内容为明文存储(与医学知识库一致)。
写入前会把患者姓名替换为「患者」以降低身份暴露面;若需强加密合规,
应改用「密文+SQL 精确查询」方案(牺牲语义检索能力),见项目分析报告第五章。
"""

import logging
from datetime import datetime

import config
import knowledge_base

logger = logging.getLogger(__name__)

# 长记忆集合名(与医学知识库 medical_knowledge 分离,检索策略与数据归属不同)
MEMORY_COLLECTION_NAME = "consultation_memory"

# cosine distance 阈值:大于此值的结果被过滤(越小越相似,0=完全相同)
# 略宽于知识库的 0.6,因为口语化对话的语义匹配更模糊
MEMORY_RELEVANCE_THRESHOLD = 0.62

# 全局集合句柄(懒加载)
_collection = None


def _get_collection():
    """获取长记忆集合(懒加载;复用 knowledge_base 的客户端与嵌入函数)"""
    global _collection
    if _collection is not None:
        return _collection
    try:
        client = knowledge_base.get_chroma_client()
        _collection = client.get_or_create_collection(
            name=MEMORY_COLLECTION_NAME,
            embedding_function=knowledge_base.get_embedding_function(),
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"长记忆集合已初始化: {MEMORY_COLLECTION_NAME},当前 { _collection.count() } 条记忆")
    except Exception as e:
        logger.warning(f"长记忆集合初始化失败(记忆功能暂不可用): {e}")
        _collection = None
    return _collection


def _sanitize(text: str, patient_name: str = "") -> str:
    """
    写入前脱敏:把患者姓名替换为「患者」。
    向量库为明文存储,剥离直接标识是身份暴露面的最小化折中。
    """
    if not text:
        return ""
    if patient_name and len(patient_name.strip()) >= 2:
        text = text.replace(patient_name.strip(), "患者")
    return text


def remember_turn(user_id: int, session_id: str, stage: int,
                 user_text: str, assistant_text: str,
                 patient_name: str = "", turn_index: int = 0) -> bool:
    """
    写入一轮对话记忆(「患者: .../医生: ...」片段)。
    Args:
        turn_index: 轮次序号,用于构造幂等 ID(同一轮重写覆盖而非追加)
    Returns: 是否写入成功(内容过短/异常返回 False)
    """
    coll = _get_collection()
    if coll is None:
        return False

    u = _sanitize(user_text, patient_name).strip()
    a = _sanitize(assistant_text, patient_name).strip()
    parts = []
    if u:
        parts.append(f"患者: {u[:500]}")
    if a:
        parts.append(f"医生: {a[:300]}")
    content = "\n".join(parts)

    if len(content) < config.MEMORY_MIN_LEN:
        return False

    doc_id = f"{session_id}_t{turn_index}"
    try:
        coll.upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[{
                "user_id": int(user_id),
                "session_id": str(session_id),
                "stage": int(stage),
                "kind": "turn",
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }],
        )
        return True
    except Exception as e:
        logger.warning(f"写入对话记忆失败: {e}")
        return False


def remember_episode(user_id: int, session_id: str, patient_data: dict,
                     patient_name: str = "") -> bool:
    """
    问诊完成时写入会话级摘要记忆(主诉/现病史/既往史/系统回顾要点)。
    这是跨会话召回价值最高的记忆形态:「上次同样症状时医生问了什么、结论是什么」。
    """
    coll = _get_collection()
    if coll is None:
        return False

    def _field(key: str, limit: int) -> str:
        v = _sanitize(str(patient_data.get(key, "") or ""), patient_name).strip()
        return v[:limit]

    parts = []
    chief = _field("chief_complaint", 200)
    if chief:
        parts.append(f"主诉: {chief}")
    illness = _field("present_illness", 400)
    if illness:
        parts.append(f"现病史: {illness}")
    past = _field("past_history", 200)
    if past:
        parts.append(f"既往史: {past}")
    review = _field("system_review", 200)
    if review:
        parts.append(f"系统回顾: {review}")
    diag = _field("diagnosis", 200)
    if diag:
        parts.append(f"诊断: {diag}")

    if not parts:
        return False

    content = "问诊摘要 | " + "; ".join(parts)
    doc_id = f"{session_id}_episode"
    try:
        coll.upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[{
                "user_id": int(user_id),
                "session_id": str(session_id),
                "kind": "episode",
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }],
        )
        return True
    except Exception as e:
        logger.warning(f"写入会话记忆失败: {e}")
        return False


def search_memories(user_id: int, query: str, top_k: int = None,
                    exclude_session_id: str = None) -> list:
    """
    语义检索该用户的历史记忆(按 user_id 作用域隔离)。
    Args:
        exclude_session_id: 排除当前会话(其内容已在对话窗口内,避免自我重复)
    Returns: [{"text", "kind", "ts", "stage", "distance", "relevance_score"}]
    """
    coll = _get_collection()
    if coll is None:
        return []

    top_k = top_k or config.MEMORY_TOP_K
    if not query or not query.strip():
        return []

    try:
        count = coll.count()
        if count == 0:
            return []

        # where 过滤:user_id 作用域 + 排除当前会话
        if exclude_session_id:
            where = {"$and": [
                {"user_id": int(user_id)},
                {"session_id": {"$ne": str(exclude_session_id)}},
            ]}
        else:
            where = {"user_id": int(user_id)}

        results = coll.query(
            query_texts=[query],
            n_results=min(top_k * 2, count),  # 多取一倍,阈值过滤后可能不足
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        if not results or not results["documents"] or not results["documents"][0]:
            return []

        memories = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 1.0
            if distance > MEMORY_RELEVANCE_THRESHOLD:
                continue
            memories.append({
                "text": doc,
                "kind": meta.get("kind", "turn"),
                "ts": meta.get("ts", ""),
                "stage": meta.get("stage"),
                "distance": distance,
                "relevance_score": round(1 - distance, 4),
            })

        memories.sort(key=lambda x: x["relevance_score"], reverse=True)
        return memories[:top_k]

    except Exception as e:
        logger.warning(f"记忆检索失败: {e}")
        return []


def count_memories() -> int:
    """当前记忆条数(诊断用)"""
    coll = _get_collection()
    if coll is None:
        return 0
    try:
        return coll.count()
    except Exception:
        return 0

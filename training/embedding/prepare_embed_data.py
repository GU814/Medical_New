"""
嵌入模型训练数据 - 医学句对生成（query, doc）

流程：
  1) 抽取：读取项目 data/knowledge 下的 .md/.txt，按段落切块
  2) 生成：调用本地 Ollama，把每个块改写成 (用户提问, 资料原文) 句对
  3) 产出：embed_pairs.jsonl，供 train_embed.py 做对比学习

说明：医学检索里 doc 用资料原文、query 用“患者会怎么问”，让嵌入模型学会
      把用户口语化提问与相关医学资料拉近。

依赖：本地 Ollama 已在运行
用法：
  python prepare_embed_data.py
"""
import os
import json
import glob
import time
from openai import OpenAI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # medical_bot/
KNOWLEDGE_DIR = os.path.join(ROOT, "data", "knowledge")
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:11434/v1")
GEN_MODEL = os.environ.get("GEN_MODEL", "deepseek-r1:8b")

client = OpenAI(api_key="ollama", base_url=API_BASE)

SYS = (
    "你是医学检索数据构造器。给定一段医学资料，请输出 1 个真实的患者式提问(query)"
    "以及该资料作为答案(doc)。query 要口语化、像普通人在问诊时会问的；doc 直接取自资料要点。"
    "只输出 JSON，格式：{\"query\":\"...\",\"doc\":\"...\"}"
)


def read_chunks():
    chunks = []
    if not os.path.isdir(KNOWLEDGE_DIR):
        print(f"[警告] 知识库目录不存在: {KNOWLEDGE_DIR}")
        return chunks
    for p in sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, "*"))):
        if not os.path.isfile(p) or not p.lower().endswith((".md", ".txt")):
            continue
        try:
            text = open(p, encoding="utf-8").read()
        except Exception:
            continue
        for sec in text.split("\n## "):
            sec = sec.strip()
            if len(sec) < 80:
                continue
            chunks.append(sec[:1200])
    print(f"[信息] 切出 {len(chunks)} 个文本块")
    return chunks


def _clean_json(raw: str):
    if "```json" in raw:
        return raw.split("```json")[1].split("```")[0].strip()
    if "```" in raw:
        return raw.split("```")[1].split("```")[0].strip()
    return raw.strip()


def main():
    chunks = read_chunks()
    pairs = []
    for i, chunk in enumerate(chunks):
        try:
            r = client.chat.completions.create(
                model=GEN_MODEL,
                messages=[
                    {"role": "system", "content": SYS},
                    {"role": "user", "content": chunk},
                ],
                temperature=0.7,
                max_tokens=600,
            )
            raw = _clean_json(r.choices[0].message.content or "")
            d = json.loads(raw)
            q, doc = d.get("query", "").strip(), d.get("doc", "").strip()
            if q and doc:
                pairs.append({"query": q, "doc": doc})
        except Exception as e:
            print(f"[生成失败] {e}")
        if i % 10 == 0:
            print(f"  处理中: {i}/{len(chunks)}，已得 {len(pairs)} 对")
        time.sleep(0.2)

    with open("embed_pairs.jsonl", "w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"\n[完成] 生成 {len(pairs)} 对 -> embed_pairs.jsonl")


if __name__ == "__main__":
    main()

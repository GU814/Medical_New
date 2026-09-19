"""
对话/问诊训练数据 - 混合数据管线（生成 + 抽取 + 校正）

流程：
  1) 抽取：读取项目 data/knowledge 下的 .md/.txt 医学文档，按段落切块
  2) 生成：调用本地 Ollama（默认 deepseek-r1:8b）把每个块改写成一段多轮问诊对话
  3) 校正：生成结果写入 data_generated/generated.jsonl，并复制一份 REVIEW_me.jsonl 供人工校正
  4) 定稿：人工改完 REVIEW_me.jsonl 后，重命名/覆盖为 train.jsonl 即用于训练

依赖：本地 Ollama 已在运行（项目默认 http://localhost:11434/v1）
用法：
  python prepare_data.py
环境变量：
  API_BASE_URL  默认 http://localhost:11434/v1
  GEN_MODEL     默认 deepseek-r1:8b（也可换任意会中文的生成模型）
"""
import os
import json
import glob
import time
import shutil
from openai import OpenAI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # medical_bot/
KNOWLEDGE_DIR = os.path.join(ROOT, "data", "knowledge")
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:11434/v1")
GEN_MODEL = os.environ.get("GEN_MODEL", "deepseek-r1:8b")

client = OpenAI(api_key="ollama", base_url=API_BASE)

GEN_SYS = (
    "你是医学数据标注员。给定一段医学资料，请生成 1 条贴近真实场景的中文问诊多轮对话，"
    "让助手以专业、温和的医生口吻，循序渐进地收集患者信息（一次只问 1-2 个问题）。"
    "对话要体现：基本信息→主诉→现病史→既往史→系统回顾 的推进感。"
    "只输出 JSON，不要任何解释，格式："
    '{"messages":['
    '{"role":"system","content":"你是一位专业的医学问诊AI助手..."},'
    '{"role":"user","content":"患者的话"},'
    '{"role":"assistant","content":"医生的提问"}, ...]}'
)


def read_chunks():
    """读取知识库文档并按段落切块（简单启发式）。"""
    chunks = []
    if not os.path.isdir(KNOWLEDGE_DIR):
        print(f"[警告] 知识库目录不存在: {KNOWLEDGE_DIR}")
        return chunks
    for p in sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, "*"))):
        if not os.path.isfile(p):
            continue
        if not p.lower().endswith((".md", ".txt")):
            continue
        try:
            text = open(p, encoding="utf-8").read()
        except Exception as e:
            print(f"[跳过] 读取失败 {p}: {e}")
            continue
        # 按 markdown 二级标题切分，单段过长再截断
        for sec in text.split("\n## "):
            sec = sec.strip()
            if len(sec) < 80:
                continue
            chunks.append(sec[:1500])
    print(f"[信息] 从 {KNOWLEDGE_DIR} 切出 {len(chunks)} 个文本块")
    return chunks


def _clean_json(raw: str):
    if "```json" in raw:
        return raw.split("```json")[1].split("```")[0].strip()
    if "```" in raw:
        return raw.split("```")[1].split("```")[0].strip()
    return raw.strip()


def gen_from_chunk(chunk: str):
    try:
        r = client.chat.completions.create(
            model=GEN_MODEL,
            messages=[
                {"role": "system", "content": GEN_SYS},
                {"role": "user", "content": chunk},
            ],
            temperature=0.8,
            max_tokens=1200,
        )
        raw = r.choices[0].message.content or ""
        raw = _clean_json(raw)
        return json.loads(raw)
    except Exception as e:
        print(f"[生成失败] {e}")
        return None


def main():
    chunks = read_chunks()
    out = []
    for i, chunk in enumerate(chunks):
        d = gen_from_chunk(chunk)
        if d and isinstance(d.get("messages"), list) and len(d["messages"]) >= 3:
            out.append(d)
        if i % 10 == 0:
            print(f"  处理中: {i}/{len(chunks)}，已得 {len(out)} 条")
        time.sleep(0.2)

    os.makedirs("data_generated", exist_ok=True)
    gen_path = os.path.join("data_generated", "generated.jsonl")
    with open(gen_path, "w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")

    # 校正副本：人工改这份，改完覆盖为 train.jsonl
    review_path = os.path.join("data_generated", "REVIEW_me.jsonl")
    shutil.copy(gen_path, review_path)

    print(f"\n[完成] 生成 {len(out)} 条 -> {gen_path}")
    print(f"[下一步] 人工校正 {review_path}（删掉不合格样本、修正医生提问）")
    print(f"         满意后执行: copy data_generated\\REVIEW_me.jsonl train.jsonl")


if __name__ == "__main__":
    main()

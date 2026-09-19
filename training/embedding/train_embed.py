"""
嵌入模型微调 - bge-small-zh 全参微调（8GB 显存可跑）

bge-small-zh 仅 24M 参数，全参微调即可；若想更大可用 bge-base-zh（仍需 8GB 内）。
用 MultipleNegativesRankingLoss 做对比学习：同一 batch 内，(query, doc) 为正对，
其它 doc 自动当负例。

输入：embed_pairs.jsonl（见 prepare_embed_data.py）
产出：./med-embed（sentence-transformers 模型）

用法：
  python train_embed.py
环境变量：EMBED_BASE 默认 BAAI/bge-small-zh；EMBED_OUT 默认 ./med-embed
"""
import os
import json
from torch.utils.data import DataLoader
from sentence_transformers import SentenceTransformer, InputExample, losses

EMBED_BASE = os.environ.get("EMBED_BASE", "BAAI/bge-small-zh")
EMBED_OUT = os.environ.get("EMBED_OUT", "./med-embed")
DATA = "embed_pairs.jsonl"

print(f"加载嵌入基座: {EMBED_BASE}")
model = SentenceTransformer(EMBED_BASE)

examples = []
with open(DATA, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        examples.append(InputExample(texts=[o["query"], o["doc"]]))
print(f"样本数: {len(examples)}")

train_dataloader = DataLoader(examples, batch_size=16, shuffle=True)
# bge 系列推荐用 MultipleNegativesRankingLoss
train_loss = losses.MultipleNegativesRankingLoss(model)

print("开始微调...")
model.fit(
    [(train_dataloader, train_loss)],
    epochs=3,
    warmup_steps=max(10, len(examples) // 16 // 10),
)
model.save(EMBED_OUT)
print(f"嵌入模型已保存至: {EMBED_OUT}")
print("下一步：python serve_embed.py  启动 OpenAI 兼容嵌入服务")

"""
自定义嵌入模型服务 - OpenAI 兼容接口（/v1/embeddings）

项目 knowledge_base.py 通过 OpenAIEmbeddingFunction 调用 embedding，只要把
config.EMBEDDING_API_BASE_URL 指向本服务即可用自训嵌入模型。

默认地址：http://127.0.0.1:8002/v1
用法：
  python serve_embed.py
环境变量：
  EMBED_MODEL  默认 ./med-embed（train_embed.py 产出）
  EMBED_PORT   默认 8002

注意：服务需在启动 medical_bot 之前先跑起来；可加进 run_all.bat 或设为开机启动。
"""
import os
from fastapi import FastAPI, Request
from sentence_transformers import SentenceTransformer
import uvicorn
import numpy as np

MODEL = os.environ.get("EMBED_MODEL", "./med-embed")
PORT = int(os.environ.get("EMBED_PORT", "8002"))

print(f"加载嵌入模型: {MODEL}")
model = SentenceTransformer(MODEL)
dim = model.get_sentence_embedding_dimension()
print(f"嵌入维度: {dim}（请把 config.EMBEDDING_DIMENSION 设为该值）")

app = FastAPI()


@app.post("/v1/embeddings")
async def embeddings(req: Request):
    body = await req.json()
    texts = body.get("input", [])
    if isinstance(texts, str):
        texts = [texts]
    # bge 系列对 query 加前缀效果更好；这里对单句统一编码
    emb = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    data = [
        {"object": "embedding", "index": i, "embedding": emb[i].tolist()}
        for i in range(len(emb))
    ]
    return {
        "object": "list",
        "data": data,
        "model": body.get("model", "med-embed"),
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


@app.get("/health")
async def health():
    return {"status": "ok", "dimension": dim}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT)

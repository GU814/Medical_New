# 自训模型训练包（对话模型 + 嵌入模型）

针对你的硬件（**8GB 显存**）设计的完整训练脚手架，把两个模型都做出来并接入 `medical_bot`。

## 目录结构
```
training/
├── README.md                  # 本说明
├── INTEGRATE.md               # 接入项目的步骤
├── run_all.bat                # 一键执行引导（分步、带暂停）
├── dialogue/                  # 对话/问诊生成模型
│   ├── requirements.txt
│   ├── prepare_data.py        # 混合数据：抽取 data/knowledge + 大模型生成 + 校正
│   ├── train_qlora.py         # Qwen2.5-3B + QLoRA(4bit)
│   ├── merge_export.py        # 合并 LoRA -> HF
│   └── Modelfile              # Ollama 注册
└── embedding/                 # 知识库检索嵌入模型
    ├── requirements.txt
    ├── prepare_embed_data.py  # 生成 (query, doc) 句对
    ├── train_embed.py         # bge-small-zh 全参微调
    ├── serve_embed.py         # OpenAI 兼容嵌入服务
    └── Modelfile              # Ollama 注册（备选）
```

## 硬件前提
- 8GB 显存：对话模型用 **Qwen2.5-3B-Instruct + 4bit QLoRA**（单卡可跑）；嵌入模型用 **bge-small-zh**（24M，全参微调可跑）。
- 训练前请确认**本地 Ollama 已在运行**（项目默认 `http://localhost:11434/v1`），数据生成脚本会调用它。

## 快速开始
```bash
cd training
call run_all.bat        # 自动建 venv、装依赖、跑全流程（含人工校正暂停点）
```
或手动分步，详见 `INTEGRATE.md`。

## 数据流总览
1. `data/knowledge` 医学文档 → `prepare_data.py` → 大模型改写成问诊对话 → `train.jsonl`
2. `train.jsonl` → `train_qlora.py` → `med-lora` → `merge_export.py` → HF → GGUF → Ollama `med-consult`
3. `data/knowledge` 医学文档 → `prepare_embed_data.py` → (query,doc) 句对 → `train_embed.py` → `med-embed` → `serve_embed.py`
4. 改 `config.py`：`MODEL_NAME/CONSULT_MODEL_NAME/REPORT_MODEL_NAME=med-consult`，`EMBEDDING_MODEL=med-embed` + `EMBEDDING_API_BASE_URL=http://127.0.0.1:8002/v1` + `EMBEDDING_DIMENSION=512`
5. 删除 `data/chroma_db` 重建索引（嵌入维度变了必须重建）

## 注意事项
- 生成数据需要人工校正（`REVIEW_me.jsonl`），质量决定上限。
- 转 GGUF 需先 `git clone https://github.com/ggerganov/llama.cpp`，按 `merge_export.py` 末尾提示执行。
- 嵌入模型默认走 `serve_embed.py` 方案（最稳）；Ollama GGUF 方案兼容性较弱，见 `embedding/Modelfile`。

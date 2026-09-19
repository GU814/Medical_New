# 把自训模型接入 medical_bot

已完成训练、拿到 `med-consult`（对话）与 `med-embed`（嵌入）后，按下面做。

---

## 一、对话/问诊模型接入（Ollama）

1. 把 `merge_export.py` 产出的 GGUF（如 `med-q4_k_m.gguf`）放到 `training/dialogue/`。
2. 注册进 Ollama：
   ```bash
   cd training/dialogue
   ollama create med-consult -f Modelfile
   ollama list          # 确认 med-consult 存在
   ollama run med-consult "我最近头晕想吐"   # 本地试跑
   ```
3. 改 `config.py`（三处都指向你的模型，问诊/报告想分开就训两个分别填）：
   ```python
   MODEL_NAME = "med-consult"
   CONSULT_MODEL_NAME = "med-consult"   # 问诊/问答，低延迟
   REPORT_MODEL_NAME = "med-consult"    # 报告深度分析
   ```
4. 启动项目：`python main.py` 或 `start.bat`。日志出现 `模型: med-consult` 即生效。

> 对话模型接入**无需改任何业务代码**，项目通过 OpenAI 兼容接口（`http://localhost:11434/v1`）调用。

---

## 二、嵌入模型接入（知识库检索）

嵌入模型有两种挂载方式，二选一：

### 方式 A（推荐，最稳）：serve_embed.py 服务
1. 先启动嵌入服务（项目启动前先跑）：
   ```bash
   cd training/embedding
   python serve_embed.py        # 监听 http://127.0.0.1:8002/v1
   ```
   可用 `run_all.bat` 末尾自动起，或设为开机自启。
2. 改 `config.py`：
   ```python
   EMBEDDING_MODEL = "med-embed"
   EMBEDDING_API_BASE_URL = "http://127.0.0.1:8002/v1"   # 指向自训嵌入服务
   EMBEDDING_DIMENSION = 512                             # bge-small-zh 维度
   ```
   > `EMBEDDING_API_BASE_URL` 是本次新增的向后兼容变量，默认等于 `API_BASE_URL`，
   > 不填时完全保持原 Ollama 行为；已同步改 `knowledge_base.py` 使用该变量。

### 方式 B（备选）：Ollama GGUF 嵌入
若你能把 `med-embed` 导出成 GGUF（llama.cpp 对 BGE 架构支持有限，新手不推荐）：
```bash
cd training/embedding
ollama create med-embed -f Modelfile     # FROM ./med-embed.gguf
```
`config.py` 设 `EMBEDDING_MODEL="med-embed"`，`EMBEDDING_API_BASE_URL` 留默认（指向 Ollama），
`EMBEDDING_DIMENSION` 按实际维度填。

---

## 三、必须重建索引（关键坑）

嵌入维度一旦变化（默认 768 → 512），`data/chroma_db` 里旧向量全部失效：

```bash
# 关闭项目后执行
rmdir /s /q data\chroma_db
# 重新启动项目，main.py 的 lifespan 会自动把 data/knowledge 重新向量化
python main.py
```
日志看到 `知识库加载完成，当前 N 条文档片段` 即重建成功。

---

## 四、验证 checklist
- [ ] `ollama list` 含 `med-consult`
- [ ] `curl http://127.0.0.1:8002/health` 返回 `{"status":"ok","dimension":512}`
- [ ] 项目启动日志出现 `模型: med-consult`
- [ ] 网页对话：问诊按你数据风格提问、JSON 字段正常回填
- [ ] 知识库检索：问医学问题，回答引用的 `[参考]` 来源更贴合
- [ ] 对比微调前（deepseek-r1:8b + nomic-embed-text）的回答，确认能力已注入

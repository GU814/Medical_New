# 医学问诊智能体

一个基于 AI 的医学问诊智能体，通过多轮对话系统性地收集患者健康信息，并生成标准医学大病历报告。

## ✨ 功能特点

- 🏥 **5阶段智能问诊**：基本信息 → 主诉现病史 → 既往史 → 系统回顾 → 生成报告
- 📋 **标准大病历报告**：严格遵循大病历格式，问过什么写什么
- 🔍 **知识库检索**：基于 ChromaDB 的语义搜索，检索相关医学知识辅助分析
- 📊 **数据库管理**：SQLite 存储患者记录，支持历史查询
- 🚨 **紧急症状识别**：识别胸痛、呼吸困难等紧急症状，立即提醒就医
- 🔌 **多模型支持**：支持 DeepSeek API / Ollama 本地模型 / 任何 OpenAI 兼容 API

## 🛠️ 技术栈

| 组件 | 技术选型 |
|------|---------|
| Web 框架 | FastAPI |
| 前端 | HTML + CSS + JavaScript |
| 数据库 | SQLite（零配置） |
| 向量数据库 | ChromaDB（开箱即用） |
| LLM | OpenAI 兼容 API（DeepSeek/Ollama） |
| Embedding | OpenAI 兼容 API |

## 📦 安装

### 1. 克隆项目

```bash
cd medical_bot
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

> **注意**：ChromaDB 安装可能需要较长时间，请耐心等待。如果安装失败，请确保系统已安装 C++ 编译工具。

### 3. 配置

#### 方式一：使用 DeepSeek API（推荐）

```bash
# 设置 API Key
export API_KEY="your-deepseek-api-key"

# 其他配置使用默认值即可
# API_BASE_URL 默认: https://api.deepseek.com
# MODEL_NAME 默认: deepseek-chat
# EMBEDDING_MODEL 默认: text-embedding-v3
```

获取 DeepSeek API Key：访问 [https://platform.deepseek.com/](https://platform.deepseek.com/) 注册并创建 API Key。

#### 方式二：使用 Ollama 本地模型

```bash
# 1. 安装 Ollama：https://ollama.ai/
# 2. 拉取模型
ollama pull deepseek-r1:7b
ollama pull nomic-embed-text

# 3. 设置环境变量
export API_BASE_URL="http://localhost:11434/v1"
export API_KEY=""
export MODEL_NAME="deepseek-r1:7b"
export EMBEDDING_MODEL="nomic-embed-text"
export EMBEDDING_DIMENSION="768"
```

#### 方式三：使用其他 OpenAI 兼容 API

```bash
export API_BASE_URL="https://your-api-endpoint"
export API_KEY="your-api-key"
export MODEL_NAME="your-model-name"
export EMBEDDING_MODEL="your-embedding-model"
```

### 4. 初始化

```bash
# 初始化数据库（可选：加 --with-test-data 插入测试数据）
python init_db.py --with-test-data

# 初始化知识库（读取 data/knowledge/ 目录下的文档）
python init_knowledge.py
```

## 🚀 运行

```bash
python main.py
```

启动后访问 [http://localhost:8000](http://localhost:8000) 即可使用。

## 📁 项目结构

```
medical_bot/
├── main.py                  # FastAPI 主程序，启动入口
├── config.py                # 配置文件（API Key、模型地址等）
├── requirements.txt         # 依赖包
├── database.py              # 数据库操作（SQLite）
├── knowledge_base.py        # 知识库操作（ChromaDB）
├── llm_client.py            # LLM 调用封装
├── consultation.py          # 问诊逻辑（5阶段状态机）
├── report_generator.py      # 报告生成
├── init_db.py               # 数据库初始化脚本
├── init_knowledge.py        # 知识库初始化脚本
├── static/
│   ├── index.html           # 聊天界面
│   ├── style.css            # 样式
│   └── chat.js              # 前端交互逻辑
├── data/
│   ├── medical.db           # SQLite 数据库文件（自动创建）
│   ├── chroma_db/           # ChromaDB 持久化目录（自动创建）
│   └── knowledge/           # 知识库文档存放目录
│       └── example.md       # 示例医学知识文档
└── README.md                # 使用说明
```

## 🔧 配置项

所有配置项均可通过环境变量覆盖：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `API_BASE_URL` | `https://api.deepseek.com` | LLM API 地址 |
| `API_KEY` | 空 | API Key |
| `MODEL_NAME` | `deepseek-chat` | 对话模型名称 |
| `EMBEDDING_MODEL` | `text-embedding-v3` | Embedding 模型名称 |
| `EMBEDDING_DIMENSION` | `1024` | Embedding 维度 |
| `MAX_TOKENS` | `4096` | 最大生成 tokens |
| `DEFAULT_TEMPERATURE` | `0.3` | 默认温度 |
| `DB_PATH` | `data/medical.db` | SQLite 数据库路径 |
| `CHROMA_PATH` | `data/chroma_db` | ChromaDB 存储路径 |
| `KNOWLEDGE_DIR` | `data/knowledge` | 知识库文档目录 |
| `CHUNK_SIZE` | `500` | 文档分块大小（字符） |
| `CHUNK_OVERLAP` | `100` | 文档分块重叠（字符） |
| `SERVER_PORT` | `8000` | 服务端口 |
| `SERVER_HOST` | `0.0.0.0` | 服务主机 |
| `LLM_TIMEOUT` | `120` | LLM 请求超时（秒） |
| `LLM_MAX_RETRIES` | `3` | LLM 重试次数 |

## 📖 问诊流程

1. **阶段1 - 基本信息**：收集姓名、性别、年龄、初步主诉
2. **阶段2 - 主诉现病史**：深入了解症状部位、性质、诱因、伴随症状等
3. **阶段3 - 既往史**：了解相关既往史、个人史、家族史
4. **阶段4 - 系统回顾**：针对相关系统做简要回顾
5. **阶段5 - 生成报告**：结合知识库参考和深度分析，生成大病历报告

## 📚 添加知识库文档

将 `.txt` 或 `.md` 格式的医学知识文档放入 `data/knowledge/` 目录，然后运行：

```bash
python init_knowledge.py
```

文档会自动分块（默认500字/块，重叠100字）并添加到 ChromaDB 向量数据库中。

## ⚠️ 免责声明

本系统由 AI 驱动，仅供学习和参考，**不能替代医生的面诊和正式诊断**。

- AI 分析结果可能存在偏差或遗漏
- 如有不适或症状加重，请及时前往正规医疗机构就诊
- 本系统不对因使用本报告而产生的任何后果承担责任

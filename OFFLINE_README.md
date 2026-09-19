# 医学问诊智能体 - 离线使用完整指南

## 📋 项目概述

这是一个基于 AI 的医学问诊系统，通过 5 阶段对话收集患者信息并生成标准医学报告。支持完全离线运行。

## 🚀 快速开始

### 方案一：一键启动（推荐）

1. **首次使用** - 设置离线环境：
   ```bash
   # 运行设置脚本
   python setup_offline.py
   # 或运行批处理文件
   setup_offline.bat
   ```

2. **日常使用** - 启动系统：
   ```bash
   # 启动医学问诊系统
   python main.py
   # 或运行批处理文件
   start.bat
   ```

3. **访问系统**：
   打开浏览器访问：http://localhost:8000

### 方案二：手动设置

#### 1. 安装 Ollama
- 下载：https://ollama.ai/download
- 安装并添加到系统 PATH
- 验证安装：`ollama --version`

#### 2. 下载模型
```bash
ollama pull deepseek-r1:8b
ollama pull nomic-embed-text
```

#### 3. 启动服务
```bash
ollama serve
```

#### 4. 运行系统
```bash
python main.py
```

## 📁 项目结构

```
medical_bot/
├── main.py                     # 主程序入口
├── setup_offline.py            # 离线环境设置脚本
├── config.py                   # 配置文件
├── consultation.py             # 问诊逻辑（5阶段状态机）
├── llm_client.py              # AI 客户端
├── knowledge_base.py          # 知识库管理
├── database.py                # 数据库操作
├── report_generator.py        # 报告生成
├── requirements.txt           # 依赖包
├── data/
│   ├── medical.db            # 患者数据库
│   ├── chroma_db/            # 知识库向量数据库
│   └── knowledge/            # 医学知识文档
├── static/
│   ├── index.html            # 前端界面
│   ├── style.css             # 样式文件
│   └── chat.js               # 前端交互
├── installer/                # Ollama 安装程序
├── models/                   # AI 模型文件
├── start.bat                 # Windows 启动脚本
├── setup_offline.bat         # Windows 设置脚本
├── OFFLINE_SETUP.md          # 离线设置详细指南
├── TROUBLESHOOTING.md        # 故障排除指南
└── README.md                 # 原始项目说明
```

## 🔧 配置说明

### 关键配置项（config.py）

```python
# AI 模型配置
API_BASE_URL = "http://localhost:11434/v1"  # Ollama 默认地址
MODEL_NAME = "deepseek-r1:8b"               # 对话模型
EMBEDDING_MODEL = "nomic-embed-text"       # 嵌入模型

# 性能配置
MAX_TOKENS = 4096                           # 最大输出长度
LLM_TIMEOUT = 120                           # 超时时间（秒）
DEFAULT_TEMPERATURE = 0.3                   # 温度参数

# 路径配置
DB_PATH = "data/medical.db"                 # 数据库路径
CHROMA_PATH = "data/chroma_db"              # 知识库路径
KNOWLEDGE_DIR = "data/knowledge"            # 知识文档目录
```

### 性能优化配置

对于低配置机器，建议修改：

```python
# 使用更小的模型
MODEL_NAME = "deepseek-r1:1.5b"  # 15亿参数（更快但精度略低）

# 增加超时时间
LLM_TIMEOUT = 300                # 5分钟

# 减少资源占用
MAX_TOKENS = 2048                # 减少输出长度
SEARCH_TOP_K = 3                 # 减少检索结果数量
```

## 📚 5阶段问诊流程

1. **基本信息收集** - 姓名、性别、年龄、主诉
2. **现病史详询** - 症状详情、时间、诱因等
3. **既往史询问** - 相关病史、个人史、家族史
4. **系统回顾** - 针对性系统检查
5. **报告生成** - 生成完整医学报告

## 🛠️ 离线环境要求

### 最低配置
- **操作系统**: Windows 7+ / Linux / macOS
- **内存**: 8GB RAM（推荐 16GB）
- **存储**: 10GB 可用空间
- **Python**: 3.8+

### 推荐配置
- **内存**: 16GB+ RAM
- **存储**: SSD 硬盘
- **CPU**: 4核以上

## 🚨 紧急功能

系统会自动检测以下紧急症状并提醒就医：
- 胸痛、胸闷
- 呼吸困难
- 意识丧失、昏迷
- 大出血
- 剧烈头痛
- 持续高热
- 抽搐、窒息
- 心脏骤停、休克

## 📊 数据管理

### 患者数据
- 存储位置：`data/medical.db`
- 格式：SQLite 数据库
- 包含：患者信息、问诊记录、诊断报告

### 知识库
- 存储位置：`data/chroma_db`
- 格式：ChromaDB 向量数据库
- 支持：语义搜索、相似病例检索

### 数据备份
```bash
# 备份患者数据
cp data/medical.db backup_medical_$(date +%Y%m%d).db

# 备份知识库
cp -r data/chroma_db/ backup_chroma_$(date +%Y%m%d)/
```

## 🔒 安全说明

- 所有数据本地存储，不上传云端
- AI 分析仅供参考，不能替代医生诊断
- 系统包含免责声明
- 紧急症状会自动提醒就医

## 🐛 常见问题

### Q: 启动时提示"无法连接到 AI 服务"
A: 运行 `python setup_offline.py` 设置离线环境

### Q: 模型下载很慢
A: 尝试使用更小的模型：`deepseek-r1:1.5b`

### Q: 内存不足
A: 1. 关闭其他程序 2. 使用更小模型 3. 增加虚拟内存

### Q: 端口被占用
A: 修改 config.py 中的 `SERVER_PORT` 配置

## 📞 技术支持

1. 查看 `TROUBLESHOOTING.md` 故障排除指南
2. 检查日志输出（控制台显示）
3. 确保 Ollama 服务正常运行
4. 验证模型是否正确下载

## 🔄 更新维护

### 更新知识库
```bash
python init_knowledge.py
```

### 更新数据库结构
```bash
python init_db.py
```

### 添加新的医学知识文档
1. 将 `.txt` 或 `.md` 文件放入 `data/knowledge/`
2. 运行：`python init_knowledge.py`

## 📝 免责声明

本系统仅供学习和参考使用：
- AI 分析结果可能存在偏差
- 不能替代医生的面诊和正式诊断
- 如有不适请及时就医
- 本系统不承担因使用产生的任何后果

---

**开始使用：**
1. 运行 `setup_offline.bat` 设置环境
2. 运行 `start.bat` 启动系统
3. 浏览器访问 http://localhost:8000

**遇到问题：**
- 查看 `TROUBLESHOOTING.md`
- 运行 `python setup_offline.py` 重新设置
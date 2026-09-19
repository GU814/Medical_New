# 离线使用设置指南

## 问题诊断

如果你在离线环境下使用医学问诊智能体时遇到"无法回答"的问题，通常是因为以下组件缺失：

1. **Ollama 未安装** - 本地 AI 推理引擎
2. **模型文件缺失** - 需要下载 AI 模型
3. **Ollama 服务未启动** - 后台服务未运行

## 解决方案

### 方法一：自动设置（推荐）

1. 运行离线设置脚本：
   ```bash
   python setup_offline.py
   ```

   这个脚本会自动：
   - 下载 Ollama Windows 安装程序
   - 检查 Ollama 是否已安装
   - 下载所需的 AI 模型
   - 启动 Ollama 服务

2. 如果 Ollama 未安装，脚本会提示你运行下载的安装程序：
   ```bash
   installer\OllamaSetup.exe
   ```

3. 安装完成后重新运行设置脚本：
   ```bash
   python setup_offline.py
   ```

### 方法二：手动设置

#### 1. 安装 Ollama

- 下载 Ollama Windows 安装程序：https://ollama.ai/download
- 运行安装程序
- 确保安装路径添加到系统环境变量

#### 2. 下载所需模型

打开命令提示符，运行：
```bash
ollama pull deepseek-r1:8b
ollama pull nomic-embed-text
```

#### 3. 启动 Ollama 服务

```bash
ollama serve
```

#### 4. 运行医学问诊智能体

```bash
python main.py
```

## 验证安装

1. 检查 Ollama 是否安装成功：
   ```bash
   ollama --version
   ```

2. 检查模型是否下载成功：
   ```bash
   ollama list
   ```

3. 测试 Ollama API：
   ```bash
   curl http://localhost:11434/api/tags
   ```

## 常见问题

### Q: 启动时提示"Ollama 安装包不存在"
A: 运行 `python setup_offline.py` 下载必要的组件

### Q: 提示"无法连接到 AI 服务"
A: 1. 确保 Ollama 已安装
   2. 确保 Ollama 服务正在运行 (`ollama serve`)
   3. 检查模型是否已下载 (`ollama list`)

### Q: 模型下载很慢或失败
A: 可以尝试：
   1. 使用更小的模型，如 `deepseek-r1:1.5b`
   2. 修改 config.py 中的 MODEL_NAME 配置
   3. 在有网络的环境下下载，然后复制到离线环境

## 目录结构说明

设置完成后，项目目录应包含：

```
medical_bot/
├── installer/
│   └── OllamaSetup.exe          # Ollama 安装程序
├── models/                      # 模型文件（自动创建）
├── data/
│   ├── medical.db              # 患者数据库
│   ├── chroma_db/              # 知识库
│   └── knowledge/              # 医学知识文档
├── main.py                     # 主程序
├── setup_offline.py            # 离线设置脚本
└── config.py                   # 配置文件
```

## 离线环境部署

要将系统部署到完全离线的环境：

1. 在有网络的环境下运行 `python setup_offline.py`
2. 将整个项目目录复制到目标机器
3. 确保目标机器已安装 Ollama（或使用 installer 目录中的安装程序）
4. 运行 `python main.py`

## 性能优化

对于配置较低的机器，可以：

1. 使用更小的模型：
   ```python
   # 在 config.py 中修改
   MODEL_NAME = "deepseek-r1:1.5b"  # 而不是 8b
   ```

2. 增加超时时间：
   ```python
   LLM_TIMEOUT = 300  # 5分钟
   ```

3. 减少最大 tokens：
   ```python
   MAX_TOKENS = 2048
   ```
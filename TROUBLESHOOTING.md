# 故障排除指南

## 常见错误及解决方案

### 1. "无法连接到 AI 服务" 或 "AI 服务暂时不可用"

**可能原因：**
- Ollama 未安装
- Ollama 服务未启动
- 所需模型未下载
- 网络连接问题（离线环境）

**解决方案：**
1. 运行离线设置：`python setup_offline.py`
2. 手动检查 Ollama 安装：`ollama --version`
3. 启动 Ollama 服务：`ollama serve`
4. 下载模型：`ollama pull deepseek-r1:8b`

### 2. "Ollama 安装包不存在"

**原因：** installer 目录中缺少 OllamaSetup.exe

**解决方案：**
1. 运行 `python setup_offline.py` 自动下载
2. 或手动下载并放置到 installer 目录

### 3. 模型下载失败或很慢

**解决方案：**
1. 使用更小的模型（修改 config.py）：
   ```python
   MODEL_NAME = "deepseek-r1:1.5b"  # 15亿参数版本
   ```
2. 在有网络的环境下下载，然后复制到目标机器
3. 增加超时时间：
   ```python
   LLM_TIMEOUT = 300
   ```

### 4. 内存不足错误

**解决方案：**
1. 使用更小的模型
2. 关闭其他占用内存的程序
3. 增加虚拟内存

### 5. 端口被占用

**错误信息：** `Error: Address already in use`

**解决方案：**
1. 修改端口号（config.py）：
   ```python
   SERVER_PORT = 8080  # 改为其他端口
   ```
2. 查找并关闭占用端口的程序：
   ```bash
   netstat -ano | findstr :8000
   taskkill /PID <进程ID> /F
   ```

### 6. ChromaDB 初始化失败

**解决方案：**
1. 删除 data/chroma_db 目录重新初始化
2. 确保有足够的磁盘空间
3. 检查文件权限

### 7. 前端页面无法加载

**解决方案：**
1. 确保使用正确的 URL：http://localhost:8000
2. 检查防火墙设置
3. 尝试使用 127.0.0.1:8000

## 日志分析

### 查看日志级别
修改 main.py 中的日志级别：
```python
logging.basicConfig(
    level=logging.DEBUG,  # 改为 DEBUG 获取更多信息
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
```

### 常见日志信息解读

- `[INFO] Ollama 已安装` - Ollama 检测成功
- `[INFO] LLM 客户端已初始化` - AI 客户端初始化成功
- `[WARNING] Ollama 不可用` - Ollama 未安装或未运行
- `[ERROR] LLM 调用失败` - AI 服务调用失败

## 性能优化

### 降低资源占用

1. **减少历史记录长度**（consultation.py）：
   ```python
   history=self.conversation_history[-3:]  # 只保留最近3条
   ```

2. **减少知识库检索数量**（config.py）：
   ```python
   SEARCH_TOP_K = 3  # 减少到3个结果
   ```

3. **增加 LLM 超时时间**：
   ```python
   LLM_TIMEOUT = 180  # 3分钟
   ```

### 提高响应速度

1. 使用本地 SSD 存储
2. 增加系统内存
3. 使用更小的模型版本

## 离线环境特殊注意事项

### 1. 确保所有依赖都已安装

```bash
pip install -r requirements.txt
```

### 2. 预下载所有必要组件

- Ollama 安装程序
- AI 模型文件
- 知识库文档

### 3. 测试离线功能

1. 断开网络连接
2. 启动系统
3. 进行完整的问诊流程测试

### 4. 备份重要数据

定期备份以下目录：
- `data/medical.db` - 患者数据
- `data/chroma_db/` - 知识库
- `data/knowledge/` - 知识文档

## 联系支持

如果以上方法都无法解决问题：

1. 收集日志信息
2. 记录错误发生的具体步骤
3. 检查系统配置（Python版本、内存大小等）
4. 尝试在另一台机器上复现问题

## 快速恢复方案

如果系统完全无法启动：

1. 删除 `__pycache__` 目录
2. 删除 `data/chroma_db` 目录（会丢失知识库）
3. 重新运行初始化：
   ```bash
   python init_db.py
   python init_knowledge.py
   ```
4. 重新启动系统
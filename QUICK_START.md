# 🚀 医学问诊智能体 - 快速开始指南

## 🎯 一句话总结

这是一个可以完全离线运行的 AI 医学问诊系统，通过 5 阶段对话收集患者信息并生成标准医学报告。

## ⚡ 30秒快速开始

### 如果是第一次使用：
1. 双击运行 `setup_offline.bat`
2. 等待设置完成
3. 双击运行 `start.bat`
4. 浏览器访问 http://localhost:8000

### 如果已经设置过：
1. 双击运行 `start.bat`
2. 浏览器访问 http://localhost:8000

## 📋 详细步骤

### 第一步：环境设置（仅首次需要）

```bash
# 方法1：使用批处理文件（推荐）
双击运行: setup_offline.bat

# 方法2：命令行运行
python setup_offline.py
```

**设置过程包括：**
- ✅ 下载 Ollama 安装程序
- ✅ 检查 Ollama 是否已安装
- ✅ 下载 AI 模型
- ✅ 启动 Ollama 服务

### 第二步：启动系统

```bash
# 方法1：使用批处理文件（推荐）
双击运行: start.bat

# 方法2：命令行运行
python main.py
```

### 第三步：使用系统

1. 打开浏览器访问：**http://localhost:8000**
2. 开始与 AI 医生对话
3. 按照提示完成 5 阶段问诊
4. 查看生成的医学报告

## 🔧 系统要求

### 最低配置
- **操作系统**: Windows 7+ / Linux / macOS
- **内存**: 8GB RAM
- **存储**: 10GB 可用空间
- **Python**: 3.8+

### 推荐配置
- **内存**: 16GB+ RAM
- **存储**: SSD 硬盘
- **CPU**: 4核以上处理器

## 🎯 核心功能

### 5阶段智能问诊
1. **基本信息** - 姓名、性别、年龄、主诉
2. **现病史** - 症状详情、时间、诱因等
3. **既往史** - 相关病史、个人史、家族史
4. **系统回顾** - 针对性系统检查
5. **报告生成** - 完整医学报告

### 智能功能
- 🤖 **AI 对话** - 自然的医患对话体验
- 🔍 **知识库检索** - 基于医学知识的智能分析
- 📊 **历史记录** - 患者就诊历史追踪
- 🚨 **紧急提醒** - 自动检测紧急症状
- 📋 **标准报告** - 专业医学报告生成

## 🛠️ 常见问题

### Q: 启动时提示"Ollama 未安装"
A: 运行 `setup_offline.bat` 自动设置环境

### Q: 提示"端口被占用"
A: 系统会自动尝试下一个端口，或使用其他端口运行

### Q: AI 响应很慢
A: 1. 确保使用 SSD 2. 关闭其他程序 3. 尝试更小的模型

### Q: 如何更换 AI 模型
A: 修改 `config.py` 中的 `MODEL_NAME` 配置

## 📁 项目结构

```
medical_bot/
├── start.bat                 # 启动脚本 ⭐
├── setup_offline.bat         # 设置脚本 ⭐
├── main.py                   # 主程序
├── config.py                 # 配置文件
├── data/
│   ├── medical.db          # 患者数据
│   └── chroma_db/          # 知识库
├── static/
│   └── index.html          # 网页界面
└── requirements.txt         # 依赖包
```

## 🔍 验证系统状态

运行测试脚本检查系统功能：
```bash
python test_system.py
```

预期输出：
```
=== 测试结果汇总 ===
配置加载: 通过
数据库初始化: 通过
知识库初始化: 通过
问诊会话: 通过
LLM客户端: 通过

总结: 5/5 项测试通过
系统基本功能正常!
```

## 📚 相关文档

- [OFFLINE_README.md](OFFLINE_README.md) - 完整离线使用指南
- [OFFLINE_SETUP.md](OFFLINE_SETUP.md) - 详细设置说明
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - 故障排除
- [OFFLINE_STATUS.md](OFFLINE_STATUS.md) - 功能状态报告

## 🚨 重要提醒

- 🔒 **数据安全** - 所有数据本地存储，不上传云端
- ⚠️ **医疗 disclaimer** - AI 分析仅供参考，不能替代医生诊断
- 🚑 **紧急情况** - 如遇紧急症状请立即就医
- 📞 **技术支持** - 查看 TROUBLESHOOTING.md 获取帮助

## 🎉 开始使用

现在你已经了解了系统的全部功能！

**下一步：**
1. 运行 `setup_offline.bat` 设置环境
2. 运行 `start.bat` 启动系统
3. 访问 http://localhost:8000 开始问诊

祝你使用愉快！ 🩺✨
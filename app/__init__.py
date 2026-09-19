"""应用包 - 医学问诊智能体小程序后端 API

承接网关/路由/服务/数据层;核心 AI 引擎模块(consultation.py 等)留在项目根目录做最小改造。
仅在 config.DESKTOP_MODE=False 时启用,桌面模式仍走根目录 main.py 旧逻辑。
"""

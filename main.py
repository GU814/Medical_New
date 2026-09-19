"""
FastAPI 主程序 - 医学问诊智能体
启动入口，提供 Web 界面和 API 接口
"""
import os
import sys
import io

# ==================== 【打包 EXE 必加：修复编码问题】====================
# 修复 Windows 控制台编码问题
if sys.platform == "win32":
    # 设置控制台输出编码为 UTF-8
    if sys.stdout is not None and hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr is not None and hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    
    # 如果是打包后的程序，确保不会因为编码问题崩溃
    if getattr(sys, 'frozen', False):
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
# ======================================================================

import logging
import uuid
import time
import threading
import subprocess
import shutil
from typing import Optional
import uvicorn

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager

import database
import knowledge_base
import report_generator
import config
from consultation import ConsultationSession

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ==================== 解决打包后路径问题 ====================
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

# ==================== Ollama 辅助函数 ====================
def check_ollama_running():
    """检查 Ollama 服务是否正在运行"""
    try:
        import requests
        response = requests.get('http://localhost:11434/api/tags', timeout=3)
        if response.status_code == 200:
            logger.info("Ollama 服务正在运行")
            return True
    except Exception as e:
        logger.info(f"Ollama 服务未运行: {e}")
    return False


def install_ollama_if_needed():
    """检测 Ollama 是否已安装，如果没有则自动安装"""
    try:
        result = subprocess.run(['where', 'ollama'], capture_output=True, text=True, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            logger.info("Ollama 已安装")
            return True
    except Exception as e:
        logger.warning(f"检测 Ollama 失败: {e}")

    # 从打包的资源中提取安装包
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(__file__)

    installer_path = os.path.join(base_path, 'installer', 'OllamaSetup.exe')

    if os.path.exists(installer_path):
        logger.info("正在安装 Ollama，请稍候...")
        try:
            subprocess.run([installer_path, '/S'], check=True)
            time.sleep(5)
            logger.info("Ollama 安装完成")
            return True
        except Exception as e:
            logger.error(f"Ollama 安装失败: {e}")
            return False
    else:
        logger.warning(f"Ollama 安装包不存在: {installer_path}")
        logger.info("请运行 setup_offline.py 下载必要的组件或手动安装 Ollama")
        return False


def load_model_files():
    """将打包的模型文件复制到正确位置"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(__file__)

    models_source = os.path.join(base_path, 'models')
    models_target = os.path.expanduser('~/.ollama/models')

    if os.path.exists(models_source):
        if not os.path.exists(models_target):
            try:
                shutil.copytree(models_source, models_target)
                logger.info("模型文件已加载")
            except Exception as e:
                logger.error(f"模型文件加载失败: {e}")
        else:
            logger.info("模型目录已存在，跳过复制")
    else:
        logger.warning(f"模型文件目录不存在: {models_source}")
        logger.info("请运行 setup_offline.py 下载模型文件")


def start_ollama_service():
    """启动 Ollama 服务"""
    try:
        # 先检查是否已运行
        if check_ollama_running():
            logger.info("Ollama 服务已在运行，无需重新启动")
            return True
            
        # 尝试启动服务
        logger.info("正在启动 Ollama 服务...")
        subprocess.Popen(['ollama', 'serve'], shell=True, 
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        
        # 等待并验证启动
        for i in range(10):
            time.sleep(1)
            if check_ollama_running():
                logger.info("Ollama 服务已成功启动")
                return True
        
        logger.warning("Ollama 服务启动超时，请检查是否正确安装")
        return False
    except Exception as e:
        logger.error(f"启动 Ollama 服务失败: {e}")
        return False


def check_models_available():
    """检查所需的模型是否可用"""
    try:
        import requests
        response = requests.get('http://localhost:11434/api/tags', timeout=5)
        if response.status_code == 200:
            data = response.json()
            models = [m.get('name', '') for m in data.get('models', [])]
            
            required_chat = config.MODEL_NAME
            required_embed = config.EMBEDDING_MODEL
            
            chat_found = any(required_chat in m for m in models)
            embed_found = any(required_embed in m for m in models)
            
            if not chat_found:
                logger.warning(f"缺少对话模型: {required_chat}，可用模型: {models}")
            if not embed_found:
                logger.warning(f"缺少嵌入模型: {required_embed}，可用模型: {models}")
            
            if chat_found and embed_found:
                logger.info("所有必需模型已就绪")
                return True
            else:
                logger.info("请运行: ollama pull deepseek-r1:8b 和 ollama pull nomic-embed-text")
                return False
        return False
    except Exception as e:
        logger.warning(f"检查模型失败: {e}")
        return False

# ==================== Lifespan 事件 ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # ========== 启动时执行 ==========
    logger.info("正在初始化医学问诊智能体...")

    # 1. 初始化数据库（快速操作，同步执行）
    try:
        os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
        database.init_database()
        logger.info("数据库初始化成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")

    # 2. 初始化知识库（快速操作，同步执行）
    try:
        knowledge_base.init_knowledge_base()
        logger.info("知识库初始化成功")
    except Exception as e:
        logger.error(f"知识库初始化失败: {e}")
        logger.warning("系统将在没有知识库功能的情况下继续运行")

    # 3. Ollama 初始化放在后台线程（耗时操作，不阻塞服务启动）
    def init_ollama_background():
        try:
            ollama_available = install_ollama_if_needed()
            if ollama_available:
                load_model_files()
                if start_ollama_service():
                    check_models_available()
                    # Ollama 启动后，检查知识库是否需要补充文档
                    try:
                        collection = knowledge_base.get_collection()
                        if collection.count() == 0:
                            logger.info("知识库为空，正在从文档加载知识...")
                            knowledge_base.add_documents(config.KNOWLEDGE_DIR)
                            logger.info(f"知识库加载完成，当前 {collection.count()} 条文档片段")
                    except Exception as e:
                        logger.warning(f"知识库文档加载失败: {e}")
            else:
                logger.warning("Ollama 不可用，系统将在没有 AI 功能的情况下启动")
                logger.info("请运行 setup_offline.py 设置离线环境或手动安装 Ollama")
        except Exception as e:
            logger.error(f"Ollama 后台初始化失败: {e}")

    threading.Thread(target=init_ollama_background, daemon=True).start()

    logger.info("医学问诊智能体启动完成（Ollama 在后台初始化中）")

    yield  # 分界线

    # ========== 关闭时执行 ==========
    logger.info("医学问诊智能体正在关闭...")

# ==================== FastAPI 应用 ====================
# DESKTOP_MODE=True: 单机桌面应用(旧路由 /chat 等 + Ollama 自动安装 + 浏览器自启)
# DESKTOP_MODE=False: 小程序后端 API 服务器(app/ 包,JWT/加密/审计中间件)
if config.DESKTOP_MODE:
    app = FastAPI(
        title="医学问诊智能体",
        version="1.0.0",
        lifespan=lifespan
    )
else:
    # 小程序 API 模式:使用 app 包工厂,执行数据库迁移与中间件注册
    # 仍复用上面的 lifespan(知识库/DB/Ollama 初始化对两种模式通用)
    from app.main import create_app as _create_app

    app = _create_app()
    app.router.lifespan_context = lifespan
    logger.info("运行于小程序 API 模式(DESKTOP_MODE=False),已加载 app/ 包路由与中间件")

# 静态文件(桌面模式挂载单页前端;API 模式由 app/main.py 内部挂载)
if config.DESKTOP_MODE:
    static_dir = os.path.join(base_path, "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    else:
        logger.warning(f"静态文件目录不存在: {static_dir}")

# ==================== 会话管理(仅桌面模式) ====================
if config.DESKTOP_MODE:
    sessions: dict[str, ConsultationSession] = {}

    def get_or_create_session(session_id: Optional[str] = None) -> ConsultationSession:
        if session_id and session_id in sessions:
            return sessions[session_id]

        new_id = session_id or str(uuid.uuid4())[:8]
        session = ConsultationSession(session_id=new_id)
        sessions[new_id] = session
        logger.info(f"创建新会话: {new_id}")
        return session

    # ==================== 请求模型 ====================
    class ChatRequest(BaseModel):
        message: str
        session_id: Optional[str] = None

    class ResetRequest(BaseModel):
        session_id: Optional[str] = None

    # ==================== API 路由(桌面模式旧路由) ====================
    @app.get("/", response_class=HTMLResponse)
    async def index():
        index_path = os.path.join(base_path, "static", "index.html")
        return FileResponse(index_path)

    def _sse(event: str, data) -> str:
        """
        将事件与数据格式化为 SSE 文本块。
        data 内的换行会被拆成多行 `data:`（SSE 规范：多行 data 由客户端用换行重组）。
        """
        lines = str(data).split("\n")
        out = f"event: {event}\n"
        for ln in lines:
            out += f"data: {ln}\n"
        return out + "\n"


    @app.post("/chat")
    async def chat(request: ChatRequest):
        # 先获取/创建会话；空消息与已完成会话走非流式 JSON 回退
        session = get_or_create_session(request.session_id)

        if not request.message or not request.message.strip():
            return JSONResponse({
                "reply": "请输入您的消息。",
                "session_id": session.session_id,
                "stage": session.stage,
                "is_complete": False,
            })

        if session.is_complete:
            return JSONResponse({
                "reply": "问诊已完成，报告正在生成中或已生成。如需重新开始，请点击重置按钮。",
                "session_id": session.session_id,
                "stage": session.stage,
                "is_complete": True,
            })

        # 非流式回退：STREAMING_OUTPUT=false 时秒级回退到一次性 JSON（便于排障/兼容旧前端）
        if not config.STREAMING_OUTPUT:
            try:
                reply = session.process_user_input(request.message)
            except Exception as e:
                logger.error(f"处理用户输入失败: {e}")
                reply = "抱歉，处理您的消息时出现了问题，请重试。"

            report_text = ""
            if session.is_complete:
                try:
                    patient_data = session.get_patient_data()
                    report_text = report_generator.generate_report(patient_data)
                    session.report = report_text
                    logger.info("报告生成成功")
                except Exception as e:
                    logger.error(f"报告生成失败: {e}")
                    report_text = "\n\n⚠️ 报告生成过程中出现错误，请重试或联系管理员。"
                    session.report = report_text

            return JSONResponse({
                "reply": reply,
                "session_id": session.session_id,
                "stage": session.stage,
                "is_complete": session.is_complete,
                "report": report_text,
            })

        # 流式输出（SSE）：逐段返回回复，完成后流式生成报告
        async def event_gen():
            try:
                async for ev in session.process_user_input_stream(request.message):
                    yield _sse(ev["event"], ev["data"])
            except Exception as e:
                logger.error(f"流式生成失败: {e}")
                yield _sse("error", "抱歉，生成过程中出现问题，请稍后重试。")

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.post("/reset")
    async def reset(request: ResetRequest):
        session_id = request.session_id
        if session_id and session_id in sessions:
            del sessions[session_id]
            logger.info(f"会话 {session_id} 已重置")

        new_session = get_or_create_session()

        return JSONResponse({
            "message": "会话已重置，可以开始新的问诊。",
            "session_id": new_session.session_id,
        })

    @app.get("/history")
    async def history(session_id: str):
        session = sessions.get(session_id)
        if not session:
            return JSONResponse({"history": [], "session_id": session_id})

        return JSONResponse({
            "history": session.get_history_for_display(),
            "session_id": session_id,
            "stage": session.stage,
            "is_complete": session.is_complete,
        })

# ==================== 主入口 ====================
if __name__ == "__main__":
    import webbrowser

    # 获取配置
    try:
        import config

        host = config.SERVER_HOST
        port = config.SERVER_PORT
    except ImportError:
        host = "127.0.0.1"
        port = 8000
        logger.warning("未找到 config.py，使用默认配置: 127.0.0.1:8000")

    # 0.0.0.0/:: 只是监听地址,浏览器无法直接访问;自动打开时替换为回环地址
    display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{display_host}:{port}"
    # 探测地址:API 模式有 /healthz 健康检查端点;桌面模式直接探测根路径
    probe_url = f"{url}/healthz" if not config.DESKTOP_MODE else url

    # 自动打开浏览器（等待服务就绪后再打开）
    def open_browser():
        import urllib.request
        import urllib.error
        # 等待 HTTP 服务真正就绪（能响应请求）再打开浏览器
        max_wait = 60  # 最多等60秒
        for i in range(max_wait):
            time.sleep(1)
            try:
                req = urllib.request.Request(probe_url, method='GET')
                urllib.request.urlopen(req, timeout=2)
                logger.info(f"HTTP 服务已就绪（{i+1}s），正在打开浏览器...")
                break
            except urllib.error.HTTPError:
                # 收到任意 HTTP 状态码(包括404)都说明服务已在响应,视为就绪
                logger.info(f"HTTP 服务已就绪（{i+1}s），正在打开浏览器...")
                break
            except Exception:
                if i % 10 == 9:
                    logger.info(f"等待 HTTP 服务就绪... ({i+1}s)")
                continue

        # 尝试多种方式打开浏览器
        opened = False

        # 方式1: 使用 webbrowser 模块（标准方式）
        try:
            result = webbrowser.open(url)
            if result:
                logger.info(f"浏览器已打开: {url}")
                opened = True
        except Exception as e:
            logger.warning(f"webbrowser.open 失败: {e}")

        # 方式2: 如果方式1失败，使用系统命令
        if not opened:
            try:
                if sys.platform == 'win32':
                    os.startfile(url)
                    logger.info(f"通过 os.startfile 打开浏览器: {url}")
                    opened = True
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', url])
                    logger.info(f"通过 open 命令打开浏览器: {url}")
                    opened = True
                else:
                    subprocess.Popen(['xdg-open', url])
                    logger.info(f"通过 xdg-open 打开浏览器: {url}")
                    opened = True
            except Exception as e:
                logger.warning(f"系统命令打开浏览器失败: {e}")

        # 方式3: 如果都失败，使用 subprocess 直接调用
        if not opened and sys.platform == 'win32':
            try:
                subprocess.Popen(['cmd', '/c', 'start', url], shell=False)
                logger.info(f"通过 cmd start 打开浏览器: {url}")
                opened = True
            except Exception as e:
                logger.warning(f"cmd start 打开浏览器失败: {e}")

        if not opened:
            logger.error(f"无法自动打开浏览器，请手动访问: {url}")

    threading.Thread(target=open_browser, daemon=True).start()

    # 启动服务
    try:
        uvicorn.run(app, host=host, port=port, log_config=None, access_log=False)
    except OSError as e:
        if "Address already in use" in str(e) or "10048" in str(e):
            logger.error(f"端口 {port} 已被占用，尝试使用端口 {port + 1}")
            new_url = f"http://{display_host}:{port + 1}"
            logger.info(f"请手动访问: {new_url}")
            try:
                uvicorn.run(app, host=host, port=port + 1, log_config=None, access_log=False)
            except OSError:
                logger.error(f"端口 {port + 1} 也被占用，请手动指定其他端口")
                logger.info("可以在 config.py 中修改 SERVER_PORT 配置")
        else:
            logger.error(f"启动服务失败: {e}")
            raise
"""
应用工厂 - 小程序后端 API 服务器

create_app() 组装:
- 中间件链(CORS → Logging → RateLimit → Auth → Audit)
- 业务路由(auth/consultation/records/share)
- 启动时执行数据库迁移

仅 config.DESKTOP_MODE=False 时使用,桌面模式仍走根目录 main.py。
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
from app.db.migrations import run_migrations
from app.middleware.audit import AuditMiddleware
from app.middleware.auth import AuthMiddleware
from app.middleware.logging import LoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import auth, consultation, records, share

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="医学问诊智能体 API",
        description="微信小程序后端 - 医学问诊/历史记录/分享",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ---------- 启动时迁移 ----------
    @app.on_event("startup")
    def _startup():
        try:
            run_migrations()
            logger.info("数据库迁移完成")
        except Exception as e:
            logger.error(f"数据库迁移失败: {e}")

    # ---------- 中间件(注册顺序即生效顺序,后注册先执行外层) ----------
    # CORS 最外层
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # 执行顺序: CORS -> Logging -> RateLimit -> Auth -> Audit -> 路由
    app.add_middleware(AuditMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(LoggingMiddleware)

    # ---------- 根路径跳转(API 模式无网页首页,引导到接口文档) ----------
    @app.get("/", include_in_schema=False)
    async def root():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/docs")

    # ---------- 健康检查 ----------
    @app.get("/healthz", tags=["运维"])
    async def healthz():
        return {"status": "ok", "mode": "miniapp-api"}

    # ---------- 业务路由 ----------
    app.include_router(auth.router)
    app.include_router(consultation.router)
    app.include_router(records.router)
    app.include_router(share.router)

    # ---------- 静态资源(可选,供分享落地页等) ----------
    import os
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    logger.info("小程序 API 应用创建完成")
    return app

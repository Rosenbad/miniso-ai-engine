# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - TrendPulse 微服务入口 (Task 7)
# ==============================================================================
# 对应 spec §3.3 TrendPulse 数据感知层微服务
#
# 本模块是 TrendPulse 的 FastAPI 应用入口:
#   - create_app()  : 应用工厂, 创建 FastAPI 实例并挂载路由 + 种子化 demo 数据
#   - app           : 模块级应用实例 (供 uvicorn 直接启动)
#
# 启动方式:
#   uvicorn trendpulse.main:app --reload --port 8000
#
# 设计要点:
#   - 使用应用工厂模式 (create_app), 便于测试隔离 (每个测试创建独立 app)
#   - demo 数据在应用创建时种子化到 app.state.trend_store
#   - 路由通过 include_router 挂载, 路径与 spec 对齐 (/trends /cross-region ...)
# ==============================================================================

"""
TrendPulse 微服务 FastAPI 应用入口。

应用工厂:
    create_app() -> FastAPI
        创建应用, 挂载路由, 种子化 demo 数据。

模块级实例:
    app : FastAPI 应用 (供 uvicorn 启动)

启动::

    uvicorn trendpulse.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.cors import setup_cors
from shared.database import close_db, init_db
from shared.error_handler import register_error_handlers
from shared.orm_models import Base  # noqa: F401  # 确保 ORM 模型被导入并注册到 Base.metadata
from trendpulse.collectors.utils import setup_logger
from trendpulse.routes import TrendStore, router

logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理: 启动时初始化数据库, 关闭时释放连接池。

    容错策略:
        - 数据库不可用时仅记录警告, 不阻断启动 (回退到内存 Store demo 模式)
        - 确保测试环境 (无 DB) 仍可正常运行
    """
    try:
        await init_db()
    except Exception as exc:  # pragma: no cover - 容错路径, 测试环境不触发
        logger.warning(
            f"数据库初始化失败, 将以内存模式运行: {exc.__class__.__name__}: {exc}"
        )
    yield
    try:
        await close_db()
    except Exception as exc:  # pragma: no cover
        logger.warning(f"关闭数据库连接池时出错: {exc.__class__.__name__}: {exc}")


def create_app() -> FastAPI:
    """创建 TrendPulse FastAPI 应用 (应用工厂模式)。

    流程:
        1. 创建 FastAPI 实例 (含标题/描述/版本, 注册 lifespan)
        2. 初始化 TrendStore 并种子化 demo 数据
        3. 挂载 TrendPulse 路由 (router)
        4. 返回应用实例

    返回:
        配置完成的 FastAPI 应用实例 (含 demo 数据)
    """
    app = FastAPI(
        title="TrendPulse API",
        description=(
            "名创优品 AI 产品开发智能决策引擎 - TrendPulse 数据感知层微服务。"
            "提供多源趋势采集、跨区域趋势对比、扩散路径检测与本地化适配建议。"
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS 中间件 — 从环境变量 CORS_ORIGINS 读取白名单 (安全修复 R1)
    setup_cors(app)

    # 全局异常处理器 — 统一 AppError → JSON 响应, 兜底未捕获 Exception
    # 必须在 include_router 之前注册
    register_error_handlers(app)

    # 初始化内存存储并种子化 demo 数据
    # (内存 Store 保留作为 demo fallback, DB 仓储层为新增持久化能力)
    store = TrendStore()
    store.seed_demo_data()
    app.state.trend_store = store

    # 挂载路由
    app.include_router(router)

    logger.info("TrendPulse FastAPI 应用已创建 (demo 数据已种子化)")
    return app


# ==============================================================================
# 模块级应用实例 (供 uvicorn 直接启动: trendpulse.main:app)
# ==============================================================================

app = create_app()


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["create_app", "app"]

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

from fastapi import FastAPI

from shared.cors import setup_cors
from trendpulse.collectors.utils import setup_logger
from trendpulse.routes import TrendStore, router

logger = setup_logger(__name__)


def create_app() -> FastAPI:
    """创建 TrendPulse FastAPI 应用 (应用工厂模式)。

    流程:
        1. 创建 FastAPI 实例 (含标题/描述/版本)
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
    )

    # CORS 中间件 — 从环境变量 CORS_ORIGINS 读取白名单 (安全修复 R1)
    setup_cors(app)

    # 初始化内存存储并种子化 demo 数据
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

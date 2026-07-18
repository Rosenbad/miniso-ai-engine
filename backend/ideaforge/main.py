# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - IdeaForge FastAPI 应用入口 (Task 11)
# ==============================================================================
# 对应 spec §5.3 IdeaForge API 服务入口。
# 创建 FastAPI 应用, 挂载路由:
#   POST /generate  - 接受 TrendSignal, 返回 ProductIdeaCard[]
#   GET  /funnel    - 返回漏斗状态
#   GET  /health    - 健康检查
#
# 启动方式:
#   uvicorn ideaforge.main:app --host 0.0.0.0 --port 8001 --reload
# ==============================================================================

"""
IdeaForge FastAPI 应用入口。

创建 FastAPI 应用并挂载 IdeaForge 路由。

端点:
    - POST /generate: 接受趋势信号, 返回 ProductIdeaCard 列表
    - GET  /funnel:   返回规模化漏斗状态
    - GET  /health:   健康检查

用法::

    uvicorn ideaforge.main:app --host 0.0.0.0 --port 8001 --reload

测试::

    from fastapi.testclient import TestClient
    from ideaforge.main import create_app
    client = TestClient(create_app())
    response = client.get("/health")
"""

from __future__ import annotations

from fastapi import FastAPI

from ideaforge.routes import router
from shared.cors import setup_cors
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。

    创建应用并挂载 IdeaForge 路由。
    每次调用返回新的应用实例 (适用于测试场景)。

    返回:
        FastAPI 应用实例, 已挂载 /generate, /funnel, /health 端点。
    """
    app = FastAPI(
        title="MINISO IdeaForge API",
        description=(
            "名创优品 AI 产品开发智能决策引擎 - IdeaForge 服务\n\n"
            "Agent 编排 + 规模化漏斗 + 爆品预测\n\n"
            "## 端点\n"
            "- POST /generate: 趋势信号 → ProductIdeaCard[]\n"
            "- GET /funnel: 规模化漏斗状态\n"
            "- GET /health: 健康检查\n"
        ),
        version="1.0.0",
    )

    # CORS 中间件 — 从环境变量 CORS_ORIGINS 读取白名单 (安全修复 R1)
    setup_cors(app)

    # 挂载路由 (无前缀, 直接根路径)
    app.include_router(router, tags=["ideaforge"])

    logger.info("IdeaForge FastAPI 应用已创建")
    return app


# 模块级应用实例 (供 uvicorn 直接引用: ideaforge.main:app)
app = create_app()


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["create_app", "app"]

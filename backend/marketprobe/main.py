# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - MarketProbe FastAPI 应用入口 (Task 12)
# ==============================================================================
# 对应 spec §5 验证反馈层 · MarketProbe API 服务入口。
# 创建 FastAPI 应用, 挂载路由:
#   POST /test-plan  - 为产品生成测试计划
#   POST /simulate   - 运行销售模拟
#   POST /analyze    - 分析模拟结果
#   POST /calibrate  - 根据结果校准模型
#   GET  /health     - 健康检查
#
# 启动方式:
#   uvicorn marketprobe.main:app --host 0.0.0.0 --port 8002 --reload
# ==============================================================================

"""
MarketProbe FastAPI 应用入口。

创建 FastAPI 应用并挂载 MarketProbe 路由。

端点:
    - POST /test-plan : 生成 A/B 测试组合矩阵
    - POST /simulate  : 模拟 7-14 天销售数据
    - POST /analyze   : 分析测试结果, 判定赢家
    - POST /calibrate : 校准模型, 调整权重 + 策略建议
    - GET  /health    : 健康检查

用法::

    uvicorn marketprobe.main:app --host 0.0.0.0 --port 8002 --reload

测试::

    from fastapi.testclient import TestClient
    from marketprobe.main import create_app
    client = TestClient(create_app())
    response = client.get("/health")
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from marketprobe.routes import MarketProbeStore, router
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。

    创建应用并挂载 MarketProbe 路由, 初始化内存状态存储。
    每次调用返回新的应用实例 (适用于测试场景)。

    返回:
        FastAPI 应用实例, 已挂载 /test-plan, /simulate, /analyze,
        /calibrate, /health 端点。
    """
    app = FastAPI(
        title="MINISO MarketProbe API",
        description=(
            "名创优品 AI 产品开发智能决策引擎 - MarketProbe 验证反馈层服务\n\n"
            "4 步闭环验证: 测试方案设计 → 数据采集 → 表现分析 → 模型校准\n\n"
            "## 端点\n"
            "- POST /test-plan: 生成 A/B 测试组合矩阵\n"
            "- POST /simulate: 模拟 7-14 天销售数据\n"
            "- POST /analyze: 分析测试结果, 判定赢家\n"
            "- POST /calibrate: 校准模型, 调整权重 + 策略建议\n"
            "- GET /health: 健康检查\n"
        ),
        version="1.0.0",
    )

    # CORS 中间件 — 允许前端跨域访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 初始化内存状态存储 (供链式调用)
    app.state.marketprobe_store = MarketProbeStore()

    # 挂载路由 (无前缀, 直接根路径)
    app.include_router(router, tags=["marketprobe"])

    logger.info("MarketProbe FastAPI 应用已创建")
    return app


# 模块级应用实例 (供 uvicorn 直接引用: marketprobe.main:app)
app = create_app()


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["create_app", "app"]

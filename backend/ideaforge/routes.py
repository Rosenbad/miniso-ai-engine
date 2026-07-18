# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - IdeaForge API 路由 (Task 11)
# ==============================================================================
# 对应 spec §5.3 IdeaForge API 端点:
#   POST /generate  - 接受 TrendSignal (或 topic 字符串), 返回 ProductIdeaCard[]
#   GET  /funnel    - 返回漏斗状态 (万级→千级→百级→Top100)
#   GET  /health    - 健康检查
#
# 路由设计要点:
#   - GenerateRequest: 灵活请求模型, 仅 topic 必填, 其余字段有默认值
#   - /generate:       调用 AgentOrchestrator.orchestrate() 返回卡片列表
#   - /funnel:         返回漏斗阶段状态 (Demo: mock 数据展示漏斗层级)
#   - /health:         返回服务健康状态
# ==============================================================================

"""
IdeaForge API 路由模块。

提供 3 个 REST API 端点:
    - POST /generate: 接受趋势信号, 返回 ProductIdeaCard 列表
    - GET  /funnel:   返回规模化漏斗状态
    - GET  /health:   健康检查

用法::

    from ideaforge.routes import router
    app = FastAPI()
    app.include_router(router, prefix="/ideaforge", tags=["ideaforge"])
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from shared.exceptions import InternalError
from shared.models import TrendSignal
from ideaforge.funnel import FunnelFilter, TOP_N
from ideaforge.orchestrator import AgentOrchestrator
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 请求/响应模型
# ==============================================================================


class GenerateRequest(BaseModel):
    """POST /generate 请求模型。

    灵活设计: 仅 topic 必填, 其余字段提供默认值。
    支持两种使用场景:
        1. 完整 TrendSignal: 传入所有字段
        2. 仅 topic: 传入 {"topic": "..."}, 其余字段使用默认值
    """

    topic: str = Field(..., description="趋势主题 (必填)")
    heatScore: float = Field(default=50.0, description="热度分 (0-100)")
    growthRate: float = Field(default=10.0, description="增长率 (%)")
    category: str = Field(default="家居/香氛", description="品类")
    sentiment: float = Field(default=0.5, description="情感倾向 (-1~1)")
    lifecycle: str = Field(default="rising", description="生命周期阶段")
    predictWindow: str = Field(default="2-4周", description="预测窗口")
    relatedKeywords: List[str] = Field(
        default_factory=list, description="关联关键词"
    )
    sourceBreakdown: Dict[str, int] = Field(
        default_factory=dict, description="来源分布"
    )
    region: str = Field(default="china", description="区域")
    zGenTags: List[str] = Field(
        default_factory=list, description="Z 世代标签"
    )
    targetAudience: Dict[str, Any] = Field(
        default_factory=lambda: {
            "ageRange": "18-25",
            "aesthetic": "自然系",
            "spendingPower": "中",
        },
        description="目标受众",
    )
    crossRegionDiff: Dict[str, str] = Field(
        default_factory=dict, description="跨区域差异"
    )


class HealthResponse(BaseModel):
    """GET /health 响应模型。"""

    status: str = Field(..., description="服务状态")
    service: str = Field(..., description="服务名称")
    version: str = Field(..., description="版本号")


class FunnelStage(BaseModel):
    """漏斗阶段信息。"""

    level: str = Field(..., description="层级名称 (万级/千级/百级/Top100)")
    count: int = Field(..., description="该层数量")
    description: str = Field(..., description="层级描述")


class FunnelResponse(BaseModel):
    """GET /funnel 响应模型。"""

    stages: List[FunnelStage] = Field(..., description="漏斗阶段列表")
    threshold: float = Field(..., description="hitScore 阈值")
    topN: int = Field(..., description="最终保留数量上限")


# ==============================================================================
# 路由器
# ==============================================================================

router = APIRouter()


# 全局编排器与漏斗实例 (延迟初始化)
_orchestrator: Optional[AgentOrchestrator] = None
_funnel: Optional[FunnelFilter] = None


def _get_orchestrator() -> AgentOrchestrator:
    """获取全局 AgentOrchestrator 实例 (延迟初始化)。"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


def _get_funnel() -> FunnelFilter:
    """获取全局 FunnelFilter 实例 (延迟初始化)。"""
    global _funnel
    if _funnel is None:
        _funnel = FunnelFilter()
    return _funnel


# ==============================================================================
# POST /generate - 接受趋势信号, 返回 ProductIdeaCard[]
# ==============================================================================


@router.post("/generate")
async def generate_ideas(request: GenerateRequest) -> List[Dict[str, Any]]:
    """接受趋势信号, 运行 Agent 编排器, 返回 ProductIdeaCard 列表。

    对应 spec §5.3 POST /generate。

    参数:
        request: GenerateRequest (含 topic 必填, 其余字段有默认值)

    返回:
        ProductIdeaCard 列表 (JSON 数组), 每张卡含 16 个字段,
        按 hitScore 降序排列。

    异常:
        500: 编排器执行失败
    """
    logger.info(f"POST /generate: topic='{request.topic}'")

    try:
        # 构造 TrendSignal
        trend = TrendSignal(
            topic=request.topic,
            heatScore=request.heatScore,
            growthRate=request.growthRate,
            category=request.category,
            sentiment=request.sentiment,
            lifecycle=request.lifecycle,  # type: ignore[arg-type]
            predictWindow=request.predictWindow,
            relatedKeywords=request.relatedKeywords,
            sourceBreakdown=request.sourceBreakdown,
            region=request.region,  # type: ignore[arg-type]
            zGenTags=request.zGenTags,
            targetAudience=request.targetAudience,
            crossRegionDiff=request.crossRegionDiff,
        )

        # 运行编排器
        orchestrator = _get_orchestrator()
        cards = orchestrator.orchestrate(trend)

        logger.info(f"POST /generate: 返回 {len(cards)} 张卡")
        return [card.model_dump() for card in cards]

    except Exception as exc:
        logger.error(f"POST /generate 失败: {exc}", exc_info=True)
        raise InternalError(detail="处理请求时发生内部错误") from exc


# ==============================================================================
# GET /funnel - 返回漏斗状态
# ==============================================================================


@router.get("/funnel")
async def get_funnel_status() -> Dict[str, Any]:
    """返回规模化漏斗状态。

    对应 spec §5.3 GET /funnel。

    返回:
        漏斗状态 JSON, 包含:
        - stages: 各阶段信息 (万级→千级→百级→Top100)
        - threshold: hitScore 阈值
        - topN: 最终保留数量上限

    说明:
        当前为 Demo 模式, 返回 mock 漏斗数据展示层级结构。
        未来可接入实际数据库统计实时漏斗状态。
    """
    logger.info("GET /funnel: 返回漏斗状态")

    # Demo: mock 漏斗数据 (展示万级→千级→百级→Top100 层级结构)
    stages = [
        FunnelStage(
            level="万级",
            count=10000,
            description="全量趋势信号扫描 (TrendSignal)",
        ),
        FunnelStage(
            level="千级",
            count=1000,
            description="TrendAnalyst + ProductPlanner 产出概念",
        ),
        FunnelStage(
            level="百级",
            count=100,
            description="AgentOrchestrator 产出 ProductIdeaCard",
        ),
        FunnelStage(
            level="Top100",
            count=100,
            description=f"FunnelFilter 动态阈值过滤 (P70 分位数)",
        ),
    ]

    # 使用 FunnelFilter 实例的动态阈值
    funnel = _get_funnel()
    current_threshold = funnel.HIT_SCORE_THRESHOLD

    response = FunnelResponse(
        stages=stages,
        threshold=current_threshold,
        topN=TOP_N,
    )

    return response.model_dump()


# ==============================================================================
# GET /health - 健康检查
# ==============================================================================


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """健康检查端点。

    返回:
        服务健康状态 JSON
    """
    logger.info("GET /health: 健康检查")
    response = HealthResponse(
        status="healthy",
        service="ideaforge",
        version="1.0.0",
    )
    return response.model_dump()


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "router",
    "GenerateRequest",
    "HealthResponse",
    "FunnelResponse",
    "FunnelStage",
]

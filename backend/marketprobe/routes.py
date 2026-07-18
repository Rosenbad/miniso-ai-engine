# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - MarketProbe API 路由 (Task 12)
# ==============================================================================
# 对应 spec §5 验证反馈层 · MarketProbe API 端点:
#   POST /test-plan  - 为产品生成测试计划
#   POST /simulate   - 运行销售模拟
#   POST /analyze    - 分析模拟结果
#   POST /calibrate  - 根据结果校准模型
#   GET  /health     - 健康检查
#
# 路由设计要点:
#   - MarketProbeStore: 内存存储 (demo), 保存 test_plan / simulation / analysis
#   - 每个端点支持显式传参 (body) 或使用存储状态 (链式调用)
#   - 4 步闭环: test-plan → simulate → analyze → calibrate
# ==============================================================================

"""
MarketProbe API 路由模块。

提供 4 步闭环验证的 REST API 端点 + 健康检查:
    - POST /test-plan : 生成 A/B 测试组合矩阵
    - POST /simulate  : 模拟 7-14 天销售数据
    - POST /analyze   : 分析测试结果, 判定赢家
    - POST /calibrate : 校准模型, 调整权重 + 策略建议
    - GET  /health    : 健康检查

链式调用 (使用存储状态)::

    POST /test-plan  → 存储测试计划
    POST /simulate   → 使用存储的测试计划, 存储模拟数据
    POST /analyze    → 使用存储的测试计划+模拟数据, 存储分析结果
    POST /calibrate  → 使用存储的分析结果

显式传参 (每步独立)::

    POST /test-plan  → 返回测试计划
    POST /simulate   → 传入 test_plan, 返回模拟数据
    POST /analyze    → 传入 test_plan + simulation_data, 返回分析结果
    POST /calibrate  → 传入 test_result + predicted_hits + actual_results
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from shared.exceptions import InternalError
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 请求/响应模型
# ==============================================================================


class TestPlanRequest(BaseModel):
    """POST /test-plan 请求模型。"""

    product_name: str = Field(..., description="产品名称")
    category: str = Field(..., description="品类")
    ip_name: Optional[str] = Field(default=None, description="IP 名称 (可选)")
    days: int = Field(default=7, description="测试天数 (7-14)")


class SimulateRequest(BaseModel):
    """POST /simulate 请求模型。"""

    test_plan: Optional[Dict[str, Any]] = Field(
        default=None, description="测试计划 (不传则使用存储的)"
    )
    days: Optional[int] = Field(default=None, description="模拟天数")
    seed: int = Field(default=42, description="随机种子")


class AnalyzeRequest(BaseModel):
    """POST /analyze 请求模型。"""

    test_plan: Optional[Dict[str, Any]] = Field(
        default=None, description="测试计划"
    )
    simulation_data: Optional[Dict[str, Any]] = Field(
        default=None, description="模拟数据"
    )


class CalibrateRequest(BaseModel):
    """POST /calibrate 请求模型。"""

    test_result: Optional[Dict[str, Any]] = Field(
        default=None, description="分析结果 (PerformanceAnalyzer 输出)"
    )
    predicted_hits: Dict[str, float] = Field(
        default_factory=dict, description="预测 hitScore {combination_id: score}"
    )
    actual_results: Dict[str, float] = Field(
        default_factory=dict, description="实际结果 {combination_id: score}"
    )


# ==============================================================================
# MarketProbeStore - 内存状态存储 (demo 模式)
# ==============================================================================


class MarketProbeStore:
    """MarketProbe 内存状态存储 (demo 模式)。

    保存 4 步闭环的中间结果, 支持链式调用:
        - test_plan:       TestDesigner 输出
        - simulation_data: SalesSimulator 输出
        - analysis_result: PerformanceAnalyzer 输出
    """

    def __init__(self) -> None:
        self.test_plan: Optional[Dict[str, Any]] = None
        self.simulation_data: Optional[Dict[str, Any]] = None
        self.analysis_result: Optional[Dict[str, Any]] = None

    def clear(self) -> None:
        """清空所有存储状态。"""
        self.test_plan = None
        self.simulation_data = None
        self.analysis_result = None


# ==============================================================================
# 路由器
# ==============================================================================

router = APIRouter(tags=["marketprobe"])


def _get_store(request: Request) -> MarketProbeStore:
    """依赖注入: 从 app.state 获取 MarketProbeStore。"""
    if not hasattr(request.app.state, "marketprobe_store"):
        request.app.state.marketprobe_store = MarketProbeStore()
    return request.app.state.marketprobe_store  # type: ignore[no-any-return]


# ==============================================================================
# GET /health - 健康检查
# ==============================================================================


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """健康检查端点。

    返回:
        服务健康状态 JSON。
    """
    logger.info("GET /health: 健康检查")
    return {"status": "healthy", "service": "marketprobe", "version": "1.0.0"}


# ==============================================================================
# POST /test-plan - 生成测试计划
# ==============================================================================


@router.post("/test-plan")
async def create_test_plan(
    request: TestPlanRequest,
    http_request: Request,
) -> Dict[str, Any]:
    """为产品生成 A/B 测试组合矩阵。

    对应 spec §5 Step 1: TestDesigner。

    参数:
        request: TestPlanRequest (product_name, category, ip_name?, days?)

    返回:
        测试计划字典 (含 combinations, test_days, kpi_baseline)。
    """
    from marketprobe.test_designer import TestDesigner

    store = _get_store(http_request)

    logger.info(
        f"POST /test-plan: product='{request.product_name}', "
        f"category='{request.category}', days={request.days}"
    )

    try:
        designer = TestDesigner()
        plan = designer.design_test_plan(
            product_name=request.product_name,
            category=request.category,
            ip_name=request.ip_name,
            days=request.days,
        )

        # 存储测试计划 (供后续步骤使用)
        store.test_plan = plan

        return plan
    except Exception as exc:
        logger.error(f"POST /test-plan 失败: {exc}", exc_info=True)
        raise InternalError(detail="处理请求时发生内部错误") from exc


# ==============================================================================
# POST /simulate - 运行销售模拟
# ==============================================================================


@router.post("/simulate")
async def run_simulation(
    request: SimulateRequest,
    http_request: Request,
) -> Dict[str, Any]:
    """运行 7-14 天销售模拟。

    对应 spec §5 SalesSimulator。

    参数:
        request: SimulateRequest (test_plan?, days?, seed?)
                 test_plan 为 None 时使用存储的测试计划。

    返回:
        模拟数据字典 (含 days, daily_data, summary)。
    """
    from marketprobe.simulator import SalesSimulator

    store = _get_store(http_request)

    # 获取测试计划: 优先使用请求体, 否则使用存储的
    test_plan = request.test_plan
    if test_plan is None:
        test_plan = store.test_plan
    if test_plan is None:
        raise HTTPException(
            status_code=400,
            detail="未提供 test_plan, 且存储中无测试计划。请先调用 POST /test-plan。",
        )

    # 存储测试计划 (供后续步骤使用)
    store.test_plan = test_plan

    days = request.days if request.days is not None else test_plan.get("test_days", 7)

    logger.info(f"POST /simulate: days={days}, seed={request.seed}")

    try:
        simulator = SalesSimulator()
        result = simulator.simulate(test_plan, days=days, seed=request.seed)

        # 存储模拟数据
        store.simulation_data = result

        return result
    except Exception as exc:
        logger.error(f"POST /simulate 失败: {exc}", exc_info=True)
        raise InternalError(detail="处理请求时发生内部错误") from exc


# ==============================================================================
# POST /analyze - 分析模拟结果
# ==============================================================================


@router.post("/analyze")
async def analyze_results(
    request: AnalyzeRequest,
    http_request: Request,
) -> Dict[str, Any]:
    """分析测试结果, 判定赢家。

    对应 spec §5 Step 3: PerformanceAnalyzer。

    参数:
        request: AnalyzeRequest (test_plan?, simulation_data?)
                 为 None 时使用存储的状态。

    返回:
        分析结果字典 (含 winner, rankings, factor_contribution, confidence)。
    """
    from marketprobe.data_collector import DataCollector
    from marketprobe.performance_analyzer import PerformanceAnalyzer

    store = _get_store(http_request)

    # 获取测试计划
    test_plan = request.test_plan
    if test_plan is None:
        test_plan = store.test_plan
    if test_plan is None:
        raise HTTPException(
            status_code=400,
            detail="未提供 test_plan, 且存储中无测试计划。请先调用 POST /test-plan。",
        )

    # 获取模拟数据
    simulation_data = request.simulation_data
    if simulation_data is None:
        simulation_data = store.simulation_data
    if simulation_data is None:
        raise HTTPException(
            status_code=400,
            detail="未提供 simulation_data, 且存储中无模拟数据。请先调用 POST /simulate。",
        )

    logger.info("POST /analyze: 分析测试结果")

    try:
        # 将模拟数据转换为 DataCollector 格式
        collector = DataCollector()
        for combo_id, daily_list in simulation_data.get("daily_data", {}).items():
            for record in daily_list:
                collector.collect_daily(
                    combination_id=combo_id,
                    day=record["day"],
                    sales=record["sales"],
                    conversion=record["conversion"],
                    return_rate=record["return_rate"],
                    z_gen_engagement=record["z_gen_engagement"],
                )

        analyzer = PerformanceAnalyzer()
        result = analyzer.analyze(test_plan, collector.get_all_data())

        # 存储分析结果
        store.analysis_result = result

        return result
    except Exception as exc:
        logger.error(f"POST /analyze 失败: {exc}", exc_info=True)
        raise InternalError(detail="处理请求时发生内部错误") from exc


# ==============================================================================
# POST /calibrate - 校准模型
# ==============================================================================


@router.post("/calibrate")
async def calibrate_model(
    request: CalibrateRequest,
    http_request: Request,
) -> Dict[str, Any]:
    """根据验证结果校准模型。

    对应 spec §5 Step 4: ModelCalibrator (反哺链路修复核心)。

    参数:
        request: CalibrateRequest (test_result?, predicted_hits, actual_results)
                 test_result 为 None 时使用存储的分析结果。

    返回:
        ModelUpdate 字典 (含 new_version, weight_changes, strategy_suggestions, prediction_errors)。
    """
    from marketprobe.model_calibrator import ModelCalibrator

    store = _get_store(http_request)

    # 获取分析结果
    test_result = request.test_result
    if test_result is None:
        test_result = store.analysis_result
    if test_result is None:
        raise HTTPException(
            status_code=400,
            detail="未提供 test_result, 且存储中无分析结果。请先调用 POST /analyze。",
        )

    # 如果 predicted_hits / actual_results 为空, 从分析结果构造默认值
    predicted_hits = request.predicted_hits
    actual_results = request.actual_results

    if not predicted_hits or not actual_results:
        # 从排名构造默认预测/实际值 (基于综合评分)
        rankings = test_result.get("rankings", [])
        if rankings:
            if not predicted_hits:
                predicted_hits = {
                    r["combination_id"]: round(0.5 + r["score"] * 0.3, 6)
                    for r in rankings
                }
            if not actual_results:
                actual_results = {
                    r["combination_id"]: round(r["score"], 6)
                    for r in rankings
                }

    logger.info(
        f"POST /calibrate: predicted={len(predicted_hits)}, "
        f"actual={len(actual_results)}"
    )

    try:
        calibrator = ModelCalibrator()
        result = calibrator.calibrate(test_result, predicted_hits, actual_results)
        return result
    except Exception as exc:
        logger.error(f"POST /calibrate 失败: {exc}", exc_info=True)
        raise InternalError(detail="处理请求时发生内部错误") from exc


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "router",
    "MarketProbeStore",
    "TestPlanRequest",
    "SimulateRequest",
    "AnalyzeRequest",
    "CalibrateRequest",
]

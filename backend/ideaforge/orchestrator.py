# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - Agent 编排器 (Task 11)
# ==============================================================================
# 对应 spec §4.1 Agent 协作流程:
#   TrendSignal → Agent 1 → Agent 2 → IP 匹配 → (Agent 3 ∥ Agent 4) → ProductIdeaCard[]
#
# 编排流程:
#   1. Agent 1 (TrendAnalyst):    TrendSignal → ProductDirection        [串行]
#   2. Agent 2 (ProductPlanner):  ProductDirection → ProductConcept[]   [串行]
#   3. IP Match Engine:           ProductConcept.ipDirection → IPMatch   [串行]
#   4. Agent 3 (HitPredictor):    ProductConcept + IPMatch → hitScore    [并行]
#      Agent 4 (ConceptDesigner): ProductConcept → conceptImages         [并行]
#   5. 组装 ProductIdeaCard[] (按 hitScore 降序排列)
#
# AgentOrchestrator 设计要点:
#   - 串行 A1→A2→IP 匹配: 前序输出作为后序输入
#   - 并行 A3∥A4: 使用 ThreadPoolExecutor 实现并行 fan-out
#   - agentTrace: 每张卡记录完整决策链路 (agent/step/output)
#   - conceptId: 顺序生成 "CPT-2025-XXXX"
#   - hitScore 排序: 最终卡片按 hitScore 降序排列
# ==============================================================================

"""
Agent 编排器模块 (spec §4.1)。

整合 4 个 Agent + IP 匹配引擎 + 爆品预测器, 实现 TrendSignal →
ProductIdeaCard[] 的完整决策链路。

编排流程:
    1. Agent 1 (TrendAnalyst):   TrendSignal → ProductDirection
    2. Agent 2 (ProductPlanner): ProductDirection → ProductConcept[]
    3. IP Match Engine:          每个 concept.ipDirection → IPMatch
    4. Agent 3 (HitPredictor):   concept + IPMatch → hitScore + topFactors  [并行]
       Agent 4 (ConceptDesigner): concept → conceptImages                   [并行]
    5. 组装 ProductIdeaCard[] (16 字段, 按 hitScore 降序)

用法::

    orchestrator = AgentOrchestrator()
    cards = orchestrator.orchestrate(trend_signal)
    # cards: List[ProductIdeaCard], len >= 3, sorted by hitScore desc
"""

from __future__ import annotations

import statistics
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from shared.models import (
    IPMatch,
    ProductConcept,
    ProductDirection,
    ProductIdeaCard,
    TrendSignal,
)
from ideaforge.agents.concept_designer import ConceptDesigner
from ideaforge.agents.product_planner import ProductPlanner
from ideaforge.agents.trend_analyst import TrendAnalyst
from ideaforge.ip_engine import IPMatchEngine
from ideaforge.models.predict import HitPredictor
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 常量
# ==============================================================================

# conceptId 前缀与年份
_CONCEPT_ID_PREFIX: str = "CPT-2025"

# 价格区间解析用的最小/最大价格 (用于归一化 price_percentile)
_MIN_PRICE: float = 19.0
_MAX_PRICE: float = 299.0

# 默认 IP 名称 (IP 匹配失败时使用)
_DEFAULT_IP_INDEX: int = 0

# Z 世代匹配度默认值
_ZGEN_MATCH_WITH_TAGS: float = 0.8
_ZGEN_MATCH_WITHOUT_TAGS: float = 0.3

# 区域适配度映射 (lifecycle → high/medium/low)
_REGION_FIT_MAP: Dict[str, str] = {
    "peak": "high",
    "rising": "high",
    "nascent": "medium",
    "declining": "low",
}
_DEFAULT_REGION_FIT: str = "medium"

# 消费力映射 (中文字符串 → 0-1 数值)
_SPENDING_POWER_MAP: Dict[str, float] = {
    "高": 0.8,
    "中": 0.5,
    "低": 0.3,
}
_DEFAULT_SPENDING_POWER: float = 0.5

# IP 可用性 → 授权紧迫度映射
_AVAILABILITY_URGENCY_MAP: Dict[str, float] = {
    "available": 0.3,
    "exclusive": 0.5,
    "expiring": 0.8,
    "unavailable": 1.0,
}
_DEFAULT_AVAILABILITY_URGENCY: float = 0.3


# ==============================================================================
# AgentOrchestrator Agent 编排器
# ==============================================================================


class AgentOrchestrator:
    """Agent 编排器 (spec §4.1)。

    整合 4 个 Agent + IP 匹配引擎 + 爆品预测器, 实现 TrendSignal →
    ProductIdeaCard[] 的完整决策链路。

    编排流程:
        1. Agent 1 (TrendAnalyst):    TrendSignal → ProductDirection
        2. Agent 2 (ProductPlanner):  ProductDirection → ProductConcept[]
        3. IP Match Engine:           concept.ipDirection → IPMatch
        4. Agent 3 (HitPredictor):    concept + IPMatch → hitScore        [并行]
           Agent 4 (ConceptDesigner): concept → conceptImages             [并行]
        5. 组装 ProductIdeaCard[] (按 hitScore 降序)

    agentTrace:
        每张卡记录完整决策链路, 每条含 {agent, step, output}。

    conceptId:
        顺序生成 "CPT-2025-0001", "CPT-2025-0002", ...

    用法::

        orchestrator = AgentOrchestrator()
        cards = orchestrator.orchestrate(trend_signal)
        # cards: List[ProductIdeaCard], len >= 3, sorted by hitScore desc
    """

    def __init__(self) -> None:
        """初始化编排器, 实例化所有 Agent 与引擎。"""
        self.trend_analyst = TrendAnalyst()
        self.product_planner = ProductPlanner()
        self.ip_engine = IPMatchEngine()
        self.hit_predictor = HitPredictor()
        self.concept_designer = ConceptDesigner()

        logger.info("AgentOrchestrator: 初始化完成 (5 个组件已就绪)")

    # ==================================================================
    # orchestrate - 主入口: TrendSignal → List[ProductIdeaCard]
    # ==================================================================

    def orchestrate(self, trend: TrendSignal) -> List[ProductIdeaCard]:
        """执行完整 Agent 编排链路, 产出 ProductIdeaCard 列表。

        对应 spec §4.1 Agent 协作流程。

        参数:
            trend: 趋势信号 (TrendSignal 实例)

        返回:
            ProductIdeaCard 列表 (≥3 张), 每张含 16 个字段,
            按 hitScore 降序排列。每张卡的 agentTrace 记录完整决策链路。
        """
        logger.info(
            f"AgentOrchestrator.orchestrate: topic='{trend.topic}', "
            f"category='{trend.category}', region='{trend.region}'"
        )

        # Step 1: Agent 1 - TrendAnalyst: TrendSignal → ProductDirection
        direction = self.trend_analyst.analyze(trend)
        logger.info(
            f"  Step 1 (TrendAnalyst): direction.category='{direction.category}', "
            f"styleTone='{direction.styleTone}'"
        )

        # Step 2: Agent 2 - ProductPlanner: ProductDirection → ProductConcept[]
        # 传递真实趋势话题和关键词, 让产品名包含趋势内容
        concepts = self.product_planner.generate(
            direction,
            trend_topic=trend.topic,
            trend_keywords=trend.relatedKeywords,
        )
        logger.info(f"  Step 2 (ProductPlanner): 生成 {len(concepts)} 个概念 (trend_topic='{trend.topic}')")

        # Step 3-4: 对每个概念执行 IP 匹配 + 并行 A3∥A4
        cards: List[ProductIdeaCard] = []
        for idx, concept in enumerate(concepts, start=1):
            concept_id = f"{_CONCEPT_ID_PREFIX}-{idx:04d}"

            # 构建 agentTrace (共享前 3 步, 每张卡独立记录)
            agent_trace: List[Dict[str, Any]] = [
                {
                    "agent": "TrendAnalyst",
                    "step": 1,
                    "output": (
                        f"ProductDirection(category={direction.category}, "
                        f"styleTone={direction.styleTone})"
                    ),
                },
                {
                    "agent": "ProductPlanner",
                    "step": 2,
                    "output": (
                        f"ProductConcept(productName={concept.productName}, "
                        f"category={concept.category})"
                    ),
                },
            ]

            # Step 3: IP Match Engine
            ip_match = self._match_ip_for_concept(concept)
            agent_trace.append(
                {
                    "agent": "IPMatchEngine",
                    "step": 3,
                    "output": (
                        f"IPMatch(ipName={ip_match.ipName}, "
                        f"matchScore={ip_match.matchScore:.2f})"
                    ),
                }
            )

            # Step 4: Agent 3 (HitPredictor) ∥ Agent 4 (ConceptDesigner) [并行]
            hit_result, concept_images = self._parallel_predict_and_design(
                concept, ip_match, trend, direction
            )

            agent_trace.append(
                {
                    "agent": "HitPredictor",
                    "step": 4,
                    "output": f"hitScore={hit_result['hitScore']:.4f}",
                }
            )
            agent_trace.append(
                {
                    "agent": "ConceptDesigner",
                    "step": 4,
                    "output": f"{len(concept_images)} images",
                }
            )

            # Step 5: 组装 ProductIdeaCard
            card = self._assemble_card(
                concept_id=concept_id,
                concept=concept,
                ip_match=ip_match,
                hit_result=hit_result,
                concept_images=concept_images,
                trend=trend,
                direction=direction,
                agent_trace=agent_trace,
            )
            cards.append(card)

        # 按 hitScore 降序排列
        cards.sort(key=lambda c: c.hitScore, reverse=True)

        logger.info(
            f"AgentOrchestrator.orchestrate: 完成 → 产出 {len(cards)} 张卡, "
            f"hitScore 范围 [{cards[-1].hitScore:.4f}, {cards[0].hitScore:.4f}]"
            if cards
            else f"AgentOrchestrator.orchestrate: 完成 → 产出 0 张卡"
        )

        return cards

    # ==================================================================
    # 内部辅助: IP 匹配
    # ==================================================================

    def _match_ip_for_concept(self, concept: ProductConcept) -> IPMatch:
        """为产品概念匹配最佳 IP。

        匹配策略 (优先级递减):
            1. 精确匹配: concept.ipDirection == IP 数据库中的名称
            2. 部分匹配: IP 数据库中某名称包含 ipDirection 或反之
            3. 默认回退: 使用 IP 数据库中第一个 IP

        参数:
            concept: 产品概念

        返回:
            IPMatch 实例
        """
        ip_name_raw = concept.ipDirection
        available_ips = self.ip_engine.list_ips()

        # 1. 精确匹配
        if ip_name_raw in available_ips:
            return self.ip_engine.full_match(ip_name_raw, concept.category)

        # 2. 部分匹配 (双向子串包含)
        for ip_name in available_ips:
            if ip_name_raw in ip_name or ip_name in ip_name_raw:
                return self.ip_engine.full_match(ip_name, concept.category)

        # 3. 默认回退: 使用第一个 IP
        default_ip = available_ips[_DEFAULT_IP_INDEX]
        logger.warning(
            f"IP 匹配失败: ipDirection='{ip_name_raw}', 回退至 '{default_ip}'"
        )
        return self.ip_engine.full_match(default_ip, concept.category)

    # ==================================================================
    # 内部辅助: 并行执行 HitPredictor + ConceptDesigner
    # ==================================================================

    def _parallel_predict_and_design(
        self,
        concept: ProductConcept,
        ip_match: IPMatch,
        trend: TrendSignal,
        direction: ProductDirection,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """并行执行 Agent 3 (HitPredictor) 与 Agent 4 (ConceptDesigner)。

        使用 ThreadPoolExecutor 实现 A3∥A4 并行 fan-out。
        若并行执行失败, 降级为串行调用。

        参数:
            concept:     产品概念
            ip_match:    IP 匹配结果
            trend:       原始趋势信号
            direction:   产品方向

        返回:
            (hit_result, concept_images) 元组:
            - hit_result: {"hitScore": float, "topFactors": [...]}
            - concept_images: [url_front, url_scene]
        """
        # 构建 HitPredictor 的原始数据
        raw_data = self._build_raw_data(concept, ip_match, trend, direction)

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_hit = executor.submit(
                    self.hit_predictor.predict, raw_data
                )
                future_design = executor.submit(
                    self.concept_designer.generate, concept
                )
                hit_result = future_hit.result()
                concept_images = future_design.result()
        except Exception as exc:
            # 降级为串行调用
            logger.warning(
                f"并行执行失败, 降级为串行 (原因: {exc})"
            )
            hit_result = self.hit_predictor.predict(raw_data)
            concept_images = self.concept_designer.generate(concept)

        return hit_result, concept_images

    # ==================================================================
    # 内部辅助: 构建 HitPredictor 原始数据 (19 特征映射)
    # ==================================================================

    def _build_raw_data(
        self,
        concept: ProductConcept,
        ip_match: IPMatch,
        trend: TrendSignal,
        direction: ProductDirection,
    ) -> Dict[str, Any]:
        """从 concept + IPMatch + trend 构建 HitPredictor 的 19 特征数据。

        将编排链路中的可用数据映射到 FeatureExtractor 的 19 个特征键。
        无法直接获取的特征使用合理默认值。

        参数:
            concept:   产品概念
            ip_match:  IP 匹配结果
            trend:     原始趋势信号
            direction: 产品方向

        返回:
            含 19 个特征键的字典, 供 FeatureExtractor.extract() 使用。
        """
        # 价格中位数 (用于 price_percentile 归一化)
        price_mid = self._parse_price_midpoint(concept.priceRange)
        price_percentile = (price_mid - _MIN_PRICE) / (_MAX_PRICE - _MIN_PRICE)
        price_percentile = max(0.0, min(1.0, price_percentile))

        # IP 区域热度方差 (用于 ip_region_heat_variance)
        heat_values = list(ip_match.regionHeatMap.values())
        heat_variance = statistics.variance(heat_values) if len(heat_values) > 1 else 0.0

        # Z 世代匹配度
        z_gen_tags = trend.zGenTags
        z_gen_match = _ZGEN_MATCH_WITH_TAGS if z_gen_tags else _ZGEN_MATCH_WITHOUT_TAGS

        # 审美标签热度 (基于 zGenTags 数量)
        aesthetic_tag_heat = min(100.0, len(z_gen_tags) * 25.0) if z_gen_tags else 30.0

        # 消费力 (从 targetAudience 映射)
        spending_power_str = trend.targetAudience.get("spendingPower", "中")
        audience_spending_power = _SPENDING_POWER_MAP.get(
            spending_power_str, _DEFAULT_SPENDING_POWER
        )

        # 社交传播度 (基于 sourceBreakdown 来源数)
        source_count = len(trend.sourceBreakdown)
        social_virality = min(1.0, source_count * 0.3)

        # 社交提及量 (sourceBreakdown 值之和)
        social_mentions = float(sum(trend.sourceBreakdown.values()))

        # 正面评价比 (sentiment -1~1 → 0~1)
        positive_review_ratio = (trend.sentiment + 1.0) / 2.0

        # IP 可用性 → 授权紧迫度
        ip_license_urgency = _AVAILABILITY_URGENCY_MAP.get(
            ip_match.availability, _DEFAULT_AVAILABILITY_URGENCY
        )

        # 跨区域扩散速度 (基于 crossRegionDiff 区域数)
        region_count = len(trend.crossRegionDiff)
        cross_region_diffusion_speed = min(1.0, region_count * 0.25)

        # 设计新颖度 (基于设计描述长度 + 变体差异化, 归一化)
        # 不同变体 (基础款/进阶款/限定款) 有不同的新颖度基线
        design_novelty = min(1.0, len(concept.designDesc) / 100.0)
        # 产品名含"限定款" → 新颖度 +0.15, "进阶款" → +0.08, "基础款" → +0.0
        if "限定款" in concept.productName:
            design_novelty = min(1.0, design_novelty + 0.15)
        elif "进阶款" in concept.productName:
            design_novelty = min(1.0, design_novelty + 0.08)

        # 材质成本比 (基于材质字符串启发式, 简单默认)
        material_cost_ratio = 0.3

        raw_data: Dict[str, Any] = {
            # 市场特征 (5)
            "category_heat": float(trend.heatScore),
            "trend_growth_rate": float(trend.growthRate),
            "seasonality_index": 0.5,  # 默认, 无直接数据源
            "competitor_density": 0.4,  # 默认, 无直接数据源
            "cross_region_diffusion_speed": cross_region_diffusion_speed,
            # 产品特征 (3)
            "price_percentile": price_percentile,
            "material_cost_ratio": material_cost_ratio,
            "design_novelty": design_novelty,
            # IP 特征 (4)
            "ip_power_score": float(ip_match.ipPowerScore),
            "ip_category_match": float(ip_match.matchScore),
            "ip_license_urgency": ip_license_urgency,
            "ip_region_heat_variance": heat_variance,
            # 受众特征 (4)
            "z_gen_match": z_gen_match,
            "aesthetic_tag_heat": aesthetic_tag_heat,
            "audience_spending_power": audience_spending_power,
            "social_virality": social_virality,
            # 情感特征 (3)
            "trend_sentiment": float(trend.sentiment),
            "social_mentions": social_mentions,
            "positive_review_ratio": positive_review_ratio,
        }

        return raw_data

    # ==================================================================
    # 内部辅助: 组装 ProductIdeaCard
    # ==================================================================

    def _assemble_card(
        self,
        concept_id: str,
        concept: ProductConcept,
        ip_match: IPMatch,
        hit_result: Dict[str, Any],
        concept_images: List[str],
        trend: TrendSignal,
        direction: ProductDirection,
        agent_trace: List[Dict[str, Any]],
    ) -> ProductIdeaCard:
        """组装 ProductIdeaCard (16 字段)。

        参数:
            concept_id:      概念 ID
            concept:         产品概念
            ip_match:        IP 匹配结果
            hit_result:      爆品预测结果 {hitScore, topFactors}
            concept_images:  概念图 URL 列表
            trend:           原始趋势信号
            direction:       产品方向
            agent_trace:     决策链路追踪

        返回:
            ProductIdeaCard 实例 (16 字段全部填充)
        """
        # zGenMatchScore: 基于 zGenTags 推导
        z_gen_match_score = self._derive_zgen_match_score(trend)

        # regionFit: 基于 trend.crossRegionDiff + trend.lifecycle 推导
        region_fit = self._derive_region_fit(trend)

        # targetAudience: 透传 concept.targetAudience (含 direction 补全)
        target_audience = dict(concept.targetAudience)

        card = ProductIdeaCard(
            conceptId=concept_id,
            productName=concept.productName,
            category=concept.category,
            designDesc=concept.designDesc,
            material=concept.material,
            priceRange=concept.priceRange,
            ipMatch=ip_match,
            sellingPoints=list(concept.sellingPoints),
            hitScore=float(hit_result["hitScore"]),
            topFactors=list(hit_result["topFactors"]),
            conceptImages=list(concept_images),
            trendSource=trend.topic,
            zGenMatchScore=z_gen_match_score,
            targetAudience=target_audience,
            regionFit=region_fit,
            agentTrace=agent_trace,
        )

        return card

    # ==================================================================
    # 内部辅助: Z 世代匹配度推导
    # ==================================================================

    @staticmethod
    def _derive_zgen_match_score(trend: TrendSignal) -> float:
        """从趋势信号推导 Z 世代匹配度 (0-1)。

        启发式规则:
            - 有 zGenTags: 0.7 + 0.05 * tag数 (上限 0.95)
            - 无 zGenTags: 0.3

        参数:
            trend: 趋势信号

        返回:
            Z 世代匹配度 0-1
        """
        tags = trend.zGenTags
        if not tags:
            return _ZGEN_MATCH_WITHOUT_TAGS

        score = _ZGEN_MATCH_WITH_TAGS + 0.05 * len(tags)
        return min(0.95, score)

    # ==================================================================
    # 内部辅助: 区域适配度推导
    # ==================================================================

    @staticmethod
    def _derive_region_fit(trend: TrendSignal) -> Dict[str, str]:
        """从趋势信号推导区域适配度 {region: high/medium/low}。

        逻辑:
            1. 当前区域 (trend.region): 基于 trend.lifecycle
               - rising/peak → high
               - declining → low
            2. crossRegionDiff 中各区域: 基于其 lifecycle 描述符
               - peak/rising → high
               - nascent → medium
               - declining → low

        参数:
            trend: 趋势信号

        返回:
            区域适配度字典 {region: high|medium|low}
        """
        region_fit: Dict[str, str] = {}

        # 当前区域: 基于 lifecycle
        current_fit = _REGION_FIT_MAP.get(trend.lifecycle, _DEFAULT_REGION_FIT)
        region_fit[trend.region] = current_fit

        # crossRegionDiff 中各区域
        for region, lifecycle_desc in trend.crossRegionDiff.items():
            if region == trend.region:
                continue
            region_fit[region] = _REGION_FIT_MAP.get(
                lifecycle_desc, _DEFAULT_REGION_FIT
            )

        return region_fit

    # ==================================================================
    # 内部辅助: 价格区间中位数解析
    # ==================================================================

    @staticmethod
    def _parse_price_midpoint(price_range: str) -> float:
        """解析价格区间字符串 'lo-hi' → 中位数 (lo + hi) / 2。

        参数:
            price_range: 价格区间字符串, 如 "49-79"

        返回:
            价格中位数; 解析失败返回 50.0 (默认中间值)
        """
        try:
            parts = price_range.split("-")
            if len(parts) == 2:
                lo = float(parts[0].strip())
                hi = float(parts[1].strip())
                return (lo + hi) / 2.0
        except (ValueError, AttributeError):
            pass
        return 50.0


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["AgentOrchestrator"]

# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - Agent 编排器 + 规模化漏斗 + IdeaForge API (Task 11)
# ==============================================================================
# 对应 Task 11: Agent 编排 + 规模化漏斗 + IdeaForge API
# 覆盖:
#   1. ConceptDesigner     - DALL-E/SD 概念图生成 (placehold.co 降级)
#   2. AgentOrchestrator   - 串行 A1→A2→IP 匹配, 并行 A3∥A4, 输出 ProductIdeaCard[]
#   3. FunnelFilter        - filter_top100 (hitScore>0.7) + batch_run
#   4. FastAPI 路由        - POST /generate, GET /funnel, GET /health
#   5. 边界场景            - 空趋势列表, 单条趋势
#
# 测试策略 (TDD):
#   Step 1: 编写测试 (本文件)
#   Step 2: 验证失败 (编排器/漏斗/路由模块尚未创建)
#   Step 3: 实现 ConceptDesigner
#   Step 4: 实现 AgentOrchestrator
#   Step 5: 实现 FunnelFilter
#   Step 6: 实现 FastAPI 路由
#   Step 7: 验证通过
# ==============================================================================

"""
测试 Agent 编排器、规模化漏斗与 IdeaForge API 路由 (Task 11)。

测试覆盖 (TDD):
  - ConceptDesigner: 返回 2 个 URL, placehold.co 格式, 含产品名
  - AgentOrchestrator.orchestrate:
    * 返回 ≥3 个 ProductIdeaCard
    * 每张卡 16 个字段全部填充
    * ipMatch 为 IPMatch 实例
    * hitScore ∈ [0,1]
    * topFactors 非空
    * conceptImages 含 2 个 URL
    * agentTrace 记录每一步
    * 卡片按 hitScore 降序排列
  - FunnelFilter:
    * filter_top100: 过滤 hitScore > 0.7
    * filter_top100: 按 hitScore 降序
    * filter_top100: 限制 100 条
    * batch_run: 处理多条趋势
  - API 路由: POST /generate, GET /funnel, GET /health
  - 边界场景: 空趋势列表, 单条趋势

环境说明:
  - 规则/模板生成 + XGBoost 预测, 无需 LLM API 调用
  - 复用 shared.models 中已定义的数据模型
  - HitPredictor 使用预训练模型 (backend/data/xgboost_model.json)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from shared.models import IPMatch, ProductIdeaCard, TrendSignal


# ==============================================================================
# 测试辅助 - 构造 TrendSignal
# ==============================================================================


def _make_signal(
    topic: str = "侘寂风家居",
    region: str = "china",
    lifecycle: str = "rising",
    heat_score: float = 72.0,
    growth_rate: float = 34.2,
    category: str = "家居/香氛",
    sentiment: float = 0.6,
    predict_window: str = "2-4周",
    z_gen_tags: Optional[List[str]] = None,
    target_audience: Optional[Dict[str, Any]] = None,
    related_keywords: Optional[List[str]] = None,
    cross_region_diff: Optional[Dict[str, str]] = None,
) -> TrendSignal:
    """构造一个 TrendSignal 测试实例。

    封装必填字段, 提供合理默认值, 减少测试样板代码。
    """
    return TrendSignal(
        topic=topic,
        heatScore=heat_score,
        growthRate=growth_rate,
        category=category,
        sentiment=sentiment,
        lifecycle=lifecycle,  # type: ignore[arg-type]
        predictWindow=predict_window,
        relatedKeywords=related_keywords or ["侘寂", "原木", "疗愈"],
        sourceBreakdown={"xiaohongshu": 50, "douyin": 30},
        region=region,  # type: ignore[arg-type]
        zGenTags=z_gen_tags if z_gen_tags is not None else ["侘寂", "自然系"],
        targetAudience=target_audience
        or {
            "ageRange": "18-25",
            "aesthetic": "侘寂自然",
            "spendingPower": "中",
        },
        crossRegionDiff=cross_region_diff if cross_region_diff is not None else {},
    )


def _make_ip_match(
    ip_name: str = "三丽鸥·库洛米",
    power_score: float = 85.0,
    match_score: float = 0.9,
    availability: str = "available",
) -> IPMatch:
    """构造一个 IPMatch 测试实例 (用于漏斗测试的 mock 卡片)。"""
    return IPMatch(
        ipName=ip_name,
        ipPowerScore=power_score,
        matchScore=match_score,
        availability=availability,  # type: ignore[arg-type]
        exclusiveUntil=None,
        regionHeatMap={"china": 92, "sea": 78, "us": 65, "eu": 45},
        recommendedCategories=["美妆/个护", "家居/香氛"],
    )


def _make_card(
    concept_id: str = "CPT-2025-0001",
    product_name: str = "测试产品",
    hit_score: float = 0.85,
    category: str = "家居/香氛",
) -> ProductIdeaCard:
    """构造一个 ProductIdeaCard 测试实例 (用于漏斗测试)。

    提供合理默认值, 关键字段 hit_score 可自定义。
    """
    return ProductIdeaCard(
        conceptId=concept_id,
        productName=product_name,
        category=category,
        designDesc="融合侘寂美学的产品概念设计",
        material="大豆蜡 + 陶瓷",
        priceRange="49-79",
        ipMatch=_make_ip_match(),
        sellingPoints=["卖点1", "卖点2", "卖点3"],
        hitScore=hit_score,
        topFactors=[
            {"feature": "category_heat", "shap_value": 0.25},
            {"feature": "ip_power_score", "shap_value": 0.18},
            {"feature": "z_gen_match", "shap_value": 0.12},
        ],
        conceptImages=[
            "https://placehold.co/600x400?text=Front",
            "https://placehold.co/600x400?text=Scene",
        ],
        trendSource="侘寂风家居",
        zGenMatchScore=0.82,
        targetAudience={
            "ageRange": "18-25",
            "aesthetic": "侘寂",
            "spendingPower": "中",
        },
        regionFit={"china": "high", "sea": "medium", "us": "low"},
        agentTrace=[
            {"agent": "TrendAnalyst", "step": 1, "output": "ProductDirection"},
            {"agent": "ProductPlanner", "step": 2, "output": "ProductConcept"},
            {"agent": "IPMatchEngine", "step": 3, "output": "IPMatch"},
            {"agent": "HitPredictor", "step": 4, "output": "hitScore=0.85"},
            {"agent": "ConceptDesigner", "step": 4, "output": "2 images"},
        ],
    )


# ==============================================================================
# 1. ConceptDesigner 测试
# ==============================================================================


class TestConceptDesigner:
    """ConceptDesigner (Agent 4) 测试 - 概念图 URL 生成。"""

    def test_generate_returns_list(self) -> None:
        """generate 应返回列表。"""
        from ideaforge.agents.concept_designer import ConceptDesigner
        from shared.models import ProductConcept

        designer = ConceptDesigner()
        concept = ProductConcept(
            productName="原木杯香薰蜡烛",
            category="家居/香氛",
            designDesc="融合侘寂美学",
            material="大豆蜡 + 陶瓷",
            priceRange="49-79",
            ipDirection="三丽鸥·库洛米",
            sellingPoints=["卖点1"],
            targetAudience={"ageRange": "18-25"},
        )
        result = designer.generate(concept)
        assert isinstance(result, list)

    def test_generate_returns_exactly_two_urls(self) -> None:
        """generate 应返回恰好 2 个 URL (正面图 + 场景图)。"""
        from ideaforge.agents.concept_designer import ConceptDesigner
        from shared.models import ProductConcept

        designer = ConceptDesigner()
        concept = ProductConcept(
            productName="原木杯香薰蜡烛",
            category="家居/香氛",
            designDesc="融合侘寂美学",
            material="大豆蜡 + 陶瓷",
            priceRange="49-79",
            ipDirection="三丽鸥·库洛米",
            sellingPoints=["卖点1"],
            targetAudience={"ageRange": "18-25"},
        )
        result = designer.generate(concept)
        assert len(result) == 2

    def test_generate_urls_are_placehold_co_format(self) -> None:
        """URL 应为 placehold.co 格式 (demo 降级模式)。"""
        from ideaforge.agents.concept_designer import ConceptDesigner
        from shared.models import ProductConcept

        designer = ConceptDesigner()
        concept = ProductConcept(
            productName="原木杯香薰蜡烛",
            category="家居/香氛",
            designDesc="融合侘寂美学",
            material="大豆蜡 + 陶瓷",
            priceRange="49-79",
            ipDirection="三丽鸥·库洛米",
            sellingPoints=["卖点1"],
            targetAudience={"ageRange": "18-25"},
        )
        result = designer.generate(concept)
        for url in result:
            assert "placehold.co" in url, f"URL 不含 placehold.co: {url}"

    def test_generate_urls_contain_product_name(self) -> None:
        """URL 应编码产品名信息。"""
        from ideaforge.agents.concept_designer import ConceptDesigner
        from shared.models import ProductConcept

        designer = ConceptDesigner()
        concept = ProductConcept(
            productName="原木杯香薰蜡烛",
            category="家居/香氛",
            designDesc="融合侘寂美学",
            material="大豆蜡 + 陶瓷",
            priceRange="49-79",
            ipDirection="三丽鸥·库洛米",
            sellingPoints=["卖点1"],
            targetAudience={"ageRange": "18-25"},
        )
        result = designer.generate(concept)
        # 至少一个 URL 应包含产品名的某种编码形式
        # (URL 编码后中文字符会变成 %XX 形式)
        combined = " ".join(result).lower()
        assert "text=" in combined, "URL 缺少 text 参数"

    def test_generate_first_url_is_front_view(self) -> None:
        """第一个 URL 应为正面图 (含 Front 标识)。"""
        from ideaforge.agents.concept_designer import ConceptDesigner
        from shared.models import ProductConcept

        designer = ConceptDesigner()
        concept = ProductConcept(
            productName="测试产品",
            category="家居/香氛",
            designDesc="描述",
            material="材质",
            priceRange="49-79",
            ipDirection="三丽鸥·库洛米",
            sellingPoints=["卖点"],
            targetAudience={"ageRange": "18-25"},
        )
        result = designer.generate(concept)
        assert "Front" in result[0] or "front" in result[0].lower()

    def test_generate_second_url_is_scene_view(self) -> None:
        """第二个 URL 应为场景图 (含 Scene 标识)。"""
        from ideaforge.agents.concept_designer import ConceptDesigner
        from shared.models import ProductConcept

        designer = ConceptDesigner()
        concept = ProductConcept(
            productName="测试产品",
            category="家居/香氛",
            designDesc="描述",
            material="材质",
            priceRange="49-79",
            ipDirection="三丽鸥·库洛米",
            sellingPoints=["卖点"],
            targetAudience={"ageRange": "18-25"},
        )
        result = designer.generate(concept)
        assert "Scene" in result[1] or "scene" in result[1].lower()


# ==============================================================================
# 2. AgentOrchestrator 测试
# ==============================================================================


class TestAgentOrchestrator:
    """AgentOrchestrator 编排器测试 - 完整决策链路。"""

    def test_orchestrate_returns_list(self) -> None:
        """orchestrate 应返回列表。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        result = orchestrator.orchestrate(_make_signal())
        assert isinstance(result, list)

    def test_orchestrate_returns_at_least_three_cards(self) -> None:
        """orchestrate 应返回 ≥3 张 ProductIdeaCard。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        result = orchestrator.orchestrate(_make_signal())
        assert len(result) >= 3, f"编排器仅产出 {len(result)} 张卡, 期望 ≥3"

    def test_orchestrate_returns_product_idea_card_instances(self) -> None:
        """列表元素应为 ProductIdeaCard 实例。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        result = orchestrator.orchestrate(_make_signal())
        for card in result:
            assert isinstance(card, ProductIdeaCard)

    def test_orchestrate_all_sixteen_fields_populated(self) -> None:
        """每张卡应填充全部 16 个字段。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        cards = orchestrator.orchestrate(_make_signal())
        for card in cards:
            # 1. conceptId
            assert card.conceptId, "conceptId 为空"
            # 2. productName
            assert card.productName, "productName 为空"
            # 3. category
            assert card.category, "category 为空"
            # 4. designDesc
            assert card.designDesc, "designDesc 为空"
            # 5. material
            assert card.material, "material 为空"
            # 6. priceRange
            assert card.priceRange, "priceRange 为空"
            # 7. ipMatch
            assert isinstance(card.ipMatch, IPMatch), "ipMatch 不是 IPMatch 实例"
            # 8. sellingPoints
            assert isinstance(card.sellingPoints, list), "sellingPoints 不是列表"
            assert len(card.sellingPoints) >= 1, "sellingPoints 为空列表"
            # 9. hitScore
            assert 0.0 <= card.hitScore <= 1.0, f"hitScore 越界: {card.hitScore}"
            # 10. topFactors
            assert isinstance(card.topFactors, list), "topFactors 不是列表"
            assert len(card.topFactors) >= 1, "topFactors 为空列表"
            # 11. conceptImages
            assert isinstance(card.conceptImages, list), "conceptImages 不是列表"
            assert len(card.conceptImages) == 2, (
                f"conceptImages 长度 {len(card.conceptImages)}, 期望 2"
            )
            # 12. trendSource
            assert card.trendSource, "trendSource 为空"
            # 13. zGenMatchScore
            assert 0.0 <= card.zGenMatchScore <= 1.0, (
                f"zGenMatchScore 越界: {card.zGenMatchScore}"
            )
            # 14. targetAudience
            assert isinstance(card.targetAudience, dict), "targetAudience 不是字典"
            assert len(card.targetAudience) >= 1, "targetAudience 为空字典"
            # 15. regionFit
            assert isinstance(card.regionFit, dict), "regionFit 不是字典"
            assert len(card.regionFit) >= 1, "regionFit 为空字典"
            # 16. agentTrace
            assert isinstance(card.agentTrace, list), "agentTrace 不是列表"
            assert len(card.agentTrace) >= 3, (
                f"agentTrace 仅 {len(card.agentTrace)} 条, 期望 ≥3"
            )

    def test_orchestrate_ipmatch_is_ipmatch_instance(self) -> None:
        """每张卡的 ipMatch 应为 IPMatch 实例。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        cards = orchestrator.orchestrate(_make_signal())
        for card in cards:
            assert isinstance(card.ipMatch, IPMatch)

    def test_orchestrate_hitscore_in_valid_range(self) -> None:
        """每张卡的 hitScore 应在 [0, 1] 范围内。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        cards = orchestrator.orchestrate(_make_signal())
        for card in cards:
            assert 0.0 <= card.hitScore <= 1.0

    def test_orchestrate_topfactors_has_items(self) -> None:
        """每张卡的 topFactors 应非空。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        cards = orchestrator.orchestrate(_make_signal())
        for card in cards:
            assert len(card.topFactors) >= 1
            # 每项应含 feature 键
            for factor in card.topFactors:
                assert "feature" in factor, f"topFactor 缺少 feature 键: {factor}"

    def test_orchestrate_conceptimages_has_two_urls(self) -> None:
        """每张卡的 conceptImages 应含 2 个 URL。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        cards = orchestrator.orchestrate(_make_signal())
        for card in cards:
            assert len(card.conceptImages) == 2

    def test_orchestrate_agenttrace_records_each_step(self) -> None:
        """每张卡的 agentTrace 应记录每一步 (≥3 步)。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        cards = orchestrator.orchestrate(_make_signal())
        for card in cards:
            assert len(card.agentTrace) >= 3
            # 每条 trace 应含 agent / step / output 键
            for trace in card.agentTrace:
                assert "agent" in trace, f"agentTrace 条目缺少 agent 键: {trace}"
                assert "step" in trace, f"agentTrace 条目缺少 step 键: {trace}"

    def test_orchestrate_cards_sorted_by_hitscore_descending(self) -> None:
        """卡片应按 hitScore 降序排列。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        cards = orchestrator.orchestrate(_make_signal())
        scores = [c.hitScore for c in cards]
        assert scores == sorted(scores, reverse=True), (
            f"hitScore 未降序排列: {scores}"
        )

    def test_orchestrate_conceptid_format(self) -> None:
        """conceptId 应为 'CPT-2025-XXXX' 格式。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        cards = orchestrator.orchestrate(_make_signal())
        for card in cards:
            assert card.conceptId.startswith("CPT-"), (
                f"conceptId 格式异常: {card.conceptId}"
            )

    def test_orchestrate_conceptids_are_distinct(self) -> None:
        """不同卡片的 conceptId 应互不相同。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        cards = orchestrator.orchestrate(_make_signal())
        ids = [c.conceptId for c in cards]
        assert len(ids) == len(set(ids)), "conceptId 存在重复"

    def test_orchestrate_trend_source_matches_input(self) -> None:
        """卡片的 trendSource 应与输入趋势 topic 一致。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        trend = _make_signal(topic="Y2K千禧风穿搭")
        cards = orchestrator.orchestrate(trend)
        for card in cards:
            assert card.trendSource == "Y2K千禧风穿搭"

    def test_orchestrate_with_different_categories(self) -> None:
        """不同品类的趋势信号都能产出 ≥3 张卡。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        for category in ["家居/香氛", "美妆/个护", "服饰/穿搭", "玩具/文创"]:
            trend = _make_signal(
                topic=f"测试趋势_{category}",
                category=category,
            )
            cards = orchestrator.orchestrate(trend)
            assert len(cards) >= 3, f"品类 {category} 仅产出 {len(cards)} 张卡"

    def test_orchestrate_agenttrace_contains_all_agents(self) -> None:
        """agentTrace 应包含所有关键 Agent 的记录。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        cards = orchestrator.orchestrate(_make_signal())
        for card in cards:
            agents = [t.get("agent", "") for t in card.agentTrace]
            # 应至少包含 TrendAnalyst 和 ProductPlanner
            assert any("Trend" in a or "Analyst" in a for a in agents), (
                f"agentTrace 缺少 TrendAnalyst: {agents}"
            )
            assert any("Planner" in a for a in agents), (
                f"agentTrace 缺少 ProductPlanner: {agents}"
            )


# ==============================================================================
# 3. FunnelFilter 测试
# ==============================================================================


class TestFunnelFilter:
    """FunnelFilter 规模化漏斗测试。"""

    def test_filter_top100_filters_low_hitscore(self) -> None:
        """filter_top100 应过滤 hitScore ≤ 0.7 的卡片。"""
        from ideaforge.funnel import FunnelFilter

        funnel = FunnelFilter()
        cards = [
            _make_card(concept_id="CPT-001", hit_score=0.9),
            _make_card(concept_id="CPT-002", hit_score=0.5),
            _make_card(concept_id="CPT-003", hit_score=0.8),
            _make_card(concept_id="CPT-004", hit_score=0.3),
        ]
        result = funnel.filter_top100(cards)
        ids = [c.conceptId for c in result]
        assert "CPT-001" in ids
        assert "CPT-003" in ids
        assert "CPT-002" not in ids
        assert "CPT-004" not in ids

    def test_filter_top100_sorts_by_hitscore_descending(self) -> None:
        """filter_top100 应按 hitScore 降序排列。"""
        from ideaforge.funnel import FunnelFilter

        funnel = FunnelFilter()
        cards = [
            _make_card(concept_id="CPT-001", hit_score=0.75),
            _make_card(concept_id="CPT-002", hit_score=0.95),
            _make_card(concept_id="CPT-003", hit_score=0.85),
        ]
        result = funnel.filter_top100(cards)
        scores = [c.hitScore for c in result]
        assert scores == sorted(scores, reverse=True)

    def test_filter_top100_limits_to_100(self) -> None:
        """filter_top100 应限制最多 100 条。"""
        from ideaforge.funnel import FunnelFilter

        funnel = FunnelFilter()
        # 构造 150 张高分卡
        cards = [
            _make_card(
                concept_id=f"CPT-{i:04d}",
                hit_score=0.71 + i * 0.001,  # 0.711 ~ 0.860
            )
            for i in range(150)
        ]
        result = funnel.filter_top100(cards)
        assert len(result) <= 100
        assert len(result) == 100

    def test_filter_top100_empty_input(self) -> None:
        """filter_top100 空输入应返回空列表。"""
        from ideaforge.funnel import FunnelFilter

        funnel = FunnelFilter()
        result = funnel.filter_top100([])
        assert result == []

    def test_filter_top100_all_below_threshold(self) -> None:
        """全部卡片低于阈值时应返回空列表。"""
        from ideaforge.funnel import FunnelFilter

        funnel = FunnelFilter()
        cards = [
            _make_card(hit_score=0.5),
            _make_card(hit_score=0.6),
            _make_card(hit_score=0.69),
        ]
        result = funnel.filter_top100(cards)
        assert result == []

    def test_filter_top100_boundary_exactly_0_7(self) -> None:
        """hitScore 恰好 0.7 应被过滤 (严格大于 0.7)。"""
        from ideaforge.funnel import FunnelFilter

        funnel = FunnelFilter()
        cards = [
            _make_card(concept_id="CPT-001", hit_score=0.7),
            _make_card(concept_id="CPT-002", hit_score=0.71),
        ]
        result = funnel.filter_top100(cards)
        ids = [c.conceptId for c in result]
        assert "CPT-002" in ids
        assert "CPT-001" not in ids

    def test_batch_run_processes_multiple_trends(self) -> None:
        """batch_run 应处理多条趋势信号。"""
        from ideaforge.funnel import FunnelFilter
        from ideaforge.orchestrator import AgentOrchestrator

        funnel = FunnelFilter()
        orchestrator = AgentOrchestrator()
        trends = [
            _make_signal(topic="侘寂风家居", category="家居/香氛"),
            _make_signal(topic="Y2K穿搭", category="服饰/穿搭"),
        ]
        result = funnel.batch_run(trends, orchestrator)
        assert isinstance(result, list)
        # 所有返回的卡片都应满足 hitScore > 0.7 (如果有的话)
        for card in result:
            assert card.hitScore > 0.7

    def test_batch_run_empty_trends(self) -> None:
        """batch_run 空趋势列表应返回空列表。"""
        from ideaforge.funnel import FunnelFilter
        from ideaforge.orchestrator import AgentOrchestrator

        funnel = FunnelFilter()
        orchestrator = AgentOrchestrator()
        result = funnel.batch_run([], orchestrator)
        assert result == []

    def test_batch_run_single_trend(self) -> None:
        """batch_run 单条趋势应正常工作。"""
        from ideaforge.funnel import FunnelFilter
        from ideaforge.orchestrator import AgentOrchestrator

        funnel = FunnelFilter()
        orchestrator = AgentOrchestrator()
        trends = [_make_signal(topic="单条趋势测试")]
        result = funnel.batch_run(trends, orchestrator)
        assert isinstance(result, list)


# ==============================================================================
# 4. API 路由测试
# ==============================================================================


class TestAPIRoutes:
    """IdeaForge FastAPI 路由测试。"""

    def test_health_endpoint(self) -> None:
        """GET /health 应返回 200 + healthy 状态。"""
        from ideaforge.main import create_app

        app = create_app()
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ideaforge"

    def test_generate_endpoint_returns_cards(self) -> None:
        """POST /generate 应返回 ProductIdeaCard 列表。"""
        from ideaforge.main import create_app

        app = create_app()
        client = TestClient(app)
        response = client.post(
            "/generate",
            json={"topic": "侘寂风家居", "category": "家居/香氛"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3

    def test_generate_endpoint_cards_have_required_fields(self) -> None:
        """POST /generate 返回的卡片应含 16 个字段。"""
        from ideaforge.main import create_app

        app = create_app()
        client = TestClient(app)
        response = client.post(
            "/generate",
            json={"topic": "测试趋势", "category": "美妆/个护"},
        )
        assert response.status_code == 200
        cards = response.json()
        required_fields = {
            "conceptId", "productName", "category", "designDesc",
            "material", "priceRange", "ipMatch", "sellingPoints",
            "hitScore", "topFactors", "conceptImages", "trendSource",
            "zGenMatchScore", "targetAudience", "regionFit", "agentTrace",
        }
        for card in cards:
            assert required_fields.issubset(card.keys()), (
                f"卡片缺少字段: {required_fields - set(card.keys())}"
            )

    def test_generate_endpoint_with_full_trend_signal(self) -> None:
        """POST /generate 接受完整 TrendSignal 应正常工作。"""
        from ideaforge.main import create_app

        app = create_app()
        client = TestClient(app)
        full_signal = _make_signal(topic="完整信号测试").model_dump()
        # lifecycle/region 需为合法枚举值
        response = client.post("/generate", json=full_signal)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3

    def test_funnel_endpoint(self) -> None:
        """GET /funnel 应返回漏斗状态。"""
        from ideaforge.main import create_app

        app = create_app()
        client = TestClient(app)
        response = client.get("/funnel")
        assert response.status_code == 200
        data = response.json()
        # 应包含漏斗阶段信息
        assert "stages" in data or "funnel" in data or "levels" in data

    def test_funnel_endpoint_has_multiple_stages(self) -> None:
        """GET /funnel 应返回多个漏斗阶段 (万级→千级→百级→Top100)。"""
        from ideaforge.main import create_app

        app = create_app()
        client = TestClient(app)
        response = client.get("/funnel")
        assert response.status_code == 200
        data = response.json()
        # 提取阶段列表
        stages = data.get("stages", data.get("funnel", data.get("levels", [])))
        assert isinstance(stages, list)
        assert len(stages) >= 3, f"漏斗阶段不足: {stages}"


# ==============================================================================
# 5. 边界场景测试
# ==============================================================================


class TestEdgeCases:
    """边界场景测试 - 空输入、单条趋势、未知品类。"""

    def test_orchestrate_single_concept_category(self) -> None:
        """单条趋势信号经编排器应正常产出卡片。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        trend = _make_signal(topic="单一趋势")
        cards = orchestrator.orchestrate(trend)
        assert len(cards) >= 1

    def test_orchestrate_unknown_category(self) -> None:
        """未知品类应仍能产出 ≥3 张卡 (fallback 模板)。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        trend = _make_signal(
            topic="未知品类趋势",
            category="未知/新品类",
        )
        cards = orchestrator.orchestrate(trend)
        assert len(cards) >= 3

    def test_orchestrate_empty_zgen_tags(self) -> None:
        """空 zGenTags 的趋势应仍能正常编排。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        trend = _make_signal(z_gen_tags=[])
        cards = orchestrator.orchestrate(trend)
        assert len(cards) >= 3
        for card in cards:
            assert 0.0 <= card.zGenMatchScore <= 1.0

    def test_orchestrate_declining_lifecycle(self) -> None:
        """declining 生命周期趋势应仍能正常编排。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        trend = _make_signal(lifecycle="declining")
        cards = orchestrator.orchestrate(trend)
        assert len(cards) >= 3

    def test_orchestrate_with_cross_region_diff(self) -> None:
        """含跨区域差异的趋势应正常编排, regionFit 非空。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        trend = _make_signal(
            region="china",
            lifecycle="rising",
            cross_region_diff={"us": "peak", "eu": "declining", "sea": "nascent"},
        )
        cards = orchestrator.orchestrate(trend)
        assert len(cards) >= 3
        for card in cards:
            assert len(card.regionFit) >= 1

    def test_batch_run_with_mixed_trends(self) -> None:
        """batch_run 处理混合品类趋势应正常工作。"""
        from ideaforge.funnel import FunnelFilter
        from ideaforge.orchestrator import AgentOrchestrator

        funnel = FunnelFilter()
        orchestrator = AgentOrchestrator()
        trends = [
            _make_signal(topic="家居趋势", category="家居/香氛"),
            _make_signal(topic="美妆趋势", category="美妆/个护"),
            _make_signal(topic="穿搭趋势", category="服饰/穿搭"),
        ]
        result = funnel.batch_run(trends, orchestrator)
        assert isinstance(result, list)
        # 所有返回的卡片 (如果有) 都应满足 hitScore > 0.7
        for card in result:
            assert card.hitScore > 0.7

    def test_orchestrate_ipmatch_has_valid_ip_name(self) -> None:
        """编排器产出的 ipMatch 应含有效 IP 名称。"""
        from ideaforge.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator()
        trend = _make_signal(category="家居/香氛")
        cards = orchestrator.orchestrate(trend)
        for card in cards:
            assert card.ipMatch.ipName, "ipMatch.ipName 为空"
            assert card.ipMatch.ipPowerScore >= 0
            assert 0.0 <= card.ipMatch.matchScore <= 1.0

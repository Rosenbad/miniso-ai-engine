# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - Agent 1 趋势分析师 + Agent 2 产品策划师 (Task 9)
# ==============================================================================
# 对应 Task 9: 决策推理层 Agent 1 (TrendAnalyst) + Agent 2 (ProductPlanner)
# 覆盖:
#   1. TrendAnalyst.analyze   - TrendSignal → ProductDirection (6 字段)
#      品类/风格/受众/价格带/Z世代标签/跨区域建议
#   2. ProductPlanner.generate - ProductDirection → ProductConcept[] (≥3, 8 字段)
#      名称/材质/价格/IP方向/卖点/受众
#   3. 边界场景               - 空 zGenTags / 空 crossRegionDiff / 未知品类
#   4. 生命周期建议           - rising/peak/declining → 主推/观望
#   5. 集成测试               - TrendAnalyst 输出 → ProductPlanner 输入
#
# 测试策略 (TDD):
#   Step 1: 编写测试 (本文件)
#   Step 2: 验证失败 (Agent 模块尚未创建)
#   Step 3: 实现 TrendAnalyst
#   Step 4: 实现 ProductPlanner
#   Step 5: 验证通过
# ==============================================================================

"""
测试 Agent 1 (TrendAnalyst 趋势分析师) 与 Agent 2 (ProductPlanner 产品策划师)。

测试覆盖 (TDD):
  - TrendAnalyst.analyze: TrendSignal → ProductDirection (6 字段全部填充)
    * category 风格调性 / 目标人群 / 价格带 / Z世代标签 / 跨区域适配建议
  - ProductPlanner.generate: ProductDirection → List[ProductConcept] (≥3, 8 字段)
    * 产品名 / 品类 / 设计描述 / 材质 / 价格 / IP方向 / 卖点 / 受众
  - 边界场景: 空 zGenTags / 空 crossRegionDiff / 未知品类 (fallback 模板)
  - 生命周期: rising/peak/declining 各阶段跨区域建议映射
  - 集成测试: Agent 1 输出直接喂入 Agent 2 验证协作链路

环境说明:
  - 规则/模板生成, 无需 LLM API 调用
  - 复用 shared.models 中已定义的 TrendSignal / ProductDirection / ProductConcept
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from shared.models import ProductConcept, ProductDirection, TrendSignal


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


def _parse_range(price_range: str) -> Tuple[float, float]:
    """解析价格区间字符串 'lo-hi' → (lo, hi)。

    用于测试中比较价格区间是否重叠/合理。
    """
    parts = price_range.split("-")
    assert len(parts) == 2, f"价格区间格式异常: {price_range}"
    lo = float(parts[0].strip())
    hi = float(parts[1].strip())
    return lo, hi


def _ranges_overlap(a: str, b: str) -> bool:
    """判断两个价格区间是否重叠 (含相邻)。"""
    a_lo, a_hi = _parse_range(a)
    b_lo, b_hi = _parse_range(b)
    return a_lo <= b_hi and b_lo <= a_hi


# ==============================================================================
# 1. TrendAnalyst.analyze 基础功能
# ==============================================================================


class TestTrendAnalystBasic:
    """TrendAnalyst.analyze 基础测试 - 返回 ProductDirection (6 字段全部填充)。"""

    def test_analyze_returns_product_direction(self) -> None:
        """analyze 应返回 ProductDirection 实例。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        result = analyst.analyze(_make_signal())
        assert isinstance(result, ProductDirection)

    def test_analyze_category_matches_trend(self) -> None:
        """ProductDirection.category 应与 trend.category 一致。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(category="美妆/个护")
        result = analyst.analyze(trend)
        assert result.category == "美妆/个护"

    def test_analyze_zgen_tags_passed_through(self) -> None:
        """ProductDirection.zGenTags 应从 trend 透传。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        tags = ["Y2K", "多巴胺", "复古"]
        trend = _make_signal(z_gen_tags=tags)
        result = analyst.analyze(trend)
        assert result.zGenTags == tags

    def test_analyze_style_tone_non_empty(self) -> None:
        """ProductDirection.styleTone 应非空。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        result = analyst.analyze(_make_signal())
        assert result.styleTone
        assert len(result.styleTone) > 0

    def test_analyze_price_range_is_valid_range_string(self) -> None:
        """ProductDirection.priceRange 应为合法区间字符串 'lo-hi'。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        result = analyst.analyze(_make_signal())
        assert "-" in result.priceRange
        lo, hi = _parse_range(result.priceRange)
        assert 0 < lo <= hi, f"价格区间不合理: {result.priceRange}"

    def test_analyze_target_audience_has_required_keys(self) -> None:
        """targetAudience 应包含 ageRange/aesthetic/spendingPower 三个键。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        result = analyst.analyze(_make_signal())
        assert "ageRange" in result.targetAudience
        assert "aesthetic" in result.targetAudience
        assert "spendingPower" in result.targetAudience

    def test_analyze_target_audience_passes_through_trend_values(self) -> None:
        """targetAudience 应透传 trend.targetAudience 的值。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        audience = {
            "ageRange": "25-30",
            "aesthetic": "极简",
            "spendingPower": "高",
        }
        trend = _make_signal(target_audience=audience)
        result = analyst.analyze(trend)
        assert result.targetAudience["ageRange"] == "25-30"
        assert result.targetAudience["spendingPower"] == "高"

    def test_analyze_cross_region_advice_is_dict(self) -> None:
        """crossRegionAdvice 应为字典类型。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        result = analyst.analyze(_make_signal())
        assert isinstance(result.crossRegionAdvice, dict)

    def test_analyze_all_six_fields_populated(self) -> None:
        """analyze 应填充 ProductDirection 全部 6 个字段。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        result = analyst.analyze(_make_signal())
        assert result.category
        assert result.styleTone
        assert result.targetAudience is not None
        assert result.priceRange
        assert result.zGenTags is not None  # 可为空列表但字段存在
        assert result.crossRegionAdvice is not None

    def test_analyze_style_tone_reflects_zgen_tags(self) -> None:
        """zGenTags 含 '侘寂' 时 styleTone 应反映侘寂风格。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(z_gen_tags=["侘寂", "自然系"], topic="侘寂风家居")
        result = analyst.analyze(trend)
        assert "侘寂" in result.styleTone


# ==============================================================================
# 2. TrendAnalyst 跨区域建议 (crossRegionAdvice) - 生命周期映射
# ==============================================================================


class TestTrendAnalystCrossRegionAdvice:
    """跨区域建议测试 - 基于 lifecycle + crossRegionDiff 生成主推/次推/观望。"""

    def test_rising_lifecycle_current_region_main_push(self) -> None:
        """trend.lifecycle='rising' → 当前区域建议为 '主推'。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(region="china", lifecycle="rising")
        result = analyst.analyze(trend)
        assert result.crossRegionAdvice.get("china") == "主推"

    def test_peak_lifecycle_current_region_main_push(self) -> None:
        """trend.lifecycle='peak' → 当前区域建议为 '主推'。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(region="china", lifecycle="peak")
        result = analyst.analyze(trend)
        assert result.crossRegionAdvice.get("china") == "主推"

    def test_declining_lifecycle_current_region_watch(self) -> None:
        """trend.lifecycle='declining' → 当前区域建议为 '观望'。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(region="china", lifecycle="declining")
        result = analyst.analyze(trend)
        assert result.crossRegionAdvice.get("china") == "观望"

    def test_cross_region_diff_peak_maps_to_main_push(self) -> None:
        """crossRegionDiff 中某区域值为 'peak' → 该区域建议 '主推'。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(
            region="china",
            lifecycle="rising",
            cross_region_diff={"us": "peak"},
        )
        result = analyst.analyze(trend)
        assert result.crossRegionAdvice.get("us") == "主推"

    def test_cross_region_diff_declining_maps_to_watch(self) -> None:
        """crossRegionDiff 中某区域值为 'declining' → 该区域建议 '观望'。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(
            region="china",
            lifecycle="peak",
            cross_region_diff={"eu": "declining"},
        )
        result = analyst.analyze(trend)
        assert result.crossRegionAdvice.get("eu") == "观望"

    def test_cross_region_diff_rising_maps_to_main_push(self) -> None:
        """crossRegionDiff 中某区域值为 'rising' → 该区域建议 '主推'。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(
            region="us",
            lifecycle="peak",
            cross_region_diff={"sea": "rising"},
        )
        result = analyst.analyze(trend)
        assert result.crossRegionAdvice.get("sea") == "主推"

    def test_cross_region_diff_nascent_maps_to_secondary(self) -> None:
        """crossRegionDiff 中某区域值为 'nascent' → 该区域建议 '次推'。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(
            region="china",
            lifecycle="peak",
            cross_region_diff={"sea": "nascent"},
        )
        result = analyst.analyze(trend)
        assert result.crossRegionAdvice.get("sea") == "次推"

    def test_cross_region_advice_includes_current_and_diff_regions(self) -> None:
        """crossRegionAdvice 应同时包含当前区域与 crossRegionDiff 中的区域。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(
            region="china",
            lifecycle="rising",
            cross_region_diff={"us": "peak", "eu": "declining"},
        )
        result = analyst.analyze(trend)
        assert "china" in result.crossRegionAdvice
        assert "us" in result.crossRegionAdvice
        assert "eu" in result.crossRegionAdvice

    def test_rising_with_other_peak_follow_up_window(self) -> None:
        """rising + 其他区域 peak (跟进窗口) → 当前区域 '主推'。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(
            region="china",
            lifecycle="rising",
            cross_region_diff={"us": "peak"},
        )
        result = analyst.analyze(trend)
        # 跟进窗口: 当前 rising 区域主推 (趋势已在他区验证)
        assert result.crossRegionAdvice["china"] == "主推"
        assert result.crossRegionAdvice["us"] == "主推"


# ==============================================================================
# 3. TrendAnalyst 边界场景
# ==============================================================================


class TestTrendAnalystEdgeCases:
    """TrendAnalyst 边界场景 - 空 zGenTags / 空 crossRegionDiff / 受众缺失。"""

    def test_empty_zgen_tags_still_returns_direction(self) -> None:
        """空 zGenTags 时仍应返回有效 ProductDirection。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(z_gen_tags=[])
        result = analyst.analyze(trend)
        assert isinstance(result, ProductDirection)
        assert result.zGenTags == []

    def test_empty_zgen_tags_style_tone_still_non_empty(self) -> None:
        """空 zGenTags 时 styleTone 仍应有默认值 (非空)。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(z_gen_tags=[])
        result = analyst.analyze(trend)
        assert result.styleTone

    def test_empty_cross_region_diff_only_current_region(self) -> None:
        """空 crossRegionDiff 时 crossRegionAdvice 仅含当前区域。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(
            region="china", lifecycle="rising", cross_region_diff={}
        )
        result = analyst.analyze(trend)
        assert "china" in result.crossRegionAdvice
        assert result.crossRegionAdvice["china"] == "主推"

    def test_target_audience_missing_keys_filled_with_defaults(self) -> None:
        """trend.targetAudience 缺少键时应补全默认值。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(target_audience={"ageRange": "20-28"})
        result = analyst.analyze(trend)
        # 缺失的 aesthetic / spendingPower 应被补全
        assert "ageRange" in result.targetAudience
        assert "aesthetic" in result.targetAudience
        assert "spendingPower" in result.targetAudience

    def test_unknown_category_still_returns_direction(self) -> None:
        """未知品类时仍应返回有效 ProductDirection (使用默认价格带)。"""
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        trend = _make_signal(category="未知/品类")
        result = analyst.analyze(trend)
        assert isinstance(result, ProductDirection)
        assert result.category == "未知/品类"
        assert "-" in result.priceRange


# ==============================================================================
# 4. ProductPlanner.generate 基础功能
# ==============================================================================


class TestProductPlannerBasic:
    """ProductPlanner.generate 基础测试 - 返回 ≥3 个 ProductConcept (8 字段)。"""

    def test_generate_returns_list(self) -> None:
        """generate 应返回列表。"""
        from ideaforge.agents.product_planner import ProductPlanner

        planner = ProductPlanner()
        direction = ProductDirection(
            category="家居/香氛",
            styleTone="侘寂自然",
            targetAudience={
                "ageRange": "18-25",
                "aesthetic": "侘寂",
                "spendingPower": "中",
            },
            priceRange="39-99",
            zGenTags=["侘寂", "自然系"],
            crossRegionAdvice={"china": "主推"},
        )
        result = planner.generate(direction)
        assert isinstance(result, list)

    def test_generate_returns_at_least_three_concepts(self) -> None:
        """generate 应返回 ≥3 个产品概念。"""
        from ideaforge.agents.product_planner import ProductPlanner

        planner = ProductPlanner()
        direction = ProductDirection(
            category="家居/香氛",
            styleTone="侘寂自然",
            targetAudience={
                "ageRange": "18-25",
                "aesthetic": "侘寂",
                "spendingPower": "中",
            },
            priceRange="39-99",
            zGenTags=["侘寂"],
            crossRegionAdvice={"china": "主推"},
        )
        result = planner.generate(direction)
        assert len(result) >= 3

    def test_generate_returns_product_concept_instances(self) -> None:
        """列表元素应为 ProductConcept 实例。"""
        from ideaforge.agents.product_planner import ProductPlanner

        planner = ProductPlanner()
        direction = ProductDirection(
            category="家居/香氛",
            styleTone="侘寂自然",
            targetAudience={
                "ageRange": "18-25",
                "aesthetic": "侘寂",
                "spendingPower": "中",
            },
            priceRange="39-99",
            zGenTags=["侘寂"],
            crossRegionAdvice={"china": "主推"},
        )
        result = planner.generate(direction)
        for concept in result:
            assert isinstance(concept, ProductConcept)

    def test_generate_all_eight_fields_populated(self) -> None:
        """每个概念应填充全部 8 个字段。"""
        from ideaforge.agents.product_planner import ProductPlanner

        planner = ProductPlanner()
        direction = ProductDirection(
            category="家居/香氛",
            styleTone="侘寂自然",
            targetAudience={
                "ageRange": "18-25",
                "aesthetic": "侘寂",
                "spendingPower": "中",
            },
            priceRange="39-99",
            zGenTags=["侘寂"],
            crossRegionAdvice={"china": "主推"},
        )
        result = planner.generate(direction)
        for concept in result:
            assert concept.productName
            assert concept.category
            assert concept.designDesc
            assert concept.material
            assert concept.priceRange
            assert concept.ipDirection
            assert isinstance(concept.sellingPoints, list)
            assert isinstance(concept.targetAudience, dict)

    def test_generate_category_matches_direction(self) -> None:
        """每个概念的 category 应与 direction.category 一致。"""
        from ideaforge.agents.product_planner import ProductPlanner

        planner = ProductPlanner()
        direction = ProductDirection(
            category="美妆/个护",
            styleTone="少女心",
            targetAudience={
                "ageRange": "18-25",
                "aesthetic": "甜美",
                "spendingPower": "中",
            },
            priceRange="29-99",
            zGenTags=["Y2K"],
            crossRegionAdvice={"china": "主推"},
        )
        result = planner.generate(direction)
        for concept in result:
            assert concept.category == "美妆/个护"

    def test_generate_selling_points_non_empty(self) -> None:
        """每个概念的 sellingPoints 应非空。"""
        from ideaforge.agents.product_planner import ProductPlanner

        planner = ProductPlanner()
        direction = ProductDirection(
            category="家居/香氛",
            styleTone="侘寂自然",
            targetAudience={
                "ageRange": "18-25",
                "aesthetic": "侘寂",
                "spendingPower": "中",
            },
            priceRange="39-99",
            zGenTags=["侘寂"],
            crossRegionAdvice={"china": "主推"},
        )
        result = planner.generate(direction)
        for concept in result:
            assert len(concept.sellingPoints) >= 1

    def test_generate_target_audience_passed_through(self) -> None:
        """概念的 targetAudience 应从 direction 透传。"""
        from ideaforge.agents.product_planner import ProductPlanner

        planner = ProductPlanner()
        audience = {
            "ageRange": "22-30",
            "aesthetic": "侘寂",
            "spendingPower": "高",
        }
        direction = ProductDirection(
            category="家居/香氛",
            styleTone="侘寂自然",
            targetAudience=audience,
            priceRange="39-99",
            zGenTags=["侘寂"],
            crossRegionAdvice={"china": "主推"},
        )
        result = planner.generate(direction)
        for concept in result:
            assert concept.targetAudience == audience

    def test_generate_product_names_are_distinct(self) -> None:
        """不同概念的产品名应互不相同。"""
        from ideaforge.agents.product_planner import ProductPlanner

        planner = ProductPlanner()
        direction = ProductDirection(
            category="家居/香氛",
            styleTone="侘寂自然",
            targetAudience={
                "ageRange": "18-25",
                "aesthetic": "侘寂",
                "spendingPower": "中",
            },
            priceRange="39-99",
            zGenTags=["侘寂"],
            crossRegionAdvice={"china": "主推"},
        )
        result = planner.generate(direction)
        names = [c.productName for c in result]
        assert len(names) == len(set(names)), "产品名存在重复"

    def test_generate_price_range_within_or_near_direction(self) -> None:
        """概念价格区间应与 direction.priceRange 重叠或在合理范围内。"""
        from ideaforge.agents.product_planner import ProductPlanner

        planner = ProductPlanner()
        direction = ProductDirection(
            category="家居/香氛",
            styleTone="侘寂自然",
            targetAudience={
                "ageRange": "18-25",
                "aesthetic": "侘寂",
                "spendingPower": "中",
            },
            priceRange="39-99",
            zGenTags=["侘寂"],
            crossRegionAdvice={"china": "主推"},
        )
        result = planner.generate(direction)
        d_lo, d_hi = _parse_range(direction.priceRange)
        for concept in result:
            c_lo, c_hi = _parse_range(concept.priceRange)
            # 概念价格应在 direction 区间附近 (允许一定浮动)
            # 判定: 重叠 或 落在 [d_lo*0.5, d_hi*1.5] 区间内
            overlaps = _ranges_overlap(concept.priceRange, direction.priceRange)
            within_band = (c_lo >= d_lo * 0.5) and (c_hi <= d_hi * 1.5)
            assert overlaps or within_band, (
                f"概念价格 {concept.priceRange} 与方向 {direction.priceRange} 不匹配"
            )


# ==============================================================================
# 5. ProductPlanner 品类模板
# ==============================================================================


class TestProductPlannerCategories:
    """ProductPlanner 品类模板测试 - 多品类均能生成 ≥3 概念。"""

    @pytest.mark.parametrize(
        "category, price_range",
        [
            ("家居/香氛", "39-99"),
            ("家居/装饰", "39-129"),
            ("美妆/个护", "29-99"),
            ("服饰/穿搭", "59-199"),
            ("数码/配件", "59-299"),
            ("玩具/文创", "19-99"),
        ],
    )
    def test_each_category_generates_at_least_three_concepts(
        self, category: str, price_range: str
    ) -> None:
        """6 大品类均应生成 ≥3 个产品概念。"""
        from ideaforge.agents.product_planner import ProductPlanner

        planner = ProductPlanner()
        direction = ProductDirection(
            category=category,
            styleTone="测试风格",
            targetAudience={
                "ageRange": "18-25",
                "aesthetic": "自然",
                "spendingPower": "中",
            },
            priceRange=price_range,
            zGenTags=["测试"],
            crossRegionAdvice={"china": "主推"},
        )
        result = planner.generate(direction)
        assert len(result) >= 3, f"品类 {category} 仅生成 {len(result)} 个概念"
        for concept in result:
            assert concept.category == category

    def test_unknown_category_uses_fallback_template(self) -> None:
        """未知品类应使用 fallback 模板仍生成 ≥3 个概念。"""
        from ideaforge.agents.product_planner import ProductPlanner

        planner = ProductPlanner()
        direction = ProductDirection(
            category="未知/新品类",
            styleTone="探索风格",
            targetAudience={
                "ageRange": "18-25",
                "aesthetic": "未知",
                "spendingPower": "中",
            },
            priceRange="39-129",
            zGenTags=["探索"],
            crossRegionAdvice={"china": "次推"},
        )
        result = planner.generate(direction)
        assert len(result) >= 3
        for concept in result:
            assert concept.category == "未知/新品类"
            assert concept.productName

    def test_ip_direction_non_empty_for_known_category(self) -> None:
        """已知品类的 ipDirection 应非空 (给出 IP 联名建议)。"""
        from ideaforge.agents.product_planner import ProductPlanner

        planner = ProductPlanner()
        direction = ProductDirection(
            category="美妆/个护",
            styleTone="少女心",
            targetAudience={
                "ageRange": "18-25",
                "aesthetic": "甜美",
                "spendingPower": "中",
            },
            priceRange="29-99",
            zGenTags=["Y2K"],
            crossRegionAdvice={"china": "主推"},
        )
        result = planner.generate(direction)
        for concept in result:
            assert concept.ipDirection


# ==============================================================================
# 6. 集成测试 - TrendAnalyst → ProductPlanner 协作链路
# ==============================================================================


class TestAgentIntegration:
    """集成测试 - Agent 1 输出直接作为 Agent 2 输入, 验证协作链路。"""

    def test_analyst_output_feeds_planner_input(self) -> None:
        """TrendAnalyst 输出应可直接作为 ProductPlanner 输入生成概念。"""
        from ideaforge.agents.product_planner import ProductPlanner
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        planner = ProductPlanner()

        trend = _make_signal(
            topic="侘寂风家居",
            category="家居/香氛",
            lifecycle="rising",
            z_gen_tags=["侘寂", "自然系"],
            cross_region_diff={"us": "peak"},
        )
        direction = analyst.analyze(trend)
        concepts = planner.generate(direction)

        assert isinstance(direction, ProductDirection)
        assert len(concepts) >= 3
        for concept in concepts:
            assert isinstance(concept, ProductConcept)
            assert concept.category == direction.category

    def test_full_pipeline_produces_distinct_concepts(self) -> None:
        """完整链路应产生互不重复的产品概念。"""
        from ideaforge.agents.product_planner import ProductPlanner
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        planner = ProductPlanner()

        trend = _make_signal(category="美妆/个护", lifecycle="peak")
        direction = analyst.analyze(trend)
        concepts = planner.generate(direction)

        names = [c.productName for c in concepts]
        assert len(names) == len(set(names))

    def test_pipeline_with_empty_zgen_tags(self) -> None:
        """空 zGenTags 的趋势信号走完整链路应正常产出概念。"""
        from ideaforge.agents.product_planner import ProductPlanner
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        planner = ProductPlanner()

        trend = _make_signal(z_gen_tags=[], lifecycle="rising")
        direction = analyst.analyze(trend)
        concepts = planner.generate(direction)
        assert len(concepts) >= 3

    def test_pipeline_with_declining_lifecycle(self) -> None:
        """declining 生命周期趋势走完整链路应正常产出概念。"""
        from ideaforge.agents.product_planner import ProductPlanner
        from ideaforge.agents.trend_analyst import TrendAnalyst

        analyst = TrendAnalyst()
        planner = ProductPlanner()

        trend = _make_signal(lifecycle="declining", category="服饰/穿搭")
        direction = analyst.analyze(trend)
        # declining 区域应为观望
        assert direction.crossRegionAdvice.get("china") == "观望"
        concepts = planner.generate(direction)
        assert len(concepts) >= 3

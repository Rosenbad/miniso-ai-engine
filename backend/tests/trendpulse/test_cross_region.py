# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 跨区域趋势对比引擎 + TrendPulse API 测试 (Task 7)
# ==============================================================================
# 对应 Task 7: 跨区域趋势对比引擎 + TrendPulse API
# 覆盖:
#   1. CrossRegionComparator        - 扩散路径检测 / 跟进窗口 / 区域热度图 / 本地化建议
#   2. FastAPI Routes               - /trends /trends/{topic} /cross-region/{topic}
#                                     /collect /health
#
# 测试策略 (TDD):
#   1. 扩散路径检测    - 按 lifecycle 阶段排序 (declining → peak → rising)
#   2. 跟进窗口识别    - US peak + CN rising → CN 跟进窗口
#   3. 区域热度图      - {region: heatScore} 输出
#   4. 本地化建议      - 海外趋势进入中国时给出价格/材质/文化适配建议
#   5. 边界场景        - 单区域 / 全同 lifecycle / 空输入
#   6. API 路由        - TestClient 测试全部 FastAPI 路由
# ==============================================================================

"""
测试跨区域趋势对比引擎与 TrendPulse API。

测试覆盖 (TDD):
  - CrossRegionComparator: 扩散路径 / 跟进窗口 / 热度图 / 本地化建议 / 边界场景
  - FastAPI 路由: /health /trends /trends/{topic} /cross-region/{topic} /collect

环境说明:
  - API 测试使用 fastapi.testclient.TestClient (基于 httpx, 同步)
  - Demo 数据在 create_app() 启动时种子化, 无需外部依赖
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from shared.models import TrendSignal
from trendpulse.cross_region import CrossRegionComparator
from trendpulse.main import create_app


# ==============================================================================
# 测试辅助 - 构造 TrendSignal
# ==============================================================================


def _make_signal(
    topic: str = "侘寂风家居",
    region: str = "china",
    lifecycle: str = "rising",
    heat_score: float = 50.0,
    growth_rate: float = 20.0,
    category: str = "家居/装饰",
    sentiment: float = 0.5,
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
        relatedKeywords=related_keywords or ["测试关键词"],
        sourceBreakdown={"test": 100},
        region=region,  # type: ignore[arg-type]
        zGenTags=z_gen_tags or [],
        targetAudience=target_audience
        or {
            "ageRange": "18-25",
            "aesthetic": "侘寂",
            "spendingPower": "中",
        },
        crossRegionDiff=cross_region_diff or {},
    )


# ==============================================================================
# 1. 扩散路径检测 (Diffusion Path Detection)
# ==============================================================================


class TestDiffusionPathDetection:
    """扩散路径检测测试 - 按 lifecycle 阶段排序输出。"""

    def test_diffusion_path_sorted_by_lifecycle(self) -> None:
        """扩散路径应按 lifecycle 排序: declining(0) → peak(1) → rising(2)。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="china", lifecycle="rising", heat_score=45.0),
            _make_signal(region="us", lifecycle="peak", heat_score=88.0),
            _make_signal(region="eu", lifecycle="declining", heat_score=30.0),
        ]
        path = comparator.detect_diffusion_path(signals)
        assert len(path) == 3
        # declining(0) → peak(1) → rising(2): eu → us → china
        assert path[0]["region"] == "eu"
        assert path[1]["region"] == "us"
        assert path[2]["region"] == "china"

    def test_diffusion_path_structure(self) -> None:
        """每个扩散路径节点应含 region/lifecycle/heatScore/role 字段。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="peak", heat_score=88.0),
            _make_signal(region="china", lifecycle="rising", heat_score=45.0),
        ]
        path = comparator.detect_diffusion_path(signals)
        for node in path:
            assert "region" in node
            assert "lifecycle" in node
            assert "heatScore" in node
            assert "role" in node

    def test_diffusion_path_assigns_roles_by_lifecycle(self) -> None:
        """role 应反映 lifecycle 语义: declining=origin, peak=peak, rising=follower。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="eu", lifecycle="declining", heat_score=30.0),
            _make_signal(region="us", lifecycle="peak", heat_score=88.0),
            _make_signal(region="china", lifecycle="rising", heat_score=45.0),
        ]
        path = comparator.detect_diffusion_path(signals)
        roles = {node["region"]: node["role"] for node in path}
        assert roles["eu"] == "origin"
        assert roles["us"] == "peak"
        assert roles["china"] == "follower"

    def test_diffusion_path_preserves_heat_scores(self) -> None:
        """扩散路径节点应保留对应区域的 heatScore。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="peak", heat_score=88.0),
            _make_signal(region="china", lifecycle="rising", heat_score=45.0),
        ]
        path = comparator.detect_diffusion_path(signals)
        heat_map = {node["region"]: node["heatScore"] for node in path}
        assert heat_map["us"] == 88.0
        assert heat_map["china"] == 45.0

    def test_diffusion_path_peak_before_rising(self) -> None:
        """peak 阶段区域应排在 rising 阶段区域之前 (扩散方向)。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="china", lifecycle="rising"),
            _make_signal(region="us", lifecycle="peak"),
        ]
        path = comparator.detect_diffusion_path(signals)
        # peak(rank 1) 在 rising(rank 2) 之前
        assert path[0]["region"] == "us"
        assert path[1]["region"] == "china"

    def test_diffusion_path_stable_order_within_same_lifecycle(self) -> None:
        """同 lifecycle 阶段的多个区域应按 heatScore 降序排列 (热度高优先)。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="sea", lifecycle="rising", heat_score=30.0),
            _make_signal(region="china", lifecycle="rising", heat_score=62.0),
            _make_signal(region="us", lifecycle="rising", heat_score=80.0),
        ]
        path = comparator.detect_diffusion_path(signals)
        # 同为 rising, 按 heatScore 降序: us(80) → china(62) → sea(30)
        assert path[0]["region"] == "us"
        assert path[1]["region"] == "china"
        assert path[2]["region"] == "sea"


# ==============================================================================
# 2. 跟进窗口识别 (Follow-up Window)
# ==============================================================================


class TestFollowUpWindow:
    """跟进窗口识别测试 - US peak + CN rising → CN 跟进窗口。"""

    def test_us_peak_cn_rising_cn_has_follow_up_window(self) -> None:
        """US peak + CN rising → CN 有跟进窗口。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(
                region="us", lifecycle="peak", heat_score=88.0, predict_window="2-4周"
            ),
            _make_signal(
                region="china", lifecycle="rising", heat_score=45.0, predict_window="2-4周"
            ),
        ]
        windows = comparator.detect_follow_up_windows(signals)
        assert len(windows) == 1
        w = windows[0]
        assert w["from_region"] == "us"
        assert w["to_region"] == "china"
        assert w["from_lifecycle"] == "peak"
        assert w["to_lifecycle"] == "rising"
        assert w["window"] == "2-4周"

    def test_follow_up_window_structure(self) -> None:
        """跟进窗口应含 from_region/to_region/from_lifecycle/to_lifecycle/window。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="peak"),
            _make_signal(region="china", lifecycle="rising"),
        ]
        windows = comparator.detect_follow_up_windows(signals)
        assert len(windows) == 1
        w = windows[0]
        for key in (
            "from_region",
            "to_region",
            "from_lifecycle",
            "to_lifecycle",
            "window",
        ):
            assert key in w, f"跟进窗口缺少字段 {key}"

    def test_declining_to_rising_also_follow_up(self) -> None:
        """declining + rising 组合也应识别为跟进窗口 (趋势已成熟扩散)。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="eu", lifecycle="declining"),
            _make_signal(region="china", lifecycle="rising"),
        ]
        windows = comparator.detect_follow_up_windows(signals)
        assert len(windows) == 1
        assert windows[0]["from_region"] == "eu"
        assert windows[0]["to_region"] == "china"

    def test_multiple_follow_up_windows(self) -> None:
        """一个 peak 区域 + 多个 rising 区域 → 多个跟进窗口。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="peak"),
            _make_signal(region="china", lifecycle="rising"),
            _make_signal(region="sea", lifecycle="rising"),
        ]
        windows = comparator.detect_follow_up_windows(signals)
        to_regions = {w["to_region"] for w in windows}
        assert to_regions == {"china", "sea"}
        for w in windows:
            assert w["from_region"] == "us"

    def test_no_follow_up_window_when_all_peak(self) -> None:
        """所有区域同为 peak 时应无跟进窗口。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="peak"),
            _make_signal(region="china", lifecycle="peak"),
        ]
        windows = comparator.detect_follow_up_windows(signals)
        assert windows == []

    def test_no_follow_up_window_when_all_rising(self) -> None:
        """所有区域同为 rising 时应无跟进窗口。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="rising"),
            _make_signal(region="china", lifecycle="rising"),
        ]
        windows = comparator.detect_follow_up_windows(signals)
        assert windows == []

    def test_no_follow_up_window_when_cn_ahead(self) -> None:
        """CN peak + US rising → US 跟进 CN, 不是 CN 跟进 (窗口在 US 侧)。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="china", lifecycle="peak"),
            _make_signal(region="us", lifecycle="rising"),
        ]
        windows = comparator.detect_follow_up_windows(signals)
        assert len(windows) == 1
        assert windows[0]["from_region"] == "china"
        assert windows[0]["to_region"] == "us"


# ==============================================================================
# 3. 区域热度图 (Regional Heat Map)
# ==============================================================================


class TestHeatMap:
    """区域热度图测试 - {region: heatScore} 输出。"""

    def test_heat_map_contains_all_regions(self) -> None:
        """热度图应包含所有输入区域。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", heat_score=88.0),
            _make_signal(region="china", heat_score=45.0),
            _make_signal(region="sea", heat_score=30.0),
        ]
        heat_map = comparator.generate_heat_map(signals)
        assert set(heat_map.keys()) == {"us", "china", "sea"}

    def test_heat_map_values_match_signals(self) -> None:
        """热度图的值应与对应信号 heatScore 一致。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", heat_score=88.5),
            _make_signal(region="china", heat_score=45.2),
        ]
        heat_map = comparator.generate_heat_map(signals)
        assert heat_map["us"] == 88.5
        assert heat_map["china"] == 45.2

    def test_heat_map_last_signal_wins_on_duplicate_region(self) -> None:
        """同区域多条信号时, 取最后一条 (调用方可按需去重)。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", heat_score=50.0),
            _make_signal(region="us", heat_score=88.0),
        ]
        heat_map = comparator.generate_heat_map(signals)
        assert heat_map["us"] == 88.0

    def test_heat_map_single_region(self) -> None:
        """单区域输入应返回单条目热度图。"""
        comparator = CrossRegionComparator()
        signals = [_make_signal(region="china", heat_score=62.0)]
        heat_map = comparator.generate_heat_map(signals)
        assert heat_map == {"china": 62.0}


# ==============================================================================
# 4. 本地化建议 (Localization Suggestions)
# ==============================================================================


class TestLocalizationSuggestions:
    """本地化建议测试 - 海外趋势进入中国时的适配建议。"""

    def test_localization_when_us_trend_entering_china(self) -> None:
        """US peak + CN rising → 应生成本地化建议。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(
                region="us",
                lifecycle="peak",
                category="家居/装饰",
                z_gen_tags=["侘寂"],
            ),
            _make_signal(
                region="china",
                lifecycle="rising",
                category="家居/装饰",
                z_gen_tags=["侘寂", "新中式"],
            ),
        ]
        result = comparator.generate_localization_suggestions(signals)
        assert result["applicable"] is True
        assert "priceRange" in result
        assert "material" in result
        assert "culturalAdaptation" in result
        assert "us" in result["source_regions"]

    def test_localization_returns_non_empty_suggestions(self) -> None:
        """本地化建议字段应为非空字符串。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="peak", category="美妆/个护"),
            _make_signal(region="china", lifecycle="rising", category="美妆/个护"),
        ]
        result = comparator.generate_localization_suggestions(signals)
        assert result["applicable"] is True
        assert isinstance(result["priceRange"], str) and result["priceRange"]
        assert isinstance(result["material"], str) and result["material"]
        assert (
            isinstance(result["culturalAdaptation"], str)
            and result["culturalAdaptation"]
        )

    def test_localization_includes_z_gen_tags(self) -> None:
        """本地化建议应聚合海外信号的 Z 世代审美标签。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(
                region="us", lifecycle="peak", z_gen_tags=["Y2K", "多巴胺"]
            ),
            _make_signal(region="china", lifecycle="rising", z_gen_tags=[]),
        ]
        result = comparator.generate_localization_suggestions(signals)
        assert result["applicable"] is True
        tags = result.get("zGenTags", [])
        assert "Y2K" in tags
        assert "多巴胺" in tags

    def test_localization_adapts_to_spending_power(self) -> None:
        """价格区间应受受众 spendingPower 影响 (高消费力上调)。"""
        comparator = CrossRegionComparator()
        # 低消费力
        signals_low = [
            _make_signal(
                region="us",
                lifecycle="peak",
                target_audience={"ageRange": "18-25", "spendingPower": "低"},
            ),
            _make_signal(
                region="china",
                lifecycle="rising",
                target_audience={"ageRange": "18-25", "spendingPower": "低"},
            ),
        ]
        # 高消费力
        signals_high = [
            _make_signal(
                region="us",
                lifecycle="peak",
                target_audience={"ageRange": "25-35", "spendingPower": "高"},
            ),
            _make_signal(
                region="china",
                lifecycle="rising",
                target_audience={"ageRange": "25-35", "spendingPower": "高"},
            ),
        ]
        low_result = comparator.generate_localization_suggestions(signals_low)
        high_result = comparator.generate_localization_suggestions(signals_high)
        # 高消费力的价格上限应不低于低消费力
        _assert_price_not_lower(high_result["priceRange"], low_result["priceRange"])

    def test_no_localization_when_no_china(self) -> None:
        """无中国信号时不生成本地化建议 (尚未进入中国)。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="peak"),
            _make_signal(region="eu", lifecycle="declining"),
        ]
        result = comparator.generate_localization_suggestions(signals)
        assert result["applicable"] is False

    def test_no_localization_when_china_already_ahead(self) -> None:
        """CN 已领先 (peak) + US rising → 不需要本地化进入建议。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="china", lifecycle="peak"),
            _make_signal(region="us", lifecycle="rising"),
        ]
        result = comparator.generate_localization_suggestions(signals)
        assert result["applicable"] is False

    def test_no_localization_when_china_at_same_stage(self) -> None:
        """CN 与海外同处 peak → 不需要进入建议 (已同步)。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="peak"),
            _make_signal(region="china", lifecycle="peak"),
        ]
        result = comparator.generate_localization_suggestions(signals)
        assert result["applicable"] is False


def _assert_price_not_lower(high_range: str, low_range: str) -> None:
    """断言 high_range 的上限 >= low_range 的上限。

    解析 "59-129" 格式, 取连字符后的数值比较。
    """
    high_upper = float(high_range.split("-")[-1])
    low_upper = float(low_range.split("-")[-1])
    assert high_upper >= low_upper, (
        f"高消费力价格上限 {high_upper} 应不低于低消费力 {low_upper}"
    )


# ==============================================================================
# 5. 边界场景 (Edge Cases)
# ==============================================================================


class TestEdgeCases:
    """边界场景测试 - 空输入 / 单区域 / 全同 lifecycle。"""

    def test_empty_input_returns_empty_structures(self) -> None:
        """空输入应返回空结构, 不抛异常。"""
        comparator = CrossRegionComparator()
        assert comparator.detect_diffusion_path([]) == []
        assert comparator.detect_follow_up_windows([]) == []
        assert comparator.generate_heat_map([]) == {}

    def test_empty_input_localization_not_applicable(self) -> None:
        """空输入时本地化建议 applicable=False。"""
        comparator = CrossRegionComparator()
        result = comparator.generate_localization_suggestions([])
        assert result["applicable"] is False

    def test_single_region_no_diffusion(self) -> None:
        """单区域输入: 扩散路径仅 1 节点, 无跟进窗口。"""
        comparator = CrossRegionComparator()
        signals = [_make_signal(region="china", lifecycle="rising", heat_score=62.0)]
        path = comparator.detect_diffusion_path(signals)
        assert len(path) == 1
        assert path[0]["region"] == "china"
        windows = comparator.detect_follow_up_windows(signals)
        assert windows == []

    def test_single_region_heat_map(self) -> None:
        """单区域输入: 热度图仅 1 条目。"""
        comparator = CrossRegionComparator()
        signals = [_make_signal(region="china", heat_score=62.0)]
        heat_map = comparator.generate_heat_map(signals)
        assert heat_map == {"china": 62.0}

    def test_all_same_lifecycle_no_follow_up(self) -> None:
        """所有区域同 lifecycle 时无跟进窗口。"""
        comparator = CrossRegionComparator()
        for stage in ("rising", "peak", "declining"):
            signals = [
                _make_signal(region="us", lifecycle=stage),
                _make_signal(region="china", lifecycle=stage),
                _make_signal(region="eu", lifecycle=stage),
            ]
            assert comparator.detect_follow_up_windows(signals) == [], (
                f"全同 {stage} 时不应有跟进窗口"
            )

    def test_all_same_lifecycle_diffusion_path_returns_all(self) -> None:
        """全同 lifecycle 时扩散路径仍应返回所有区域 (按 heatScore 降序)。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="peak", heat_score=88.0),
            _make_signal(region="china", lifecycle="peak", heat_score=62.0),
            _make_signal(region="eu", lifecycle="peak", heat_score=70.0),
        ]
        path = comparator.detect_diffusion_path(signals)
        assert len(path) == 3
        # 同 lifecycle 按 heatScore 降序: us(88) → eu(70) → china(62)
        assert [n["region"] for n in path] == ["us", "eu", "china"]


# ==============================================================================
# 6. compare() 主入口测试
# ==============================================================================


class TestCompareMain:
    """compare() 主入口测试 - 聚合所有跨区域分析结果。"""

    def test_compare_returns_aggregated_structure(self) -> None:
        """compare() 应返回聚合结构 (含 topic/区域数/扩散路径/跟进窗口/热度图/本地化)。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="peak", heat_score=88.0),
            _make_signal(region="china", lifecycle="rising", heat_score=45.0),
        ]
        result = comparator.compare(signals)
        assert result["topic"] == "侘寂风家居"
        assert result["region_count"] == 2
        assert "diffusion_path" in result
        assert "follow_up_windows" in result
        assert "heat_map" in result
        assert "localization_suggestions" in result

    def test_compare_regions_list(self) -> None:
        """compare() 应返回参与对比的区域列表。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="peak"),
            _make_signal(region="china", lifecycle="rising"),
            _make_signal(region="sea", lifecycle="declining"),
        ]
        result = comparator.compare(signals)
        assert set(result["regions"]) == {"us", "china", "sea"}

    def test_compare_identifies_leading_region(self) -> None:
        """compare() 应识别 leading_region (扩散路径最前端的区域)。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="eu", lifecycle="declining"),
            _make_signal(region="us", lifecycle="peak"),
            _make_signal(region="china", lifecycle="rising"),
        ]
        result = comparator.compare(signals)
        # declining 最前端 (origin)
        assert result["leading_region"] == "eu"

    def test_compare_identifies_max_heat_region(self) -> None:
        """compare() 应识别 max_heat_region (热度最高的区域)。"""
        comparator = CrossRegionComparator()
        signals = [
            _make_signal(region="us", lifecycle="peak", heat_score=88.0),
            _make_signal(region="china", lifecycle="rising", heat_score=92.0),
        ]
        result = comparator.compare(signals)
        assert result["max_heat_region"] == "china"

    def test_compare_empty_input(self) -> None:
        """compare() 空输入应返回安全默认值, 不抛异常。"""
        comparator = CrossRegionComparator()
        result = comparator.compare([])
        assert result["region_count"] == 0
        assert result["diffusion_path"] == []
        assert result["follow_up_windows"] == []
        assert result["heat_map"] == {}
        assert result["localization_suggestions"]["applicable"] is False


# ==============================================================================
# 7. API 路由测试 (FastAPI Routes)
# ==============================================================================


@pytest.fixture
def client() -> TestClient:
    """创建带有 demo 数据的 TestClient。"""
    app = create_app()
    return TestClient(app)


class TestAPIHealth:
    """/health 健康检查测试。"""

    def test_health_returns_200(self, client: TestClient) -> None:
        """/health 应返回 200。"""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_status_healthy(self, client: TestClient) -> None:
        """/health 应返回 status=healthy。"""
        resp = client.get("/health")
        body = resp.json()
        assert body["status"] == "healthy"

    def test_health_includes_service_name(self, client: TestClient) -> None:
        """/health 应包含 service 字段标识 TrendPulse。"""
        resp = client.get("/health")
        body = resp.json()
        assert body["service"] == "trendpulse"


class TestAPIListTrends:
    """GET /trends 趋势列表测试。"""

    def test_list_trends_returns_200(self, client: TestClient) -> None:
        """GET /trends 应返回 200。"""
        resp = client.get("/trends")
        assert resp.status_code == 200

    def test_list_trends_returns_list(self, client: TestClient) -> None:
        """GET /trends 应返回列表 (按 topic 去重)。"""
        resp = client.get("/trends")
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) >= 1

    def test_list_trends_items_have_topic_field(self, client: TestClient) -> None:
        """每个趋势条目应含 topic 字段。"""
        resp = client.get("/trends")
        body = resp.json()
        for item in body:
            assert "topic" in item

    def test_list_trends_deduplicated_by_topic(self, client: TestClient) -> None:
        """趋势列表应按 topic 去重 (同 topic 多区域信号合并为一条)。"""
        resp = client.get("/trends")
        body = resp.json()
        topics = [item["topic"] for item in body]
        assert len(topics) == len(set(topics)), "趋势列表存在重复 topic"


class TestAPIGetTrendDetail:
    """GET /trends/{topic} 趋势详情测试。"""

    def test_get_trend_detail_returns_200(self, client: TestClient) -> None:
        """存在的 topic 应返回 200。"""
        # 先获取一个存在的 topic
        topics = client.get("/trends").json()
        topic = topics[0]["topic"]
        resp = client.get(f"/trends/{topic}")
        assert resp.status_code == 200

    def test_get_trend_detail_returns_topic_and_signals(self, client: TestClient) -> None:
        """趋势详情应含 topic 与 signals (多区域信号列表)。"""
        topics = client.get("/trends").json()
        topic = topics[0]["topic"]
        resp = client.get(f"/trends/{topic}")
        body = resp.json()
        assert body["topic"] == topic
        assert "signals" in body
        assert isinstance(body["signals"], list)
        assert len(body["signals"]) >= 1

    def test_get_trend_detail_not_found_returns_404(self, client: TestClient) -> None:
        """不存在的 topic 应返回 404。"""
        resp = client.get("/trends/不存在的趋势话题XYZ123")
        assert resp.status_code == 404


class TestAPICrossRegion:
    """GET /cross-region/{topic} 跨区域对比测试。"""

    def test_cross_region_returns_200(self, client: TestClient) -> None:
        """存在的多区域 topic 应返回 200。"""
        topics = client.get("/trends").json()
        topic = topics[0]["topic"]
        resp = client.get(f"/cross-region/{topic}")
        assert resp.status_code == 200

    def test_cross_region_returns_full_structure(self, client: TestClient) -> None:
        """跨区域对比应返回完整结构 (扩散路径/跟进窗口/热度图/本地化建议)。"""
        topics = client.get("/trends").json()
        topic = topics[0]["topic"]
        resp = client.get(f"/cross-region/{topic}")
        body = resp.json()
        assert body["topic"] == topic
        assert "diffusion_path" in body
        assert "follow_up_windows" in body
        assert "heat_map" in body
        assert "localization_suggestions" in body

    def test_cross_region_not_found_returns_404(self, client: TestClient) -> None:
        """不存在的 topic 应返回 404。"""
        resp = client.get("/cross-region/不存在的趋势话题XYZ123")
        assert resp.status_code == 404

    def test_cross_region_demo_topic_has_diffusion(
        self, client: TestClient
    ) -> None:
        """demo 数据中至少一个 topic 应存在跨区域扩散路径。"""
        topics = client.get("/trends").json()
        found_diffusion = False
        for item in topics:
            topic = item["topic"]
            resp = client.get(f"/cross-region/{topic}")
            body = resp.json()
            if body["follow_up_windows"]:
                found_diffusion = True
                break
        assert found_diffusion, "demo 数据应至少包含一条跨区域跟进窗口"


class TestAPICollect:
    """POST /collect 数据采集触发测试。"""

    def test_collect_returns_200(self, client: TestClient) -> None:
        """POST /collect 应返回 200。"""
        resp = client.post("/collect")
        assert resp.status_code == 200

    def test_collect_returns_summary_structure(self, client: TestClient) -> None:
        """POST /collect 应返回采集摘要 (status/sources/total_signals)。"""
        resp = client.post("/collect")
        body = resp.json()
        assert "status" in body
        assert "sources" in body
        assert "total_signals" in body

    def test_collect_status_completed(self, client: TestClient) -> None:
        """采集状态应为 completed (demo 模式同步完成)。"""
        resp = client.post("/collect")
        body = resp.json()
        assert body["status"] == "completed"

    def test_collect_sources_is_list(self, client: TestClient) -> None:
        """sources 应为列表, 每项含 name/status/count。"""
        resp = client.post("/collect")
        body = resp.json()
        assert isinstance(body["sources"], list)
        assert len(body["sources"]) >= 1
        for src in body["sources"]:
            assert "name" in src
            assert "status" in src
            assert "count" in src

    def test_collect_refreshes_trends(self, client: TestClient) -> None:
        """POST /collect 后 GET /trends 仍应返回趋势列表 (数据已刷新)。"""
        before = client.get("/trends").json()
        client.post("/collect")
        after = client.get("/trends").json()
        assert isinstance(before, list)
        assert isinstance(after, list)
        assert len(after) >= 1

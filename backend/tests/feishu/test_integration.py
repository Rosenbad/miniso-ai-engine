# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 飞书生态集成层 (Task 13)
# ==============================================================================
# 对应 Task 13: 飞书生态集成层
# 覆盖:
#   1. FeishuClient    - tenant_access_token 管理 + 自动续期 + demo 模式
#   2. FeishuBitable   - define_top100_fields + create_table + insert_records
#   3. FeishuBot       - send_card (interactive) + send_text + send_webhook
#   4. FeishuAI        - generate_trend_report + generate_decision_summary
#   5. FeishuWiki      - search_cases + search_ip_knowledge
#   6. Templates       - build_decision_card / build_trend_report_card / build_validation_result_card
#   7. 边界场景        - 空数据 / 单条数据 / 缺失字段
#
# 测试策略 (TDD):
#   Step 1: 编写测试 (本文件)
#   Step 2: 验证失败 (飞书模块尚未实现)
#   Step 3-8: 实现 6 个模块
#   Step 9: 验证通过
#
# 环境说明:
#   - 无真实飞书 API 凭据, 全部使用 demo 模式 / mock httpx 响应
#   - FeishuClient 检测 FEISHU_APP_ID 缺失时自动进入 demo 模式
#   - demo 模式下返回结构正确的 mock 响应
# ==============================================================================

"""
测试飞书生态集成层 (Task 13)。

测试覆盖 (TDD):
  - FeishuClient: demo 模式 (无凭据), token 缓存, request 方法
  - FeishuBitable: define_top100_fields 字段定义, create_table, insert_records
  - FeishuBot: send_card, send_text, send_webhook
  - FeishuAI: generate_trend_report 非空, generate_decision_summary
  - FeishuWiki: search_cases 返回列表, search_ip_knowledge 返回字典
  - Templates:
    * build_decision_card: 含 "Top 100" 文本, 卡片结构 (config/header/elements)
    * build_trend_report_card: 含趋势信息, 卡片结构
    * build_validation_result_card: 含验证信息, 卡片结构
  - 边界场景: 空数据, 单条数据, 缺失字段

环境说明:
  - demo 模式: 无 FEISHU_APP_ID 时返回 mock 响应
  - 测试使用 mock httpx 响应, 不发起真实 API 调用
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.models import IPMatch, ProductIdeaCard, TrendSignal


# ==============================================================================
# 测试辅助 - 构造 TrendSignal / ProductIdeaCard
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
    """构造一个 TrendSignal 测试实例。"""
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
    """构造一个 IPMatch 测试实例。"""
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
    product_name: str = "原木杯香薰蜡烛",
    hit_score: float = 0.85,
    category: str = "家居/香氛",
) -> ProductIdeaCard:
    """构造一个 ProductIdeaCard 测试实例。"""
    return ProductIdeaCard(
        conceptId=concept_id,
        productName=product_name,
        category=category,
        designDesc="融合侘寂美学的产品概念设计",
        material="大豆蜡 + 陶瓷",
        priceRange="49-79",
        ipMatch=_make_ip_match(),
        sellingPoints=["侘寂美学", "天然大豆蜡", "疗愈香氛"],
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
        ],
    )


def _make_trend_data() -> Dict[str, Any]:
    """构造趋势数据字典 (用于趋势报告卡片与 AI 生成)。"""
    return {
        "topic": "侘寂风家居",
        "heatScore": 72.0,
        "growthRate": 34.2,
        "category": "家居/香氛",
        "lifecycle": "rising",
        "predictWindow": "2-4周",
        "zGenTags": ["侘寂", "自然系"],
        "region": "china",
        "crossRegionDiff": {"us": "peak", "eu": "declining", "sea": "nascent"},
        "relatedKeywords": ["侘寂", "原木", "疗愈"],
    }


def _make_validation_result() -> Dict[str, Any]:
    """构造验证结果字典 (用于验证结果卡片)。"""
    return {
        "winner": {
            "combination_id": "C001",
            "composite_score": 88.5,
            "price": "medium",
            "packaging": "ip_collab",
            "channel": "online",
            "region": "china",
        },
        "predicted_hit": 0.75,
        "actual_performance": 0.82,
        "confidence": 0.87,
        "total_sales": 560,
        "avg_conversion": 0.065,
        "rankings": [
            {"combination_id": "C001", "score": 88.5},
            {"combination_id": "C002", "score": 75.2},
            {"combination_id": "C003", "score": 68.0},
        ],
    }


# ==============================================================================
# 1. FeishuClient 测试
# ==============================================================================


class TestFeishuClient:
    """FeishuClient 测试 - tenant_access_token 管理 + demo 模式。"""

    def test_demo_mode_when_no_credentials(self) -> None:
        """无凭据时应进入 demo 模式。"""
        from feishu.client import FeishuClient

        client = FeishuClient(app_id=None, app_secret=None)
        assert client.is_demo_mode is True

    def test_real_mode_when_credentials_provided(self) -> None:
        """提供凭据时应为非 demo 模式。"""
        from feishu.client import FeishuClient

        client = FeishuClient(app_id="cli_test_id", app_secret="test_secret")
        assert client.is_demo_mode is False

    def test_demo_mode_reads_from_env(self) -> None:
        """无凭据参数时应从环境变量读取。"""
        from feishu.client import FeishuClient

        # 确保 env 无凭据 → demo 模式
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FEISHU_APP_ID", None)
            os.environ.pop("FEISHU_APP_SECRET", None)
            client = FeishuClient()
            assert client.is_demo_mode is True

    async def test_get_tenant_access_token_demo_mode(self) -> None:
        """demo 模式下 get_tenant_access_token 应返回 demo token。"""
        from feishu.client import FeishuClient

        client = FeishuClient(app_id=None, app_secret=None)
        token = await client.get_tenant_access_token()
        assert isinstance(token, str)
        assert len(token) > 0
        assert "demo" in token.lower()

    async def test_token_caching(self) -> None:
        """连续调用 get_tenant_access_token 应使用缓存 (不重复获取)。"""
        from feishu.client import FeishuClient

        client = FeishuClient(app_id=None, app_secret=None)
        token1 = await client.get_tenant_access_token()
        token2 = await client.get_tenant_access_token()
        assert token1 == token2, "token 缓存失效, 两次获取结果不同"

    async def test_token_expiry_triggers_renewal(self) -> None:
        """token 过期后应自动续期。"""
        from feishu.client import FeishuClient

        client = FeishuClient(app_id=None, app_secret=None)
        token1 = await client.get_tenant_access_token()
        # 模拟 token 过期
        client._token_expires_at = time.monotonic() - 1
        token2 = await client.get_tenant_access_token()
        # demo 模式下 token 可能相同, 但应触发重新获取逻辑
        assert isinstance(token2, str)
        assert len(token2) > 0

    async def test_request_demo_mode_returns_mock(self) -> None:
        """demo 模式下 request 应返回 mock 响应。"""
        from feishu.client import FeishuClient

        client = FeishuClient(app_id=None, app_secret=None)
        result = await client.request("GET", "/some/endpoint")
        assert isinstance(result, dict)

    async def test_request_demo_mode_contains_demo_flag(self) -> None:
        """demo 模式响应应标记 demo 旗标。"""
        from feishu.client import FeishuClient

        client = FeishuClient(app_id=None, app_secret=None)
        result = await client.request("GET", "/some/endpoint")
        assert result.get("demo") is True or result.get("_demo") is True

    async def test_request_with_mock_httpx(self) -> None:
        """有凭据时 request 应通过 httpx 发起真实请求 (mock)。"""
        from feishu.client import FeishuClient

        client = FeishuClient(app_id="cli_test", app_secret="secret")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "msg": "ok", "data": {"id": 1}}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            # mock token 获取
            with patch.object(
                client, "get_tenant_access_token", new_callable=AsyncMock
            ) as mock_token:
                mock_token.return_value = "mock-token-xxx"
                result = await client.request("GET", "/test/path")

            assert isinstance(result, dict)

    def test_base_url_constant(self) -> None:
        """BASE_URL 应为飞书开放平台 API 地址。"""
        from feishu.client import FeishuClient

        assert FeishuClient.BASE_URL == "https://open.feishu.cn/open-apis"


# ==============================================================================
# 2. FeishuBitable 测试
# ==============================================================================


class TestFeishuBitable:
    """FeishuBitable 测试 - Top 100 打版池字段定义 + 表操作。"""

    def test_define_top100_fields_returns_list(self) -> None:
        """define_top100_fields 应返回列表。"""
        from feishu.bitable import FeishuBitable
        from feishu.client import FeishuClient

        bitable = FeishuBitable(FeishuClient(app_id=None, app_secret=None))
        fields = bitable.define_top100_fields()
        assert isinstance(fields, list)

    def test_define_top100_fields_has_required_field_names(self) -> None:
        """Top 100 字段应含 spec 要求的核心字段。"""
        from feishu.bitable import FeishuBitable
        from feishu.client import FeishuClient

        bitable = FeishuBitable(FeishuClient(app_id=None, app_secret=None))
        fields = bitable.define_top100_fields()
        field_names = {f["field_name"] for f in fields}
        required = {
            "conceptId",
            "productName",
            "hitScore",
            "ipMatch",
            "zGenMatchScore",
            "regionFit",
            "status",
        }
        assert required.issubset(field_names), (
            f"缺少必需字段: {required - field_names}"
        )

    def test_define_top100_fields_has_field_type(self) -> None:
        """每个字段定义应含 field_name 和 type。"""
        from feishu.bitable import FeishuBitable
        from feishu.client import FeishuClient

        bitable = FeishuBitable(FeishuClient(app_id=None, app_secret=None))
        fields = bitable.define_top100_fields()
        for f in fields:
            assert "field_name" in f, f"字段定义缺少 field_name: {f}"
            assert "type" in f, f"字段定义缺少 type: {f}"

    def test_define_top100_fields_includes_category_and_design(self) -> None:
        """Top 100 字段还应含 category / designDesc / sellingPoints。"""
        from feishu.bitable import FeishuBitable
        from feishu.client import FeishuClient

        bitable = FeishuBitable(FeishuClient(app_id=None, app_secret=None))
        fields = bitable.define_top100_fields()
        field_names = {f["field_name"] for f in fields}
        assert "category" in field_names
        assert "designDesc" in field_names
        assert "sellingPoints" in field_names

    async def test_create_table_demo_mode(self) -> None:
        """demo 模式下 create_table 应返回 mock 响应。"""
        from feishu.bitable import FeishuBitable
        from feishu.client import FeishuClient

        bitable = FeishuBitable(FeishuClient(app_id=None, app_secret=None))
        fields = bitable.define_top100_fields()
        result = await bitable.create_table(
            app_token="demo_app_token",
            name="Top100打版池",
            fields=fields,
        )
        assert isinstance(result, dict)
        assert "table_id" in result or "tableId" in result

    async def test_create_table_with_mock_httpx(self) -> None:
        """有凭据时 create_table 应通过 API 创建表 (mock)。"""
        from feishu.bitable import FeishuBitable
        from feishu.client import FeishuClient

        client = FeishuClient(app_id="cli_test", app_secret="secret")
        bitable = FeishuBitable(client)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 0,
            "msg": "ok",
            "data": {"table_id": "tbl123456"},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            with patch.object(
                client, "get_tenant_access_token", new_callable=AsyncMock
            ) as mock_token:
                mock_token.return_value = "mock-token"
                fields = bitable.define_top100_fields()
                result = await bitable.create_table(
                    app_token="appXXX",
                    name="测试表",
                    fields=fields,
                )

        assert isinstance(result, dict)

    async def test_insert_records_demo_mode(self) -> None:
        """demo 模式下 insert_records 应返回 mock 响应。"""
        from feishu.bitable import FeishuBitable
        from feishu.client import FeishuClient

        bitable = FeishuBitable(FeishuClient(app_id=None, app_secret=None))
        records = [
            {
                "conceptId": "CPT-2025-0001",
                "productName": "原木杯香薰蜡烛",
                "hitScore": 0.85,
            },
            {
                "conceptId": "CPT-2025-0002",
                "productName": "侘寂风陶器",
                "hitScore": 0.82,
            },
        ]
        result = await bitable.insert_records(
            app_token="demo_app_token",
            table_id="demo_table_id",
            records=records,
        )
        assert isinstance(result, dict)

    async def test_insert_records_empty_list(self) -> None:
        """空记录列表应正常返回, 不报错。"""
        from feishu.bitable import FeishuBitable
        from feishu.client import FeishuClient

        bitable = FeishuBitable(FeishuClient(app_id=None, app_secret=None))
        result = await bitable.insert_records(
            app_token="demo_app_token",
            table_id="demo_table_id",
            records=[],
        )
        assert isinstance(result, dict)

    async def test_insert_records_single_record(self) -> None:
        """单条记录应正常插入。"""
        from feishu.bitable import FeishuBitable
        from feishu.client import FeishuClient

        bitable = FeishuBitable(FeishuClient(app_id=None, app_secret=None))
        records = [
            {
                "conceptId": "CPT-2025-0001",
                "productName": "原木杯香薰蜡烛",
                "hitScore": 0.85,
            }
        ]
        result = await bitable.insert_records(
            app_token="demo_app_token",
            table_id="demo_table_id",
            records=records,
        )
        assert isinstance(result, dict)


# ==============================================================================
# 3. FeishuBot 测试
# ==============================================================================


class TestFeishuBot:
    """FeishuBot 测试 - 机器人消息推送。"""

    async def test_send_card_demo_mode(self) -> None:
        """demo 模式下 send_card 应返回 mock 响应。"""
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient

        bot = FeishuBot(FeishuClient(app_id=None, app_secret=None))
        card = {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": "测试"}},
            "elements": [],
        }
        result = await bot.send_card(chat_id="oc_test", card=card)
        assert isinstance(result, dict)

    async def test_send_card_demo_mode_has_demo_flag(self) -> None:
        """demo 模式下 send_card 响应应标记 demo。"""
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient

        bot = FeishuBot(FeishuClient(app_id=None, app_secret=None))
        card = {"config": {}, "header": {}, "elements": []}
        result = await bot.send_card(chat_id="oc_test", card=card)
        assert result.get("demo") is True or result.get("_demo") is True

    async def test_send_card_with_mock_httpx(self) -> None:
        """有凭据时 send_card 应通过 API 发送 (mock)。"""
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient

        client = FeishuClient(app_id="cli_test", app_secret="secret")
        bot = FeishuBot(client)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 0,
            "msg": "ok",
            "data": {"message_id": "om_123456"},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            with patch.object(
                client, "get_tenant_access_token", new_callable=AsyncMock
            ) as mock_token:
                mock_token.return_value = "mock-token"
                card = {"config": {}, "header": {}, "elements": []}
                result = await bot.send_card(chat_id="oc_test", card=card)

        assert isinstance(result, dict)

    async def test_send_text_demo_mode(self) -> None:
        """demo 模式下 send_text 应返回 mock 响应。"""
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient

        bot = FeishuBot(FeishuClient(app_id=None, app_secret=None))
        result = await bot.send_text(chat_id="oc_test", text="Hello, 飞书!")
        assert isinstance(result, dict)

    async def test_send_text_demo_mode_has_demo_flag(self) -> None:
        """demo 模式下 send_text 响应应标记 demo。"""
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient

        bot = FeishuBot(FeishuClient(app_id=None, app_secret=None))
        result = await bot.send_text(chat_id="oc_test", text="测试文本")
        assert result.get("demo") is True or result.get("_demo") is True

    async def test_send_webhook_demo_mode(self) -> None:
        """demo 模式下 send_webhook 应返回 mock 响应。"""
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient

        bot = FeishuBot(
            FeishuClient(app_id=None, app_secret=None),
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/test",
        )
        card = {"config": {}, "header": {}, "elements": []}
        result = await bot.send_webhook(card=card)
        assert isinstance(result, dict)

    async def test_send_webhook_no_url_returns_demo(self) -> None:
        """无 webhook_url 时 send_webhook 应返回 demo 响应。"""
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient

        bot = FeishuBot(FeishuClient(app_id=None, app_secret=None))
        card = {"config": {}, "header": {}, "elements": []}
        result = await bot.send_webhook(card=card)
        assert isinstance(result, dict)

    async def test_send_webhook_with_mock_httpx(self) -> None:
        """有 webhook_url 时 send_webhook 应通过 httpx 发送 (mock)。"""
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient

        bot = FeishuBot(
            FeishuClient(app_id=None, app_secret=None),
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/test",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "msg": "ok"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            card = {"config": {}, "header": {}, "elements": []}
            result = await bot.send_webhook(card=card)
            assert isinstance(result, dict)

    def test_bot_stores_webhook_url(self) -> None:
        """Bot 应存储 webhook_url。"""
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient

        url = "https://example.com/hook"
        bot = FeishuBot(
            FeishuClient(app_id=None, app_secret=None),
            webhook_url=url,
        )
        assert bot.webhook_url == url


# ==============================================================================
# 4. FeishuAI 测试
# ==============================================================================


class TestFeishuAI:
    """FeishuAI 测试 - 趋势报告生成 + 决策摘要。"""

    async def test_generate_trend_report_returns_str(self) -> None:
        """generate_trend_report 应返回字符串。"""
        from feishu.ai import FeishuAI
        from feishu.client import FeishuClient

        ai = FeishuAI(FeishuClient(app_id=None, app_secret=None))
        report = await ai.generate_trend_report(_make_trend_data())
        assert isinstance(report, str)

    async def test_generate_trend_report_non_empty(self) -> None:
        """趋势报告应非空。"""
        from feishu.ai import FeishuAI
        from feishu.client import FeishuClient

        ai = FeishuAI(FeishuClient(app_id=None, app_secret=None))
        report = await ai.generate_trend_report(_make_trend_data())
        assert len(report) > 0

    async def test_generate_trend_report_contains_topic(self) -> None:
        """报告应包含趋势话题名。"""
        from feishu.ai import FeishuAI
        from feishu.client import FeishuClient

        ai = FeishuAI(FeishuClient(app_id=None, app_secret=None))
        report = await ai.generate_trend_report(_make_trend_data())
        assert "侘寂风家居" in report

    async def test_generate_trend_report_contains_heat_score(self) -> None:
        """报告应包含热度分信息。"""
        from feishu.ai import FeishuAI
        from feishu.client import FeishuClient

        ai = FeishuAI(FeishuClient(app_id=None, app_secret=None))
        report = await ai.generate_trend_report(_make_trend_data())
        assert "72" in report

    async def test_generate_trend_report_contains_lifecycle(self) -> None:
        """报告应包含生命周期阶段信息。"""
        from feishu.ai import FeishuAI
        from feishu.client import FeishuClient

        ai = FeishuAI(FeishuClient(app_id=None, app_secret=None))
        report = await ai.generate_trend_report(_make_trend_data())
        # rising / 上升 / 生命周期 至少出现一个
        assert any(kw in report for kw in ["rising", "上升", "生命周期"])

    async def test_generate_trend_report_empty_data(self) -> None:
        """空趋势数据应仍返回非空字符串 (优雅降级)。"""
        from feishu.ai import FeishuAI
        from feishu.client import FeishuClient

        ai = FeishuAI(FeishuClient(app_id=None, app_secret=None))
        report = await ai.generate_trend_report({})
        assert isinstance(report, str)
        assert len(report) > 0

    async def test_generate_decision_summary_returns_str(self) -> None:
        """generate_decision_summary 应返回字符串。"""
        from feishu.ai import FeishuAI
        from feishu.client import FeishuClient

        ai = FeishuAI(FeishuClient(app_id=None, app_secret=None))
        cards = [_make_card(), _make_card(concept_id="CPT-2025-0002")]
        summary = await ai.generate_decision_summary(cards)
        assert isinstance(summary, str)

    async def test_generate_decision_summary_non_empty(self) -> None:
        """决策摘要应非空。"""
        from feishu.ai import FeishuAI
        from feishu.client import FeishuClient

        ai = FeishuAI(FeishuClient(app_id=None, app_secret=None))
        cards = [_make_card()]
        summary = await ai.generate_decision_summary(cards)
        assert len(summary) > 0

    async def test_generate_decision_summary_contains_product_name(self) -> None:
        """决策摘要应包含产品名。"""
        from feishu.ai import FeishuAI
        from feishu.client import FeishuClient

        ai = FeishuAI(FeishuClient(app_id=None, app_secret=None))
        cards = [_make_card(product_name="原木杯香薰蜡烛")]
        summary = await ai.generate_decision_summary(cards)
        assert "原木杯香薰蜡烛" in summary

    async def test_generate_decision_summary_empty_cards(self) -> None:
        """空卡片列表应仍返回非空字符串。"""
        from feishu.ai import FeishuAI
        from feishu.client import FeishuClient

        ai = FeishuAI(FeishuClient(app_id=None, app_secret=None))
        summary = await ai.generate_decision_summary([])
        assert isinstance(summary, str)
        assert len(summary) > 0

    async def test_generate_decision_summary_with_card_dicts(self) -> None:
        """决策摘要也应接受 dict 格式的卡片 (非 ProductIdeaCard 实例)。"""
        from feishu.ai import FeishuAI
        from feishu.client import FeishuClient

        ai = FeishuAI(FeishuClient(app_id=None, app_secret=None))
        cards = [
            {
                "conceptId": "CPT-2025-0001",
                "productName": "测试产品A",
                "hitScore": 0.85,
                "category": "家居/香氛",
            }
        ]
        summary = await ai.generate_decision_summary(cards)
        assert isinstance(summary, str)
        assert len(summary) > 0


# ==============================================================================
# 5. FeishuWiki 测试
# ==============================================================================


class TestFeishuWiki:
    """FeishuWiki 测试 - 爆品案例库 RAG 检索。"""

    async def test_search_cases_returns_list(self) -> None:
        """search_cases 应返回列表。"""
        from feishu.client import FeishuClient
        from feishu.wiki import FeishuWiki

        wiki = FeishuWiki(FeishuClient(app_id=None, app_secret=None))
        result = await wiki.search_cases(query="香薰蜡烛")
        assert isinstance(result, list)

    async def test_search_cases_demo_mode_non_empty(self) -> None:
        """demo 模式下搜索应返回非空案例列表。"""
        from feishu.client import FeishuClient
        from feishu.wiki import FeishuWiki

        wiki = FeishuWiki(FeishuClient(app_id=None, app_secret=None))
        result = await wiki.search_cases(query="香薰")
        assert len(result) >= 1

    async def test_search_cases_each_item_has_required_fields(self) -> None:
        """每个案例应含 case_name / category / hit_score 等字段。"""
        from feishu.client import FeishuClient
        from feishu.wiki import FeishuWiki

        wiki = FeishuWiki(FeishuClient(app_id=None, app_secret=None))
        result = await wiki.search_cases(query="香薰")
        for case in result:
            assert isinstance(case, dict)
            # 至少应有名称相关字段
            has_name = any(
                k in case for k in ("case_name", "name", "productName", "title")
            )
            assert has_name, f"案例缺少名称字段: {case}"

    async def test_search_cases_with_category_filter(self) -> None:
        """指定 category 时应正常返回。"""
        from feishu.client import FeishuClient
        from feishu.wiki import FeishuWiki

        wiki = FeishuWiki(FeishuClient(app_id=None, app_secret=None))
        result = await wiki.search_cases(query="联名", category="美妆/个护")
        assert isinstance(result, list)

    async def test_search_cases_empty_query(self) -> None:
        """空查询应正常返回 (不报错)。"""
        from feishu.client import FeishuClient
        from feishu.wiki import FeishuWiki

        wiki = FeishuWiki(FeishuClient(app_id=None, app_secret=None))
        result = await wiki.search_cases(query="")
        assert isinstance(result, list)

    async def test_search_ip_knowledge_returns_dict(self) -> None:
        """search_ip_knowledge 应返回字典。"""
        from feishu.client import FeishuClient
        from feishu.wiki import FeishuWiki

        wiki = FeishuWiki(FeishuClient(app_id=None, app_secret=None))
        result = await wiki.search_ip_knowledge(ip_name="三丽鸥·库洛米")
        assert isinstance(result, dict)

    async def test_search_ip_knowledge_has_ip_name(self) -> None:
        """IP 知识库返回应包含 IP 名称。"""
        from feishu.client import FeishuClient
        from feishu.wiki import FeishuWiki

        wiki = FeishuWiki(FeishuClient(app_id=None, app_secret=None))
        result = await wiki.search_ip_knowledge(ip_name="三丽鸥·库洛米")
        # 应包含 IP 名称相关字段
        has_ip = any(
            "三丽鸥" in str(v) or "库洛米" in str(v)
            for v in result.values()
        ) or any(
            k in result for k in ("ip_name", "ipName", "name", "ip")
        )
        assert has_ip, f"IP 知识库结果缺少 IP 名称: {result}"

    async def test_search_ip_knowledge_has_recommended_categories(self) -> None:
        """IP 知识库应包含推荐品类。"""
        from feishu.client import FeishuClient
        from feishu.wiki import FeishuWiki

        wiki = FeishuWiki(FeishuClient(app_id=None, app_secret=None))
        result = await wiki.search_ip_knowledge(ip_name="三丽鸥·库洛米")
        has_cats = any(
            k in result
            for k in (
                "recommended_categories",
                "recommendedCategories",
                "categories",
            )
        )
        assert has_cats, f"IP 知识库缺少推荐品类: {result}"

    async def test_search_ip_knowledge_empty_name(self) -> None:
        """空 IP 名称应正常返回 (不报错)。"""
        from feishu.client import FeishuClient
        from feishu.wiki import FeishuWiki

        wiki = FeishuWiki(FeishuClient(app_id=None, app_secret=None))
        result = await wiki.search_ip_knowledge(ip_name="")
        assert isinstance(result, dict)


# ==============================================================================
# 6. Templates 测试 - build_decision_card
# ==============================================================================


class TestDecisionCard:
    """build_decision_card 测试 - Top 100 决策就绪卡片。"""

    def test_returns_dict(self) -> None:
        """build_decision_card 应返回字典。"""
        from feishu.templates import build_decision_card

        cards = [_make_card(), _make_card(concept_id="CPT-2025-0002")]
        result = build_decision_card(cards, total_count=100)
        assert isinstance(result, dict)

    def test_has_card_structure(self) -> None:
        """卡片应含 config / header / elements 三大结构。"""
        from feishu.templates import build_decision_card

        cards = [_make_card()]
        result = build_decision_card(cards)
        assert "config" in result
        assert "header" in result
        assert "elements" in result

    def test_contains_top100_text(self) -> None:
        """卡片内容应包含 'Top 100' 文本。"""
        from feishu.templates import build_decision_card

        cards = [_make_card()]
        result = build_decision_card(cards)
        # 在 header title 或 elements 中搜索
        card_text = str(result)
        assert "Top 100" in card_text or "Top100" in card_text, (
            f"卡片缺少 Top 100 文本: {card_text[:200]}"
        )

    def test_contains_ready_notification(self) -> None:
        """卡片应包含就绪通知语 ('就绪' / '已就绪' / 'ready')。"""
        from feishu.templates import build_decision_card

        cards = [_make_card()]
        result = build_decision_card(cards)
        card_text = str(result)
        assert any(kw in card_text for kw in ["就绪", "ready", "Ready"]), (
            f"卡片缺少就绪通知: {card_text[:200]}"
        )

    def test_header_has_title(self) -> None:
        """header 应含 title 字段。"""
        from feishu.templates import build_decision_card

        cards = [_make_card()]
        result = build_decision_card(cards)
        assert "title" in result["header"]

    def test_header_title_has_content(self) -> None:
        """header.title 应含 content 字段。"""
        from feishu.templates import build_decision_card

        cards = [_make_card()]
        result = build_decision_card(cards)
        title = result["header"]["title"]
        assert "content" in title
        assert len(title["content"]) > 0

    def test_header_has_template_color(self) -> None:
        """header 应含 template 颜色。"""
        from feishu.templates import build_decision_card

        cards = [_make_card()]
        result = build_decision_card(cards)
        assert "template" in result["header"]
        assert result["header"]["template"] in [
            "blue",
            "green",
            "orange",
            "red",
            "grey",
            "turquoise",
            "purple",
            "indigo",
            "wathet",
            "yellow",
        ]

    def test_elements_non_empty(self) -> None:
        """elements 列表应非空。"""
        from feishu.templates import build_decision_card

        cards = [_make_card()]
        result = build_decision_card(cards)
        assert len(result["elements"]) > 0

    def test_contains_top3_ideas_summary(self) -> None:
        """卡片应包含 Top 3 创意摘要。"""
        from feishu.templates import build_decision_card

        cards = [
            _make_card(concept_id="CPT-001", product_name="产品A", hit_score=0.95),
            _make_card(concept_id="CPT-002", product_name="产品B", hit_score=0.90),
            _make_card(concept_id="CPT-003", product_name="产品C", hit_score=0.88),
        ]
        result = build_decision_card(cards)
        card_text = str(result)
        assert "产品A" in card_text, "卡片缺少 Top 1 创意摘要"

    def test_has_review_action_button(self) -> None:
        """卡片应含评审按钮 (action)。"""
        from feishu.templates import build_decision_card

        cards = [_make_card()]
        result = build_decision_card(cards)
        elements = result["elements"]
        has_action = any(e.get("tag") == "action" for e in elements)
        assert has_action, "卡片缺少 action 元素 (评审按钮)"

    def test_empty_cards(self) -> None:
        """空卡片列表应仍返回有效卡片结构。"""
        from feishu.templates import build_decision_card

        result = build_decision_card([])
        assert "config" in result
        assert "header" in result
        assert "elements" in result

    def test_single_card(self) -> None:
        """单张卡片应正常构建。"""
        from feishu.templates import build_decision_card

        result = build_decision_card([_make_card()])
        assert "config" in result
        assert len(result["elements"]) > 0

    def test_total_count_displayed(self) -> None:
        """卡片应显示 total_count (默认 100)。"""
        from feishu.templates import build_decision_card

        cards = [_make_card()]
        result = build_decision_card(cards, total_count=50)
        card_text = str(result)
        assert "50" in card_text


# ==============================================================================
# 7. Templates 测试 - build_trend_report_card
# ==============================================================================


class TestTrendReportCard:
    """build_trend_report_card 测试 - 趋势洞察报告卡片。"""

    def test_returns_dict(self) -> None:
        """build_trend_report_card 应返回字典。"""
        from feishu.templates import build_trend_report_card

        result = build_trend_report_card(_make_trend_data())
        assert isinstance(result, dict)

    def test_has_card_structure(self) -> None:
        """卡片应含 config / header / elements 三大结构。"""
        from feishu.templates import build_trend_report_card

        result = build_trend_report_card(_make_trend_data())
        assert "config" in result
        assert "header" in result
        assert "elements" in result

    def test_contains_trend_topic(self) -> None:
        """卡片应包含趋势话题名。"""
        from feishu.templates import build_trend_report_card

        result = build_trend_report_card(_make_trend_data())
        card_text = str(result)
        assert "侘寂风家居" in card_text

    def test_contains_heat_score(self) -> None:
        """卡片应包含热度分。"""
        from feishu.templates import build_trend_report_card

        result = build_trend_report_card(_make_trend_data())
        card_text = str(result)
        assert "72" in card_text

    def test_contains_lifecycle_info(self) -> None:
        """卡片应包含生命周期阶段信息。"""
        from feishu.templates import build_trend_report_card

        result = build_trend_report_card(_make_trend_data())
        card_text = str(result)
        assert any(
            kw in card_text for kw in ["rising", "上升", "生命周期", "peak", "declining"]
        )

    def test_contains_zgen_tags(self) -> None:
        """卡片应包含 Z 世代标签。"""
        from feishu.templates import build_trend_report_card

        result = build_trend_report_card(_make_trend_data())
        card_text = str(result)
        assert "侘寂" in card_text or "自然系" in card_text

    def test_contains_prediction_window(self) -> None:
        """卡片应包含预测窗口期。"""
        from feishu.templates import build_trend_report_card

        result = build_trend_report_card(_make_trend_data())
        card_text = str(result)
        assert "2-4周" in card_text or "预测" in card_text or "窗口" in card_text

    def test_header_has_title(self) -> None:
        """header 应含 title。"""
        from feishu.templates import build_trend_report_card

        result = build_trend_report_card(_make_trend_data())
        assert "title" in result["header"]

    def test_elements_non_empty(self) -> None:
        """elements 应非空。"""
        from feishu.templates import build_trend_report_card

        result = build_trend_report_card(_make_trend_data())
        assert len(result["elements"]) > 0

    def test_empty_trend_data(self) -> None:
        """空趋势数据应仍返回有效卡片结构。"""
        from feishu.templates import build_trend_report_card

        result = build_trend_report_card({})
        assert "config" in result
        assert "header" in result
        assert "elements" in result

    def test_minimal_trend_data(self) -> None:
        """仅含 topic 的趋势数据应正常构建。"""
        from feishu.templates import build_trend_report_card

        result = build_trend_report_card({"topic": "测试趋势"})
        assert "config" in result
        assert len(result["elements"]) > 0


# ==============================================================================
# 8. Templates 测试 - build_validation_result_card
# ==============================================================================


class TestValidationResultCard:
    """build_validation_result_card 测试 - 验证结果卡片。"""

    def test_returns_dict(self) -> None:
        """build_validation_result_card 应返回字典。"""
        from feishu.templates import build_validation_result_card

        result = build_validation_result_card(_make_validation_result())
        assert isinstance(result, dict)

    def test_has_card_structure(self) -> None:
        """卡片应含 config / header / elements 三大结构。"""
        from feishu.templates import build_validation_result_card

        result = build_validation_result_card(_make_validation_result())
        assert "config" in result
        assert "header" in result
        assert "elements" in result

    def test_contains_winner_info(self) -> None:
        """卡片应包含赢家信息。"""
        from feishu.templates import build_validation_result_card

        result = build_validation_result_card(_make_validation_result())
        card_text = str(result)
        assert "C001" in card_text or "winner" in card_text.lower() or "赢家" in card_text

    def test_contains_sales_data(self) -> None:
        """卡片应包含销量数据。"""
        from feishu.templates import build_validation_result_card

        result = build_validation_result_card(_make_validation_result())
        card_text = str(result)
        assert "560" in card_text or "销量" in card_text or "sales" in card_text.lower()

    def test_contains_prediction_vs_actual(self) -> None:
        """卡片应包含预测 vs 实际对比。"""
        from feishu.templates import build_validation_result_card

        result = build_validation_result_card(_make_validation_result())
        card_text = str(result)
        assert (
            "0.75" in card_text
            or "0.82" in card_text
            or "预测" in card_text
            or "实际" in card_text
        )

    def test_header_has_title(self) -> None:
        """header 应含 title。"""
        from feishu.templates import build_validation_result_card

        result = build_validation_result_card(_make_validation_result())
        assert "title" in result["header"]

    def test_elements_non_empty(self) -> None:
        """elements 应非空。"""
        from feishu.templates import build_validation_result_card

        result = build_validation_result_card(_make_validation_result())
        assert len(result["elements"]) > 0

    def test_empty_result(self) -> None:
        """空验证结果应仍返回有效卡片结构。"""
        from feishu.templates import build_validation_result_card

        result = build_validation_result_card({})
        assert "config" in result
        assert "header" in result
        assert "elements" in result

    def test_minimal_result(self) -> None:
        """仅含 winner 的验证结果应正常构建。"""
        from feishu.templates import build_validation_result_card

        result = build_validation_result_card(
            {"winner": {"combination_id": "C001", "composite_score": 80.0}}
        )
        assert "config" in result
        assert len(result["elements"]) > 0

    def test_contains_confidence(self) -> None:
        """卡片应包含置信度信息。"""
        from feishu.templates import build_validation_result_card

        result = build_validation_result_card(_make_validation_result())
        card_text = str(result)
        assert "0.87" in card_text or "置信" in card_text or "confidence" in card_text.lower()


# ==============================================================================
# 9. 集成场景测试
# ==============================================================================


class TestIntegrationScenarios:
    """飞书集成层端到端场景测试。"""

    async def test_full_decision_notification_flow(self) -> None:
        """完整决策通知流程: 构建卡片 → Bot 发送。"""
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient
        from feishu.templates import build_decision_card

        client = FeishuClient(app_id=None, app_secret=None)
        bot = FeishuBot(client)

        cards = [
            _make_card(concept_id="CPT-001", product_name="产品A", hit_score=0.95),
            _make_card(concept_id="CPT-002", product_name="产品B", hit_score=0.90),
        ]
        card = build_decision_card(cards, total_count=100)
        result = await bot.send_card(chat_id="oc_test_chat", card=card)
        assert isinstance(result, dict)

    async def test_trend_report_flow(self) -> None:
        """趋势报告流程: AI 生成报告 → 构建卡片 → Bot 发送。"""
        from feishu.ai import FeishuAI
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient
        from feishu.templates import build_trend_report_card

        client = FeishuClient(app_id=None, app_secret=None)
        ai = FeishuAI(client)
        bot = FeishuBot(client)

        trend_data = _make_trend_data()
        report = await ai.generate_trend_report(trend_data)
        card = build_trend_report_card(trend_data)
        result = await bot.send_card(chat_id="oc_test", card=card)
        assert isinstance(result, dict)
        assert len(report) > 0

    async def test_validation_result_flow(self) -> None:
        """验证结果流程: 构建卡片 → Bot 发送。"""
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient
        from feishu.templates import build_validation_result_card

        client = FeishuClient(app_id=None, app_secret=None)
        bot = FeishuBot(client)

        validation = _make_validation_result()
        card = build_validation_result_card(validation)
        result = await bot.send_card(chat_id="oc_test", card=card)
        assert isinstance(result, dict)

    async def test_bitable_top100_flow(self) -> None:
        """Bitable Top100 流程: 定义字段 → 创建表 → 插入记录。"""
        from feishu.bitable import FeishuBitable
        from feishu.client import FeishuClient

        client = FeishuClient(app_id=None, app_secret=None)
        bitable = FeishuBitable(client)

        fields = bitable.define_top100_fields()
        table_result = await bitable.create_table(
            app_token="demo_token",
            name="Top100打版池",
            fields=fields,
        )
        records = [
            {
                "conceptId": "CPT-2025-0001",
                "productName": "原木杯香薰蜡烛",
                "hitScore": 0.85,
            }
        ]
        insert_result = await bitable.insert_records(
            app_token="demo_token",
            table_id=table_result.get("table_id", table_result.get("tableId", "")),
            records=records,
        )
        assert isinstance(table_result, dict)
        assert isinstance(insert_result, dict)

    async def test_wiki_rag_flow(self) -> None:
        """Wiki RAG 流程: 搜索案例 → 搜索 IP 知识。"""
        from feishu.client import FeishuClient
        from feishu.wiki import FeishuWiki

        client = FeishuClient(app_id=None, app_secret=None)
        wiki = FeishuWiki(client)

        cases = await wiki.search_cases(query="香薰蜡烛", category="家居/香氛")
        ip_info = await wiki.search_ip_knowledge(ip_name="三丽鸥·库洛米")
        assert isinstance(cases, list)
        assert isinstance(ip_info, dict)

    async def test_webhook_notification_flow(self) -> None:
        """Webhook 通知流程: 构建卡片 → Webhook 发送。"""
        from feishu.bot import FeishuBot
        from feishu.client import FeishuClient
        from feishu.templates import build_decision_card

        client = FeishuClient(app_id=None, app_secret=None)
        bot = FeishuBot(
            client,
            webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/demo",
        )
        cards = [_make_card()]
        card = build_decision_card(cards)
        result = await bot.send_webhook(card=card)
        assert isinstance(result, dict)

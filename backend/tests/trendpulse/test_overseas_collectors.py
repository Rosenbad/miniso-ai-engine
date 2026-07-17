# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 海外数据源采集器单元测试 (Task 5)
# ==============================================================================
# 对应 Task 5: 海外数据源采集器
# 覆盖 2 个采集器:
#   1. TiktokCollector     - TikTok 全球热门话题 + 商品 (112 国区域覆盖)
#   2. InstagramCollector  - Instagram 标签趋势 + 网红帖子
#
# 对齐 spec §3.1 海外数据源:
#   - TikTok    : 全球流行先行信号
#   - Instagram : 审美与视觉风格趋势
#
# 测试策略 (TDD):
#   - Mock httpx.AsyncClient 响应 (不发起真实 HTTP 请求)
#   - 验证 _fetch 返回包含 source/region (TikTok) 或 source/tag (Instagram) 字段
#   - 独立测试各解析方法 (_parse_video / _parse_post)
#   - 测试错误处理 (HTTP 错误 / API 错误码 / 空响应 / 畸形数据) — 异常应被抛出, 不吞没
#   - 测试 TikTok 区域校验 (未知 region 抛 ValueError)
#   - 至少 1 个 collect() 集成测试 / 采集器 (验证重试 / 熔断器联动)
# ==============================================================================

"""
测试海外数据源采集器 (TikTok / Instagram)。

Mock 策略:
  - httpx.AsyncClient : 通过 mocker.patch 替换为 AsyncMock, 支持异步上下文管理器
  - response.json()   : 使用 MagicMock (同步方法) 返回预设数据
  - response.status_code : 通过 MagicMock 属性设置
  - 辅助方法 (_get_trending / _get_by_keyword / _get_tag_trends) :
    直接传入 mock client 测试, 无需 patch httpx
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from trendpulse.collectors.base import (
    BaseCollector,
    CircuitBreakerOpenError,
    CircuitState,
)
from trendpulse.collectors.instagram import InstagramCollector
from trendpulse.collectors.tiktok import TiktokCollector


# ==============================================================================
# 测试辅助函数 - Mock httpx 响应与客户端
# ==============================================================================


def _make_mock_response(json_data: Any, status_code: int = 200) -> MagicMock:
    """构造 mock httpx.Response 对象。

    参数:
        json_data    : response.json() 返回的数据
        status_code  : HTTP 状态码

    返回:
        配置好的 MagicMock, 含 .status_code 属性与 .json() 方法
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


def _make_mock_client(response: Any, mocker: Any) -> AsyncMock:
    """构造 mock httpx.AsyncClient (支持 async with 上下文管理器)。

    参数:
        response : client.get() 返回的 mock response (单个) 或 side_effect 列表
        mocker   : pytest-mock 的 mocker fixture

    返回:
        配置好的 AsyncMock, __aenter__ 返回自身, get 为 AsyncMock
    """
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    if isinstance(response, list):
        # side_effect 列表: 每次 get 返回不同响应
        mock_client.get = AsyncMock(side_effect=response)
    else:
        mock_client.get = AsyncMock(return_value=response)
    return mock_client


# ==============================================================================
# 1. TiktokCollector TikTok 采集器测试
# ==============================================================================


class TestTiktokCollector:
    """TikTok 采集器测试。"""

    # --- 构造器 ---

    def test_construction_defaults(self) -> None:
        """默认构造应设置 name / qps_limit / cache_ttl。"""
        collector = TiktokCollector()
        assert collector.name == "tiktok"
        assert collector.qps_limit == 1.0
        assert collector.cache_ttl == 3600
        assert isinstance(collector, BaseCollector)

    def test_construction_custom_base_url(self) -> None:
        """应支持通过构造器自定义 base_url (测试灵活性)。"""
        collector = TiktokCollector(base_url="http://mock-tiktok:9999")
        assert collector.base_url == "http://mock-tiktok:9999"

    def test_inherits_from_base_collector(self) -> None:
        """TiktokCollector 应继承 BaseCollector。"""
        collector = TiktokCollector()
        assert isinstance(collector, BaseCollector)

    def test_known_regions_includes_required(self) -> None:
        """_KNOWN_REGIONS 至少应包含 spec 要求的 12 个区域 (112 国覆盖最低集合)。"""
        collector = TiktokCollector()
        required = {"us", "gb", "jp", "kr", "th", "id", "vn", "de", "fr", "br", "mx", "sea"}
        assert required.issubset(collector._KNOWN_REGIONS)

    # --- _parse_video 解析方法 ---

    def test_parse_video_full_data(self) -> None:
        """完整视频数据解析应返回所有字段, 含 source/region。"""
        collector = TiktokCollector()
        raw_video = {
            "aweme_id": "v1",
            "desc": "Summer fashion haul 2026",
            "statistics": {
                "digg_count": 5000,
                "share_count": 200,
                "play_count": 50000,
            },
            "author": {"unique_id": "fashionista"},
            "share_url": "https://www.tiktok.com/@fashionista/video/v1",
        }
        result = collector._parse_video(raw_video, region="us")
        assert result["topic"] == "Summer fashion haul 2026"
        assert result["source"] == "tiktok"
        assert result["region"] == "us"
        assert result["description"] == "Summer fashion haul 2026"
        assert result["likes"] == 5000
        assert result["shares"] == 200
        assert result["play_count"] == 50000
        assert result["author"] == "fashionista"
        assert result["url"] == "https://www.tiktok.com/@fashionista/video/v1"

    def test_parse_video_missing_fields(self) -> None:
        """缺失字段时应返回默认值 (空字符串 / 0), 不抛异常。"""
        collector = TiktokCollector()
        raw_video = {"aweme_id": "v2"}
        result = collector._parse_video(raw_video, region="jp")
        assert result["topic"] == ""
        assert result["source"] == "tiktok"
        assert result["region"] == "jp"
        assert result["description"] == ""
        assert result["likes"] == 0
        assert result["shares"] == 0
        assert result["play_count"] == 0
        assert result["author"] == ""
        assert "url" in result

    def test_parse_video_string_statistics(self) -> None:
        """统计字段为字符串时应正确转为 int。"""
        collector = TiktokCollector()
        raw_video = {
            "aweme_id": "v3",
            "desc": "viral product",
            "statistics": {
                "digg_count": "5000",
                "share_count": "200",
                "play_count": "50000",
            },
            "author": {"unique_id": "influencer"},
            "share_url": "https://example.com/v3",
        }
        result = collector._parse_video(raw_video, region="gb")
        assert result["likes"] == 5000
        assert result["shares"] == 200
        assert result["play_count"] == 50000
        assert result["region"] == "gb"

    def test_parse_video_constructs_url_from_id(self) -> None:
        """缺少 share_url 时应基于 aweme_id 构造 URL。"""
        collector = TiktokCollector()
        raw_video = {"aweme_id": "abc999", "desc": "test"}
        result = collector._parse_video(raw_video, region="us")
        assert "abc999" in result["url"]

    def test_parse_video_empty(self) -> None:
        """空 dict 解析应返回默认值, 不抛异常。"""
        collector = TiktokCollector()
        result = collector._parse_video({}, region="kr")
        assert result["source"] == "tiktok"
        assert result["region"] == "kr"
        assert result["likes"] == 0

    # --- _fetch 主流程 (mock httpx) ---

    async def test_fetch_trending_returns_parsed_videos(self, mocker: Any) -> None:
        """_fetch (无 keyword) 应走 trending 端点, 返回含 source/region 的列表。"""
        api_response = {
            "status_code": 0,
            "data": {
                "list": [
                    {
                        "aweme_id": "v1",
                        "desc": "Trending topic US",
                        "statistics": {
                            "digg_count": 5000,
                            "share_count": 200,
                            "play_count": 50000,
                        },
                        "author": {"unique_id": "creatorA"},
                        "share_url": "https://www.tiktok.com/@creatorA/video/v1",
                    },
                    {
                        "aweme_id": "v2",
                        "desc": "Viral product",
                        "statistics": {
                            "digg_count": 10000,
                            "share_count": 500,
                            "play_count": 100000,
                        },
                        "author": {"unique_id": "creatorB"},
                        "share_url": "https://www.tiktok.com/@creatorB/video/v2",
                    },
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.tiktok.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = TiktokCollector()

        result = await collector._fetch(keyword="", region="us", limit=20)

        assert len(result) == 2
        for item in result:
            assert "topic" in item
            assert item["source"] == "tiktok"
            assert item["region"] == "us"
        assert result[0]["topic"] == "Trending topic US"
        assert result[0]["play_count"] == 50000
        assert result[1]["author"] == "creatorB"

    async def test_fetch_with_keyword_returns_search_results(self, mocker: Any) -> None:
        """_fetch (传入 keyword) 应走 keyword 搜索端点, 返回含 region 的列表。"""
        api_response = {
            "status_code": 0,
            "data": {
                "list": [
                    {
                        "aweme_id": "s1",
                        "desc": "wabi sabi decor",
                        "statistics": {
                            "digg_count": 1500,
                            "share_count": 80,
                            "play_count": 20000,
                        },
                        "author": {"unique_id": "decorJP"},
                        "share_url": "https://www.tiktok.com/@decorJP/video/s1",
                    }
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.tiktok.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = TiktokCollector()

        result = await collector._fetch(keyword="wabi-sabi", region="jp", limit=20)

        assert len(result) == 1
        assert result[0]["source"] == "tiktok"
        assert result[0]["region"] == "jp"
        assert result[0]["topic"] == "wabi sabi decor"
        assert result[0]["play_count"] == 20000

    async def test_fetch_http_error_raises(self, mocker: Any) -> None:
        """HTTP 非 200 应抛出 RuntimeError (不吞没), 由 BaseCollector 重试。"""
        mock_response = _make_mock_response({}, status_code=500)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.tiktok.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = TiktokCollector()

        with pytest.raises(RuntimeError, match="HTTP 请求失败"):
            await collector._fetch(region="us")

    async def test_fetch_api_error_code_raises(self, mocker: Any) -> None:
        """API 返回错误码 (status_code != 0) 应抛出 RuntimeError, 不再吞没返回 []。"""
        api_response = {"status_code": 1, "status_msg": "rate limited"}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.tiktok.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = TiktokCollector()

        with pytest.raises(RuntimeError, match="API 业务错误码"):
            await collector._fetch(region="us")

    async def test_fetch_empty_list_returns_empty(self, mocker: Any) -> None:
        """API 成功 (status_code=0) 但 list 为空时应返回空列表 (合法空结果)。"""
        api_response = {"status_code": 0, "data": {"list": []}}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.tiktok.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = TiktokCollector()

        result = await collector._fetch(region="us")

        assert result == []

    async def test_fetch_malformed_response_raises(self, mocker: Any) -> None:
        """畸形响应 (缺少 status_code, 视为 != 0) 应抛出 RuntimeError, 不再吞没。"""
        api_response = {"unexpected": True}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.tiktok.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = TiktokCollector()

        with pytest.raises(RuntimeError, match="API 业务错误码"):
            await collector._fetch(region="us")

    async def test_fetch_json_parse_failure_raises(self, mocker: Any) -> None:
        """response.json() 抛 ValueError 时应向上抛出, 不再吞没返回 []。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("invalid json")
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.tiktok.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = TiktokCollector()

        with pytest.raises(ValueError, match="invalid json"):
            await collector._fetch(region="us")

    async def test_fetch_network_error_raises(self, mocker: Any) -> None:
        """client.get 抛出网络异常时应向上抛出, 触发 BaseCollector 重试。"""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mocker.patch(
            "trendpulse.collectors.tiktok.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = TiktokCollector()

        with pytest.raises(httpx.ConnectError):
            await collector._fetch(region="us")

    # --- 区域校验 (未知 region 抛 ValueError) ---

    async def test_fetch_unknown_region_raises_value_error(self, mocker: Any) -> None:
        """未知 region 应抛出 ValueError, 不再静默兜底默认区域。"""
        mock_client = _make_mock_client(_make_mock_response({}), mocker)
        mocker.patch(
            "trendpulse.collectors.tiktok.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = TiktokCollector()

        with pytest.raises(ValueError, match="Unknown region"):
            await collector._fetch(region="mars")

    def test_validate_region_known_returns_true(self) -> None:
        """已知 region 校验应通过 (不抛异常)。"""
        collector = TiktokCollector()
        for region in ["us", "gb", "jp", "kr", "th", "id", "vn", "de", "fr", "br", "mx", "sea"]:
            # 不抛异常即视为通过
            collector._validate_region(region)

    def test_validate_region_unknown_raises(self) -> None:
        """未知 region 校验应抛 ValueError。"""
        collector = TiktokCollector()
        with pytest.raises(ValueError, match="Unknown region"):
            collector._validate_region("atlantis")

    # --- keyword 路由 (有关键词走 _get_by_keyword, 无关键词走 _get_trending) ---

    async def test_fetch_with_keyword_uses_search_endpoint(self, mocker: Any) -> None:
        """传入 keyword 时应调用 _get_by_keyword, URL 含搜索端点路径。"""
        api_response = {
            "status_code": 0,
            "data": {
                "list": [
                    {
                        "aweme_id": "s1",
                        "desc": "search result",
                        "statistics": {
                            "digg_count": 100,
                            "share_count": 5,
                            "play_count": 1000,
                        },
                        "author": {"unique_id": "creator"},
                        "share_url": "https://example.com/s1",
                    }
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.tiktok.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = TiktokCollector()

        result = await collector._fetch(keyword="kawaii", region="jp", limit=20)

        call_args = mock_client.get.call_args
        # 应使用搜索端点 (与 trending 端点不同)
        assert "keyword" in call_args.kwargs.get("params", {})
        assert call_args.kwargs["params"]["keyword"] == "kawaii"
        assert call_args.kwargs["params"]["region"] == "jp"
        assert len(result) == 1
        assert result[0]["region"] == "jp"

    async def test_fetch_without_keyword_uses_trending_endpoint(self, mocker: Any) -> None:
        """未传 keyword 时应调用 _get_trending, params 不含 keyword。"""
        api_response = {
            "status_code": 0,
            "data": {
                "list": [
                    {
                        "aweme_id": "t1",
                        "desc": "trending video",
                        "statistics": {
                            "digg_count": 500,
                            "share_count": 10,
                            "play_count": 5000,
                        },
                        "author": {"unique_id": "hot_creator"},
                        "share_url": "https://example.com/t1",
                    }
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.tiktok.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = TiktokCollector()

        result = await collector._fetch(keyword="", region="gb", limit=10)

        call_args = mock_client.get.call_args
        assert "keyword" not in call_args.kwargs.get("params", {})
        assert call_args.kwargs["params"]["region"] == "gb"
        assert len(result) == 1
        assert result[0]["topic"] == "trending video"

    # --- _get_trending / _get_by_keyword 辅助方法 ---

    async def test_get_trending_calls_get(self, mocker: Any) -> None:
        """_get_trending 应调用 client.get 并返回解析结果。"""
        api_response = {
            "status_code": 0,
            "data": {
                "list": [
                    {
                        "aweme_id": "t1",
                        "desc": "trending",
                        "statistics": {
                            "digg_count": 500,
                            "share_count": 10,
                            "play_count": 5000,
                        },
                        "author": {"unique_id": "creator"},
                        "share_url": "https://example.com/t1",
                    }
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = TiktokCollector()
        result = await collector._get_trending(mock_client, region="us", limit=10)

        mock_client.get.assert_awaited_once()
        assert len(result) == 1
        assert result[0]["topic"] == "trending"
        assert result[0]["region"] == "us"

    async def test_get_by_keyword_calls_get(self, mocker: Any) -> None:
        """_get_by_keyword 应调用 client.get 并返回解析结果。"""
        api_response = {
            "status_code": 0,
            "data": {
                "list": [
                    {
                        "aweme_id": "s1",
                        "desc": "search result",
                        "statistics": {
                            "digg_count": 100,
                            "share_count": 5,
                            "play_count": 1000,
                        },
                        "author": {"unique_id": "creator"},
                        "share_url": "https://example.com/s1",
                    }
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = TiktokCollector()
        result = await collector._get_by_keyword(
            mock_client, keyword="decor", region="de", limit=10
        )

        mock_client.get.assert_awaited_once()
        call_args = mock_client.get.call_args
        assert call_args.kwargs["params"]["keyword"] == "decor"
        assert call_args.kwargs["params"]["region"] == "de"
        assert len(result) == 1
        assert result[0]["region"] == "de"


# ==============================================================================
# 2. InstagramCollector Instagram 采集器测试
# ==============================================================================


class TestInstagramCollector:
    """Instagram 采集器测试。"""

    # --- 构造器 ---

    def test_construction_defaults(self) -> None:
        """默认构造应设置 name / qps_limit (0.5 更严格) / cache_ttl。"""
        collector = InstagramCollector()
        assert collector.name == "instagram"
        assert collector.qps_limit == 0.5
        assert collector.cache_ttl == 3600
        assert isinstance(collector, BaseCollector)

    def test_construction_custom_base_url(self) -> None:
        """应支持自定义 base_url。"""
        collector = InstagramCollector(base_url="http://mock-ig:8080")
        assert collector.base_url == "http://mock-ig:8080"

    def test_inherits_from_base_collector(self) -> None:
        """InstagramCollector 应继承 BaseCollector。"""
        collector = InstagramCollector()
        assert isinstance(collector, BaseCollector)

    # --- _parse_post 解析方法 ---

    def test_parse_post_full_data(self) -> None:
        """完整帖子数据解析应返回所有字段, 含 source/tag。"""
        collector = InstagramCollector()
        raw_post = {
            "id": "p1",
            "caption": "Summer vibes #wabiSabi #aesthetic",
            "like_count": 300,
            "comment_count": 15,
            "user": {"username": "aesthetic_blog"},
            "permalink": "https://www.instagram.com/p/p1/",
            "image_url": "https://scontent.instagram.com/p1.jpg",
        }
        result = collector._parse_post(raw_post)
        assert result["topic"] == "Summer vibes #wabiSabi #aesthetic"
        assert result["source"] == "instagram"
        assert result["caption"] == "Summer vibes #wabiSabi #aesthetic"
        assert result["likes"] == 300
        assert result["comments"] == 15
        assert result["author"] == "aesthetic_blog"
        assert result["url"] == "https://www.instagram.com/p/p1/"
        assert result["image_url"] == "https://scontent.instagram.com/p1.jpg"

    def test_parse_post_with_tag_field(self) -> None:
        """解析结果含 tag 字段 (来自 _get_tag_trends 注入或 raw_post)。"""
        collector = InstagramCollector()
        raw_post = {
            "id": "p2",
            "caption": "minimalist living",
            "like_count": 200,
            "comment_count": 10,
            "user": {"username": "min_blog"},
            "permalink": "https://www.instagram.com/p/p2/",
            "image_url": "https://scontent.instagram.com/p2.jpg",
        }
        result = collector._parse_post(raw_post, tag="minimalism")
        assert result["tag"] == "minimalism"
        assert result["source"] == "instagram"

    def test_parse_post_missing_fields(self) -> None:
        """缺失字段时应返回默认值 (空字符串 / 0), 不抛异常。

        使用空 dict (无 id 也无 permalink) → url 应为 ""。
        (有 id 时会构造 URL, 详见 test_parse_post_constructs_url_from_id)
        """
        collector = InstagramCollector()
        raw_post: Dict[str, Any] = {}
        result = collector._parse_post(raw_post)
        assert result["source"] == "instagram"
        assert result["topic"] == ""
        assert result["caption"] == ""
        assert result["likes"] == 0
        assert result["comments"] == 0
        assert result["author"] == ""
        assert result["url"] == ""
        assert result["image_url"] == ""

    def test_parse_post_string_counts(self) -> None:
        """like_count / comment_count 为字符串时应正确转为 int。"""
        collector = InstagramCollector()
        raw_post = {
            "id": "p3",
            "caption": "test",
            "like_count": "300",
            "comment_count": "15",
            "user": {"username": "u"},
            "permalink": "https://example.com/p3",
            "image_url": "https://example.com/img.jpg",
        }
        result = collector._parse_post(raw_post)
        assert result["likes"] == 300
        assert result["comments"] == 15

    def test_parse_post_constructs_url_from_id(self) -> None:
        """缺少 permalink 时应基于 id 构造 URL。"""
        collector = InstagramCollector()
        raw_post = {"id": "abc123", "caption": "no permalink"}
        result = collector._parse_post(raw_post)
        assert "abc123" in result["url"]

    def test_parse_post_empty(self) -> None:
        """空 dict 解析应返回默认值, 不抛异常。"""
        collector = InstagramCollector()
        result = collector._parse_post({})
        assert result["source"] == "instagram"
        assert result["likes"] == 0

    # --- _fetch 主流程 (mock httpx) ---

    async def test_fetch_returns_parsed_posts(self, mocker: Any) -> None:
        """_fetch 成功时应返回解析后的帖子列表, 每项含 source / tag。"""
        api_response = {
            "status_code": 0,
            "data": {
                "list": [
                    {
                        "id": "p1",
                        "caption": "Wabi-sabi home decor #wabisabi",
                        "like_count": 300,
                        "comment_count": 15,
                        "user": {"username": "wabi_home"},
                        "permalink": "https://www.instagram.com/p/p1/",
                        "image_url": "https://scontent.instagram.com/p1.jpg",
                    },
                    {
                        "id": "p2",
                        "caption": "Aesthetic morning routine",
                        "like_count": 800,
                        "comment_count": 40,
                        "user": {"username": "morning_vibes"},
                        "permalink": "https://www.instagram.com/p/p2/",
                        "image_url": "https://scontent.instagram.com/p2.jpg",
                    },
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.instagram.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = InstagramCollector()

        result = await collector._fetch(tag="wabisabi", limit=20)

        assert len(result) == 2
        for item in result:
            assert "topic" in item
            assert item["source"] == "instagram"
            assert item["tag"] == "wabisabi"
        assert result[0]["topic"] == "Wabi-sabi home decor #wabisabi"
        assert result[0]["likes"] == 300
        assert result[0]["image_url"] == "https://scontent.instagram.com/p1.jpg"
        assert result[1]["author"] == "morning_vibes"

    async def test_fetch_http_error_raises(self, mocker: Any) -> None:
        """HTTP 非 200 应抛出 RuntimeError。"""
        mock_response = _make_mock_response({}, status_code=403)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.instagram.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = InstagramCollector()

        with pytest.raises(RuntimeError, match="HTTP 请求失败"):
            await collector._fetch(tag="aesthetic")

    async def test_fetch_api_error_raises(self, mocker: Any) -> None:
        """API 错误状态码 (status_code != 0) 应抛出 RuntimeError。"""
        api_response = {"status_code": 1, "status_msg": "oauth error"}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.instagram.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = InstagramCollector()

        with pytest.raises(RuntimeError, match="API 业务错误码"):
            await collector._fetch(tag="aesthetic")

    async def test_fetch_empty_list_returns_empty(self, mocker: Any) -> None:
        """API 成功 (status_code=0) 但 list 为空时应返回空列表 (合法空结果)。"""
        api_response = {"status_code": 0, "data": {"list": []}}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.instagram.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = InstagramCollector()

        result = await collector._fetch(tag="emptytag")

        assert result == []

    async def test_fetch_malformed_response_raises(self, mocker: Any) -> None:
        """畸形响应 (缺少 status_code, 视为 != 0) 应抛出 RuntimeError。"""
        api_response = {"unexpected": True}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.instagram.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = InstagramCollector()

        with pytest.raises(RuntimeError, match="API 业务错误码"):
            await collector._fetch(tag="aesthetic")

    async def test_fetch_json_parse_failure_raises(self, mocker: Any) -> None:
        """response.json() 抛 ValueError 时应向上抛出。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("invalid json")
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.instagram.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = InstagramCollector()

        with pytest.raises(ValueError, match="invalid json"):
            await collector._fetch(tag="aesthetic")

    async def test_fetch_network_error_raises(self, mocker: Any) -> None:
        """client.get 抛出网络异常时应向上抛出, 触发 BaseCollector 重试。"""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mocker.patch(
            "trendpulse.collectors.instagram.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = InstagramCollector()

        with pytest.raises(httpx.ConnectError):
            await collector._fetch(tag="aesthetic")

    # --- _get_tag_trends 辅助方法 ---

    async def test_get_tag_trends_calls_get(self, mocker: Any) -> None:
        """_get_tag_trends 应调用 client.get, params 含 tag。"""
        api_response = {
            "status_code": 0,
            "data": {
                "list": [
                    {
                        "id": "g1",
                        "caption": "tagged post",
                        "like_count": 100,
                        "comment_count": 5,
                        "user": {"username": "creator"},
                        "permalink": "https://www.instagram.com/p/g1/",
                        "image_url": "https://example.com/g1.jpg",
                    }
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = InstagramCollector()
        result = await collector._get_tag_trends(mock_client, tag="minimalism", limit=10)

        mock_client.get.assert_awaited_once()
        call_args = mock_client.get.call_args
        assert call_args.kwargs["params"]["tag"] == "minimalism"
        assert len(result) == 1
        assert result[0]["tag"] == "minimalism"
        assert result[0]["topic"] == "tagged post"


# ==============================================================================
# 3. 跨采集器一致性测试
# ==============================================================================


class TestOverseasCollectorConsistency:
    """验证海外采集器返回的数据项均含 topic / source 及各自的区域/标签字段。"""

    async def test_all_overseas_collectors_return_topic_and_source(self, mocker: Any) -> None:
        """两个海外采集器的 _fetch 输出均含 topic 和 source 字段。"""
        # TikTok
        tt_resp = _make_mock_response(
            {
                "status_code": 0,
                "data": {
                    "list": [
                        {
                            "aweme_id": "1",
                            "desc": "t",
                            "statistics": {"digg_count": 1, "share_count": 1, "play_count": 1},
                            "author": {"unique_id": "u"},
                        }
                    ]
                },
            }
        )
        tt_client = _make_mock_client(tt_resp, mocker)
        mocker.patch(
            "trendpulse.collectors.tiktok.httpx.AsyncClient",
            return_value=tt_client,
        )
        tt = TiktokCollector()
        tt_data = await tt._fetch(region="us")
        assert all("topic" in d and "source" in d and "region" in d for d in tt_data)

        # Instagram
        ig_resp = _make_mock_response(
            {
                "status_code": 0,
                "data": {
                    "list": [
                        {
                            "id": "1",
                            "caption": "t",
                            "like_count": 1,
                            "comment_count": 1,
                            "user": {"username": "u"},
                        }
                    ]
                },
            }
        )
        ig_client = _make_mock_client(ig_resp, mocker)
        mocker.patch(
            "trendpulse.collectors.instagram.httpx.AsyncClient",
            return_value=ig_client,
        )
        ig = InstagramCollector()
        ig_data = await ig._fetch(tag="t")
        assert all("topic" in d and "source" in d and "tag" in d for d in ig_data)

    def test_source_field_values(self) -> None:
        """各采集器的 source 字段应为对应标识。"""
        assert TiktokCollector()._parse_video({}, region="us")["source"] == "tiktok"
        assert InstagramCollector()._parse_post({})["source"] == "instagram"


# ==============================================================================
# 4. collect() 集成测试 - 端到端验证熔断 / 缓存 / 重试联动
# ==============================================================================


class TestOverseasCollectIntegration:
    """collect() 主流程集成测试 (海外采集器)。

    端到端验证 BaseCollector 的熔断 / 缓存 / 重试机制与 TikTok / Instagram 采集器的联动。
    使用 mock _fetch / _get_cached / _set_cached / _check_rate_limit 隔离依赖。
    """

    async def test_tiktok_collect_failing_fetch_triggers_retries_and_opens_circuit(
        self, mocker: Any
    ) -> None:
        """TikTok: collect() 持续失败时触发重试, 并最终使熔断器 OPEN。

        场景:
            - _fetch 每次抛 RuntimeError (模拟 HTTP 失败)
            - max_retries=3 → 每次 collect 调用 _fetch 4 次 (1 初始 + 3 重试)
            - 连续 3 次 collect 失败 → 熔断器 failure_threshold=3 → OPEN

        验证:
            - 前 3 次 collect 均抛 RuntimeError (重试耗尽)
            - 第 4 次 collect 抛 CircuitBreakerOpenError (熔断器已 OPEN)
            - _fetch 总调用次数 = 3 * 4 = 12 次
        """
        mocker.patch.object(
            TiktokCollector, "_check_rate_limit", new=mocker.AsyncMock()
        )
        mocker.patch.object(
            TiktokCollector, "_get_cached", new=mocker.AsyncMock(return_value=None)
        )
        mocker.patch.object(
            TiktokCollector, "_set_cached", new=mocker.AsyncMock()
        )
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )

        collector = TiktokCollector(max_retries=3)
        fetch_mock = AsyncMock(side_effect=RuntimeError("network error"))
        collector._fetch = fetch_mock

        for _ in range(3):
            with pytest.raises(RuntimeError, match="network error"):
                await collector.collect(region="us")

        assert collector.circuit_breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenError):
            await collector.collect(region="us")

        assert fetch_mock.await_count == 12

    async def test_tiktok_collect_successful_fetch_caches_result(
        self, mocker: Any
    ) -> None:
        """TikTok: collect() 成功时结果被缓存, 第二次 collect 命中缓存。"""
        mocker.patch.object(
            TiktokCollector, "_check_rate_limit", new=mocker.AsyncMock()
        )
        mocker.patch.object(
            TiktokCollector, "_set_cached", new=mocker.AsyncMock()
        )

        cached_data = [{"topic": "cached_tt", "source": "tiktok", "region": "us"}]
        fresh_data = [{"topic": "fresh_tt", "source": "tiktok", "region": "us"}]

        get_cached = mocker.patch.object(
            TiktokCollector,
            "_get_cached",
            new=mocker.AsyncMock(side_effect=[None, cached_data]),
        )
        collector = TiktokCollector()
        fetch_mock = AsyncMock(return_value=fresh_data)
        collector._fetch = fetch_mock

        result1 = await collector.collect(region="us")
        assert result1 == fresh_data
        assert fetch_mock.await_count == 1

        result2 = await collector.collect(region="us")
        assert result2 == cached_data
        assert fetch_mock.await_count == 1

        assert get_cached.await_count == 2

    async def test_tiktok_collect_circuit_breaker_open_fails_fast(
        self, mocker: Any
    ) -> None:
        """TikTok: 熔断器 OPEN 时 collect() 快速失败, 不调用 _fetch。"""
        collector = TiktokCollector()
        for _ in range(collector.circuit_breaker.failure_threshold):
            await collector.circuit_breaker.record_failure()
        assert collector.circuit_breaker.state == CircuitState.OPEN

        fetch_mock = AsyncMock(return_value=[{"topic": "should_not_be_called"}])
        collector._fetch = fetch_mock

        with pytest.raises(CircuitBreakerOpenError):
            await collector.collect(region="us")

        fetch_mock.assert_not_called()

    async def test_instagram_collect_failing_fetch_triggers_retries_and_opens_circuit(
        self, mocker: Any
    ) -> None:
        """Instagram: collect() 持续失败时触发重试, 并最终使熔断器 OPEN。"""
        mocker.patch.object(
            InstagramCollector, "_check_rate_limit", new=mocker.AsyncMock()
        )
        mocker.patch.object(
            InstagramCollector, "_get_cached", new=mocker.AsyncMock(return_value=None)
        )
        mocker.patch.object(
            InstagramCollector, "_set_cached", new=mocker.AsyncMock()
        )
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )

        collector = InstagramCollector(max_retries=3)
        fetch_mock = AsyncMock(side_effect=RuntimeError("network error"))
        collector._fetch = fetch_mock

        for _ in range(3):
            with pytest.raises(RuntimeError, match="network error"):
                await collector.collect(tag="aesthetic")

        assert collector.circuit_breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitBreakerOpenError):
            await collector.collect(tag="aesthetic")

        assert fetch_mock.await_count == 12

    async def test_instagram_collect_successful_fetch_caches_result(
        self, mocker: Any
    ) -> None:
        """Instagram: collect() 成功时结果被缓存, 第二次 collect 命中缓存。"""
        mocker.patch.object(
            InstagramCollector, "_check_rate_limit", new=mocker.AsyncMock()
        )
        mocker.patch.object(
            InstagramCollector, "_set_cached", new=mocker.AsyncMock()
        )

        cached_data = [{"topic": "cached_ig", "source": "instagram", "tag": "aesthetic"}]
        fresh_data = [{"topic": "fresh_ig", "source": "instagram", "tag": "aesthetic"}]

        get_cached = mocker.patch.object(
            InstagramCollector,
            "_get_cached",
            new=mocker.AsyncMock(side_effect=[None, cached_data]),
        )
        collector = InstagramCollector()
        fetch_mock = AsyncMock(return_value=fresh_data)
        collector._fetch = fetch_mock

        result1 = await collector.collect(tag="aesthetic")
        assert result1 == fresh_data
        assert fetch_mock.await_count == 1

        result2 = await collector.collect(tag="aesthetic")
        assert result2 == cached_data
        assert fetch_mock.await_count == 1

        assert get_cached.await_count == 2

    async def test_instagram_collect_circuit_breaker_open_fails_fast(
        self, mocker: Any
    ) -> None:
        """Instagram: 熔断器 OPEN 时 collect() 快速失败, 不调用 _fetch。"""
        collector = InstagramCollector()
        for _ in range(collector.circuit_breaker.failure_threshold):
            await collector.circuit_breaker.record_failure()
        assert collector.circuit_breaker.state == CircuitState.OPEN

        fetch_mock = AsyncMock(return_value=[{"topic": "should_not_be_called"}])
        collector._fetch = fetch_mock

        with pytest.raises(CircuitBreakerOpenError):
            await collector.collect(tag="aesthetic")

        fetch_mock.assert_not_called()

    async def test_instagram_collect_failed_fetch_returns_cached_fallback(
        self, mocker: Any
    ) -> None:
        """Instagram: _fetch 重试耗尽后, 若有缓存则返回缓存降级数据。"""
        mocker.patch.object(
            InstagramCollector, "_check_rate_limit", new=mocker.AsyncMock()
        )
        mocker.patch.object(
            InstagramCollector, "_set_cached", new=mocker.AsyncMock()
        )
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )

        cached_data = [{"topic": "stale_cache_ig", "source": "instagram"}]
        mocker.patch.object(
            InstagramCollector,
            "_get_cached",
            new=mocker.AsyncMock(side_effect=[None, cached_data]),
        )

        collector = InstagramCollector(max_retries=2)
        collector._fetch = AsyncMock(side_effect=RuntimeError("network down"))

        result = await collector.collect(tag="aesthetic")
        assert result == cached_data

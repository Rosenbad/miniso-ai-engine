# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 中国数据源采集器单元测试 (Task 4)
# ==============================================================================
# 对应 Task 4: 中国数据源采集器
# 覆盖 4 个采集器:
#   1. XiaohongshuCollector - 小红书笔记采集
#   2. DouyinCollector       - 抖音话题/商品采集
#   3. EcommerceCollector    - 电商热销榜采集 (淘宝/拼多多)
#   4. SearchIndexCollector  - 搜索指数采集 (百度/微信)
#
# 测试策略 (TDD):
#   - Mock httpx.AsyncClient 响应 (不发起真实 HTTP 请求)
#   - 验证 _fetch 返回包含 topic / source 字段的解析结果
#   - 独立测试各解析方法 (_parse_note / _parse_video / _parse_product / _parse_index)
#   - 测试错误处理 (HTTP 错误 / API 错误码 / 空响应 / 畸形数据)
# ==============================================================================

"""
测试中国数据源采集器 (小红书 / 抖音 / 电商 / 搜索指数)。

Mock 策略:
  - httpx.AsyncClient : 通过 mocker.patch 替换为 AsyncMock, 支持异步上下文管理器
  - response.json()   : 使用 MagicMock (同步方法) 返回预设数据
  - response.status_code : 通过 MagicMock 属性设置
  - 辅助方法 (_search_notes 等) : 直接传入 mock client 测试, 无需 patch httpx
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from trendpulse.collectors.base import BaseCollector
from trendpulse.collectors.xiaohongshu import XiaohongshuCollector
from trendpulse.collectors.douyin import DouyinCollector
from trendpulse.collectors.ecommerce import EcommerceCollector
from trendpulse.collectors.search_index import SearchIndexCollector


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
# 1. XiaohongshuCollector 小红书采集器测试
# ==============================================================================


class TestXiaohongshuCollector:
    """小红书采集器测试。"""

    # --- 构造器 ---

    def test_construction_defaults(self) -> None:
        """默认构造应设置 name / qps_limit / cache_ttl。"""
        collector = XiaohongshuCollector()
        assert collector.name == "xiaohongshu"
        assert collector.qps_limit == 0.5
        assert collector.cache_ttl == 3600
        assert isinstance(collector, BaseCollector)

    def test_construction_custom_base_url(self) -> None:
        """应支持通过构造器自定义 base_url (测试灵活性)。"""
        collector = XiaohongshuCollector(base_url="http://mock-server:9999")
        assert collector.base_url == "http://mock-server:9999"

    def test_inherits_from_base_collector(self) -> None:
        """XiaohongshuCollector 应继承 BaseCollector。"""
        collector = XiaohongshuCollector()
        assert isinstance(collector, BaseCollector)

    # --- _parse_note 解析方法 ---

    def test_parse_note_full_data(self) -> None:
        """完整数据解析应返回所有字段。"""
        collector = XiaohongshuCollector()
        raw_note = {
            "note_id": "abc123",
            "note_card": {
                "title": "侘寂风家居分享",
                "desc": "今天分享一套侘寂风家居搭配",
                "user": {"nickname": "家居达人"},
                "interact_info": {"liked_count": "100", "comment_count": "20"},
                "note_url": "https://www.xiaohongshu.com/note/abc123",
            },
        }
        result = collector._parse_note(raw_note)
        assert result["topic"] == "侘寂风家居分享"
        assert result["source"] == "xiaohongshu"
        assert result["content"] == "今天分享一套侘寂风家居搭配"
        assert result["likes"] == 100
        assert result["comments"] == 20
        assert result["author"] == "家居达人"
        assert result["url"] == "https://www.xiaohongshu.com/note/abc123"

    def test_parse_note_missing_fields(self) -> None:
        """缺失字段时应返回默认值 (空字符串 / 0), 不抛异常。"""
        collector = XiaohongshuCollector()
        raw_note = {"note_id": "x1", "note_card": {}}
        result = collector._parse_note(raw_note)
        assert result["topic"] == ""
        assert result["source"] == "xiaohongshu"
        assert result["content"] == ""
        assert result["likes"] == 0
        assert result["comments"] == 0
        assert result["author"] == ""
        assert "url" in result

    def test_parse_note_flat_structure(self) -> None:
        """扁平结构 (无 note_card 嵌套) 也应能解析。"""
        collector = XiaohongshuCollector()
        raw_note = {
            "note_id": "flat1",
            "title": "扁平笔记",
            "desc": "扁平描述",
            "user": {"nickname": "扁平作者"},
            "interact_info": {"liked_count": "50", "comment_count": "5"},
        }
        result = collector._parse_note(raw_note)
        assert result["topic"] == "扁平笔记"
        assert result["author"] == "扁平作者"
        assert result["likes"] == 50

    def test_parse_note_empty(self) -> None:
        """空 dict 解析应返回默认值, 不抛异常。"""
        collector = XiaohongshuCollector()
        result = collector._parse_note({})
        assert result["source"] == "xiaohongshu"
        assert result["likes"] == 0

    # --- _fetch 主流程 (mock httpx) ---

    async def test_fetch_returns_parsed_notes(self, mocker: Any) -> None:
        """_fetch 成功时应返回解析后的笔记列表, 每项含 topic / source。"""
        api_response = {
            "code": 0,
            "data": {
                "items": [
                    {
                        "note_id": "n1",
                        "note_card": {
                            "title": "侘寂风家居",
                            "desc": "分享",
                            "user": {"nickname": "达人A"},
                            "interact_info": {"liked_count": "100", "comment_count": "10"},
                            "note_url": "https://www.xiaohongshu.com/note/n1",
                        },
                    },
                    {
                        "note_id": "n2",
                        "note_card": {
                            "title": "多巴胺穿搭",
                            "desc": "夏日穿搭",
                            "user": {"nickname": "达人B"},
                            "interact_info": {"liked_count": "200", "comment_count": "30"},
                            "note_url": "https://www.xiaohongshu.com/note/n2",
                        },
                    },
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.xiaohongshu.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = XiaohongshuCollector()

        result = await collector._fetch(keyword="侘寂风", limit=20)

        assert len(result) == 2
        for item in result:
            assert "topic" in item
            assert item["source"] == "xiaohongshu"
        assert result[0]["topic"] == "侘寂风家居"
        assert result[0]["likes"] == 100
        assert result[1]["topic"] == "多巴胺穿搭"
        assert result[1]["author"] == "达人B"

    async def test_fetch_http_error_returns_empty(self, mocker: Any) -> None:
        """HTTP 非 200 状态码应返回空列表, 不抛异常。"""
        mock_response = _make_mock_response({}, status_code=500)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.xiaohongshu.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = XiaohongshuCollector()

        result = await collector._fetch(keyword="test")

        assert result == []

    async def test_fetch_api_error_code_returns_empty(self, mocker: Any) -> None:
        """API 返回错误码 (code != 0) 应返回空列表。"""
        api_response = {"code": 1001, "msg": "参数错误", "data": {}}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.xiaohongshu.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = XiaohongshuCollector()

        result = await collector._fetch(keyword="test")

        assert result == []

    async def test_fetch_empty_items_returns_empty(self, mocker: Any) -> None:
        """API 返回空 items 列表时应返回空列表。"""
        api_response = {"code": 0, "data": {"items": []}}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.xiaohongshu.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = XiaohongshuCollector()

        result = await collector._fetch(keyword="test")

        assert result == []

    async def test_fetch_malformed_response_returns_empty(self, mocker: Any) -> None:
        """畸形响应 (缺少 data 字段) 应返回空列表, 不抛异常。"""
        api_response = {"unexpected": "structure"}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.xiaohongshu.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = XiaohongshuCollector()

        result = await collector._fetch(keyword="test")

        assert result == []

    # --- _search_notes 辅助方法 (直接传入 mock client) ---

    async def test_search_notes_calls_get(self, mocker: Any) -> None:
        """_search_notes 应调用 client.get 并返回解析结果。"""
        api_response = {
            "code": 0,
            "data": {
                "items": [
                    {
                        "note_id": "x1",
                        "note_card": {
                            "title": "测试笔记",
                            "desc": "描述",
                            "user": {"nickname": "作者"},
                            "interact_info": {"liked_count": "10", "comment_count": "1"},
                            "note_url": "https://example.com/x1",
                        },
                    }
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = XiaohongshuCollector()
        result = await collector._search_notes(mock_client, "测试", 10)

        mock_client.get.assert_awaited_once()
        assert len(result) == 1
        assert result[0]["topic"] == "测试笔记"


# ==============================================================================
# 2. DouyinCollector 抖音采集器测试
# ==============================================================================


class TestDouyinCollector:
    """抖音采集器测试。"""

    # --- 构造器 ---

    def test_construction_defaults(self) -> None:
        """默认构造应设置 name / qps_limit / cache_ttl。"""
        collector = DouyinCollector()
        assert collector.name == "douyin"
        assert collector.qps_limit == 1.0
        assert collector.cache_ttl == 3600
        assert isinstance(collector, BaseCollector)

    def test_construction_custom_base_url(self) -> None:
        """应支持自定义 base_url。"""
        collector = DouyinCollector(base_url="http://mock-douyin:8080")
        assert collector.base_url == "http://mock-douyin:8080"

    # --- _parse_video 解析方法 ---

    def test_parse_video_full_data(self) -> None:
        """完整视频数据解析应返回所有字段。"""
        collector = DouyinCollector()
        raw_video = {
            "aweme_id": "v1",
            "desc": "夏日清凉好物推荐",
            "statistics": {
                "digg_count": 1000,
                "share_count": 50,
                "play_count": 10000,
            },
            "author": {"nickname": "好物达人"},
            "share_url": "https://www.douyin.com/video/v1",
        }
        result = collector._parse_video(raw_video)
        assert result["topic"] == "夏日清凉好物推荐"
        assert result["source"] == "douyin"
        assert result["description"] == "夏日清凉好物推荐"
        assert result["likes"] == 1000
        assert result["shares"] == 50
        assert result["play_count"] == 10000
        assert result["author"] == "好物达人"
        assert result["url"] == "https://www.douyin.com/video/v1"

    def test_parse_video_missing_fields(self) -> None:
        """缺失字段时应返回默认值, 不抛异常。"""
        collector = DouyinCollector()
        raw_video = {"aweme_id": "v2"}
        result = collector._parse_video(raw_video)
        assert result["topic"] == ""
        assert result["source"] == "douyin"
        assert result["likes"] == 0
        assert result["shares"] == 0
        assert result["play_count"] == 0
        assert result["author"] == ""

    def test_parse_video_string_statistics(self) -> None:
        """统计字段为字符串时应正确转为 int。"""
        collector = DouyinCollector()
        raw_video = {
            "aweme_id": "v3",
            "desc": "测试",
            "statistics": {"digg_count": "500", "share_count": "25", "play_count": "8000"},
            "author": {"nickname": "达人"},
            "share_url": "https://example.com/v3",
        }
        result = collector._parse_video(raw_video)
        assert result["likes"] == 500
        assert result["shares"] == 25
        assert result["play_count"] == 8000

    def test_parse_video_empty(self) -> None:
        """空 dict 解析应返回默认值。"""
        collector = DouyinCollector()
        result = collector._parse_video({})
        assert result["source"] == "douyin"
        assert result["likes"] == 0

    # --- _fetch 主流程 ---

    async def test_fetch_returns_parsed_videos(self, mocker: Any) -> None:
        """_fetch 成功时应返回解析后的视频列表, 每项含 topic / source。"""
        api_response = {
            "status_code": 0,
            "data": {
                "list": [
                    {
                        "aweme_id": "v1",
                        "desc": "好物推荐",
                        "statistics": {"digg_count": 1000, "share_count": 50, "play_count": 10000},
                        "author": {"nickname": "达人A"},
                        "share_url": "https://www.douyin.com/video/v1",
                    },
                    {
                        "aweme_id": "v2",
                        "desc": "夏日穿搭",
                        "statistics": {"digg_count": 2000, "share_count": 100, "play_count": 20000},
                        "author": {"nickname": "达人B"},
                        "share_url": "https://www.douyin.com/video/v2",
                    },
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.douyin.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = DouyinCollector()

        result = await collector._fetch(keyword="好物", limit=20)

        assert len(result) == 2
        for item in result:
            assert "topic" in item
            assert item["source"] == "douyin"
        assert result[0]["topic"] == "好物推荐"
        assert result[0]["play_count"] == 10000
        assert result[1]["author"] == "达人B"

    async def test_fetch_http_error_returns_empty(self, mocker: Any) -> None:
        """HTTP 非 200 应返回空列表。"""
        mock_response = _make_mock_response({}, status_code=403)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.douyin.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = DouyinCollector()

        result = await collector._fetch(keyword="test")

        assert result == []

    async def test_fetch_api_error_returns_empty(self, mocker: Any) -> None:
        """API 错误状态码应返回空列表。"""
        api_response = {"status_code": 1, "status_msg": "rate limited"}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.douyin.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = DouyinCollector()

        result = await collector._fetch(keyword="test")

        assert result == []

    async def test_fetch_empty_list_returns_empty(self, mocker: Any) -> None:
        """空 list 应返回空列表。"""
        api_response = {"status_code": 0, "data": {"list": []}}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.douyin.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = DouyinCollector()

        result = await collector._fetch(keyword="test")

        assert result == []

    async def test_fetch_malformed_response_returns_empty(self, mocker: Any) -> None:
        """畸形响应应返回空列表。"""
        api_response = {"unexpected": True}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.douyin.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = DouyinCollector()

        result = await collector._fetch(keyword="test")

        assert result == []

    # --- _get_trending 辅助方法 ---

    async def test_get_trending_calls_get(self, mocker: Any) -> None:
        """_get_trending 应调用 client.get。"""
        api_response = {
            "status_code": 0,
            "data": {
                "list": [
                    {
                        "aweme_id": "t1",
                        "desc": "热门视频",
                        "statistics": {"digg_count": 500, "share_count": 10, "play_count": 5000},
                        "author": {"nickname": "热门达人"},
                        "share_url": "https://example.com/t1",
                    }
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = DouyinCollector()
        result = await collector._get_trending(mock_client, limit=10)

        mock_client.get.assert_awaited_once()
        assert len(result) == 1
        assert result[0]["topic"] == "热门视频"


# ==============================================================================
# 3. EcommerceCollector 电商采集器测试
# ==============================================================================


class TestEcommerceCollector:
    """电商热销榜采集器测试。"""

    # --- 构造器 ---

    def test_construction_defaults(self) -> None:
        """默认构造应设置 name / qps_limit / cache_ttl。"""
        collector = EcommerceCollector()
        assert collector.name == "ecommerce"
        assert collector.qps_limit == 1.0
        assert collector.cache_ttl == 3600
        assert isinstance(collector, BaseCollector)

    def test_construction_custom_base_urls(self) -> None:
        """应支持自定义各平台 base_url。"""
        collector = EcommerceCollector(
            taobao_url="http://mock-taobao:8080",
            pinduoduo_url="http://mock-pdd:8081",
        )
        assert collector.taobao_url == "http://mock-taobao:8080"
        assert collector.pinduoduo_url == "http://mock-pdd:8081"

    # --- _parse_product 解析方法 ---

    def test_parse_product_taobao_full_data(self) -> None:
        """淘宝商品完整数据解析。"""
        collector = EcommerceCollector()
        raw_product = {
            "item_id": "i1",
            "title": "侘寂风陶瓷花瓶",
            "price": "29.9",
            "sales": "5000",
            "item_url": "https://item.taobao.com/i1",
            "category": "家居装饰",
        }
        result = collector._parse_product(raw_product, "taobao")
        assert result["topic"] == "侘寂风陶瓷花瓶"
        assert result["source"] == "ecommerce"
        assert result["product_name"] == "侘寂风陶瓷花瓶"
        assert result["price"] == 29.9
        assert result["sales"] == 5000
        assert result["platform"] == "taobao"
        assert result["url"] == "https://item.taobao.com/i1"
        assert result["category"] == "家居装饰"

    def test_parse_product_pinduoduo(self) -> None:
        """拼多多商品解析, platform 应为 pinduoduo。"""
        collector = EcommerceCollector()
        raw_product = {
            "item_id": "p1",
            "title": "多巴胺收纳盒",
            "price": "9.9",
            "sales": "10000",
            "item_url": "https://mobile.yangkeduo.com/p1",
            "category": "收纳",
        }
        result = collector._parse_product(raw_product, "pinduoduo")
        assert result["platform"] == "pinduoduo"
        assert result["price"] == 9.9
        assert result["sales"] == 10000

    def test_parse_product_missing_fields(self) -> None:
        """缺失字段时应返回默认值, 不抛异常。"""
        collector = EcommerceCollector()
        raw_product = {"item_id": "x1"}
        result = collector._parse_product(raw_product, "taobao")
        assert result["topic"] == ""
        assert result["source"] == "ecommerce"
        assert result["product_name"] == ""
        assert result["price"] == 0
        assert result["sales"] == 0
        assert result["platform"] == "taobao"

    def test_parse_product_empty(self) -> None:
        """空 dict 解析应返回默认值。"""
        collector = EcommerceCollector()
        result = collector._parse_product({}, "taobao")
        assert result["source"] == "ecommerce"
        assert result["price"] == 0

    # --- _fetch 主流程 ---

    async def test_fetch_taobao_returns_products(self, mocker: Any) -> None:
        """_fetch (taobao) 成功时应返回解析后的商品列表。"""
        api_response = {
            "code": 0,
            "data": {
                "items": [
                    {
                        "item_id": "i1",
                        "title": "侘寂风花瓶",
                        "price": "29.9",
                        "sales": "5000",
                        "item_url": "https://item.taobao.com/i1",
                        "category": "家居",
                    },
                    {
                        "item_id": "i2",
                        "title": "香薰蜡烛",
                        "price": "19.9",
                        "sales": "8000",
                        "item_url": "https://item.taobao.com/i2",
                        "category": "家居",
                    },
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.ecommerce.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = EcommerceCollector()

        result = await collector._fetch(platform="taobao", category="家居", limit=50)

        assert len(result) == 2
        for item in result:
            assert "topic" in item
            assert item["source"] == "ecommerce"
            assert item["platform"] == "taobao"
        assert result[0]["topic"] == "侘寂风花瓶"
        assert result[0]["price"] == 29.9
        assert result[1]["sales"] == 8000

    async def test_fetch_pinduoduo_returns_products(self, mocker: Any) -> None:
        """_fetch (pinduoduo) 成功时应返回 platform=pinduoduo 的商品。"""
        api_response = {
            "code": 0,
            "data": {
                "items": [
                    {
                        "item_id": "p1",
                        "title": "拼多多爆款",
                        "price": "5.9",
                        "sales": "20000",
                        "item_url": "https://mobile.yangkeduo.com/p1",
                        "category": "日用",
                    }
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.ecommerce.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = EcommerceCollector()

        result = await collector._fetch(platform="pinduoduo", limit=50)

        assert len(result) == 1
        assert result[0]["platform"] == "pinduoduo"
        assert result[0]["price"] == 5.9

    async def test_fetch_http_error_returns_empty(self, mocker: Any) -> None:
        """HTTP 错误应返回空列表。"""
        mock_response = _make_mock_response({}, status_code=500)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.ecommerce.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = EcommerceCollector()

        result = await collector._fetch(platform="taobao")

        assert result == []

    async def test_fetch_api_error_returns_empty(self, mocker: Any) -> None:
        """API 错误码应返回空列表。"""
        api_response = {"code": 500, "msg": "error"}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.ecommerce.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = EcommerceCollector()

        result = await collector._fetch(platform="taobao")

        assert result == []

    async def test_fetch_empty_items_returns_empty(self, mocker: Any) -> None:
        """空 items 应返回空列表。"""
        api_response = {"code": 0, "data": {"items": []}}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.ecommerce.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = EcommerceCollector()

        result = await collector._fetch(platform="taobao")

        assert result == []

    async def test_fetch_malformed_response_returns_empty(self, mocker: Any) -> None:
        """畸形响应应返回空列表。"""
        api_response = {"no_data": True}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.ecommerce.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = EcommerceCollector()

        result = await collector._fetch(platform="taobao")

        assert result == []

    # --- _get_hotlist 辅助方法 ---

    async def test_get_hotlist_calls_get(self, mocker: Any) -> None:
        """_get_hotlist 应调用 client.get。"""
        api_response = {
            "code": 0,
            "data": {
                "items": [
                    {
                        "item_id": "h1",
                        "title": "热销商品",
                        "price": "15.9",
                        "sales": "3000",
                        "item_url": "https://item.taobao.com/h1",
                        "category": "家居",
                    }
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = EcommerceCollector()
        result = await collector._get_hotlist(mock_client, "taobao", "家居", 50)

        mock_client.get.assert_awaited_once()
        assert len(result) == 1
        assert result[0]["topic"] == "热销商品"


# ==============================================================================
# 4. SearchIndexCollector 搜索指数采集器测试
# ==============================================================================


class TestSearchIndexCollector:
    """搜索指数采集器测试。"""

    # --- 构造器 ---

    def test_construction_defaults(self) -> None:
        """默认构造应设置 name / qps_limit / cache_ttl (较短 TTL)。"""
        collector = SearchIndexCollector()
        assert collector.name == "search_index"
        assert collector.qps_limit == 2.0
        assert collector.cache_ttl == 1800
        assert isinstance(collector, BaseCollector)

    def test_construction_custom_base_urls(self) -> None:
        """应支持自定义百度/微信指数 base_url。"""
        collector = SearchIndexCollector(
            baidu_url="http://mock-baidu:8080",
            weixin_url="http://mock-weixin:8081",
        )
        assert collector.baidu_url == "http://mock-baidu:8080"
        assert collector.weixin_url == "http://mock-weixin:8081"

    # --- _parse_index 解析方法 ---

    def test_parse_index_baidu_full_data(self) -> None:
        """百度指数完整数据解析。"""
        collector = SearchIndexCollector()
        raw_data = {
            "index": 1234,
            "trend": "rising",
            "date": "2026-07-17",
        }
        result = collector._parse_index(raw_data, "侘寂风", "baidu")
        assert result["topic"] == "侘寂风"
        assert result["source"] == "search_index"
        assert result["keyword"] == "侘寂风"
        assert result["index_value"] == 1234
        assert result["trend"] == "rising"
        assert result["platform"] == "baidu"
        assert result["date"] == "2026-07-17"

    def test_parse_index_weixin(self) -> None:
        """微信指数解析, platform 应为 weixin。"""
        collector = SearchIndexCollector()
        raw_data = {
            "index": 5678,
            "trend": "peak",
            "date": "2026-07-17",
        }
        result = collector._parse_index(raw_data, "多巴胺", "weixin")
        assert result["platform"] == "weixin"
        assert result["index_value"] == 5678
        assert result["trend"] == "peak"

    def test_parse_index_string_index(self) -> None:
        """index 为字符串时应正确转为 int。"""
        collector = SearchIndexCollector()
        raw_data = {"index": "999", "trend": "declining", "date": "2026-07-17"}
        result = collector._parse_index(raw_data, "test", "baidu")
        assert result["index_value"] == 999
        assert result["trend"] == "declining"

    def test_parse_index_missing_fields(self) -> None:
        """缺失字段时应返回默认值, 不抛异常。"""
        collector = SearchIndexCollector()
        result = collector._parse_index({}, "test", "baidu")
        assert result["topic"] == "test"
        assert result["source"] == "search_index"
        assert result["keyword"] == "test"
        assert result["index_value"] == 0
        assert result["trend"] == ""
        assert result["platform"] == "baidu"
        assert result["date"] == ""

    def test_parse_index_empty(self) -> None:
        """空 dict 解析应返回默认值。"""
        collector = SearchIndexCollector()
        result = collector._parse_index({}, "kw", "weixin")
        assert result["source"] == "search_index"
        assert result["index_value"] == 0

    # --- _fetch 主流程 ---

    async def test_fetch_baidu_returns_index(self, mocker: Any) -> None:
        """_fetch (baidu) 成功时应返回解析后的指数数据列表。"""
        api_response = {
            "code": 0,
            "data": {
                "keyword": "侘寂风",
                "index_list": [
                    {"index": 1234, "trend": "rising", "date": "2026-07-17"},
                    {"index": 1500, "trend": "rising", "date": "2026-07-16"},
                ],
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.search_index.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = SearchIndexCollector()

        result = await collector._fetch(keyword="侘寂风", platform="baidu", limit=20)

        assert len(result) == 2
        for item in result:
            assert "topic" in item
            assert item["source"] == "search_index"
            assert item["platform"] == "baidu"
        assert result[0]["index_value"] == 1234
        assert result[0]["trend"] == "rising"
        assert result[1]["index_value"] == 1500

    async def test_fetch_weixin_returns_index(self, mocker: Any) -> None:
        """_fetch (weixin) 成功时应返回 platform=weixin 的指数。"""
        api_response = {
            "code": 0,
            "data": {
                "keyword": "多巴胺",
                "index_list": [
                    {"index": 888, "trend": "peak", "date": "2026-07-17"},
                ],
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.search_index.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = SearchIndexCollector()

        result = await collector._fetch(keyword="多巴胺", platform="weixin")

        assert len(result) == 1
        assert result[0]["platform"] == "weixin"
        assert result[0]["index_value"] == 888

    async def test_fetch_http_error_returns_empty(self, mocker: Any) -> None:
        """HTTP 错误应返回空列表。"""
        mock_response = _make_mock_response({}, status_code=502)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.search_index.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = SearchIndexCollector()

        result = await collector._fetch(keyword="test", platform="baidu")

        assert result == []

    async def test_fetch_api_error_returns_empty(self, mocker: Any) -> None:
        """API 错误码应返回空列表。"""
        api_response = {"code": 1, "msg": "invalid"}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.search_index.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = SearchIndexCollector()

        result = await collector._fetch(keyword="test", platform="baidu")

        assert result == []

    async def test_fetch_empty_list_returns_empty(self, mocker: Any) -> None:
        """空 index_list 应返回空列表。"""
        api_response = {"code": 0, "data": {"keyword": "test", "index_list": []}}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.search_index.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = SearchIndexCollector()

        result = await collector._fetch(keyword="test", platform="baidu")

        assert result == []

    async def test_fetch_malformed_response_returns_empty(self, mocker: Any) -> None:
        """畸形响应应返回空列表。"""
        api_response = {"broken": True}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.search_index.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = SearchIndexCollector()

        result = await collector._fetch(keyword="test", platform="baidu")

        assert result == []

    # --- _get_index 辅助方法 ---

    async def test_get_index_calls_get(self, mocker: Any) -> None:
        """_get_index 应调用 client.get。"""
        api_response = {
            "code": 0,
            "data": {
                "keyword": "测试",
                "index_list": [
                    {"index": 100, "trend": "rising", "date": "2026-07-17"},
                ],
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = SearchIndexCollector()
        result = await collector._get_index(mock_client, "测试", "baidu")

        mock_client.get.assert_awaited_once()
        assert len(result) == 1
        assert result[0]["keyword"] == "测试"
        assert result[0]["index_value"] == 100


# ==============================================================================
# 5. 跨采集器一致性测试
# ==============================================================================


class TestCollectorConsistency:
    """验证所有采集器返回的数据项均含 topic / source 字段。"""

    async def test_all_collectors_return_topic_and_source(self, mocker: Any) -> None:
        """所有 4 个采集器的 _fetch 输出均含 topic 和 source 字段。"""
        # 小红书
        xhs_resp = _make_mock_response(
            {"code": 0, "data": {"items": [{"note_id": "1", "note_card": {"title": "t"}}]}}
        )
        xhs_client = _make_mock_client(xhs_resp, mocker)
        mocker.patch(
            "trendpulse.collectors.xiaohongshu.httpx.AsyncClient",
            return_value=xhs_client,
        )
        xhs = XiaohongshuCollector()
        xhs_data = await xhs._fetch(keyword="t")
        assert all("topic" in d and "source" in d for d in xhs_data)

        # 抖音
        dy_resp = _make_mock_response(
            {"status_code": 0, "data": {"list": [{"aweme_id": "1", "desc": "t"}]}}
        )
        dy_client = _make_mock_client(dy_resp, mocker)
        mocker.patch(
            "trendpulse.collectors.douyin.httpx.AsyncClient",
            return_value=dy_client,
        )
        dy = DouyinCollector()
        dy_data = await dy._fetch(keyword="t")
        assert all("topic" in d and "source" in d for d in dy_data)

        # 电商
        ec_resp = _make_mock_response(
            {"code": 0, "data": {"items": [{"item_id": "1", "title": "t"}]}}
        )
        ec_client = _make_mock_client(ec_resp, mocker)
        mocker.patch(
            "trendpulse.collectors.ecommerce.httpx.AsyncClient",
            return_value=ec_client,
        )
        ec = EcommerceCollector()
        ec_data = await ec._fetch(platform="taobao")
        assert all("topic" in d and "source" in d for d in ec_data)

        # 搜索指数
        si_resp = _make_mock_response(
            {"code": 0, "data": {"index_list": [{"index": 1, "trend": "rising", "date": "2026-07-17"}]}}
        )
        si_client = _make_mock_client(si_resp, mocker)
        mocker.patch(
            "trendpulse.collectors.search_index.httpx.AsyncClient",
            return_value=si_client,
        )
        si = SearchIndexCollector()
        si_data = await si._fetch(keyword="t", platform="baidu")
        assert all("topic" in d and "source" in d for d in si_data)

    def test_source_field_values(self) -> None:
        """各采集器的 source 字段应为对应标识。"""
        assert XiaohongshuCollector()._parse_note({})["source"] == "xiaohongshu"
        assert DouyinCollector()._parse_video({})["source"] == "douyin"
        assert EcommerceCollector()._parse_product({}, "taobao")["source"] == "ecommerce"
        assert SearchIndexCollector()._parse_index({}, "t", "baidu")["source"] == "search_index"

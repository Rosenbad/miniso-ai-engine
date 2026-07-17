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

import httpx
import pytest

from trendpulse.collectors.base import BaseCollector, CircuitBreakerOpenError, CircuitState
from trendpulse.collectors.xiaohongshu import XiaohongshuCollector
from trendpulse.collectors.douyin import DouyinCollector
from trendpulse.collectors.ecommerce import EcommerceCollector
from trendpulse.collectors.search_index import SearchIndexCollector
from trendpulse.collectors.utils import safe_float, safe_int, setup_logger


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

    async def test_fetch_http_error_raises(self, mocker: Any) -> None:
        """HTTP 非 200 状态码应抛出 RuntimeError (不返回空列表), 由 BaseCollector 重试。"""
        mock_response = _make_mock_response({}, status_code=500)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.xiaohongshu.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = XiaohongshuCollector()

        with pytest.raises(RuntimeError, match="HTTP 请求失败"):
            await collector._fetch(keyword="test")

    async def test_fetch_api_error_code_raises(self, mocker: Any) -> None:
        """API 返回错误码 (code != 0) 应抛出 RuntimeError, 不再吞没返回 []。"""
        api_response = {"code": 1001, "msg": "参数错误", "data": {}}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.xiaohongshu.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = XiaohongshuCollector()

        with pytest.raises(RuntimeError, match="API 业务错误码"):
            await collector._fetch(keyword="test")

    async def test_fetch_empty_items_returns_empty(self, mocker: Any) -> None:
        """API 返回成功 (code=0) 但 items 列表为空时应返回空列表 (合法空结果)。"""
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

    async def test_fetch_malformed_response_raises(self, mocker: Any) -> None:
        """畸形响应 (缺少 code 字段, code != 0) 应抛出 RuntimeError, 不再吞没。"""
        api_response = {"unexpected": "structure"}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.xiaohongshu.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = XiaohongshuCollector()

        with pytest.raises(RuntimeError, match="API 业务错误码"):
            await collector._fetch(keyword="test")

    async def test_fetch_json_parse_failure_raises(self, mocker: Any) -> None:
        """response.json() 抛 ValueError 时应向上抛出, 不再吞没返回 [] (I6)。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("invalid json")
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.xiaohongshu.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = XiaohongshuCollector()

        with pytest.raises(ValueError, match="invalid json"):
            await collector._fetch(keyword="test")

    async def test_fetch_network_error_raises(self, mocker: Any) -> None:
        """client.get 抛出网络异常时应向上抛出, 触发 BaseCollector 重试 (C1)。"""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mocker.patch(
            "trendpulse.collectors.xiaohongshu.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = XiaohongshuCollector()

        with pytest.raises(httpx.ConnectError):
            await collector._fetch(keyword="test")

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

    async def test_fetch_http_error_raises(self, mocker: Any) -> None:
        """HTTP 非 200 应抛出 RuntimeError (C1)。"""
        mock_response = _make_mock_response({}, status_code=403)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.douyin.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = DouyinCollector()

        with pytest.raises(RuntimeError, match="HTTP 请求失败"):
            await collector._fetch(keyword="test")

    async def test_fetch_api_error_raises(self, mocker: Any) -> None:
        """API 错误状态码 (status_code != 0) 应抛出 RuntimeError (C1)。"""
        api_response = {"status_code": 1, "status_msg": "rate limited"}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.douyin.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = DouyinCollector()

        with pytest.raises(RuntimeError, match="API 业务错误码"):
            await collector._fetch(keyword="test")

    async def test_fetch_empty_list_returns_empty(self, mocker: Any) -> None:
        """API 成功 (status_code=0) 但 list 为空时应返回空列表 (合法空结果)。"""
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

    async def test_fetch_malformed_response_raises(self, mocker: Any) -> None:
        """畸形响应 (缺少 status_code, 视为 != 0) 应抛出 RuntimeError (C1)。"""
        api_response = {"unexpected": True}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.douyin.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = DouyinCollector()

        with pytest.raises(RuntimeError, match="API 业务错误码"):
            await collector._fetch(keyword="test")

    async def test_fetch_json_parse_failure_raises(self, mocker: Any) -> None:
        """response.json() 抛 ValueError 时应向上抛出 (I6)。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("invalid json")
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.douyin.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = DouyinCollector()

        with pytest.raises(ValueError, match="invalid json"):
            await collector._fetch(keyword="test")

    # --- keyword 路由 (I2: 关键词走搜索端点, 无关键词走热门榜) ---

    async def test_fetch_with_keyword_uses_search_endpoint(self, mocker: Any) -> None:
        """传入 keyword 时应调用搜索端点 (I2)。"""
        api_response = {
            "status_code": 0,
            "data": {
                "list": [
                    {
                        "aweme_id": "s1",
                        "desc": "搜索结果",
                        "statistics": {"digg_count": 100, "share_count": 5, "play_count": 1000},
                        "author": {"nickname": "达人"},
                        "share_url": "https://example.com/s1",
                    }
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

        # 验证调用搜索端点 (URL 含 /web/search/item/)
        call_args = mock_client.get.call_args
        assert "/web/search/item/" in call_args.args[0]
        # 验证 params 含 keyword
        assert call_args.kwargs.get("params", {}).get("keyword") == "好物"
        assert len(result) == 1
        assert result[0]["topic"] == "搜索结果"

    async def test_fetch_without_keyword_uses_trending_endpoint(self, mocker: Any) -> None:
        """未传 keyword 时应调用热门榜端点 (I2)。"""
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
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.douyin.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = DouyinCollector()

        result = await collector._fetch(keyword="", limit=10)

        # 验证调用热门榜端点 (URL 含 /web/hot/search/list)
        call_args = mock_client.get.call_args
        assert "/web/hot/search/list" in call_args.args[0]
        # 验证 params 不含 keyword
        assert "keyword" not in call_args.kwargs.get("params", {})
        assert len(result) == 1
        assert result[0]["topic"] == "热门视频"

    # --- _get_trending 辅助方法 ---

    async def test_get_trending_calls_get(self, mocker: Any) -> None:
        """_get_trending 应调用 client.get (未传 keyword 走热门榜端点)。"""
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
        result = await collector._get_trending(mock_client, keyword="", limit=10)

        mock_client.get.assert_awaited_once()
        assert len(result) == 1
        assert result[0]["topic"] == "热门视频"

    async def test_get_trending_with_keyword_calls_search(self, mocker: Any) -> None:
        """_get_trending 传入 keyword 时应调用搜索端点 (I2)。"""
        api_response = {
            "status_code": 0,
            "data": {
                "list": [
                    {
                        "aweme_id": "s1",
                        "desc": "搜索结果",
                        "statistics": {"digg_count": 100, "share_count": 5, "play_count": 1000},
                        "author": {"nickname": "达人"},
                        "share_url": "https://example.com/s1",
                    }
                ]
            },
        }
        mock_response = _make_mock_response(api_response)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        collector = DouyinCollector()
        result = await collector._get_trending(mock_client, keyword="好物", limit=10)

        mock_client.get.assert_awaited_once()
        call_args = mock_client.get.call_args
        assert "/web/search/item/" in call_args.args[0]
        assert call_args.kwargs.get("params", {}).get("keyword") == "好物"
        assert len(result) == 1
        assert result[0]["topic"] == "搜索结果"


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

    async def test_fetch_http_error_raises(self, mocker: Any) -> None:
        """HTTP 错误应抛出 RuntimeError (C1)。"""
        mock_response = _make_mock_response({}, status_code=500)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.ecommerce.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = EcommerceCollector()

        with pytest.raises(RuntimeError, match="HTTP 请求失败"):
            await collector._fetch(platform="taobao")

    async def test_fetch_api_error_raises(self, mocker: Any) -> None:
        """API 错误码 (code != 0) 应抛出 RuntimeError (C1)。"""
        api_response = {"code": 500, "msg": "error"}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.ecommerce.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = EcommerceCollector()

        with pytest.raises(RuntimeError, match="API 业务错误码"):
            await collector._fetch(platform="taobao")

    async def test_fetch_empty_items_returns_empty(self, mocker: Any) -> None:
        """API 成功 (code=0) 但 items 为空时应返回空列表 (合法空结果)。"""
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

    async def test_fetch_malformed_response_raises(self, mocker: Any) -> None:
        """畸形响应 (缺少 code, 视为 != 0) 应抛出 RuntimeError (C1)。"""
        api_response = {"no_data": True}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.ecommerce.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = EcommerceCollector()

        with pytest.raises(RuntimeError, match="API 业务错误码"):
            await collector._fetch(platform="taobao")

    async def test_fetch_json_parse_failure_raises(self, mocker: Any) -> None:
        """response.json() 抛 ValueError 时应向上抛出 (I6)。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("invalid json")
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.ecommerce.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = EcommerceCollector()

        with pytest.raises(ValueError, match="invalid json"):
            await collector._fetch(platform="taobao")

    # --- 未知平台校验 (I4) ---

    async def test_fetch_unknown_platform_raises_value_error(self, mocker: Any) -> None:
        """未知 platform 应抛出 ValueError (I4), 不再静默兜底默认平台。"""
        mock_client = _make_mock_client(_make_mock_response({}), mocker)
        mocker.patch(
            "trendpulse.collectors.ecommerce.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = EcommerceCollector()

        with pytest.raises(ValueError, match="Unknown platform"):
            await collector._fetch(platform="jd")

    def test_get_platform_base_url_unknown_raises(self) -> None:
        """_get_platform_base_url 未知平台应抛 ValueError (I4)。"""
        collector = EcommerceCollector()
        with pytest.raises(ValueError, match="Unknown platform"):
            collector._get_platform_base_url("amazon")

    def test_get_platform_base_url_known_returns_url(self) -> None:
        """_get_platform_base_url 已知平台应返回对应 URL (I4 回归)。"""
        collector = EcommerceCollector(
            taobao_url="http://mock-tb", pinduoduo_url="http://mock-pdd"
        )
        assert collector._get_platform_base_url("taobao") == "http://mock-tb"
        assert collector._get_platform_base_url("pinduoduo") == "http://mock-pdd"

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

    async def test_fetch_http_error_raises(self, mocker: Any) -> None:
        """HTTP 错误应抛出 RuntimeError (C1)。"""
        mock_response = _make_mock_response({}, status_code=502)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.search_index.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = SearchIndexCollector()

        with pytest.raises(RuntimeError, match="HTTP 请求失败"):
            await collector._fetch(keyword="test", platform="baidu")

    async def test_fetch_api_error_raises(self, mocker: Any) -> None:
        """API 错误码 (code != 0) 应抛出 RuntimeError (C1)。"""
        api_response = {"code": 1, "msg": "invalid"}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.search_index.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = SearchIndexCollector()

        with pytest.raises(RuntimeError, match="API 业务错误码"):
            await collector._fetch(keyword="test", platform="baidu")

    async def test_fetch_empty_list_returns_empty(self, mocker: Any) -> None:
        """API 成功 (code=0) 但 index_list 为空时应返回空列表 (合法空结果)。"""
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

    async def test_fetch_malformed_response_raises(self, mocker: Any) -> None:
        """畸形响应 (缺少 code, 视为 != 0) 应抛出 RuntimeError (C1)。"""
        api_response = {"broken": True}
        mock_response = _make_mock_response(api_response)
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.search_index.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = SearchIndexCollector()

        with pytest.raises(RuntimeError, match="API 业务错误码"):
            await collector._fetch(keyword="test", platform="baidu")

    async def test_fetch_json_parse_failure_raises(self, mocker: Any) -> None:
        """response.json() 抛 ValueError 时应向上抛出 (I6)。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("invalid json")
        mock_client = _make_mock_client(mock_response, mocker)
        mocker.patch(
            "trendpulse.collectors.search_index.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = SearchIndexCollector()

        with pytest.raises(ValueError, match="invalid json"):
            await collector._fetch(keyword="test", platform="baidu")

    # --- 未知平台校验 (I4) ---

    async def test_fetch_unknown_platform_raises_value_error(self, mocker: Any) -> None:
        """未知 platform 应抛出 ValueError (I4), 不再静默兜底默认平台。"""
        mock_client = _make_mock_client(_make_mock_response({}), mocker)
        mocker.patch(
            "trendpulse.collectors.search_index.httpx.AsyncClient",
            return_value=mock_client,
        )
        collector = SearchIndexCollector()

        with pytest.raises(ValueError, match="Unknown platform"):
            await collector._fetch(keyword="test", platform="google")

    def test_get_platform_base_url_unknown_raises(self) -> None:
        """_get_platform_base_url 未知平台应抛 ValueError (I4)。"""
        collector = SearchIndexCollector()
        with pytest.raises(ValueError, match="Unknown platform"):
            collector._get_platform_base_url("zhihu")

    def test_get_platform_base_url_known_returns_url(self) -> None:
        """_get_platform_base_url 已知平台应返回对应 URL (I4 回归)。"""
        collector = SearchIndexCollector(
            baidu_url="http://mock-bd", weixin_url="http://mock-wx"
        )
        assert collector._get_platform_base_url("baidu") == "http://mock-bd"
        assert collector._get_platform_base_url("weixin") == "http://mock-wx"

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


# ==============================================================================
# 6. collect() 集成测试 (C2) - 端到端验证熔断 / 缓存 / 重试联动
# ==============================================================================


class TestCollectIntegration:
    """collect() 主流程集成测试 (C2)。

    端到端验证 BaseCollector 的熔断 / 缓存 / 重试机制与具体采集器的联动:
        1. _fetch 持续失败 → 重试 max_retries 次后熔断器 OPEN
        2. _fetch 成功 → 结果被缓存, 第二次 collect 直接命中缓存
        3. 熔断器 OPEN → collect 快速失败, 不调用 _fetch

    使用 XiaohongshuCollector 作为代表, mock _fetch / _get_cached / _set_cached /
    _check_rate_limit 隔离 Redis / 限流 / 真实 HTTP 依赖。
    """

    async def test_collect_failing_fetch_triggers_retries_and_opens_circuit(
        self, mocker: Any
    ) -> None:
        """C2-1: collect() 持续失败时触发重试, 并最终使熔断器 OPEN。

        场景:
            - _fetch 每次抛 RuntimeError (模拟 HTTP 失败)
            - max_retries=3 → 每次collect调用 _fetch 4 次 (1 初始 + 3 重试)
            - 连续 3 次 collect 失败 → 熔断器 failure_threshold=3 → OPEN

        验证:
            - 前 3 次 collect 均抛 RuntimeError (重试耗尽)
            - 第 4 次 collect 抛 CircuitBreakerOpenError (熔断器已 OPEN)
            - _fetch 总调用次数 = 3 次 collect * 4 次/collect = 12 次
        """
        # 隔离限流 / 缓存 (返回 None 视为缓存未命中)
        mocker.patch.object(
            XiaohongshuCollector, "_check_rate_limit", new=mocker.AsyncMock()
        )
        mocker.patch.object(
            XiaohongshuCollector, "_get_cached", new=mocker.AsyncMock(return_value=None)
        )
        mocker.patch.object(
            XiaohongshuCollector, "_set_cached", new=mocker.AsyncMock()
        )
        # 跳过退避真实等待
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )

        collector = XiaohongshuCollector(max_retries=3)
        fetch_mock = AsyncMock(side_effect=RuntimeError("network error"))
        collector._fetch = fetch_mock

        # 前 3 次 collect: 每次重试 3 次 (总 4 次 _fetch), 全部失败
        for _ in range(3):
            with pytest.raises(RuntimeError, match="network error"):
                await collector.collect(keyword="test")

        # 熔断器应已 OPEN
        assert collector.circuit_breaker.state == CircuitState.OPEN

        # 第 4 次 collect: 熔断器 OPEN, 快速失败, 不再调用 _fetch
        with pytest.raises(CircuitBreakerOpenError):
            await collector.collect(keyword="test")

        # _fetch 总调用次数 = 3 次 collect * 4 次/collect = 12 次
        # (第 4 次 collect 因熔断未调用 _fetch)
        assert fetch_mock.await_count == 12

    async def test_collect_successful_fetch_caches_result(
        self, mocker: Any
    ) -> None:
        """C2-2: collect() 成功时结果被缓存, 第二次 collect 命中缓存。

        场景:
            - 第一次 collect: _get_cached 返回 None → 调用 _fetch → 成功 → 写缓存
            - 第二次 collect: _get_cached 返回缓存数据 → 直接返回, 不调用 _fetch

        验证:
            - 第一次 collect 返回 _fetch 的数据, _set_cached 被调用
            - 第二次 collect 返回缓存数据, _fetch 未被再次调用
        """
        mocker.patch.object(
            XiaohongshuCollector, "_check_rate_limit", new=mocker.AsyncMock()
        )
        mocker.patch.object(
            XiaohongshuCollector, "_set_cached", new=mocker.AsyncMock()
        )

        cached_data = [{"topic": "cached_note", "source": "xiaohongshu"}]
        fresh_data = [{"topic": "fresh_note", "source": "xiaohongshu"}]

        # 第一次: 缓存未命中; 第二次: 缓存命中
        get_cached = mocker.patch.object(
            XiaohongshuCollector,
            "_get_cached",
            new=mocker.AsyncMock(side_effect=[None, cached_data]),
        )
        collector = XiaohongshuCollector()
        fetch_mock = AsyncMock(return_value=fresh_data)
        collector._fetch = fetch_mock

        # 第一次 collect: 缓存未命中, 调用 _fetch, 返回新鲜数据并写缓存
        result1 = await collector.collect(keyword="test")
        assert result1 == fresh_data
        assert fetch_mock.await_count == 1

        # 第二次 collect: 缓存命中, 直接返回缓存数据, 不调用 _fetch
        result2 = await collector.collect(keyword="test")
        assert result2 == cached_data
        assert fetch_mock.await_count == 1  # 未增加

        # _get_cached 被调用 2 次
        assert get_cached.await_count == 2

    async def test_collect_circuit_breaker_open_fails_fast(
        self, mocker: Any
    ) -> None:
        """C2-3: 熔断器 OPEN 时 collect() 快速失败, 不调用 _fetch。

        场景:
            - 手动将熔断器置为 OPEN (连续 3 次 record_failure)
            - collect() 应抛 CircuitBreakerOpenError, 且不调用 _fetch

        验证:
            - collect 抛 CircuitBreakerOpenError
            - _fetch 未被调用 (快速失败)
        """
        collector = XiaohongshuCollector()
        # 触发熔断 (failure_threshold 默认 3)
        for _ in range(collector.circuit_breaker.failure_threshold):
            await collector.circuit_breaker.record_failure()
        assert collector.circuit_breaker.state == CircuitState.OPEN

        fetch_mock = AsyncMock(return_value=[{"topic": "should_not_be_called"}])
        collector._fetch = fetch_mock

        with pytest.raises(CircuitBreakerOpenError):
            await collector.collect(keyword="test")

        # _fetch 不应被调用
        fetch_mock.assert_not_called()

    async def test_collect_circuit_breaker_open_returns_cached_fallback(
        self, mocker: Any
    ) -> None:
        """C2 补充: 熔断器 OPEN 但有缓存时, collect() 返回缓存而非抛异常。"""
        cached_data = [{"topic": "cached_fallback", "source": "xiaohongshu"}]
        mocker.patch.object(
            XiaohongshuCollector,
            "_get_cached",
            new=mocker.AsyncMock(return_value=cached_data),
        )

        collector = XiaohongshuCollector()
        for _ in range(collector.circuit_breaker.failure_threshold):
            await collector.circuit_breaker.record_failure()
        assert collector.circuit_breaker.state == CircuitState.OPEN

        fetch_mock = AsyncMock()
        collector._fetch = fetch_mock

        result = await collector.collect(keyword="test")
        assert result == cached_data
        fetch_mock.assert_not_called()

    async def test_collect_failed_fetch_returns_cached_fallback(
        self, mocker: Any
    ) -> None:
        """C2 补充: _fetch 重试耗尽后, 若有缓存则返回缓存降级数据。"""
        mocker.patch.object(
            XiaohongshuCollector, "_check_rate_limit", new=mocker.AsyncMock()
        )
        mocker.patch.object(
            XiaohongshuCollector, "_set_cached", new=mocker.AsyncMock()
        )
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )

        cached_data = [{"topic": "stale_cache", "source": "xiaohongshu"}]
        # 第一次 _get_cached (缓存检查) 返回 None, 第二次 (失败回退) 返回缓存
        mocker.patch.object(
            XiaohongshuCollector,
            "_get_cached",
            new=mocker.AsyncMock(side_effect=[None, cached_data]),
        )

        collector = XiaohongshuCollector(max_retries=2)
        collector._fetch = AsyncMock(side_effect=RuntimeError("network down"))

        result = await collector.collect(keyword="test")
        assert result == cached_data


# ==============================================================================
# 7. 公共工具 utils.py 测试 (I1)
# ==============================================================================


class TestUtils:
    """utils.py 公共工具函数测试 (I1)。

    验证抽取出的 safe_int / safe_float / setup_logger 行为正确,
    确保各采集器导入使用后不丢失原有功能。
    """

    # --- safe_int ---

    def test_safe_int_normal(self) -> None:
        """正常 int / 字符串应正确转换。"""
        assert safe_int(100) == 100
        assert safe_int("100") == 100

    def test_safe_int_none(self) -> None:
        """None 应返回 default。"""
        assert safe_int(None) == 0
        assert safe_int(None, default=-1) == -1

    def test_safe_int_empty_string(self) -> None:
        """空字符串应返回 default。"""
        assert safe_int("") == 0
        assert safe_int("", default=5) == 5

    def test_safe_int_invalid_string(self) -> None:
        """非数字字符串应返回 default。"""
        assert safe_int("abc") == 0
        assert safe_int("abc", default=-1) == -1

    def test_safe_int_float_string(self) -> None:
        """浮点字符串 int() 会抛 ValueError, 应返回 default (保持原 _safe_int 语义)。"""
        # int("29.9") 抛 ValueError → 返回 default
        assert safe_int("29.9") == 0
        assert safe_int("29.9", default=-1) == -1
        # 但 float 类型值会被 int() 截断
        assert safe_int(29.9) == 29

    # --- safe_float ---

    def test_safe_float_normal(self) -> None:
        """正常 float / 字符串应正确转换。"""
        assert safe_float(29.9) == 29.9
        assert safe_float("29.9") == 29.9

    def test_safe_float_none(self) -> None:
        """None 应返回 default。"""
        assert safe_float(None) == 0.0
        assert safe_float(None, default=-1.0) == -1.0

    def test_safe_float_empty_string(self) -> None:
        """空字符串应返回 default。"""
        assert safe_float("") == 0.0
        assert safe_float("", default=1.5) == 1.5

    def test_safe_float_invalid_string(self) -> None:
        """非数字字符串应返回 default。"""
        assert safe_float("abc") == 0.0
        assert safe_float("abc", default=-1.0) == -1.0

    # --- setup_logger ---

    def test_setup_logger_returns_logger(self) -> None:
        """setup_logger 应返回一个可用的日志器对象。"""
        log = setup_logger("test_module")
        # 应该有 debug / info / warning / error 等日志方法
        assert hasattr(log, "info")
        assert hasattr(log, "warning")
        assert hasattr(log, "error")

    def test_setup_logger_same_name_returns_logger(self) -> None:
        """setup_logger 多次调用应返回可用的日志器。"""
        log1 = setup_logger("module_a")
        log2 = setup_logger("module_b")
        # 两者都应可用 (loguru 是单例, 标准logging按name区分)
        assert log1 is not None
        assert log2 is not None

    # --- 各采集器使用 utils 的回归测试 ---

    def test_collectors_use_shared_safe_int(self) -> None:
        """4 个采集器的 _parse_* 方法应使用共享 safe_int (I1 回归)。"""
        # 小红书: likes / comments
        xhs = XiaohongshuCollector()
        note = xhs._parse_note({"note_card": {"interact_info": {"liked_count": "100"}}})
        assert note["likes"] == 100

        # 抖音: likes / shares / play_count
        dy = DouyinCollector()
        video = dy._parse_video({"statistics": {"digg_count": "500", "play_count": "8000"}})
        assert video["likes"] == 500
        assert video["play_count"] == 8000

        # 电商: sales (safe_int)
        ec = EcommerceCollector()
        product = ec._parse_product({"sales": "5000"}, "taobao")
        assert product["sales"] == 5000

        # 搜索指数: index_value
        si = SearchIndexCollector()
        index = si._parse_index({"index": "999"}, "kw", "baidu")
        assert index["index_value"] == 999

    def test_ecommerce_uses_shared_safe_float(self) -> None:
        """EcommerceCollector._parse_product 应使用共享 safe_float (I1 回归)。"""
        ec = EcommerceCollector()
        product = ec._parse_product({"price": "29.9"}, "taobao")
        assert product["price"] == 29.9

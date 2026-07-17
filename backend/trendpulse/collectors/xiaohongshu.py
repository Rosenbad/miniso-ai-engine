# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 小红书数据采集器 (Task 4)
# ==============================================================================
# 对应 spec §3.1 中国数据源 - 小红书:
#   采集内容: 笔记 + 评论
#   角色: 生活方式趋势发源地
#
# XiaohongshuCollector 继承 BaseCollector, 自动获得:
#   - QPS 限流 (qps_limit=0.5, 慢速避免触发反爬)
#   - 指数退避重试 (0.5s / 1s / 2s)
#   - 熔断器 (连续失败降级)
#   - Redis 缓存 (TTL=3600s)
#
# 设计要点:
#   - 使用 httpx.AsyncClient 异步 HTTP 请求, 默认 10s 超时
#   - base_url 可通过构造器 / 环境变量配置 (测试灵活性)
#   - 真实 API 需鉴权, 本实现聚焦解析逻辑正确性与可测试性
#   - 异常分级: HTTP 错误 / API 错误码 / JSON 解析失败均向上抛出
#     (由 BaseCollector 的重试 / 熔断 / 缓存机制处理);
#     仅 API 成功 (code=0) 但数据列表为空时返回 []
# ==============================================================================

"""
小红书数据采集器。

采集小红书笔记 (含互动数据), 作为生活方式趋势发源地数据源。

类:
    XiaohongshuCollector - 小红书笔记采集器

用法::

    collector = XiaohongshuCollector()
    data = await collector.collect(keyword="侘寂风", limit=20)
    # data: [{"topic", "source", "content", "likes", "comments", "author", "url"}, ...]
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from trendpulse.collectors.base import BaseCollector
from trendpulse.collectors.utils import safe_int, setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# XiaohongshuCollector 小红书采集器
# ==============================================================================


class XiaohongshuCollector(BaseCollector):
    """小红书笔记采集器。

    继承 BaseCollector, 获得 QPS 限流 / 指数退避重试 / 熔断器 / Redis 缓存能力。

    构造参数:
        base_url : 小红书 API 基础地址 (默认从环境变量 XHS_BASE_URL 读取)
        **kwargs : 传递给 BaseCollector (如 qps_limit, cache_ttl, max_retries)

    采集参数 (_fetch):
        keyword : 搜索关键词
        limit   : 返回笔记数量上限 (默认 20)

    返回格式:
        [{"topic", "source", "content", "likes", "comments", "author", "url"}, ...]

    异常:
        _fetch 在 HTTP 失败 / 非 200 / JSON 解析失败 / API 业务错误码 (code != 0)
        时向上抛出异常, 由 BaseCollector 的重试 / 熔断 / 缓存机制处理;
        仅当 API 成功 (code=0) 但 items 列表为空时返回 []。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        # 小红书反爬严格, 使用低 QPS (0.5 = 每 2 秒 1 次)
        kwargs.setdefault("qps_limit", 0.5)
        kwargs.setdefault("cache_ttl", 3600)
        super().__init__(name="xiaohongshu", **kwargs)
        self.base_url: str = base_url or os.getenv(
            "XHS_BASE_URL", "https://edith.xiaohongshu.com"
        )

    # ==================================================================
    # _fetch - 主采集入口 (由 BaseCollector.collect 调用)
    # ==================================================================

    async def _fetch(
        self,
        keyword: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """执行小红书笔记搜索采集。

        创建 httpx.AsyncClient 上下文, 委托给 _search_notes 执行实际请求与解析。
        异常向上抛出 (不吞没), 由 BaseCollector 处理重试 / 熔断 / 缓存降级。

        参数:
            keyword : 搜索关键词
            limit   : 返回数量上限

        返回:
            解析后的笔记数据列表; API 成功但 items 为空时返回 []

        异常:
            httpx.HTTPError / 网络异常 / 非 200 状态码 /
            JSON 解析失败 / API 业务错误码 (code != 0) 均向上抛出
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await self._search_notes(client, keyword, limit)

    # ==================================================================
    # _search_notes - 搜索笔记 (实际 HTTP 请求 + 解析)
    # ==================================================================

    async def _search_notes(
        self,
        client: httpx.AsyncClient,
        keyword: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """通过小红书搜索 API 获取笔记列表并解析。

        参数:
            client  : httpx.AsyncClient 实例 (由 _fetch 创建)
            keyword : 搜索关键词
            limit   : 返回数量上限

        返回:
            解析后的笔记数据列表; API 成功 (code=0) 但 items 为空时返回 []

        异常:
            - httpx.HTTPError 等: 网络请求失败 (向上抛出, 触发重试)
            - RuntimeError: HTTP 非 200 / JSON 解析失败 / API 业务错误码 (code != 0)
        """
        url = f"{self.base_url}/api/sns/web/v1/search/notes"
        params = {"keyword": keyword, "page": 1, "page_size": limit}

        # HTTP 请求异常 (网络错误 / 超时) 直接向上抛出, 触发 BaseCollector 重试
        response = await client.get(url, params=params)

        if response.status_code != 200:
            raise RuntimeError(
                f"[xiaohongshu] HTTP 请求失败, 状态码: {response.status_code}"
            )

        # JSON 解析失败向上抛出 (若 .json() 抛 ValueError, 不再吞没)
        data = response.json()

        # 校验 API 业务码: code == 0 表示成功, 否则视为业务失败 (向上抛出)
        if data.get("code", -1) != 0:
            raise RuntimeError(
                f"[xiaohongshu] API 业务错误码: code={data.get('code')}, "
                f"msg={data.get('msg', '')}"
            )

        # API 成功: 提取 items 列表 (防御性处理 data["data"] 结构缺失)
        raw_data = data.get("data")
        if not isinstance(raw_data, dict):
            # code=0 但 data 结构异常, 视为 API 契约违反, 返回空列表
            return []
        items: List[Dict[str, Any]] = raw_data.get("items", [])
        return [self._parse_note(item) for item in items]

    # ==================================================================
    # _parse_note - 解析单条笔记
    # ==================================================================

    def _parse_note(self, raw_note: Dict[str, Any]) -> Dict[str, Any]:
        """将原始笔记数据解析为标准格式。

        兼容两种结构:
            - 嵌套结构: {note_id, note_card: {title, desc, user, interact_info, note_url}}
            - 扁平结构: {note_id, title, desc, user, interact_info, note_url}

        参数:
            raw_note : 原始笔记 dict

        返回:
            {topic, source, content, likes, comments, author, url}
            缺失字段返回默认值 (空字符串 / 0), 不抛异常 (解析层保持防御性)
        """
        # 兼容嵌套 note_card 与扁平结构
        note_card: Dict[str, Any] = raw_note.get("note_card", raw_note)

        interact_info: Dict[str, Any] = note_card.get("interact_info", {}) or {}
        user: Dict[str, Any] = note_card.get("user", {}) or {}

        note_id: str = raw_note.get("note_id", "")
        # URL 优先级: note_card.note_url > raw_note.note_url > 基于 note_id 构造
        url: str = (
            note_card.get("note_url")
            or raw_note.get("note_url", "")
            or (f"https://www.xiaohongshu.com/note/{note_id}" if note_id else "")
        )

        return {
            "topic": note_card.get("title", "") or "",
            "source": "xiaohongshu",
            "content": note_card.get("desc", "") or "",
            "likes": safe_int(interact_info.get("liked_count", 0)),
            "comments": safe_int(interact_info.get("comment_count", 0)),
            "author": user.get("nickname", "") or "",
            "url": url,
        }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["XiaohongshuCollector"]

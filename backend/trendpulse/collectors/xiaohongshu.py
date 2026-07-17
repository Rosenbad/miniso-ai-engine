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
#   - 优雅降级: HTTP 错误 / API 错误码 / 空响应 / 畸形数据均返回空列表
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

try:
    from loguru import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]

from trendpulse.collectors.base import BaseCollector


# ==============================================================================
# 辅助函数 - 安全类型转换
# ==============================================================================


def _safe_int(value: Any, default: int = 0) -> int:
    """安全转换为 int, 失败时返回 default。

    处理 None / 空字符串 / 非数字字符串等异常输入。
    """
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


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

        参数:
            keyword : 搜索关键词
            limit   : 返回数量上限

        返回:
            解析后的笔记数据列表; 任何错误均返回空列表 (不抛异常)
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                return await self._search_notes(client, keyword, limit)
        except Exception as exc:
            logger.warning(f"[xiaohongshu] _fetch 异常, 返回空列表: {exc}")
            return []

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
            解析后的笔记数据列表; HTTP 错误 / API 错误码 / 空结果均返回空列表
        """
        url = f"{self.base_url}/api/sns/web/v1/search/notes"
        params = {"keyword": keyword, "page": 1, "page_size": limit}

        try:
            response = await client.get(url, params=params)
        except Exception as exc:
            logger.warning(f"[xiaohongshu] 请求失败: {exc}")
            return []

        if response.status_code != 200:
            logger.debug(
                f"[xiaohongshu] HTTP {response.status_code}, 跳过"
            )
            return []

        try:
            data = response.json()
        except Exception as exc:
            logger.warning(f"[xiaohongshu] JSON 解析失败: {exc}")
            return []

        # 校验 API 业务码: code == 0 表示成功
        if data.get("code", -1) != 0:
            logger.debug(f"[xiaohongshu] API 错误码: {data.get('code')}")
            return []

        items: List[Dict[str, Any]] = (
            data.get("data", {}).get("items", []) if isinstance(data.get("data"), dict) else []
        )
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
            缺失字段返回默认值 (空字符串 / 0), 不抛异常
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
            "likes": _safe_int(interact_info.get("liked_count", 0)),
            "comments": _safe_int(interact_info.get("comment_count", 0)),
            "author": user.get("nickname", "") or "",
            "url": url,
        }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["XiaohongshuCollector"]

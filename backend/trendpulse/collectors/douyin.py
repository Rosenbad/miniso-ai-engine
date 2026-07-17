# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 抖音数据采集器 (Task 4)
# ==============================================================================
# 对应 spec §3.1 中国数据源 - 抖音:
#   采集内容: 话题 + 商品
#   角色: 短视频带货趋势
#
# DouyinCollector 继承 BaseCollector, 自动获得:
#   - QPS 限流 (qps_limit=1.0)
#   - 指数退避重试 (0.5s / 1s / 2s)
#   - 熔断器 (连续失败降级)
#   - Redis 缓存 (TTL=3600s)
#
# 设计要点:
#   - 使用 httpx.AsyncClient 异步 HTTP 请求, 默认 10s 超时
#   - base_url 可通过构造器 / 环境变量配置 (测试灵活性)
#   - 采集热门视频/话题, 含播放量/点赞/分享等带货指标
#   - 优雅降级: HTTP 错误 / API 错误码 / 空响应 / 畸形数据均返回空列表
# ==============================================================================

"""
抖音数据采集器。

采集抖音热门视频/话题 (含带货指标), 作为短视频带货趋势数据源。

类:
    DouyinCollector - 抖音采集器

用法::

    collector = DouyinCollector()
    data = await collector.collect(keyword="好物", limit=20)
    # data: [{"topic", "source", "description", "likes", "shares",
    #         "play_count", "author", "url"}, ...]
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
# DouyinCollector 抖音采集器
# ==============================================================================


class DouyinCollector(BaseCollector):
    """抖音热门视频/话题采集器。

    继承 BaseCollector, 获得 QPS 限流 / 指数退避重试 / 熔断器 / Redis 缓存能力。

    构造参数:
        base_url : 抖音 API 基础地址 (默认从环境变量 DOUYIN_BASE_URL 读取)
        **kwargs : 传递给 BaseCollector

    采集参数 (_fetch):
        keyword : 搜索关键词 (可选, 用于过滤)
        limit   : 返回视频数量上限 (默认 20)

    返回格式:
        [{"topic", "source", "description", "likes", "shares",
          "play_count", "author", "url"}, ...]
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("qps_limit", 1.0)
        kwargs.setdefault("cache_ttl", 3600)
        super().__init__(name="douyin", **kwargs)
        self.base_url: str = base_url or os.getenv(
            "DOUYIN_BASE_URL", "https://www.douyin.com/aweme/v1"
        )

    # ==================================================================
    # _fetch - 主采集入口
    # ==================================================================

    async def _fetch(
        self,
        keyword: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """执行抖音热门视频采集。

        创建 httpx.AsyncClient 上下文, 委托给 _get_trending 执行实际请求与解析。

        参数:
            keyword : 搜索关键词 (可选)
            limit   : 返回数量上限

        返回:
            解析后的视频数据列表; 任何错误均返回空列表 (不抛异常)
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                return await self._get_trending(client, limit)
        except Exception as exc:
            logger.warning(f"[douyin] _fetch 异常, 返回空列表: {exc}")
            return []

    # ==================================================================
    # _get_trending - 获取热门视频列表
    # ==================================================================

    async def _get_trending(
        self,
        client: httpx.AsyncClient,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """通过抖音热门 API 获取视频列表并解析。

        参数:
            client : httpx.AsyncClient 实例
            limit  : 返回数量上限

        返回:
            解析后的视频数据列表; HTTP 错误 / API 错误码 / 空结果均返回空列表
        """
        url = f"{self.base_url}/web/hot/search/list"
        params = {"count": limit}

        try:
            response = await client.get(url, params=params)
        except Exception as exc:
            logger.warning(f"[douyin] 请求失败: {exc}")
            return []

        if response.status_code != 200:
            logger.debug(f"[douyin] HTTP {response.status_code}, 跳过")
            return []

        try:
            data = response.json()
        except Exception as exc:
            logger.warning(f"[douyin] JSON 解析失败: {exc}")
            return []

        # 校验 API 业务码: status_code == 0 表示成功
        if data.get("status_code", -1) != 0:
            logger.debug(f"[douyin] API 错误码: {data.get('status_code')}")
            return []

        items: List[Dict[str, Any]] = (
            data.get("data", {}).get("list", [])
            if isinstance(data.get("data"), dict)
            else []
        )
        return [self._parse_video(item) for item in items]

    # ==================================================================
    # _parse_video - 解析单条视频
    # ==================================================================

    def _parse_video(self, raw_video: Dict[str, Any]) -> Dict[str, Any]:
        """将原始视频数据解析为标准格式。

        参数:
            raw_video : 原始视频 dict
                预期字段: aweme_id, desc, statistics{digg_count, share_count,
                play_count}, author{nickname}, share_url

        返回:
            {topic, source, description, likes, shares, play_count, author, url}
            缺失字段返回默认值 (空字符串 / 0), 不抛异常
        """
        statistics: Dict[str, Any] = raw_video.get("statistics", {}) or {}
        author: Dict[str, Any] = raw_video.get("author", {}) or {}

        aweme_id: str = raw_video.get("aweme_id", "")
        url: str = (
            raw_video.get("share_url", "")
            or (f"https://www.douyin.com/video/{aweme_id}" if aweme_id else "")
        )

        desc: str = raw_video.get("desc", "") or ""

        return {
            "topic": desc,
            "source": "douyin",
            "description": desc,
            "likes": _safe_int(statistics.get("digg_count", 0)),
            "shares": _safe_int(statistics.get("share_count", 0)),
            "play_count": _safe_int(statistics.get("play_count", 0)),
            "author": author.get("nickname", "") or "",
            "url": url,
        }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["DouyinCollector"]

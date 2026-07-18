# ==============================================================================
# 免费/无需鉴权的真实数据源采集器
# ==============================================================================
# 这些采集器调用公开免费 API, 无需任何凭证即可获取真实数据:
#   1. BilibiliHotCollector  - B站热门视频排行榜 (公开 API)
#   2. ToutiaoHotCollector   - 头条热榜 (公开 API)
#   3. DoubanHotCollector    - 豆瓣热门影视 (公开 API)
#
# 数据源特点:
#   - B站: Z世代视频趋势, 含播放量/点赞/投币, 反映年轻人兴趣
#   - 头条: 大众关注热点, 含热度值, 反映社会趋势
#   - 豆瓣: 影视/文化消费趋势, 含评分, 反映审美偏好
#
# 所有采集器继承 BaseCollector, 自动获得 QPS限流/重试/熔断/缓存能力。
# ==============================================================================

from __future__ import annotations

from typing import Any, Dict, List

import httpx

from trendpulse.collectors.base import BaseCollector
from trendpulse.collectors.utils import safe_int, setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# BilibiliHotCollector - B站热门视频
# ==============================================================================


class BilibiliHotCollector(BaseCollector):
    """B站热门视频排行榜采集器 (免费公开 API)。

    API: https://api.bilibili.com/x/web-interface/ranking/v2
    无需鉴权, 返回全站热门视频排行榜。

    返回格式:
        [{"topic", "source", "description", "likes", "views", "shares",
          "author", "url", "region"}]
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("qps_limit", 2.0)
        kwargs.setdefault("cache_ttl", 1800)
        super().__init__(name="bilibili", **kwargs)

    async def _fetch(
        self,
        keyword: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """从B站排行榜 API 获取热门视频。"""
        url = "https://api.bilibili.com/x/web-interface/ranking/v2"
        params = {"rid": 0, "type": "all"}

        async with httpx.AsyncClient(timeout=10.0, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }) as client:
            response = await client.get(url, params=params)

            if response.status_code != 200:
                raise RuntimeError(f"[bilibili] HTTP {response.status_code}")

            data = response.json()
            if data.get("code", -1) != 0:
                raise RuntimeError(f"[bilibili] API code={data.get('code')}")

            raw_list = data.get("data", {}).get("list", [])

            # 如果有关键词, 做简单过滤
            if keyword:
                raw_list = [
                    item for item in raw_list
                    if keyword.lower() in item.get("title", "").lower()
                    or keyword.lower() in item.get("desc", "").lower()
                ]

            items: List[Dict[str, Any]] = []
            for raw in raw_list[:limit]:
                stat = raw.get("stat", {})
                owner = raw.get("owner", {})
                bvid = raw.get("bvid", "")
                items.append({
                    "topic": raw.get("title", "")[:50],
                    "source": "bilibili",
                    "description": raw.get("desc", "")[:100],
                    "likes": safe_int(stat.get("like", 0)),
                    "views": safe_int(stat.get("view", 0)),
                    "shares": safe_int(stat.get("share", 0)),
                    "comments": safe_int(stat.get("reply", 0)),
                    "author": owner.get("name", ""),
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "region": "china",
                    "heat_score": min(100.0, safe_int(stat.get("view", 0)) / 10000.0),
                    "growth_rate": round(safe_int(stat.get("like", 0)) / max(1, safe_int(stat.get("view", 0))) * 100, 1),
                })

            logger.info(f"[bilibili] 采集成功: {len(items)} 条视频")
            return items


# ==============================================================================
# ToutiaoHotCollector - 头条热榜
# ==============================================================================


class ToutiaoHotCollector(BaseCollector):
    """今日头条热榜采集器 (免费公开 API)。

    API: https://www.toutiao.com/hot-event/hot-board/
    无需鉴权, 返回当前热搜榜单。

    返回格式:
        [{"topic", "source", "heat_value", "url", "region"}]
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("qps_limit", 2.0)
        kwargs.setdefault("cache_ttl", 1800)
        super().__init__(name="toutiao", **kwargs)

    async def _fetch(
        self,
        keyword: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """从头条热榜 API 获取热搜数据。"""
        url = "https://www.toutiao.com/hot-event/hot-board/"
        params = {"origin": "toutiao_pc"}

        async with httpx.AsyncClient(timeout=10.0, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }) as client:
            response = await client.get(url, params=params)

            if response.status_code != 200:
                raise RuntimeError(f"[toutiao] HTTP {response.status_code}")

            data = response.json()
            raw_list = data.get("data", [])

            if keyword:
                raw_list = [
                    item for item in raw_list
                    if keyword in item.get("Title", "")
                ]

            items: List[Dict[str, Any]] = []
            for raw in raw_list[:limit]:
                hot = safe_int(raw.get("HotValue", 0))
                items.append({
                    "topic": raw.get("Title", "")[:50],
                    "source": "toutiao",
                    "description": raw.get("Title", ""),
                    "heat_value": hot,
                    "url": raw.get("Url", raw.get("Link", "")),
                    "region": "china",
                    "heat_score": min(100.0, hot / 1000000.0),
                    "growth_rate": round(hot / 1000000.0, 1),
                    "likes": 0,
                    "comments": 0,
                })

            logger.info(f"[toutiao] 采集成功: {len(items)} 条热榜")
            return items


# ==============================================================================
# DoubanHotCollector - 豆瓣热门影视
# ==============================================================================


class DoubanHotCollector(BaseCollector):
    """豆瓣热门影视采集器 (免费公开 API)。

    API: https://movie.douban.com/j/search_subjects
    无需鉴权, 返回当前热门影视列表。

    返回格式:
        [{"topic", "source", "rating", "url", "region"}]
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("qps_limit", 2.0)
        kwargs.setdefault("cache_ttl", 3600)
        super().__init__(name="douban", **kwargs)

    async def _fetch(
        self,
        keyword: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """从豆瓣 API 获取热门影视数据。"""
        url = "https://movie.douban.com/j/search_subjects"
        params = {"type": "hot", "tag": "热门", "page_limit": limit, "page_start": 0}

        async with httpx.AsyncClient(timeout=10.0, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }) as client:
            response = await client.get(url, params=params)

            if response.status_code != 200:
                raise RuntimeError(f"[douban] HTTP {response.status_code}")

            data = response.json()
            raw_list = data.get("subjects", [])

            items: List[Dict[str, Any]] = []
            for raw in raw_list:
                rate = raw.get("rate", "0")
                try:
                    rating = float(rate)
                except (ValueError, TypeError):
                    rating = 0.0

                items.append({
                    "topic": raw.get("title", ""),
                    "source": "douban",
                    "description": raw.get("title", ""),
                    "rating": rating,
                    "url": raw.get("url", ""),
                    "cover": raw.get("cover", ""),
                    "region": "china",
                    "heat_score": rating * 10,  # 0-100 scale
                    "growth_rate": round(rating * 5, 1),
                    "likes": 0,
                    "comments": 0,
                })

            logger.info(f"[douban] 采集成功: {len(items)} 条影视")
            return items


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["BilibiliHotCollector", "ToutiaoHotCollector", "DoubanHotCollector"]

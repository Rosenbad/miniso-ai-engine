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
#   - keyword 支持: 传入关键词时走搜索端点, 未传时走热门榜端点
#   - 异常分级: HTTP 错误 / API 错误码 / JSON 解析失败均向上抛出
#     (由 BaseCollector 的重试 / 熔断 / 缓存机制处理);
#     仅 API 成功 (status_code=0) 但数据列表为空时返回 []
# ==============================================================================

"""
抖音数据采集器。

采集抖音热门视频/话题 (含带货指标), 作为短视频带货趋势数据源。

类:
    DouyinCollector - 抖音采集器

用法::

    collector = DouyinCollector()
    # 不传 keyword: 获取热门榜
    data = await collector.collect(keyword="", limit=20)
    # 传 keyword: 按关键词搜索
    data = await collector.collect(keyword="好物", limit=20)
    # data: [{"topic", "source", "description", "likes", "shares",
    #         "play_count", "author", "url"}, ...]
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from trendpulse.collectors.base import BaseCollector
from trendpulse.collectors.utils import safe_int, setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# API 端点路径配置
# ==============================================================================

# 热门榜端点 (无关键词时使用)
_TRENDING_PATH: str = "/web/hot/search/list"

# 搜索端点 (有关键词时使用)
_SEARCH_PATH: str = "/web/search/item/"


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
        keyword : 搜索关键词 (可选)
                  - 传入非空关键词: 走搜索端点, 按关键词搜索视频
                  - 未传 / 空字符串: 走热门榜端点, 获取全站热门视频
        limit   : 返回视频数量上限 (默认 20)

    返回格式:
        [{"topic", "source", "description", "likes", "shares",
          "play_count", "author", "url"}, ...]

    异常:
        _fetch 在 HTTP 失败 / 非 200 / JSON 解析失败 / API 业务错误码
        (status_code != 0) 时向上抛出异常, 由 BaseCollector 的
        重试 / 熔断 / 缓存机制处理; 仅当 API 成功但 list 为空时返回 []。
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
        """执行抖音视频采集。

        创建 httpx.AsyncClient 上下文, 委托给 _get_trending 执行实际请求与解析。
        异常向上抛出 (不吞没), 由 BaseCollector 处理重试 / 熔断 / 缓存降级。

        参数:
            keyword : 搜索关键词 (可选; 非空走搜索端点, 空走热门榜端点)
            limit   : 返回数量上限

        返回:
            解析后的视频数据列表; API 成功但 list 为空时返回 []

        异常:
            httpx.HTTPError / 网络异常 / 非 200 状态码 /
            JSON 解析失败 / API 业务错误码均向上抛出
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await self._get_trending(client, keyword, limit)

    # ==================================================================
    # _get_trending - 获取热门视频 / 搜索视频列表
    # ==================================================================

    async def _get_trending(
        self,
        client: httpx.AsyncClient,
        keyword: str = "",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """通过抖音 API 获取视频列表并解析。

        根据是否传入 keyword 选择端点:
            - keyword 非空: 调用搜索端点, params 含 keyword
            - keyword 空  : 调用热门榜端点

        参数:
            client  : httpx.AsyncClient 实例
            keyword : 搜索关键词 (可选; 决定使用搜索 / 热门榜端点)
            limit   : 返回数量上限

        返回:
            解析后的视频数据列表; API 成功 (status_code=0) 但 list 为空时返回 []

        异常:
            - httpx.HTTPError 等: 网络请求失败 (向上抛出, 触发重试)
            - RuntimeError: HTTP 非 200 / JSON 解析失败 / API 业务错误码 (status_code != 0)
        """
        # 根据是否传入 keyword 选择端点与参数
        if keyword:
            url = f"{self.base_url}{_SEARCH_PATH}"
            params: Dict[str, Any] = {
                "keyword": keyword,
                "count": limit,
                "search_source": "normal_search",
            }
        else:
            url = f"{self.base_url}{_TRENDING_PATH}"
            params = {"count": limit}

        # HTTP 请求异常 (网络错误 / 超时) 直接向上抛出, 触发 BaseCollector 重试
        response = await client.get(url, params=params)

        if response.status_code != 200:
            raise RuntimeError(
                f"[douyin] HTTP 请求失败, 状态码: {response.status_code}"
            )

        # JSON 解析失败向上抛出 (若 .json() 抛 ValueError, 不再吞没)
        data = response.json()

        # 校验 API 业务码: status_code == 0 表示成功, 否则视为业务失败 (向上抛出)
        if data.get("status_code", -1) != 0:
            raise RuntimeError(
                f"[douyin] API 业务错误码: status_code={data.get('status_code')}, "
                f"status_msg={data.get('status_msg', '')}"
            )

        # API 成功: 提取 list 列表 (防御性处理 data["data"] 结构缺失)
        raw_data = data.get("data")
        if not isinstance(raw_data, dict):
            # status_code=0 但 data 结构异常, 视为 API 契约违反, 返回空列表
            return []
        items: List[Dict[str, Any]] = raw_data.get("list", [])
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
            缺失字段返回默认值 (空字符串 / 0), 不抛异常 (解析层保持防御性)
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
            "likes": safe_int(statistics.get("digg_count", 0)),
            "shares": safe_int(statistics.get("share_count", 0)),
            "play_count": safe_int(statistics.get("play_count", 0)),
            "author": author.get("nickname", "") or "",
            "url": url,
        }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["DouyinCollector"]

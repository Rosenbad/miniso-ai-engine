# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - TikTok 海外数据采集器 (Task 5)
# ==============================================================================
# 对应 spec §3.1 海外数据源 - TikTok:
#   采集内容: 全球热门话题 + 商品
#   角色: 全球流行先行信号
#
# TiktokCollector 继承 BaseCollector, 自动获得:
#   - QPS 限流 (qps_limit=1.0)
#   - 指数退避重试 (0.5s / 1s / 2s)
#   - 熔断器 (连续失败降级)
#   - Redis 缓存 (TTL=3600s)
#
# 设计要点:
#   - 使用 httpx.AsyncClient 异步 HTTP 请求, 默认 10s 超时
#   - base_url 可通过构造器 / 环境变量配置 (测试灵活性)
#   - 支持区域 (region) 参数, 覆盖 spec §3.1 全球 112 国数据源要求
#     至少覆盖: us / gb / jp / kr / th / id / vn / de / fr / br / mx / sea
#   - keyword 路由: 传入关键词走搜索端点, 未传走全球热门榜端点
#   - 异常分级: HTTP 错误 / API 错误码 / JSON 解析失败均向上抛出
#     (由 BaseCollector 的重试 / 熔断 / 缓存机制处理);
#     仅 API 成功 (status_code=0) 但数据列表为空时返回 []
#   - 未知 region 抛 ValueError (不再静默兜底)
# ==============================================================================

"""
TikTok 海外数据采集器。

采集 TikTok 全球热门话题/视频 (含带货指标), 作为全球流行先行信号数据源。

类:
    TiktokCollector - TikTok 采集器

用法::

    collector = TiktokCollector()
    # 不传 keyword: 获取区域热门榜
    data = await collector.collect(region="us", limit=20)
    # 传 keyword: 按区域搜索关键词
    data = await collector.collect(keyword="kawaii", region="jp", limit=20)
    # data: [{"topic", "source", "region", "description", "likes", "shares",
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

# 全球热门榜端点 (无关键词时使用, 按区域获取热门话题/视频)
_TRENDING_PATH: str = "/api/explore/trending/"

# 关键词搜索端点 (有关键词时使用, 在指定区域内搜索)
_SEARCH_PATH: str = "/api/search/item/"


# ==============================================================================
# TiktokCollector TikTok 采集器
# ==============================================================================


class TiktokCollector(BaseCollector):

    # spec §3.1 要求全球 112 国数据源覆盖; 此处列出 30+ 个区域作为最低覆盖集合,
    # 包含 spec 明确要求的 us / gb / jp / kr / th / id / vn / de / fr / br / mx / sea
    # 共 12 个区域。实际生产可通过对接 TikTok Business API 的完整 112 国区域码进一步扩充。
    _KNOWN_REGIONS: frozenset = frozenset(
        {
            # 北美
            "us",  # 美国
            "ca",  # 加拿大
            "mx",  # 墨西哥
            # 欧洲
            "gb",  # 英国
            "de",  # 德国
            "fr",  # 法国
            "it",  # 意大利
            "es",  # 西班牙
            "nl",  # 荷兰
            # 亚太
            "jp",  # 日本
            "kr",  # 韩国
            "th",  # 泰国
            "id",  # 印度尼西亚
            "vn",  # 越南
            "ph",  # 菲律宾
            "my",  # 马来西亚
            "sg",  # 新加坡
            "in",  # 印度
            "au",  # 澳大利亚
            "nz",  # 新西兰
            # 南美
            "br",  # 巴西
            "ar",  # 阿根廷
            "co",  # 哥伦比亚
            "cl",  # 智利
            # 中东 / 非洲
            "sa",  # 沙特
            "ae",  # 阿联酋
            "tr",  # 土耳其
            "za",  # 南非
            "eg",  # 埃及
            # 区域聚合
            "sea",  # 东南亚聚合
            "eu",   # 欧洲聚合
            "mena",  # 中东北非聚合
        }
    )
    """TikTok 全球热门话题/视频采集器。

    继承 BaseCollector, 获得 QPS 限流 / 指数退避重试 / 熔断器 / Redis 缓存能力。

    构造参数:
        base_url : TikTok API 基础地址 (默认从环境变量 TIKTOK_API_URL 读取)
        **kwargs : 传递给 BaseCollector (如 qps_limit, cache_ttl, max_retries)

    采集参数 (_fetch):
        keyword : 搜索关键词 (可选)
                  - 传入非空关键词: 走搜索端点, 在指定区域内搜索视频
                  - 未传 / 空字符串: 走热门榜端点, 获取指定区域热门视频
        region  : 区域码 (默认 us, 必须在 _KNOWN_REGIONS 集合中)
        limit   : 返回视频数量上限 (默认 20)

    返回格式:
        [{"topic", "source", "region", "description", "likes", "shares",
          "play_count", "author", "url"}, ...]

    异常:
        - _fetch 在 HTTP 失败 / 非 200 / JSON 解析失败 / API 业务错误码
          (status_code != 0) 时向上抛出异常, 由 BaseCollector 的
          重试 / 熔断 / 缓存机制处理; 仅当 API 成功但 list 为空时返回 []。
        - _validate_region / _fetch 在 region 不属于 _KNOWN_REGIONS 时
          抛出 ValueError (不再静默兜底默认区域)。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("qps_limit", 1.0)
        kwargs.setdefault("cache_ttl", 3600)
        super().__init__(name="tiktok", **kwargs)
        self.base_url: str = base_url or os.getenv(
            "TIKTOK_API_URL", "https://www.tiktok.com/api/v1"
        )

    # ==================================================================
    # 区域校验
    # ==================================================================

    def _validate_region(self, region: str) -> None:
        """校验 region 是否在已知区域集合中。

        参数:
            region : 区域码 (ISO 国家码小写或区域聚合码, 如 us / jp / sea)

        异常:
            ValueError: region 不在 _KNOWN_REGIONS 集合中
        """
        if region not in self._KNOWN_REGIONS:
            raise ValueError(
                f"Unknown region: {region} "
                f"(known regions: {sorted(self._KNOWN_REGIONS)})"
            )

    # ==================================================================
    # _fetch - 主采集入口 (由 BaseCollector.collect 调用)
    # ==================================================================

    async def _fetch(
        self,
        keyword: str = "",
        region: str = "us",
        limit: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """执行 TikTok 视频采集。

        创建 httpx.AsyncClient 上下文, 根据 keyword 路由:
            - keyword 非空: 委托给 _get_by_keyword 在指定区域内搜索
            - keyword 空  : 委托给 _get_trending 获取指定区域热门榜

        异常向上抛出 (不吞没), 由 BaseCollector 处理重试 / 熔断 / 缓存降级。

        参数:
            keyword : 搜索关键词 (可选; 非空走搜索端点, 空走热门榜端点)
            region  : 区域码 (默认 us, 必须在 _KNOWN_REGIONS 中)
            limit   : 返回数量上限

        返回:
            解析后的视频数据列表; API 成功但 list 为空时返回 []

        异常:
            ValueError: 未知 region
            httpx.HTTPError / 网络异常 / 非 200 状态码 /
            JSON 解析失败 / API 业务错误码 (status_code != 0) 均向上抛出
        """
        # 未知区域在创建 client 前即抛出, 快速失败
        self._validate_region(region)

        async with httpx.AsyncClient(timeout=10.0) as client:
            if keyword:
                return await self._get_by_keyword(client, keyword, region, limit)
            return await self._get_trending(client, region, limit)

    # ==================================================================
    # _get_trending - 获取区域热门视频
    # ==================================================================

    async def _get_trending(
        self,
        client: httpx.AsyncClient,
        region: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """通过 TikTok 热门榜 API 获取指定区域的热门视频列表并解析。

        参数:
            client : httpx.AsyncClient 实例 (由 _fetch 创建)
            region : 区域码 (调用方需保证已校验)
            limit  : 返回数量上限

        返回:
            解析后的视频数据列表; API 成功 (status_code=0) 但 list 为空时返回 []

        异常:
            - httpx.HTTPError 等: 网络请求失败 (向上抛出, 触发重试)
            - RuntimeError: HTTP 非 200 / JSON 解析失败 /
              API 业务错误码 (status_code != 0)
        """
        url = f"{self.base_url}{_TRENDING_PATH}"
        params: Dict[str, Any] = {"region": region, "count": limit}

        # HTTP 请求异常 (网络错误 / 超时) 直接向上抛出, 触发 BaseCollector 重试
        response = await client.get(url, params=params)

        if response.status_code != 200:
            raise RuntimeError(
                f"[tiktok] HTTP 请求失败, 状态码: {response.status_code}"
            )

        # JSON 解析失败向上抛出 (若 .json() 抛 ValueError, 不再吞没)
        data = response.json()

        # 校验 API 业务码: status_code == 0 表示成功, 否则视为业务失败 (向上抛出)
        if data.get("status_code", -1) != 0:
            raise RuntimeError(
                f"[tiktok] API 业务错误码: status_code={data.get('status_code')}, "
                f"status_msg={data.get('status_msg', '')}"
            )

        # API 成功: 提取 list 列表 (防御性处理 data["data"] 结构缺失)
        raw_data = data.get("data")
        if not isinstance(raw_data, dict):
            # status_code=0 但 data 结构异常, 视为 API 契约违反, 返回空列表
            return []
        items: List[Dict[str, Any]] = raw_data.get("list", [])
        return [self._parse_video(item, region) for item in items]

    # ==================================================================
    # _get_by_keyword - 按关键词在指定区域内搜索视频
    # ==================================================================

    async def _get_by_keyword(
        self,
        client: httpx.AsyncClient,
        keyword: str,
        region: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """通过 TikTok 搜索 API 在指定区域内按关键词搜索视频并解析。

        参数:
            client  : httpx.AsyncClient 实例
            keyword : 搜索关键词
            region  : 区域码 (调用方需保证已校验)
            limit   : 返回数量上限

        返回:
            解析后的视频数据列表; API 成功 (status_code=0) 但 list 为空时返回 []

        异常:
            - httpx.HTTPError 等: 网络请求失败 (向上抛出, 触发重试)
            - RuntimeError: HTTP 非 200 / JSON 解析失败 /
              API 业务错误码 (status_code != 0)
        """
        url = f"{self.base_url}{_SEARCH_PATH}"
        params: Dict[str, Any] = {
            "keyword": keyword,
            "region": region,
            "count": limit,
        }

        # HTTP 请求异常 (网络错误 / 超时) 直接向上抛出, 触发 BaseCollector 重试
        response = await client.get(url, params=params)

        if response.status_code != 200:
            raise RuntimeError(
                f"[tiktok] HTTP 请求失败, 状态码: {response.status_code}"
            )

        # JSON 解析失败向上抛出 (若 .json() 抛 ValueError, 不再吞没)
        data = response.json()

        # 校验 API 业务码: status_code == 0 表示成功, 否则视为业务失败 (向上抛出)
        if data.get("status_code", -1) != 0:
            raise RuntimeError(
                f"[tiktok] API 业务错误码: status_code={data.get('status_code')}, "
                f"status_msg={data.get('status_msg', '')}"
            )

        # API 成功: 提取 list 列表 (防御性处理 data["data"] 结构缺失)
        raw_data = data.get("data")
        if not isinstance(raw_data, dict):
            # status_code=0 但 data 结构异常, 视为 API 契约违反, 返回空列表
            return []
        items: List[Dict[str, Any]] = raw_data.get("list", [])
        return [self._parse_video(item, region) for item in items]

    # ==================================================================
    # _parse_video - 解析单条视频
    # ==================================================================

    def _parse_video(
        self,
        raw_video: Dict[str, Any],
        region: str = "us",
    ) -> Dict[str, Any]:
        """将原始视频数据解析为标准格式。

        参数:
            raw_video : 原始视频 dict
                预期字段: aweme_id, desc, statistics{digg_count, share_count,
                play_count}, author{unique_id}, share_url
            region : 所属区域码 (由调用方传入, 写入解析结果的 region 字段)

        返回:
            {topic, source, region, description, likes, shares, play_count,
             author, url}
            缺失字段返回默认值 (空字符串 / 0), 不抛异常 (解析层保持防御性)
        """
        statistics: Dict[str, Any] = raw_video.get("statistics", {}) or {}
        author: Dict[str, Any] = raw_video.get("author", {}) or {}

        aweme_id: str = raw_video.get("aweme_id", "")
        # URL 优先级: share_url > 基于 aweme_id 构造
        url: str = (
            raw_video.get("share_url", "")
            or (
                f"https://www.tiktok.com/@{author.get('unique_id', '')}/video/{aweme_id}"
                if aweme_id
                else ""
            )
        )

        desc: str = raw_video.get("desc", "") or ""

        return {
            "topic": desc,
            "source": "tiktok",
            "region": region,
            "description": desc,
            "likes": safe_int(statistics.get("digg_count", 0)),
            "shares": safe_int(statistics.get("share_count", 0)),
            "play_count": safe_int(statistics.get("play_count", 0)),
            "author": author.get("unique_id", "") or "",
            "url": url,
        }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["TiktokCollector"]

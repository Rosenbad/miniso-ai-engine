# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 电商热销榜采集器 (Task 4)
# ==============================================================================
# 对应 spec §3.1 中国数据源 - 电商榜:
#   采集内容: 淘宝/拼多多热销榜
#   角色: 已验证的商业信号
#
# EcommerceCollector 继承 BaseCollector, 自动获得:
#   - QPS 限流 (qps_limit=1.0)
#   - 指数退避重试 (0.5s / 1s / 2s)
#   - 熔断器 (连续失败降级)
#   - Redis 缓存 (TTL=3600s)
#
# 设计要点:
#   - 支持多平台: 淘宝 (taobao) / 拼多多 (pinduoduo)
#   - 各平台 base_url 独立配置 (构造器 / 环境变量)
#   - 采集热销商品 (含价格/销量/品类), 作为已验证商业信号
#   - 异常分级: HTTP 错误 / API 错误码 / JSON 解析失败均向上抛出
#     (由 BaseCollector 的重试 / 熔断 / 缓存机制处理);
#     仅 API 成功 (code=0) 但数据列表为空时返回 []
#   - 未知平台抛 ValueError (不再静默兜底)
# ==============================================================================

"""
电商热销榜数据采集器。

采集淘宝/拼多多热销商品榜单, 作为已验证的商业信号数据源。

类:
    EcommerceCollector - 电商热销榜采集器

用法::

    collector = EcommerceCollector()
    data = await collector.collect(platform="taobao", category="家居", limit=50)
    # data: [{"topic", "source", "product_name", "price", "sales",
    #         "platform", "url", "category"}, ...]
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from trendpulse.collectors.base import BaseCollector
from trendpulse.collectors.utils import safe_float, safe_int, setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 支持的平台配置
# ==============================================================================

# 已知平台集合 (用于 _get_platform_base_url 校验)
_KNOWN_PLATFORMS = frozenset({"taobao", "pinduoduo"})

_PLATFORM_DEFAULT_URL: Dict[str, str] = {
    "taobao": "https://h5api.m.taobao.com",
    "pinduoduo": "https://mobile.yangkeduo.com",
}

_PLATFORM_DEFAULT_PATH: Dict[str, str] = {
    "taobao": "/h5/mtop.relationrecommend.wirelessrecommend.recommend/1.0",
    "pinduoduo": "/api/categroy/hot_list",
}


# ==============================================================================
# EcommerceCollector 电商热销榜采集器
# ==============================================================================


class EcommerceCollector(BaseCollector):
    """电商热销榜采集器 (淘宝 / 拼多多)。

    继承 BaseCollector, 获得 QPS 限流 / 指数退避重试 / 熔断器 / Redis 缓存能力。

    构造参数:
        taobao_url    : 淘宝 API 基础地址 (默认从 TAOBAO_API_URL 读取)
        pinduoduo_url : 拼多多 API 基础地址 (默认从 PDD_API_URL 读取)
        **kwargs      : 传递给 BaseCollector

    采集参数 (_fetch):
        platform : 电商平台 (taobao | pinduoduo, 默认 taobao)
        category : 商品品类 (可选过滤)
        limit    : 返回商品数量上限 (默认 50)

    返回格式:
        [{"topic", "source", "product_name", "price", "sales",
          "platform", "url", "category"}, ...]

    异常:
        - _fetch 在 HTTP 失败 / 非 200 / JSON 解析失败 / API 业务错误码
          (code != 0) 时向上抛出异常
        - _get_platform_base_url 在 platform 不属于 {taobao, pinduoduo} 时
          抛出 ValueError (不再静默兜底默认平台)
    """

    def __init__(
        self,
        taobao_url: Optional[str] = None,
        pinduoduo_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("qps_limit", 1.0)
        kwargs.setdefault("cache_ttl", 3600)
        super().__init__(name="ecommerce", **kwargs)
        self.taobao_url: str = taobao_url or os.getenv(
            "TAOBAO_API_URL", _PLATFORM_DEFAULT_URL["taobao"]
        )
        self.pinduoduo_url: str = pinduoduo_url or os.getenv(
            "PDD_API_URL", _PLATFORM_DEFAULT_URL["pinduoduo"]
        )

    # ==================================================================
    # 平台 URL 解析
    # ==================================================================

    def _get_platform_base_url(self, platform: str) -> str:
        """根据平台名获取对应 base_url。

        参数:
            platform : taobao | pinduoduo

        返回:
            对应平台的 base_url

        异常:
            ValueError: platform 不在已知平台集合中
        """
        if platform == "taobao":
            return self.taobao_url
        if platform == "pinduoduo":
            return self.pinduoduo_url
        raise ValueError(
            f"Unknown platform: {platform} "
            f"(known platforms: {sorted(_KNOWN_PLATFORMS)})"
        )

    # ==================================================================
    # _fetch - 主采集入口
    # ==================================================================

    async def _fetch(
        self,
        platform: str = "taobao",
        category: str = "",
        limit: int = 50,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """执行电商热销榜采集。

        创建 httpx.AsyncClient 上下文, 委托给 _get_hotlist 执行实际请求与解析。
        异常向上抛出 (不吞没), 由 BaseCollector 处理重试 / 熔断 / 缓存降级。

        参数:
            platform : 电商平台 (taobao | pinduoduo)
            category : 商品品类 (可选)
            limit    : 返回数量上限

        返回:
            解析后的商品数据列表; API 成功但 items 为空时返回 []

        异常:
            ValueError: 未知 platform
            httpx.HTTPError / 网络异常 / 非 200 状态码 /
            JSON 解析失败 / API 业务错误码 (code != 0) 均向上抛出
        """
        # 未知平台在创建 client 前即抛出, 快速失败
        # (调用 _get_platform_base_url 触发校验)
        self._get_platform_base_url(platform)

        async with httpx.AsyncClient(timeout=10.0) as client:
            return await self._get_hotlist(client, platform, category, limit)

    # ==================================================================
    # _get_hotlist - 获取热销榜
    # ==================================================================

    async def _get_hotlist(
        self,
        client: httpx.AsyncClient,
        platform: str,
        category: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """通过电商平台 API 获取热销商品列表并解析。

        参数:
            client   : httpx.AsyncClient 实例
            platform : taobao | pinduoduo (调用方需保证已校验)
            category : 商品品类
            limit    : 返回数量上限

        返回:
            解析后的商品数据列表; API 成功 (code=0) 但 items 为空时返回 []

        异常:
            - ValueError: 未知 platform
            - httpx.HTTPError 等: 网络请求失败 (向上抛出, 触发重试)
            - RuntimeError: HTTP 非 200 / JSON 解析失败 / API 业务错误码 (code != 0)
        """
        base_url = self._get_platform_base_url(platform)
        path = _PLATFORM_DEFAULT_PATH.get(platform, "/api/hot_list")
        url = f"{base_url}{path}"
        params = {"category": category, "count": limit}

        # HTTP 请求异常 (网络错误 / 超时) 直接向上抛出, 触发 BaseCollector 重试
        response = await client.get(url, params=params)

        if response.status_code != 200:
            raise RuntimeError(
                f"[ecommerce:{platform}] HTTP 请求失败, 状态码: {response.status_code}"
            )

        # JSON 解析失败向上抛出 (若 .json() 抛 ValueError, 不再吞没)
        data = response.json()

        # 校验 API 业务码: code == 0 表示成功, 否则视为业务失败 (向上抛出)
        if data.get("code", -1) != 0:
            raise RuntimeError(
                f"[ecommerce:{platform}] API 业务错误码: code={data.get('code')}, "
                f"msg={data.get('msg', '')}"
            )

        # API 成功: 提取 items 列表 (防御性处理 data["data"] 结构缺失)
        raw_data = data.get("data")
        if not isinstance(raw_data, dict):
            # code=0 但 data 结构异常, 视为 API 契约违反, 返回空列表
            return []
        items: List[Dict[str, Any]] = raw_data.get("items", [])
        return [self._parse_product(item, platform) for item in items]

    # ==================================================================
    # _parse_product - 解析单条商品
    # ==================================================================

    def _parse_product(
        self,
        raw_product: Dict[str, Any],
        platform: str,
    ) -> Dict[str, Any]:
        """将原始商品数据解析为标准格式。

        参数:
            raw_product : 原始商品 dict
                预期字段: item_id, title, price, sales, item_url, category
            platform : 所属电商平台 (taobao | pinduoduo)

        返回:
            {topic, source, product_name, price, sales, platform, url, category}
            缺失字段返回默认值 (空字符串 / 0), 不抛异常 (解析层保持防御性)
        """
        item_id: str = raw_product.get("item_id", "")
        url: str = (
            raw_product.get("item_url", "")
            or (f"https://item.{platform}.com/{item_id}" if item_id else "")
        )
        title: str = raw_product.get("title", "") or ""

        return {
            "topic": title,
            "source": "ecommerce",
            "product_name": title,
            "price": safe_float(raw_product.get("price", 0)),
            "sales": safe_int(raw_product.get("sales", 0)),
            "platform": platform,
            "url": url,
            "category": raw_product.get("category", "") or "",
        }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["EcommerceCollector"]

# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 搜索指数采集器 (Task 4)
# ==============================================================================
# 对应 spec §3.1 中国数据源 - 搜索指数:
#   采集内容: 百度/微信指数
#   角色: 大众关注度基线
#
# SearchIndexCollector 继承 BaseCollector, 自动获得:
#   - QPS 限流 (qps_limit=2.0, 较快 - 指数 API 限流宽松)
#   - 指数退避重试 (0.5s / 1s / 2s)
#   - 熔断器 (连续失败降级)
#   - Redis 缓存 (TTL=1800s, 较短 TTL 保证数据新鲜度)
#
# 设计要点:
#   - 支持多平台: 百度 (baidu) / 微信 (weixin)
#   - 各平台 base_url 独立配置 (构造器 / 环境变量)
#   - 采集关键词搜索指数 (含趋势方向与日期), 作为大众关注度基线
#   - 优雅降级: HTTP 错误 / API 错误码 / 空响应 / 畸形数据均返回空列表
# ==============================================================================

"""
搜索指数数据采集器。

采集百度/微信搜索指数 (含趋势方向), 作为大众关注度基线数据源。

类:
    SearchIndexCollector - 搜索指数采集器

用法::

    collector = SearchIndexCollector()
    data = await collector.collect(keyword="侘寂风", platform="baidu", limit=20)
    # data: [{"topic", "source", "keyword", "index_value", "trend",
    #         "platform", "date"}, ...]
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
    """安全转换为 int, 失败时返回 default。"""
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


# ==============================================================================
# 平台默认配置
# ==============================================================================

_PLATFORM_DEFAULT_URL: Dict[str, str] = {
    "baidu": "https://index.baidu.com",
    "weixin": "https://index.weixin.qq.com",
}

_PLATFORM_DEFAULT_PATH: Dict[str, str] = {
    "baidu": "/api/SearchApi/index",
    "weixin": "/api/search/keywordindex",
}


# ==============================================================================
# SearchIndexCollector 搜索指数采集器
# ==============================================================================


class SearchIndexCollector(BaseCollector):
    """搜索指数采集器 (百度 / 微信)。

    继承 BaseCollector, 获得 QPS 限流 / 指数退避重试 / 熔断器 / Redis 缓存能力。
    缓存 TTL 较短 (1800s = 30 分钟), 保证指数数据新鲜度。

    构造参数:
        baidu_url : 百度指数 API 基础地址 (默认从 BAIDU_INDEX_URL 读取)
        weixin_url: 微信指数 API 基础地址 (默认从 WEIXIN_INDEX_URL 读取)
        **kwargs  : 传递给 BaseCollector

    采集参数 (_fetch):
        keyword  : 搜索关键词
        platform : 指数平台 (baidu | weixin, 默认 baidu)
        limit    : 返回数据点数量上限 (默认 20)

    返回格式:
        [{"topic", "source", "keyword", "index_value", "trend",
          "platform", "date"}, ...]
    """

    def __init__(
        self,
        baidu_url: Optional[str] = None,
        weixin_url: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("qps_limit", 2.0)
        kwargs.setdefault("cache_ttl", 1800)  # 较短 TTL 保证新鲜度
        super().__init__(name="search_index", **kwargs)
        self.baidu_url: str = baidu_url or os.getenv(
            "BAIDU_INDEX_URL", _PLATFORM_DEFAULT_URL["baidu"]
        )
        self.weixin_url: str = weixin_url or os.getenv(
            "WEIXIN_INDEX_URL", _PLATFORM_DEFAULT_URL["weixin"]
        )

    # ==================================================================
    # 平台 URL 解析
    # ==================================================================

    def _get_platform_base_url(self, platform: str) -> str:
        """根据平台名获取对应 base_url。

        参数:
            platform : baidu | weixin

        返回:
            对应平台的 base_url; 未知平台返回百度 URL 作为兜底
        """
        if platform == "weixin":
            return self.weixin_url
        return self.baidu_url  # 默认百度

    # ==================================================================
    # _fetch - 主采集入口
    # ==================================================================

    async def _fetch(
        self,
        keyword: str = "",
        platform: str = "baidu",
        limit: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """执行搜索指数采集。

        创建 httpx.AsyncClient 上下文, 委托给 _get_index 执行实际请求与解析。

        参数:
            keyword  : 搜索关键词
            platform : 指数平台 (baidu | weixin)
            limit    : 返回数据点数量上限

        返回:
            解析后的指数数据列表; 任何错误均返回空列表 (不抛异常)
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                return await self._get_index(client, keyword, platform)
        except Exception as exc:
            logger.warning(f"[search_index] _fetch 异常, 返回空列表: {exc}")
            return []

    # ==================================================================
    # _get_index - 获取搜索指数
    # ==================================================================

    async def _get_index(
        self,
        client: httpx.AsyncClient,
        keyword: str,
        platform: str,
    ) -> List[Dict[str, Any]]:
        """通过搜索指数 API 获取关键词指数数据并解析。

        参数:
            client   : httpx.AsyncClient 实例
            keyword  : 搜索关键词
            platform : baidu | weixin

        返回:
            解析后的指数数据列表 (每个数据点为一条记录);
            HTTP 错误 / API 错误码 / 空结果均返回空列表
        """
        base_url = self._get_platform_base_url(platform)
        path = _PLATFORM_DEFAULT_PATH.get(platform, "/api/index")
        url = f"{base_url}{path}"
        params = {"keyword": keyword, "platform": platform}

        try:
            response = await client.get(url, params=params)
        except Exception as exc:
            logger.warning(f"[search_index:{platform}] 请求失败: {exc}")
            return []

        if response.status_code != 200:
            logger.debug(
                f"[search_index:{platform}] HTTP {response.status_code}, 跳过"
            )
            return []

        try:
            data = response.json()
        except Exception as exc:
            logger.warning(f"[search_index:{platform}] JSON 解析失败: {exc}")
            return []

        # 校验 API 业务码: code == 0 表示成功
        if data.get("code", -1) != 0:
            logger.debug(f"[search_index:{platform}] API 错误码: {data.get('code')}")
            return []

        # 提取指数数据点列表
        raw_data = data.get("data", {})
        if not isinstance(raw_data, dict):
            return []

        index_list: List[Dict[str, Any]] = raw_data.get("index_list", [])
        return [
            self._parse_index(item, keyword, platform) for item in index_list
        ]

    # ==================================================================
    # _parse_index - 解析单条指数数据
    # ==================================================================

    def _parse_index(
        self,
        raw_data: Dict[str, Any],
        keyword: str,
        platform: str,
    ) -> Dict[str, Any]:
        """将原始指数数据解析为标准格式。

        参数:
            raw_data : 原始指数数据 dict
                预期字段: index (指数值), trend (趋势方向), date (日期)
            keyword  : 搜索关键词
            platform : 指数平台 (baidu | weixin)

        返回:
            {topic, source, keyword, index_value, trend, platform, date}
            缺失字段返回默认值 (空字符串 / 0), 不抛异常
        """
        return {
            "topic": keyword,
            "source": "search_index",
            "keyword": keyword,
            "index_value": _safe_int(raw_data.get("index", 0)),
            "trend": raw_data.get("trend", "") or "",
            "platform": platform,
            "date": raw_data.get("date", "") or "",
        }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["SearchIndexCollector"]

# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - Instagram 海外数据采集器 (Task 5)
# ==============================================================================
# 对应 spec §3.1 海外数据源 - Instagram:
#   采集内容: 标签趋势 + 网红帖子
#   角色: 审美与视觉风格趋势
#
# InstagramCollector 继承 BaseCollector, 自动获得:
#   - QPS 限流 (qps_limit=0.5, 较严格 - Instagram API 限流较紧)
#   - 指数退避重试 (0.5s / 1s / 2s)
#   - 熔断器 (连续失败降级)
#   - Redis 缓存 (TTL=3600s)
#
# 设计要点:
#   - 使用 httpx.AsyncClient 异步 HTTP 请求, 默认 10s 超时
#   - base_url 可通过构造器 / 环境变量配置 (测试灵活性)
#   - 采集指定标签 (hashtag) 下的热门帖子, 含图片 URL / 点赞 / 评论数据
#   - Instagram API 限流严格, 使用较低 QPS (0.5 = 每 2 秒 1 次)
#   - 异常分级: HTTP 错误 / API 错误码 / JSON 解析失败均向上抛出
#     (由 BaseCollector 的重试 / 熔断 / 缓存机制处理);
#     仅 API 成功 (status_code=0) 但数据列表为空时返回 []
# ==============================================================================

"""
Instagram 海外数据采集器。

采集 Instagram 标签趋势下的网红帖子 (含图片/互动数据),
作为审美与视觉风格趋势数据源。

类:
    InstagramCollector - Instagram 采集器

用法::

    collector = InstagramCollector()
    data = await collector.collect(tag="wabisabi", limit=20)
    # data: [{"topic", "source", "tag", "caption", "likes", "comments",
    #         "author", "url", "image_url"}, ...]
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

# 标签帖子端点 (按 hashtag 获取热门帖子)
_TAG_TRENDS_PATH: str = "/v1/tags/{tag}/media"


# ==============================================================================
# InstagramCollector Instagram 采集器
# ==============================================================================


class InstagramCollector(BaseCollector):
    """Instagram 标签趋势采集器。

    继承 BaseCollector, 获得 QPS 限流 / 指数退避重试 / 熔断器 / Redis 缓存能力。
    Instagram API 限流严格, 使用较低 QPS (0.5 = 每 2 秒 1 次)。

    构造参数:
        base_url : Instagram Graph API 基础地址
                   (默认从环境变量 INSTAGRAM_API_URL 读取)
        **kwargs : 传递给 BaseCollector (如 qps_limit, cache_ttl, max_retries)

    采集参数 (_fetch):
        tag   : 标签名 (hashtag, 不含 # 符号); 空字符串时获取平台热门标签帖子
        limit : 返回帖子数量上限 (默认 20)

    返回格式:
        [{"topic", "source", "tag", "caption", "likes", "comments",
          "author", "url", "image_url"}, ...]

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
        # Instagram API 限流严格, 使用较低 QPS (0.5 = 每 2 秒 1 次)
        kwargs.setdefault("qps_limit", 0.5)
        kwargs.setdefault("cache_ttl", 3600)
        super().__init__(name="instagram", **kwargs)
        self.base_url: str = base_url or os.getenv(
            "INSTAGRAM_API_URL", "https://graph.instagram.com"
        )

    # ==================================================================
    # _fetch - 主采集入口 (由 BaseCollector.collect 调用)
    # ==================================================================

    async def _fetch(
        self,
        tag: str = "",
        limit: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """执行 Instagram 标签帖子采集。

        创建 httpx.AsyncClient 上下文, 委托给 _get_tag_trends 执行实际请求与解析。
        异常向上抛出 (不吞没), 由 BaseCollector 处理重试 / 熔断 / 缓存降级。

        参数:
            tag   : 标签名 (hashtag, 不含 # 符号)
            limit : 返回数量上限

        返回:
            解析后的帖子数据列表; API 成功但 list 为空时返回 []

        异常:
            httpx.HTTPError / 网络异常 / 非 200 状态码 /
            JSON 解析失败 / API 业务错误码 (status_code != 0) 均向上抛出
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await self._get_tag_trends(client, tag, limit)

    # ==================================================================
    # _get_tag_trends - 获取标签下的热门帖子
    # ==================================================================

    async def _get_tag_trends(
        self,
        client: httpx.AsyncClient,
        tag: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """通过 Instagram Graph API 获取指定标签下的热门帖子并解析。

        参数:
            client : httpx.AsyncClient 实例 (由 _fetch 创建)
            tag    : 标签名 (hashtag, 不含 # 符号)
            limit  : 返回数量上限

        返回:
            解析后的帖子数据列表; API 成功 (status_code=0) 但 list 为空时返回 []

        异常:
            - httpx.HTTPError 等: 网络请求失败 (向上抛出, 触发重试)
            - RuntimeError: HTTP 非 200 / JSON 解析失败 /
              API 业务错误码 (status_code != 0)
        """
        # 构造端点 URL (路径中包含 tag, 需对 tag 做安全处理避免路径注入;
        # 此处使用简单拼接, 生产环境应做 URL 编码)
        safe_tag: str = tag.lstrip("#").strip()
        url = f"{self.base_url}{_TAG_TRENDS_PATH.format(tag=safe_tag)}"
        params: Dict[str, Any] = {
            "tag": safe_tag,
            "count": limit,
        }

        # HTTP 请求异常 (网络错误 / 超时) 直接向上抛出, 触发 BaseCollector 重试
        response = await client.get(url, params=params)

        if response.status_code != 200:
            raise RuntimeError(
                f"[instagram] HTTP 请求失败, 状态码: {response.status_code}"
            )

        # JSON 解析失败向上抛出 (若 .json() 抛 ValueError, 不再吞没)
        data = response.json()

        # 校验 API 业务码: status_code == 0 表示成功, 否则视为业务失败 (向上抛出)
        # 注: Instagram Graph API 实际使用 HTTP 状态码表达错误,
        # 此处沿用项目统一的 status_code 业务码约定以便与其它采集器对齐。
        if data.get("status_code", -1) != 0:
            raise RuntimeError(
                f"[instagram] API 业务错误码: status_code={data.get('status_code')}, "
                f"status_msg={data.get('status_msg', '')}"
            )

        # API 成功: 提取 list 列表 (防御性处理 data["data"] 结构缺失)
        raw_data = data.get("data")
        if not isinstance(raw_data, dict):
            # status_code=0 但 data 结构异常, 视为 API 契约违反, 返回空列表
            return []
        items: List[Dict[str, Any]] = raw_data.get("list", [])
        return [self._parse_post(item, tag=safe_tag) for item in items]

    # ==================================================================
    # _parse_post - 解析单条帖子
    # ==================================================================

    def _parse_post(
        self,
        raw_post: Dict[str, Any],
        tag: str = "",
    ) -> Dict[str, Any]:
        """将原始帖子数据解析为标准格式。

        参数:
            raw_post : 原始帖子 dict
                预期字段: id, caption, like_count, comment_count,
                user{username}, permalink, image_url (或 media_url)
            tag : 所属标签 (由调用方传入, 写入解析结果的 tag 字段)

        返回:
            {topic, source, tag, caption, likes, comments, author, url, image_url}
            缺失字段返回默认值 (空字符串 / 0), 不抛异常 (解析层保持防御性)
        """
        user: Dict[str, Any] = raw_post.get("user", {}) or {}

        post_id: str = raw_post.get("id", "")
        # URL 优先级: permalink > 基于 id 构造
        url: str = (
            raw_post.get("permalink", "")
            or (f"https://www.instagram.com/p/{post_id}/" if post_id else "")
        )

        # 图片 URL 兼容字段: image_url (项目约定) > media_url (Instagram Graph API 原生)
        image_url: str = (
            raw_post.get("image_url", "")
            or raw_post.get("media_url", "")
            or ""
        )

        caption: str = raw_post.get("caption", "") or ""

        return {
            "topic": caption,
            "source": "instagram",
            "tag": tag,
            "caption": caption,
            "likes": safe_int(raw_post.get("like_count", 0)),
            "comments": safe_int(raw_post.get("comment_count", 0)),
            "author": user.get("username", "") or "",
            "url": url,
            "image_url": image_url,
        }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["InstagramCollector"]

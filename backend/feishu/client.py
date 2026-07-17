# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 飞书客户端 (Task 13)
# ==============================================================================
# 对应 spec §2.2 飞书生态集成层:
#   - tenant_access_token 管理 (获取 + 缓存 + 自动续期)
#   - 统一 API 请求封装 (认证头注入)
#   - demo 模式 (无凭据时返回 mock 响应, 适配原型演示)
#
# 本模块提供:
#   1. FeishuClient - 飞书开放平台 API 客户端基类
#
# 设计要点:
#   - token 缓存: 首次获取后缓存, 接近过期时自动续期 (飞书 token 有效期 ~2h)
#   - demo 模式: 无 FEISHU_APP_ID 时自动进入, 返回结构正确的 mock 响应
#   - 统一 request(): 自动注入 Authorization 头, 处理响应 JSON
#   - httpx.AsyncClient: 异步 HTTP, 与项目 TrendPulse 采集器保持一致
# ==============================================================================

"""
飞书客户端模块。

核心组件:
    - FeishuClient : 飞书开放平台 API 客户端
        * tenant_access_token 管理 (缓存 + 自动续期)
        * 统一 request() 方法 (认证头注入 + 响应处理)
        * demo 模式 (无凭据时返回 mock 响应)

设计说明:
    - 飞书 tenant_access_token 有效期约 2 小时, 本模块在过期前 5 分钟自动续期
    - demo 模式: 当 FEISHU_APP_ID 未设置时, 所有 API 返回 mock 响应,
      适配无真实凭据的原型演示场景
    - 真实模式: 通过 httpx.AsyncClient 发起 HTTPS 请求, 注入 Bearer token

用法示例::

    client = FeishuClient()  # 自动从环境变量读取凭据
    token = await client.get_tenant_access_token()
    result = await client.request("POST", "/im/v1/messages", json=payload)
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import httpx

try:
    from loguru import logger
except ImportError:  # loguru 尚未安装时降级为标准 logging
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]


# ==============================================================================
# 常量
# ==============================================================================

# token 续期提前量 (秒): 在过期前 5 分钟续期, 避免边界过期
_TOKEN_RENEWAL_BUFFER: int = 300

# demo 模式 token 标识
_DEMO_TOKEN: str = "demo-tenant-access-token"

# demo 模式默认 token 有效期 (秒): 2 小时
_DEMO_TOKEN_TTL: int = 7200


# ==============================================================================
# FeishuClient - 飞书开放平台 API 客户端
# ==============================================================================


class FeishuClient:
    """飞书开放平台 API 客户端。

    提供 tenant_access_token 管理 (缓存 + 自动续期) 与统一 API 请求封装。
    无凭据时自动进入 demo 模式, 返回结构正确的 mock 响应。

    属性:
        BASE_URL          : 飞书开放平台 API 基础地址
        app_id            : 飞书应用 App ID
        app_secret        : 飞书应用 App Secret
        is_demo_mode      : 是否处于 demo 模式 (无真实凭据)

    用法::

        # 从环境变量自动读取凭据
        client = FeishuClient()

        # 显式传参
        client = FeishuClient(app_id="cli_xxx", app_secret="secret")

        # 获取 token (带缓存)
        token = await client.get_tenant_access_token()

        # 发起 API 请求 (自动注入认证头)
        result = await client.request("POST", "/im/v1/messages", json=payload)
    """

    BASE_URL: str = "https://open.feishu.cn/open-apis"
    """飞书开放平台 API 基础地址。"""

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
    ) -> None:
        """初始化飞书客户端。

        参数:
            app_id     : 飞书应用 App ID。为 None 时从环境变量 FEISHU_APP_ID 读取。
            app_secret : 飞书应用 App Secret。为 None 时从环境变量 FEISHU_APP_SECRET 读取。

        说明:
            - 若 app_id 和 app_secret 均为空 (参数 + 环境变量均无值),
              则进入 demo 模式, 所有 API 返回 mock 响应。
            - demo 模式适用于无真实飞书凭据的原型演示场景。
        """
        self.app_id: Optional[str] = app_id or os.environ.get("FEISHU_APP_ID")
        self.app_secret: Optional[str] = app_secret or os.environ.get(
            "FEISHU_APP_SECRET"
        )

        # demo 模式判定: 无 app_id 或无 app_secret
        self.is_demo_mode: bool = not (self.app_id and self.app_secret)

        # token 缓存
        self._cached_token: Optional[str] = None
        self._token_expires_at: float = 0.0

        if self.is_demo_mode:
            logger.info(
                "FeishuClient: 进入 demo 模式 (无 FEISHU_APP_ID / FEISHU_APP_SECRET), "
                "所有 API 将返回 mock 响应"
            )

    # ==================================================================
    # tenant_access_token 管理
    # ==================================================================

    async def get_tenant_access_token(self) -> str:
        """获取 tenant_access_token (带缓存与自动续期)。

        飞书 tenant_access_token 有效期约 2 小时。本方法:
            1. 检查缓存的 token 是否仍然有效 (未过期 + 未接近过期)
            2. 若有效 → 返回缓存 token
            3. 若过期/接近过期 → 重新获取并缓存
            4. demo 模式 → 返回 demo token

        返回:
            tenant_access_token 字符串

        说明:
            - 真实模式下通过 POST /auth/v3/tenant_access_token/internal 获取
            - demo 模式返回 "demo-tenant-access-token"
            - token 在过期前 5 分钟 (_TOKEN_RENEWAL_BUFFER) 自动续期
        """
        # --- demo 模式: 返回 demo token (带缓存) ---
        if self.is_demo_mode:
            now = time.monotonic()
            if self._cached_token is None or now >= self._token_expires_at:
                self._cached_token = _DEMO_TOKEN
                self._token_expires_at = now + _DEMO_TOKEN_TTL
                logger.debug(
                    f"FeishuClient [demo]: 获取 demo token, "
                    f"有效期 {_DEMO_TOKEN_TTL}s"
                )
            return self._cached_token  # type: ignore[return-value]

        # --- 真实模式: 检查缓存 ---
        now = time.monotonic()
        if (
            self._cached_token is not None
            and now < self._token_expires_at - _TOKEN_RENEWAL_BUFFER
        ):
            logger.debug("FeishuClient: 使用缓存的 tenant_access_token")
            return self._cached_token

        # --- 真实模式: 重新获取 token ---
        logger.info("FeishuClient: tenant_access_token 已过期或未缓存, 重新获取")
        token, expire = await self._fetch_tenant_access_token()
        self._cached_token = token
        self._token_expires_at = now + expire
        return token

    async def _fetch_tenant_access_token(self) -> tuple[str, int]:
        """通过飞书 API 获取 tenant_access_token (真实模式)。

        POST /auth/v3/tenant_access_token/internal
        Body: {"app_id": "...", "app_secret": "..."}

        返回:
            (token, expire_seconds) 元组

        异常:
            httpx.HTTPStatusError : API 返回非 2xx
            KeyError              : 响应缺少 tenant_access_token 字段
        """
        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        payload: Dict[str, Any] = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        token: str = data["tenant_access_token"]
        expire: int = data.get("expire", 7200)
        logger.info(
            f"FeishuClient: 获取 tenant_access_token 成功, "
            f"有效期 {expire}s"
        )
        return token, expire

    # ==================================================================
    # 统一 API 请求
    # ==================================================================

    async def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """发起认证 API 请求 (自动注入 Authorization 头)。

        参数:
            method   : HTTP 方法 ("GET" / "POST" / "PUT" / "DELETE")
            path     : API 路径 (如 "/im/v1/messages"), 自动拼接 BASE_URL
            **kwargs : 传递给 httpx.AsyncClient.request 的额外参数
                       (如 json=, params=, headers= 等)

        返回:
            API 响应 JSON 字典

        说明:
            - 真实模式: 通过 httpx 发起请求, 注入 Bearer token
            - demo 模式: 返回结构正确的 mock 响应 (含 demo 旗标)
            - 路径以 http 开头时直接使用, 否则拼接 BASE_URL
        """
        # --- demo 模式: 返回 mock 响应 ---
        if self.is_demo_mode:
            return self._demo_response(method, path, **kwargs)

        # --- 真实模式: 通过 httpx 发起请求 ---
        url = (
            path
            if path.startswith("http")
            else f"{self.BASE_URL}{path}"
        )

        # 注入认证头
        token = await self.get_tenant_access_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers["Content-Type"] = "application/json; charset=utf-8"

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method, url, headers=headers, **kwargs
            )
            response.raise_for_status()
            return response.json()

    # ==================================================================
    # demo 模式 mock 响应生成
    # ==================================================================

    def _demo_response(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """生成 demo 模式的 mock 响应。

        根据 API 路径返回结构正确的 mock 数据, 适配原型演示。
        所有 mock 响应均含 ``"demo": True`` 旗标, 便于区分真实/demo 响应。

        参数:
            method : HTTP 方法
            path   : API 路径
            **kwargs : 请求参数 (用于生成更精确的 mock)

        返回:
            mock 响应字典
        """
        # 消息发送 API
        if "/im/v1/messages" in path:
            return {
                "code": 0,
                "msg": "success",
                "data": {"message_id": "om_demo_message_001"},
                "demo": True,
            }

        # 多维表格 - 创建表
        if "tables" in path and method == "POST":
            return {
                "code": 0,
                "msg": "success",
                "data": {"table_id": "tblDemoTop100"},
                "demo": True,
            }

        # 多维表格 - 插入记录
        if "records" in path and method == "POST":
            body = kwargs.get("json", {})
            records = body.get("records", []) if isinstance(body, dict) else []
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "records": [
                        {"record_id": f"recDemo{i:04d}"}
                        for i in range(len(records))
                    ],
                },
                "demo": True,
            }

        # token 获取 API
        if "tenant_access_token" in path:
            return {
                "code": 0,
                "tenant_access_token": _DEMO_TOKEN,
                "expire": _DEMO_TOKEN_TTL,
                "demo": True,
            }

        # 通用默认响应
        return {
            "code": 0,
            "msg": "success (demo mode)",
            "data": {},
            "demo": True,
        }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["FeishuClient"]

# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 飞书机器人 (Task 13)
# ==============================================================================
# 对应 spec §2.2 飞书生态集成层:
#   - 飞书机器人 (Bot) 作为人机协同入口
#   - 决策卡片推送 ("Top 100 已就绪, 请评审")
#   - Agent 推理过程通知
#   - 验证结果实时播报
#
# 本模块提供:
#   1. FeishuBot - 飞书机器人消息推送
#      * send_card()    : 发送 interactive 消息卡片
#      * send_text()    : 发送文本消息
#      * send_webhook() : 通过自定义机器人 Webhook 发送卡片 (无需 chat_id)
#
# 飞书消息 API:
#   - 发送消息: POST /im/v1/messages?receive_id_type=chat_id
#   - Webhook : POST {webhook_url} (自定义机器人, 无需 token)
# ==============================================================================

"""
飞书机器人模块。

核心组件:
    - FeishuBot : 飞书机器人消息推送
        * send_card()    : 发送 interactive 消息卡片 (决策卡片/趋势报告/验证结果)
        * send_text()    : 发送纯文本消息
        * send_webhook() : 通过自定义机器人 Webhook 发送卡片

设计说明:
    - send_card / send_text 使用飞书 IM API (需 tenant_access_token)
    - send_webhook 使用自定义机器人 Webhook URL (无需 token, 更简单)
    - demo 模式下所有方法返回 mock 响应
    - Webhook 模式: 当配置了 webhook_url 时, 可直接发送无需 chat_id

飞书消息卡片格式 (interactive):
    {
        "config": {"wide_screen_mode": true},
        "header": {"title": {...}, "template": "blue"},
        "elements": [{"tag": "div", ...}, {"tag": "action", ...}]
    }

用法示例::

    client = FeishuClient()
    bot = FeishuBot(client, webhook_url="https://open.feishu.cn/.../hook/xxx")

    # 发送卡片到指定群聊
    await bot.send_card(chat_id="oc_xxx", card=card_dict)

    # 发送文本消息
    await bot.send_text(chat_id="oc_xxx", text="验证完成!")

    # 通过 Webhook 发送 (无需 chat_id)
    await bot.send_webhook(card=card_dict)
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]

from feishu.client import FeishuClient


# ==============================================================================
# FeishuBot - 飞书机器人消息推送
# ==============================================================================


class FeishuBot:
    """飞书机器人消息推送。

    支持三种发送方式:
        1. send_card()    : 通过 IM API 发送 interactive 消息卡片 (需 chat_id + token)
        2. send_text()    : 通过 IM API 发送文本消息 (需 chat_id + token)
        3. send_webhook() : 通过自定义机器人 Webhook 发送卡片 (无需 token)

    用法::

        client = FeishuClient()
        bot = FeishuBot(client, webhook_url="https://open.feishu.cn/.../hook/xxx")

        await bot.send_card("oc_xxx", card_dict)
        await bot.send_text("oc_xxx", "Hello!")
        await bot.send_webhook(card_dict)
    """

    def __init__(
        self,
        client: FeishuClient,
        webhook_url: Optional[str] = None,
    ) -> None:
        """初始化飞书机器人。

        参数:
            client       : FeishuClient 实例 (提供 API 认证与请求能力)
            webhook_url  : 自定义机器人 Webhook URL (可选)。
                           配置后可通过 send_webhook() 发送消息, 无需 chat_id。
                           默认从环境变量 FEISHU_WEBHOOK_URL 读取。
        """
        import os

        self.client: FeishuClient = client
        self.webhook_url: Optional[str] = webhook_url or os.environ.get(
            "FEISHU_WEBHOOK_URL"
        )

    # ==================================================================
    # 发送消息卡片 (interactive)
    # ==================================================================

    async def send_card(
        self,
        chat_id: str,
        card: Dict[str, Any],
    ) -> Dict[str, Any]:
        """发送 interactive 消息卡片到指定群聊。

        POST /im/v1/messages?receive_id_type=chat_id
        Body: {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(card)
        }

        参数:
            chat_id : 目标群聊 ID (如 "oc_xxx")
            card    : 飞书消息卡片字典 (config / header / elements 结构)

        返回:
            发送结果字典, 含 message_id:
            {"code": 0, "data": {"message_id": "om_xxx"}, ...}

        说明:
            - demo 模式返回 mock message_id
            - 卡片内容通过 json.dumps 序列化为字符串放入 content 字段
        """
        content = json.dumps(card, ensure_ascii=False)
        payload: Dict[str, Any] = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": content,
        }

        result = await self.client.request(
            "POST",
            "/im/v1/messages?receive_id_type=chat_id",
            json=payload,
        )

        if self.client.is_demo_mode:
            logger.info(f"FeishuBot [demo]: 发送卡片到群 {chat_id} (mock)")
        else:
            logger.info(f"FeishuBot: 发送卡片到群 {chat_id}")

        return result

    # ==================================================================
    # 发送文本消息
    # ==================================================================

    async def send_text(
        self,
        chat_id: str,
        text: str,
    ) -> Dict[str, Any]:
        """发送纯文本消息到指定群聊。

        POST /im/v1/messages?receive_id_type=chat_id
        Body: {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text})
        }

        参数:
            chat_id : 目标群聊 ID
            text    : 文本内容

        返回:
            发送结果字典, 含 message_id

        说明:
            - demo 模式返回 mock message_id
            - 文本内容包裹在 {"text": "..."} 中并序列化为 JSON 字符串
        """
        content = json.dumps({"text": text}, ensure_ascii=False)
        payload: Dict[str, Any] = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": content,
        }

        result = await self.client.request(
            "POST",
            "/im/v1/messages?receive_id_type=chat_id",
            json=payload,
        )

        if self.client.is_demo_mode:
            logger.info(
                f"FeishuBot [demo]: 发送文本到群 {chat_id}: "
                f"{text[:50]}{'...' if len(text) > 50 else ''} (mock)"
            )
        else:
            logger.info(f"FeishuBot: 发送文本到群 {chat_id}")

        return result

    # ==================================================================
    # 通过 Webhook 发送卡片
    # ==================================================================

    async def send_webhook(
        self,
        card: Dict[str, Any],
    ) -> Dict[str, Any]:
        """通过自定义机器人 Webhook 发送消息卡片。

        POST {webhook_url}
        Body: {"msg_type": "interactive", "card": card}

        参数:
            card : 飞书消息卡片字典

        返回:
            发送结果字典

        说明:
            - Webhook 模式无需 tenant_access_token, 更简单
            - 无 webhook_url 时, 在 demo 模式下返回 mock 响应;
              在真实模式下抛出 ValueError
            - demo 模式 + 无 webhook_url: 返回 mock 响应 (含 demo 旗标)
        """
        # demo 模式: 无需真实 Webhook
        if self.client.is_demo_mode:
            logger.info("FeishuBot [demo]: 通过 Webhook 发送卡片 (mock)")
            return {
                "code": 0,
                "msg": "success (demo webhook)",
                "data": {"message_id": "om_demo_webhook_001"},
                "demo": True,
            }

        # 真实模式: 检查 webhook_url
        if not self.webhook_url:
            raise ValueError(
                "send_webhook 需要 webhook_url, 但未配置。"
                "请通过构造函数传入或设置 FEISHU_WEBHOOK_URL 环境变量。"
            )

        payload: Dict[str, Any] = {
            "msg_type": "interactive",
            "card": card,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(self.webhook_url, json=payload)
            response.raise_for_status()
            result = response.json()

        logger.info("FeishuBot: 通过 Webhook 发送卡片成功")
        return result


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["FeishuBot"]

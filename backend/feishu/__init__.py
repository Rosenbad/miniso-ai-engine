"""飞书(Feishu)生态集成层。

提供飞书机器人通知、多维表格数据同步、
AI 报告生成、知识库检索等飞书生态能力。

组件清单:
    - FeishuClient    : 飞书开放平台 API 客户端 (token 管理 + demo 模式)
    - FeishuBitable   : 多维表格操作 (Top 100 打版池管理)
    - FeishuBot       : 机器人消息推送 (决策卡片/趋势报告/验证结果)
    - FeishuAI        : 飞书 AI 报告生成 (趋势洞察/决策摘要)
    - FeishuWiki      : 知识库检索 (爆品案例库/IP 联名知识库)
    - Templates       : 消息卡片模板 (build_decision_card 等)
"""

__version__ = "0.2.0"

from feishu.ai import FeishuAI
from feishu.bitable import FeishuBitable
from feishu.bot import FeishuBot
from feishu.client import FeishuClient
from feishu.wiki import FeishuWiki

__all__ = [
    "FeishuClient",
    "FeishuBitable",
    "FeishuBot",
    "FeishuAI",
    "FeishuWiki",
]

# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 飞书多维表格 (Task 13)
# ==============================================================================
# 对应 spec §2.2 飞书生态集成层:
#   - 飞书多维表格 (Bitable) 作为数据底座
#   - Top 100 打版池管理: 字段定义 + 建表 + 批量插入记录
#   - 趋势信号存储 / 创意卡看板 / 验证结果追踪
#
# 本模块提供:
#   1. FeishuBitable - 多维表格操作封装
#      * define_top100_fields() : Top 100 打版池字段定义
#      * create_table()         : 创建数据表
#      * insert_records()       : 批量插入记录
#
# 字段定义对齐 spec §4.4 ProductIdeaCard 核心字段:
#   conceptId / productName / category / hitScore / ipMatch /
#   zGenMatchScore / regionFit / status / designDesc / sellingPoints
# ==============================================================================

"""
飞书多维表格模块。

核心组件:
    - FeishuBitable : 多维表格操作封装
        * define_top100_fields() : Top 100 打版池字段定义 (10 字段)
        * create_table()         : 创建数据表
        * insert_records()       : 批量插入记录

设计说明:
    - 字段定义对齐 spec §4.4 ProductIdeaCard 核心字段
    - demo 模式下 create_table / insert_records 返回 mock 响应
    - 真实模式下通过 FeishuClient.request() 调用飞书 API

飞书多维表格 API:
    - 创建表: POST /bitable/v1/apps/{app_token}/tables
    - 插入记录: POST /bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create

用法示例::

    client = FeishuClient()
    bitable = FeishuBitable(client)

    fields = bitable.define_top100_fields()
    table = await bitable.create_table("appXXX", "Top100打版池", fields)
    result = await bitable.insert_records("appXXX", table["table_id"], records)
"""

from __future__ import annotations

from typing import Any, Dict, List

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]

from feishu.client import FeishuClient


# ==============================================================================
# 飞书多维表格字段类型常量
# ==============================================================================

# 飞书多维表格字段类型 (type 值)
FIELD_TYPE_TEXT: int = 1
"""多行文本"""

FIELD_TYPE_NUMBER: int = 2
"""数字"""

FIELD_TYPE_SINGLE_SELECT: int = 3
"""单选"""

FIELD_TYPE_MULTI_SELECT: int = 4
"""多选"""

FIELD_TYPE_DATE: int = 5
"""日期"""


# ==============================================================================
# FeishuBitable - 多维表格操作封装
# ==============================================================================


class FeishuBitable:
    """飞书多维表格操作封装。

    提供 Top 100 打版池的字段定义、建表与批量插入记录能力。
    依赖 FeishuClient 进行 API 认证与请求。

    用法::

        client = FeishuClient()
        bitable = FeishuBitable(client)

        fields = bitable.define_top100_fields()
        table = await bitable.create_table("appXXX", "Top100打版池", fields)
        await bitable.insert_records("appXXX", table["table_id"], records)
    """

    def __init__(self, client: FeishuClient) -> None:
        """初始化多维表格操作器。

        参数:
            client : FeishuClient 实例 (提供 API 认证与请求能力)
        """
        self.client: FeishuClient = client

    # ==================================================================
    # Top 100 打版池字段定义
    # ==================================================================

    def define_top100_fields(self) -> List[Dict[str, Any]]:
        """定义 Top 100 打版池的多维表格字段。

        字段对齐 spec §4.4 ProductIdeaCard 核心字段, 共 10 个字段:
            1. conceptId       - 创意 ID (多行文本, 主键)
            2. productName     - 产品名称 (多行文本)
            3. category        - 品类 (多行文本)
            4. hitScore        - 爆品概率 (数字, 0-1)
            5. ipMatch         - IP 匹配信息 (多行文本)
            6. zGenMatchScore  - Z 世代匹配度 (数字, 0-1)
            7. regionFit       - 区域适配度 (多行文本)
            8. status          - 打版状态 (单选: 待评审/已通过/已打样/已验证)
            9. designDesc      - 设计描述 (多行文本)
            10. sellingPoints  - 核心卖点 (多行文本)

        返回:
            字段定义列表, 每个元素为 {"field_name": str, "type": int} 字典
        """
        return [
            {
                "field_name": "conceptId",
                "type": FIELD_TYPE_TEXT,
                "description": "创意 ID, 如 CPT-2025-0001",
            },
            {
                "field_name": "productName",
                "type": FIELD_TYPE_TEXT,
                "description": "产品名称",
            },
            {
                "field_name": "category",
                "type": FIELD_TYPE_TEXT,
                "description": "品类, 如 家居/香氛",
            },
            {
                "field_name": "hitScore",
                "type": FIELD_TYPE_NUMBER,
                "description": "爆品概率 0-1",
            },
            {
                "field_name": "ipMatch",
                "type": FIELD_TYPE_TEXT,
                "description": "IP 联名匹配信息 (IP名称 + 匹配度)",
            },
            {
                "field_name": "zGenMatchScore",
                "type": FIELD_TYPE_NUMBER,
                "description": "Z 世代匹配度 0-1",
            },
            {
                "field_name": "regionFit",
                "type": FIELD_TYPE_TEXT,
                "description": "区域适配度, 如 china:high,sea:medium",
            },
            {
                "field_name": "status",
                "type": FIELD_TYPE_SINGLE_SELECT,
                "property": {
                    "options": [
                        {"name": "待评审"},
                        {"name": "已通过"},
                        {"name": "已打样"},
                        {"name": "已验证"},
                    ]
                },
                "description": "打版状态",
            },
            {
                "field_name": "designDesc",
                "type": FIELD_TYPE_TEXT,
                "description": "设计描述",
            },
            {
                "field_name": "sellingPoints",
                "type": FIELD_TYPE_TEXT,
                "description": "核心卖点 (分号分隔)",
            },
        ]

    # ==================================================================
    # 创建数据表
    # ==================================================================

    async def create_table(
        self,
        app_token: str,
        name: str,
        fields: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """在多维表格中创建数据表。

        POST /bitable/v1/apps/{app_token}/tables
        Body: {"table": {"name": "...", "default_view_name": "...", "fields": [...]}}

        参数:
            app_token : 多维表格 App Token
            name      : 表名称 (如 "Top100打版池")
            fields    : 字段定义列表 (由 define_top100_fields() 生成)

        返回:
            创建结果字典, 含 table_id:
            {"code": 0, "data": {"table_id": "tblXXX"}, ...}

        说明:
            - demo 模式返回 mock table_id
            - 真实模式通过飞书 API 创建
        """
        path = f"/bitable/v1/apps/{app_token}/tables"
        payload: Dict[str, Any] = {
            "table": {
                "name": name,
                "default_view_name": "默认视图",
                "fields": fields,
            }
        }

        result = await self.client.request("POST", path, json=payload)

        # 归一化: 将 data.table_id 提取到顶层, 方便调用方访问
        # (飞书 API 返回 {data: {table_id: ...}}, 此处扁平化为顶层 table_id)
        if "data" in result and isinstance(result["data"], dict):
            if "table_id" in result["data"]:
                result["table_id"] = result["data"]["table_id"]
                logger.info(
                    f"FeishuBitable: 创建表 '{name}' 成功, "
                    f"table_id={result['table_id']}"
                )
            elif self.client.is_demo_mode:
                logger.info(f"FeishuBitable [demo]: 创建表 '{name}' (mock)")
        elif self.client.is_demo_mode:
            logger.info(f"FeishuBitable [demo]: 创建表 '{name}' (mock)")

        return result

    # ==================================================================
    # 批量插入记录
    # ==================================================================

    async def insert_records(
        self,
        app_token: str,
        table_id: str,
        records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """向多维表格批量插入记录。

        POST /bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create
        Body: {"records": [{"fields": {...}}, ...]}

        参数:
            app_token : 多维表格 App Token
            table_id  : 数据表 ID
            records   : 记录列表, 每个元素为字段值字典
                        (如 {"conceptId": "CPT-001", "productName": "..."})

        返回:
            插入结果字典, 含 record_id 列表:
            {"code": 0, "data": {"records": [{"record_id": "recXXX"}, ...]}, ...}

        说明:
            - 空记录列表时直接返回成功 (不调用 API)
            - demo 模式返回 mock record_id 列表
            - 真实模式通过飞书 API 批量插入
        """
        # 空记录直接返回
        if not records:
            logger.info("FeishuBitable: 空记录列表, 跳过插入")
            return {
                "code": 0,
                "msg": "success (no records)",
                "data": {"records": []},
                "demo": self.client.is_demo_mode,
            }

        path = (
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
        )
        # 飞书要求每条记录包裹在 {"fields": {...}} 中
        payload: Dict[str, Any] = {
            "records": [{"fields": record} for record in records]
        }

        result = await self.client.request("POST", path, json=payload)

        if self.client.is_demo_mode:
            logger.info(
                f"FeishuBitable [demo]: 插入 {len(records)} 条记录 (mock)"
            )
        else:
            logger.info(
                f"FeishuBitable: 插入 {len(records)} 条记录到表 {table_id}"
            )

        return result


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["FeishuBitable"]

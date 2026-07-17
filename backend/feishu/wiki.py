# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 飞书知识库 (Task 13)
# ==============================================================================
# 对应 spec §2.2 飞书生态集成层:
#   - 飞书知识库 (Wiki) 作为爆品 RAG 数据源
#   - 健身爆品案例库: 搜索历史爆品案例
#   - IP 联名知识库: 查询 IP 匹配信息
#   - 品类知识库: 品类趋势与最佳实践
#
# 本模块提供:
#   1. FeishuWiki - 飞书知识库检索
#      * search_cases()        : 搜索历史爆品案例库
#      * search_ip_knowledge() : 搜索 IP 联名知识库
#
# 设计说明:
#   - demo 模式: 返回预置的 mock 案例数据 (含真实品类/IP/爆品信息)
#   - 真实模式: 通过飞书 Wiki API 检索知识库节点内容
#   - 检索结果用于 IdeaForge 决策推理的 RAG 上下文增强
# ==============================================================================

"""
飞书知识库模块。

核心组件:
    - FeishuWiki : 飞书知识库检索
        * search_cases()        : 搜索历史爆品案例库
        * search_ip_knowledge() : 搜索 IP 联名知识库

设计说明:
    - demo 模式: 返回预置 mock 数据 (含真实品类/IP/爆品信息)
    - 真实模式: 通过飞书 Wiki API 检索知识库节点
    - 检索结果用于 IdeaForge 决策推理的 RAG 上下文增强

飞书知识库 API:
    - 搜索知识库节点: POST /wiki/v2/spaces/search
    - 获取节点内容: GET /wiki/v2/spaces/get_node

用法示例::

    client = FeishuClient()
    wiki = FeishuWiki(client)

    cases = await wiki.search_cases(query="香薰蜡烛", category="家居/香氛")
    ip_info = await wiki.search_ip_knowledge(ip_name="三丽鸥·库洛米")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]

from feishu.client import FeishuClient


# ==============================================================================
# demo 模式预置案例数据
# ==============================================================================

_DEMO_CASES: List[Dict[str, Any]] = [
    {
        "case_name": "侘寂风大豆蜡香薰蜡烛",
        "category": "家居/香氛",
        "hit_score": 0.92,
        "launch_date": "2024-09",
        "sales_volume": 120000,
        "ip_collab": "无 (原创设计)",
        "region": "china",
        "key_success_factors": ["侘寂美学趋势", "Z世代疗愈需求", "天然材质"],
        "price_range": "49-79",
        "summary": "融合侘寂美学的大豆蜡香薰蜡烛, 凭借天然材质和疗愈定位, "
        "在 Z 世代群体中实现 12 万件销量。",
    },
    {
        "case_name": "三丽鸥联名库洛米护手霜",
        "category": "美妆/个护",
        "hit_score": 0.88,
        "launch_date": "2024-07",
        "sales_volume": 85000,
        "ip_collab": "三丽鸥·库洛米",
        "region": "china",
        "key_success_factors": ["IP热度高", "包装设计精美", "季节性需求"],
        "price_range": "29-49",
        "summary": "三丽鸥库洛米IP联名护手霜, 凭借精美包装和IP势能, "
        "夏季上市后快速成为爆款。",
    },
    {
        "case_name": "Y2K千禧风金属发夹套装",
        "category": "服饰/穿搭",
        "hit_score": 0.85,
        "launch_date": "2024-08",
        "sales_volume": 65000,
        "ip_collab": "无 (趋势驱动)",
        "region": "sea",
        "key_success_factors": ["Y2K复兴趋势", "社交媒体传播", "低价高频"],
        "price_range": "19-39",
        "summary": "Y2K千禧风金属发夹套装, 抓住复古潮流趋势, "
        "在东南亚市场通过社交媒体传播成为爆款。",
    },
    {
        "case_name": "迪士尼联名玲娜贝儿毛绒挂件",
        "category": "玩具/文创",
        "hit_score": 0.95,
        "launch_date": "2024-06",
        "sales_volume": 200000,
        "ip_collab": "迪士尼·玲娜贝儿",
        "region": "china",
        "key_success_factors": ["顶流IP", "情感共鸣", "社交货币属性"],
        "price_range": "39-69",
        "summary": "迪士尼玲娜贝儿IP联名毛绒挂件, 凭借顶流IP势能和强社交属性, "
        "销量突破 20 万件。",
    },
    {
        "case_name": "多巴胺配色硅胶手环",
        "category": "服饰/穿搭",
        "hit_score": 0.78,
        "launch_date": "2024-05",
        "sales_volume": 45000,
        "ip_collab": "无 (趋势驱动)",
        "region": "us",
        "key_success_factors": ["多巴胺配色趋势", "低成本高颜值", "Z世代社交分享"],
        "price_range": "15-25",
        "summary": "多巴胺配色硅胶手环, 抓住色彩心理学趋势, "
        "在美国 Z 世代市场通过 TikTok 传播走红。",
    },
]

_DEMO_IP_KNOWLEDGE: Dict[str, Dict[str, Any]] = {
    "三丽鸥·库洛米": {
        "ip_name": "三丽鸥·库洛米",
        "ip_power_score": 88,
        "availability": "available",
        "exclusive_until": None,
        "recommended_categories": ["美妆/个护", "家居/香氛", "玩具/文创", "服饰/穿搭"],
        "region_heat_map": {"china": 92, "sea": 78, "us": 65, "eu": 45},
        "target_audience": {
            "ageRange": "15-25",
            "aesthetic": "暗黑可爱 / Y2K",
            "spendingPower": "中低",
        },
        "collab_history": [
            {"brand": "名创优品", "product": "库洛米护手霜", "year": 2024, "sales": 85000},
            {"brand": "名创优品", "product": "库洛米笔记本", "year": 2023, "sales": 60000},
        ],
        "best_practice": "库洛米IP适合暗黑可爱风格产品, 包装以紫黑配色为主, "
        "价格带 29-79 元, Z 世代女性为主要客群。",
    },
    "迪士尼·玲娜贝儿": {
        "ip_name": "迪士尼·玲娜贝儿",
        "ip_power_score": 95,
        "availability": "exclusive",
        "exclusive_until": "2025-12-31",
        "recommended_categories": ["玩具/文创", "服饰/穿搭", "家居/装饰"],
        "region_heat_map": {"china": 98, "sea": 80, "us": 70, "eu": 50},
        "target_audience": {
            "ageRange": "12-30",
            "aesthetic": "可爱 / 治愈",
            "spendingPower": "中",
        },
        "collab_history": [
            {"brand": "名创优品", "product": "玲娜贝儿毛绒挂件", "year": 2024, "sales": 200000},
        ],
        "best_practice": "玲娜贝儿为顶流IP, 适合毛绒/文创类产品, "
        "情感共鸣和社交货币属性是核心驱动力, 价格带 39-99 元。",
    },
    "泡泡玛特·SKULLPANDA": {
        "ip_name": "泡泡玛特·SKULLPANDA",
        "ip_power_score": 82,
        "availability": "available",
        "exclusive_until": None,
        "recommended_categories": ["玩具/文创", "服饰/穿搭"],
        "region_heat_map": {"china": 85, "sea": 60, "us": 45, "eu": 30},
        "target_audience": {
            "ageRange": "18-30",
            "aesthetic": "潮酷 / 暗黑",
            "spendingPower": "中高",
        },
        "collab_history": [],
        "best_practice": "SKULLPANDA适合潮酷风格盲盒和文创周边, "
        "以暗黑美学为核心, 价格带 59-199 元。",
    },
}


# ==============================================================================
# FeishuWiki - 飞书知识库检索
# ==============================================================================


class FeishuWiki:
    """飞书知识库检索。

    提供爆品案例库与 IP 联名知识库的检索能力,
    检索结果用于 IdeaForge 决策推理的 RAG 上下文增强。

    用法::

        client = FeishuClient()
        wiki = FeishuWiki(client)

        cases = await wiki.search_cases(query="香薰蜡烛", category="家居/香氛")
        ip_info = await wiki.search_ip_knowledge(ip_name="三丽鸥·库洛米")
    """

    def __init__(self, client: FeishuClient) -> None:
        """初始化飞书知识库检索器。

        参数:
            client : FeishuClient 实例 (提供 API 认证与请求能力)
        """
        self.client: FeishuClient = client

    # ==================================================================
    # 搜索历史爆品案例
    # ==================================================================

    async def search_cases(
        self,
        query: str,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """搜索历史爆品案例库。

        参数:
            query    : 搜索关键词 (如 "香薰蜡烛", "IP联名")
            category : 可选品类过滤 (如 "家居/香氛", "美妆/个护")

        返回:
            案例列表, 每个元素为案例字典, 含:
            - case_name          : 案例名称
            - category           : 品类
            - hit_score          : 爆品分数
            - launch_date        : 上市日期
            - sales_volume       : 销量
            - ip_collab          : IP 联名信息
            - region             : 区域
            - key_success_factors: 成功因素
            - price_range        : 价格区间
            - summary            : 案例摘要

        说明:
            - demo 模式: 从预置案例库中检索 (支持关键词 + 品类过滤)
            - 真实模式: 通过飞书 Wiki API 检索知识库节点
            - 空查询时返回全部案例
        """
        # --- demo 模式: 本地检索 ---
        if self.client.is_demo_mode:
            return self._demo_search_cases(query, category)

        # --- 真实模式: 飞书 Wiki API ---
        payload: Dict[str, Any] = {
            "query": query,
            "space_type": "case_library",
            "page_size": 20,
        }
        if category:
            payload["filters"] = {"category": category}

        result = await self.client.request(
            "POST",
            "/wiki/v2/spaces/search",
            json=payload,
        )

        # 提取案例列表
        if "data" in result and "items" in result["data"]:
            return result["data"]["items"]
        return []

    def _demo_search_cases(
        self,
        query: str,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """demo 模式下从预置案例库检索。

        参数:
            query    : 搜索关键词
            category : 品类过滤

        返回:
            匹配的案例列表
        """
        results: List[Dict[str, Any]] = []

        for case in _DEMO_CASES:
            # 品类过滤
            if category and case.get("category") != category:
                continue

            # 关键词匹配 (空查询返回全部)
            if not query:
                results.append(case)
                continue

            # 在多个字段中搜索关键词
            searchable_text = " ".join(
                str(v)
                for v in case.values()
                if isinstance(v, (str, int, float))
            )
            if query.lower() in searchable_text.lower():
                results.append(case)

        logger.info(
            f"FeishuWiki [demo]: 搜索案例 '{query}' "
            f"(category={category}), 匹配 {len(results)} 条"
        )
        return results

    # ==================================================================
    # 搜索 IP 联名知识库
    # ==================================================================

    async def search_ip_knowledge(self, ip_name: str) -> Dict[str, Any]:
        """搜索 IP 联名知识库。

        参数:
            ip_name : IP 名称 (如 "三丽鸥·库洛米")

        返回:
            IP 知识字典, 含:
            - ip_name              : IP 名称
            - ip_power_score       : IP 势能分
            - availability         : 可用性状态
            - exclusive_until      : 独家期截止
            - recommended_categories: 推荐品类
            - region_heat_map      : 区域热度分布
            - target_audience      : 目标受众
            - collab_history       : 历史合作记录
            - best_practice        : 最佳实践建议

        说明:
            - demo 模式: 从预置 IP 知识库中检索
            - 真实模式: 通过飞书 Wiki API 检索
            - 未找到时返回默认空结构 (不报错)
        """
        # --- demo 模式: 本地检索 ---
        if self.client.is_demo_mode:
            return self._demo_search_ip(ip_name)

        # --- 真实模式: 飞书 Wiki API ---
        payload: Dict[str, Any] = {
            "query": ip_name,
            "space_type": "ip_knowledge_base",
            "page_size": 5,
        }

        result = await self.client.request(
            "POST",
            "/wiki/v2/spaces/search",
            json=payload,
        )

        # 提取 IP 知识
        if "data" in result and "items" in result["data"] and result["data"]["items"]:
            return result["data"]["items"][0]
        return self._default_ip_result(ip_name)

    def _demo_search_ip(self, ip_name: str) -> Dict[str, Any]:
        """demo 模式下从预置 IP 知识库检索。

        参数:
            ip_name : IP 名称

        返回:
            IP 知识字典
        """
        # 精确匹配
        if ip_name in _DEMO_IP_KNOWLEDGE:
            logger.info(
                f"FeishuWiki [demo]: IP 知识检索 '{ip_name}' 命中"
            )
            return _DEMO_IP_KNOWLEDGE[ip_name]

        # 模糊匹配 (IP 名称中包含搜索词)
        for key, value in _DEMO_IP_KNOWLEDGE.items():
            if ip_name and ip_name.lower() in key.lower():
                logger.info(
                    f"FeishuWiki [demo]: IP 知识检索 '{ip_name}' "
                    f"模糊匹配 '{key}'"
                )
                return value

        # 未找到: 返回默认结构
        logger.info(
            f"FeishuWiki [demo]: IP 知识检索 '{ip_name}' 未命中, "
            f"返回默认结构"
        )
        return self._default_ip_result(ip_name)

    @staticmethod
    def _default_ip_result(ip_name: str) -> Dict[str, Any]:
        """生成默认 IP 知识结果 (未找到时)。

        参数:
            ip_name : IP 名称

        返回:
            默认 IP 知识字典
        """
        return {
            "ip_name": ip_name or "未知IP",
            "ip_power_score": 0,
            "availability": "unknown",
            "exclusive_until": None,
            "recommended_categories": [],
            "region_heat_map": {},
            "target_audience": {},
            "collab_history": [],
            "best_practice": "暂无该 IP 的历史合作数据, 建议进一步调研 IP 势能与品类匹配度。",
        }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["FeishuWiki"]

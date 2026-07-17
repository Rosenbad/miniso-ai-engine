# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 飞书 AI (Task 13)
# ==============================================================================
# 对应 spec §2.2 飞书生态集成层:
#   - 飞书 AI (Lark AI) 用于报告生成
#   - 趋势洞察报告自动生成
#   - 决策摘要文档输出
#
# 本模块提供:
#   1. FeishuAI - 飞书 AI 报告生成
#      * generate_trend_report()    : 调用飞书 AI 生成趋势洞察报告
#      * generate_decision_summary(): 生成决策摘要文档
#
# 设计说明:
#   - demo 模式: 基于趋势数据/创意卡片本地生成结构化报告文本
#   - 真实模式: 通过飞书 AI API (需开放对应权限) 生成自然语言报告
#   - 报告内容对齐 spec §3.4 TrendSignal + §4.4 ProductIdeaCard
# ==============================================================================

"""
飞书 AI 模块。

核心组件:
    - FeishuAI : 飞书 AI 报告生成
        * generate_trend_report()    : 趋势洞察报告生成
        * generate_decision_summary(): 决策摘要文档生成

设计说明:
    - demo 模式: 基于输入数据本地生成结构化报告 (Markdown 格式)
    - 真实模式: 通过飞书 AI API 生成自然语言报告
    - 报告内容覆盖趋势热度/生命周期/Z世代标签/跨区域差异等维度

用法示例::

    client = FeishuClient()
    ai = FeishuAI(client)

    report = await ai.generate_trend_report(trend_data)
    summary = await ai.generate_decision_summary(idea_cards)
"""

from __future__ import annotations

from typing import Any, Dict, List, Union

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]

from feishu.client import FeishuClient


# ==============================================================================
# 生命周期中文映射
# ==============================================================================

_LIFECYCLE_MAP: Dict[str, str] = {
    "rising": "上升期",
    "peak": "峰值期",
    "declining": "衰退期",
}

_REGION_MAP: Dict[str, str] = {
    "china": "中国",
    "sea": "东南亚",
    "us": "美国",
    "eu": "欧洲",
    "global": "全球",
}


# ==============================================================================
# FeishuAI - 飞书 AI 报告生成
# ==============================================================================


class FeishuAI:
    """飞书 AI 报告生成。

    提供趋势洞察报告与决策摘要文档的自动生成能力。
    demo 模式下基于输入数据本地生成结构化报告。

    用法::

        client = FeishuClient()
        ai = FeishuAI(client)

        report = await ai.generate_trend_report(trend_data)
        summary = await ai.generate_decision_summary(idea_cards)
    """

    def __init__(self, client: FeishuClient) -> None:
        """初始化飞书 AI 报告生成器。

        参数:
            client : FeishuClient 实例 (提供 API 认证与请求能力)
        """
        self.client: FeishuClient = client

    # ==================================================================
    # 趋势洞察报告生成
    # ==================================================================

    async def generate_trend_report(self, trend_data: Dict[str, Any]) -> str:
        """生成趋势洞察报告。

        报告内容覆盖:
            - 趋势话题与品类
            - 热度分与增长率
            - 生命周期阶段
            - Z 世代审美标签
            - 预测窗口期
            - 跨区域热度差异
            - 关联关键词
            - 行动建议

        参数:
            trend_data : 趋势数据字典 (含 topic / heatScore / growthRate /
                         lifecycle / zGenTags / predictWindow / crossRegionDiff 等)

        返回:
            报告文本字符串 (Markdown 格式)

        说明:
            - demo 模式: 基于数据本地生成结构化报告
            - 真实模式: 通过飞书 AI API 生成 (需配置对应权限)
            - 空数据时返回默认提示文本 (优雅降级)
        """
        # --- demo 模式: 本地生成 ---
        if self.client.is_demo_mode:
            return self._demo_trend_report(trend_data)

        # --- 真实模式: 调用飞书 AI API ---
        # 飞书 AI API 需要开放对应权限, 此处为结构化请求
        prompt = self._build_trend_prompt(trend_data)
        payload: Dict[str, Any] = {
            "model": "feishu-ai-v1",
            "prompt": prompt,
            "max_tokens": 2000,
        }

        result = await self.client.request(
            "POST",
            "/ai/v1/text/generate",
            json=payload,
        )

        # 提取 AI 生成的文本
        if "data" in result and "text" in result["data"]:
            return result["data"]["text"]
        elif "text" in result:
            return result["text"]
        else:
            # 降级: 使用本地生成
            logger.warning("FeishuAI: 飞书 AI 响应格式异常, 降级为本地生成")
            return self._demo_trend_report(trend_data)

    def _demo_trend_report(self, trend_data: Dict[str, Any]) -> str:
        """demo 模式下本地生成趋势洞察报告。

        参数:
            trend_data : 趋势数据字典

        返回:
            Markdown 格式的趋势报告文本
        """
        if not trend_data:
            return (
                "# 趋势洞察报告\n\n"
                "暂无趋势数据, 无法生成报告。\n\n"
                "请提供完整的趋势信号数据后重试。"
            )

        topic = trend_data.get("topic", "未知趋势")
        heat_score = trend_data.get("heatScore", 0)
        growth_rate = trend_data.get("growthRate", 0)
        category = trend_data.get("category", "未知品类")
        lifecycle = trend_data.get("lifecycle", "unknown")
        sentiment = trend_data.get("sentiment", 0)
        predict_window = trend_data.get("predictWindow", "未知")
        z_gen_tags = trend_data.get("zGenTags", [])
        related_keywords = trend_data.get("relatedKeywords", [])
        cross_region_diff = trend_data.get("crossRegionDiff", {})
        region = trend_data.get("region", "global")
        source_breakdown = trend_data.get("sourceBreakdown", {})

        lifecycle_cn = _LIFECYCLE_MAP.get(lifecycle, lifecycle)
        region_cn = _REGION_MAP.get(region, region)

        # 格式化数值
        heat_str = (
            f"{heat_score:.1f}" if isinstance(heat_score, (int, float)) else str(heat_score)
        )
        growth_str = (
            f"+{growth_rate:.1f}%"
            if isinstance(growth_rate, (int, float))
            else str(growth_rate)
        )
        sentiment_str = (
            f"{sentiment:.2f}" if isinstance(sentiment, (int, float)) else str(sentiment)
        )

        lines: List[str] = []
        lines.append(f"# 趋势洞察报告: {topic}")
        lines.append("")
        lines.append("## 一、趋势概览")
        lines.append(f"- **话题**: {topic}")
        lines.append(f"- **品类**: {category}")
        lines.append(f"- **区域**: {region_cn}")
        lines.append(f"- **热度分**: {heat_str} / 100")
        lines.append(f"- **周环比增长**: {growth_str}")
        lines.append(f"- **情感倾向**: {sentiment_str} (-1~1)")
        lines.append("")

        lines.append("## 二、生命周期分析")
        lines.append(f"- **当前阶段**: {lifecycle_cn}")
        lines.append(f"- **预测窗口期**: {predict_window}")
        if lifecycle == "rising":
            lines.append("- **建议**: 趋势处于上升期, 建议尽快布局产品开发, 把握窗口期。")
        elif lifecycle == "peak":
            lines.append("- **建议**: 趋势处于峰值期, 市场竞争激烈, 建议差异化定位。")
        elif lifecycle == "declining":
            lines.append("- **建议**: 趋势处于衰退期, 建议谨慎投入, 关注新兴替代趋势。")
        lines.append("")

        if z_gen_tags:
            lines.append("## 三、Z 世代审美标签")
            lines.append(f"- {' / '.join(z_gen_tags)}")
            lines.append("")

        if related_keywords:
            lines.append("## 四、关联关键词")
            lines.append(f"- {' / '.join(related_keywords)}")
            lines.append("")

        if cross_region_diff:
            lines.append("## 五、跨区域热度差异")
            for r, status in cross_region_diff.items():
                r_cn = _REGION_MAP.get(r, r)
                lines.append(f"- {r_cn}: {status}")
            lines.append("")

        if source_breakdown:
            lines.append("## 六、数据来源分布")
            for source, count in source_breakdown.items():
                lines.append(f"- {source}: {count}")
            lines.append("")

        lines.append("## 七、行动建议")
        lines.append(f"1. 围绕「{topic}」趋势, 在「{category}」品类开发 3-5 个创意方案")
        lines.append("2. 优先匹配 Z 世代审美偏好, 强化产品视觉吸引力")
        if cross_region_diff:
            lines.append("3. 根据跨区域差异, 制定差异化区域推广策略")
        lines.append("4. 在预测窗口期内完成打样验证, 快速迭代")

        return "\n".join(lines)

    def _build_trend_prompt(self, trend_data: Dict[str, Any]) -> str:
        """构建飞书 AI 趋势报告生成 prompt (真实模式)。

        参数:
            trend_data : 趋势数据字典

        返回:
            prompt 字符串
        """
        topic = trend_data.get("topic", "未知趋势")
        heat_score = trend_data.get("heatScore", 0)
        lifecycle = trend_data.get("lifecycle", "unknown")
        z_gen_tags = trend_data.get("zGenTags", [])

        return (
            f"请基于以下趋势数据生成一份趋势洞察报告:\n"
            f"话题: {topic}\n"
            f"热度分: {heat_score}\n"
            f"生命周期: {lifecycle}\n"
            f"Z世代标签: {', '.join(z_gen_tags)}\n"
            f"报告需包含: 趋势概览、生命周期分析、Z世代偏好、行动建议。"
        )

    # ==================================================================
    # 决策摘要文档生成
    # ==================================================================

    async def generate_decision_summary(
        self,
        idea_cards: List[Union[Dict[str, Any], Any]],
    ) -> str:
        """生成决策摘要文档。

        摘要内容覆盖:
            - Top N 创意概览
            - 每个创意的核心信息 (产品名/品类/爆品概率/IP匹配/Z世代匹配度)
            - 品类分布统计
            - IP 联名推荐
            - 整体决策建议

        参数:
            idea_cards : ProductIdeaCard 列表 (或 dict 列表)

        返回:
            决策摘要文本字符串 (Markdown 格式)

        说明:
            - demo 模式: 基于数据本地生成结构化摘要
            - 真实模式: 通过飞书 AI API 生成
            - 空列表时返回默认提示文本 (优雅降级)
            - 兼容 ProductIdeaCard 实例和 dict 格式
        """
        # --- demo 模式: 本地生成 ---
        if self.client.is_demo_mode:
            return self._demo_decision_summary(idea_cards)

        # --- 真实模式: 调用飞书 AI API ---
        prompt = self._build_decision_prompt(idea_cards)
        payload: Dict[str, Any] = {
            "model": "feishu-ai-v1",
            "prompt": prompt,
            "max_tokens": 2000,
        }

        result = await self.client.request(
            "POST",
            "/ai/v1/text/generate",
            json=payload,
        )

        if "data" in result and "text" in result["data"]:
            return result["data"]["text"]
        elif "text" in result:
            return result["text"]
        else:
            logger.warning("FeishuAI: 飞书 AI 响应格式异常, 降级为本地生成")
            return self._demo_decision_summary(idea_cards)

    def _demo_decision_summary(
        self,
        idea_cards: List[Union[Dict[str, Any], Any]],
    ) -> str:
        """demo 模式下本地生成决策摘要文档。

        参数:
            idea_cards : 创意卡片列表 (ProductIdeaCard 实例或 dict)

        返回:
            Markdown 格式的决策摘要文本
        """
        if not idea_cards:
            return (
                "# 决策摘要文档\n\n"
                "暂无创意卡片数据, 无法生成决策摘要。\n\n"
                "请运行 IdeaForge 创意生成流程后重试。"
            )

        lines: List[str] = []
        lines.append("# Top 100 决策摘要文档")
        lines.append("")
        lines.append(f"**创意总数**: {len(idea_cards)}")
        lines.append("")

        lines.append("## 一、Top 5 创意概览")
        top5 = idea_cards[:5]
        for i, card in enumerate(top5, 1):
            product_name = self._get_field(card, "productName", "未命名")
            concept_id = self._get_field(card, "conceptId", "N/A")
            category = self._get_field(card, "category", "未知品类")
            hit_score = self._get_field(card, "hitScore", 0)
            z_gen_score = self._get_field(card, "zGenMatchScore", 0)
            price_range = self._get_field(card, "priceRange", "N/A")
            ip_match = self._get_field(card, "ipMatch", None)

            ip_name = ""
            if ip_match is not None:
                if isinstance(ip_match, dict):
                    ip_name = ip_match.get("ipName", "")
                elif hasattr(ip_match, "ipName"):
                    ip_name = ip_match.ipName

            hit_pct = (
                f"{hit_score * 100:.1f}%"
                if isinstance(hit_score, (int, float))
                else "N/A"
            )
            zgen_pct = (
                f"{z_gen_score * 100:.1f}%"
                if isinstance(z_gen_score, (int, float))
                else "N/A"
            )

            lines.append(f"### {i}. {product_name} ({concept_id})")
            lines.append(f"- **品类**: {category}")
            lines.append(f"- **爆品概率**: {hit_pct}")
            lines.append(f"- **Z 世代匹配度**: {zgen_pct}")
            lines.append(f"- **价格区间**: {price_range}")
            if ip_name:
                lines.append(f"- **IP 联名**: {ip_name}")
            lines.append("")

        # 品类分布统计
        category_counts: Dict[str, int] = {}
        for card in idea_cards:
            cat = self._get_field(card, "category", "未知")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        if category_counts:
            lines.append("## 二、品类分布")
            for cat, count in sorted(
                category_counts.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"- {cat}: {count} 个创意")
            lines.append("")

        # IP 联名统计
        ip_names: List[str] = []
        for card in idea_cards:
            ip_match = self._get_field(card, "ipMatch", None)
            if ip_match is not None:
                if isinstance(ip_match, dict):
                    name = ip_match.get("ipName", "")
                elif hasattr(ip_match, "ipName"):
                    name = ip_match.ipName
                else:
                    name = ""
                if name and name not in ip_names:
                    ip_names.append(name)

        if ip_names:
            lines.append("## 三、IP 联名推荐")
            for name in ip_names[:5]:
                lines.append(f"- {name}")
            lines.append("")

        lines.append("## 四、决策建议")
        lines.append("1. 优先打样 Top 3 创意, 验证市场反馈")
        lines.append("2. 关注高 Z 世代匹配度的创意, 匹配品牌年轻化战略")
        lines.append("3. IP 联名创意建议优先排期, 把握 IP 热度窗口")
        lines.append("4. 跨品类布局, 分散风险并探索增长机会")

        return "\n".join(lines)

    def _build_decision_prompt(
        self,
        idea_cards: List[Union[Dict[str, Any], Any]],
    ) -> str:
        """构建飞书 AI 决策摘要生成 prompt (真实模式)。

        参数:
            idea_cards : 创意卡片列表

        返回:
            prompt 字符串
        """
        card_summaries: List[str] = []
        for card in idea_cards[:5]:
            name = self._get_field(card, "productName", "未命名")
            hit = self._get_field(card, "hitScore", 0)
            card_summaries.append(f"- {name} (爆品概率: {hit})")

        return (
            f"请基于以下 {len(idea_cards)} 个产品创意生成决策摘要:\n"
            + "\n".join(card_summaries)
            + "\n摘要需包含: 创意概览、品类分布、IP推荐、决策建议。"
        )

    # ==================================================================
    # 辅助方法
    # ==================================================================

    @staticmethod
    def _get_field(
        card: Union[Dict[str, Any], Any],
        field: str,
        default: Any = "",
    ) -> Any:
        """从卡片数据中安全获取字段值。

        兼容 ProductIdeaCard 实例和 dict。

        参数:
            card    : 卡片数据 (ProductIdeaCard 实例或 dict)
            field   : 字段名
            default : 默认值

        返回:
            字段值
        """
        if isinstance(card, dict):
            return card.get(field, default)
        if hasattr(card, "model_dump"):
            return card.model_dump().get(field, default)
        return getattr(card, field, default)


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["FeishuAI"]

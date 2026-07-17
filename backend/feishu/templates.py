# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 飞书消息卡片模板 (Task 13)
# ==============================================================================
# 对应 spec §2.2 飞书生态集成层:
#   - 飞书机器人 (Bot) 决策卡片推送
#   - 三种核心卡片模板:
#     1. build_decision_card          - Top 100 打版池就绪通知
#     2. build_trend_report_card      - 趋势洞察报告
#     3. build_validation_result_card - 验证结果播报
#
# 飞书 interactive 消息卡片格式:
#   {
#       "config": {"wide_screen_mode": true},
#       "header": {
#           "title": {"tag": "plain_text", "content": "标题"},
#           "template": "blue"  # blue/green/orange/red/grey/...
#       },
#       "elements": [
#           {"tag": "div", "text": {"tag": "lark_md", "content": "**内容**"}},
#           {"tag": "action", "actions": [
#               {"tag": "button", "text": {...}, "type": "primary", "value": {...}}
#           ]}
#       ]
#   }
# ==============================================================================

"""
飞书消息卡片模板模块。

提供三种核心卡片模板构建函数:
    1. build_decision_card()          - Top 100 打版池就绪通知
    2. build_trend_report_card()      - 趋势洞察报告
    3. build_validation_result_card() - 验证结果播报

卡片结构遵循飞书 interactive 消息格式:
    - config  : 卡片配置 (宽屏模式等)
    - header  : 卡片头部 (标题 + 颜色模板)
    - elements: 卡片内容元素列表 (div 文本块 / action 按钮组)

用法示例::

    from feishu.templates import build_decision_card

    card = build_decision_card(cards_list, total_count=100)
    await bot.send_card(chat_id="oc_xxx", card=card)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]


# ==============================================================================
# 辅助函数
# ==============================================================================


def _make_div(content: str) -> Dict[str, Any]:
    """构建一个 lark_md 格式的 div 文本元素。

    参数:
        content : 文本内容 (支持 lark_md 语法, 如 **加粗**)

    返回:
        {"tag": "div", "text": {"tag": "lark_md", "content": content}}
    """
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": content},
    }


def _make_divider() -> Dict[str, Any]:
    """构建一个分割线元素。"""
    return {"tag": "hr"}


def _make_action_button(
    text: str,
    value: Dict[str, Any],
    button_type: str = "primary",
) -> Dict[str, Any]:
    """构建一个 action 按钮组 (含单个按钮)。

    参数:
        text        : 按钮文本
        value       : 按钮点击时回传的值
        button_type : 按钮样式 (primary / default / danger)

    返回:
        {"tag": "action", "actions": [{"tag": "button", ...}]}
    """
    return {
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": text},
                "type": button_type,
                "value": value,
            }
        ],
    }


def _make_header(title: str, template: str = "blue") -> Dict[str, Any]:
    """构建卡片头部。

    参数:
        title    : 标题文本
        template : 颜色模板 (blue/green/orange/red/grey/turquoise/purple/indigo/wathet/yellow)

    返回:
        {"title": {"tag": "plain_text", "content": title}, "template": template}
    """
    return {
        "title": {"tag": "plain_text", "content": title},
        "template": template,
    }


def _get_card_field(card: Union[Dict[str, Any], Any], field: str, default: Any = "") -> Any:
    """从卡片数据中安全获取字段值。

    兼容 ProductIdeaCard 实例 (通过 model_dump 或属性访问) 和 dict。

    参数:
        card    : 卡片数据 (ProductIdeaCard 实例或 dict)
        field   : 字段名
        default : 默认值

    返回:
        字段值
    """
    # dict 直接取
    if isinstance(card, dict):
        return card.get(field, default)

    # ProductIdeaCard 实例: 尝试 model_dump
    if hasattr(card, "model_dump"):
        dump = card.model_dump()
        return dump.get(field, default)

    # 退化为属性访问
    return getattr(card, field, default)


# ==============================================================================
# 1. build_decision_card - Top 100 打版池就绪通知
# ==============================================================================


def build_decision_card(
    cards: List[Union[Dict[str, Any], Any]],
    total_count: int = 100,
) -> Dict[str, Any]:
    """构建 Top 100 打版池就绪决策卡片。

    卡片内容:
        - 标题: "Top 100 打版池已就绪, 请评审"
        - 概览: 总创意数 / Top 3 创意摘要
        - Top 3 创意: 产品名 + 爆品概率 + IP 匹配
        - 评审按钮: 跳转多维表格评审

    参数:
        cards       : ProductIdeaCard 列表 (或 dict 列表)
        total_count : 总创意数 (默认 100, 用于显示 "Top N of M")

    返回:
        飞书 interactive 消息卡片字典

    说明:
        - 空列表时仍返回有效卡片结构 (显示 "暂无创意")
        - 取前 3 张卡作为 Top 3 摘要展示
    """
    elements: List[Dict[str, Any]] = []

    # --- 概览 ---
    actual_count = len(cards)
    display_count = total_count if actual_count >= total_count else actual_count
    elements.append(
        _make_div(
            f"**Top 100 打版池已就绪**\n"
            f"共筛选出 **{display_count}** 个高潜力创意"
            + (f" (满分 {total_count})" if actual_count < total_count else "")
        )
    )

    if cards:
        elements.append(_make_divider())

        # --- Top 3 创意摘要 ---
        top3 = cards[:3]
        top3_lines: List[str] = ["**Top 3 创意摘要:**"]
        for i, card in enumerate(top3, 1):
            product_name = _get_card_field(card, "productName", "未命名")
            hit_score = _get_card_field(card, "hitScore", 0)
            ip_match = _get_card_field(card, "ipMatch", None)

            # IP 名称提取
            ip_name = ""
            if ip_match is not None:
                if isinstance(ip_match, dict):
                    ip_name = ip_match.get("ipName", "")
                elif hasattr(ip_match, "ipName"):
                    ip_name = ip_match.ipName

            hit_pct = f"{hit_score * 100:.1f}%" if isinstance(hit_score, (int, float)) else "N/A"
            line = f"{i}. **{product_name}** | 爆品概率: {hit_pct}"
            if ip_name:
                line += f" | IP: {ip_name}"
            top3_lines.append(line)

        elements.append(_make_div("\n".join(top3_lines)))

        # --- 评审按钮 ---
        elements.append(
            _make_action_button(
                text="前往评审 Top 100",
                value={"action": "review_top100", "total": total_count},
                button_type="primary",
            )
        )
    else:
        elements.append(_make_div("暂无符合条件的创意, 请调整筛选条件后重试。"))

    return {
        "config": {"wide_screen_mode": True},
        "header": _make_header(
            "Top 100 打版池已就绪, 请评审", template="blue"
        ),
        "elements": elements,
    }


# ==============================================================================
# 2. build_trend_report_card - 趋势洞察报告
# ==============================================================================


def build_trend_report_card(trend_data: Dict[str, Any]) -> Dict[str, Any]:
    """构建趋势洞察报告卡片。

    卡片内容:
        - 标题: "趋势洞察报告: {话题名}"
        - 热度分 + 增长率
        - 生命周期阶段
        - Z 世代审美标签
        - 预测窗口期
        - 跨区域差异 (如有)

    参数:
        trend_data : 趋势数据字典, 含 topic / heatScore / growthRate /
                      lifecycle / zGenTags / predictWindow / crossRegionDiff 等

    返回:
        飞书 interactive 消息卡片字典

    说明:
        - 空字典时仍返回有效卡片结构 (显示 "暂无数据")
        - 缺失字段时优雅降级, 不报错
    """
    topic = trend_data.get("topic", "未知趋势")
    heat_score = trend_data.get("heatScore", "N/A")
    growth_rate = trend_data.get("growthRate", "N/A")
    lifecycle = trend_data.get("lifecycle", "unknown")
    category = trend_data.get("category", "未知品类")
    z_gen_tags = trend_data.get("zGenTags", [])
    predict_window = trend_data.get("predictWindow", "N/A")
    cross_region_diff = trend_data.get("crossRegionDiff", {})
    related_keywords = trend_data.get("relatedKeywords", [])

    elements: List[Dict[str, Any]] = []

    # --- 趋势概览 ---
    heat_str = (
        f"{heat_score:.1f}" if isinstance(heat_score, (int, float)) else str(heat_score)
    )
    growth_str = (
        f"+{growth_rate:.1f}%"
        if isinstance(growth_rate, (int, float))
        else str(growth_rate)
    )
    elements.append(
        _make_div(
            f"**趋势话题:** {topic}\n"
            f"**品类:** {category}\n"
            f"**热度分:** {heat_str}  |  **周环比增长:** {growth_str}"
        )
    )

    elements.append(_make_divider())

    # --- 生命周期 ---
    lifecycle_map = {
        "rising": "上升期 (Rising)",
        "peak": "峰值期 (Peak)",
        "declining": "衰退期 (Declining)",
    }
    lifecycle_text = lifecycle_map.get(lifecycle, str(lifecycle))
    elements.append(
        _make_div(
            f"**生命周期阶段:** {lifecycle_text}\n"
            f"**预测窗口期:** {predict_window}"
        )
    )

    # --- Z 世代标签 ---
    if z_gen_tags:
        tags_str = " / ".join(z_gen_tags)
        elements.append(_make_div(f"**Z 世代审美标签:** {tags_str}"))

    # --- 关联关键词 ---
    if related_keywords:
        keywords_str = " / ".join(related_keywords)
        elements.append(_make_div(f"**关联关键词:** {keywords_str}"))

    # --- 跨区域差异 ---
    if cross_region_diff:
        diff_lines = ["**跨区域热度差异:**"]
        for region, status in cross_region_diff.items():
            diff_lines.append(f"  - {region}: {status}")
        elements.append(_make_div("\n".join(diff_lines)))

    # --- 查看详情按钮 ---
    elements.append(
        _make_action_button(
            text="查看完整趋势报告",
            value={"action": "view_trend_report", "topic": topic},
            button_type="primary",
        )
    )

    return {
        "config": {"wide_screen_mode": True},
        "header": _make_header(
            f"趋势洞察报告: {topic}", template="turquoise"
        ),
        "elements": elements,
    }


# ==============================================================================
# 3. build_validation_result_card - 验证结果播报
# ==============================================================================


def build_validation_result_card(result: Dict[str, Any]) -> Dict[str, Any]:
    """构建验证结果播报卡片。

    卡片内容:
        - 标题: "验证结果播报"
        - 赢家组合信息 (价格/包装/渠道/区域)
        - 销量数据 + 转化率
        - 预测 vs 实际对比
        - 置信度
        - 排名概览 (Top 3)

    参数:
        result : 验证结果字典, 含 winner / predicted_hit / actual_performance /
                  confidence / total_sales / avg_conversion / rankings 等

    返回:
        飞书 interactive 消息卡片字典

    说明:
        - 空字典时仍返回有效卡片结构 (显示 "暂无验证结果")
        - 缺失字段时优雅降级, 不报错
    """
    winner = result.get("winner", {})
    predicted_hit = result.get("predicted_hit", "N/A")
    actual_performance = result.get("actual_performance", "N/A")
    confidence = result.get("confidence", "N/A")
    total_sales = result.get("total_sales", "N/A")
    avg_conversion = result.get("avg_conversion", "N/A")
    rankings = result.get("rankings", [])

    elements: List[Dict[str, Any]] = []

    # --- 赢家信息 ---
    if winner:
        winner_id = winner.get("combination_id", winner.get("id", "N/A"))
        winner_score = winner.get("composite_score", winner.get("score", "N/A"))
        winner_price = winner.get("price", "N/A")
        winner_packaging = winner.get("packaging", "N/A")
        winner_channel = winner.get("channel", "N/A")
        winner_region = winner.get("region", "N/A")

        score_str = (
            f"{winner_score:.1f}"
            if isinstance(winner_score, (int, float))
            else str(winner_score)
        )
        elements.append(
            _make_div(
                f"**赢家组合:** {winner_id}\n"
                f"**综合评分:** {score_str}\n"
                f"**价格:** {winner_price}  |  **包装:** {winner_packaging}\n"
                f"**渠道:** {winner_channel}  |  **区域:** {winner_region}"
            )
        )
    else:
        elements.append(_make_div("暂无验证结果数据。"))

    elements.append(_make_divider())

    # --- 销量与转化率 ---
    sales_str = (
        str(total_sales) if total_sales != "N/A" else "N/A"
    )
    conv_str = (
        f"{avg_conversion * 100:.1f}%"
        if isinstance(avg_conversion, (int, float))
        else str(avg_conversion)
    )
    elements.append(
        _make_div(
            f"**总销量:** {sales_str}  |  **平均转化率:** {conv_str}"
        )
    )

    # --- 预测 vs 实际 ---
    pred_str = (
        f"{predicted_hit * 100:.1f}%"
        if isinstance(predicted_hit, (int, float))
        else str(predicted_hit)
    )
    actual_str = (
        f"{actual_performance * 100:.1f}%"
        if isinstance(actual_performance, (int, float))
        else str(actual_performance)
    )
    elements.append(
        _make_div(
            f"**预测爆品概率:** {pred_str}  |  **实际表现:** {actual_str}"
        )
    )

    # --- 置信度 ---
    if isinstance(confidence, (int, float)):
        conf_str = f"{confidence * 100:.1f}%"
    else:
        conf_str = str(confidence)
    elements.append(_make_div(f"**置信度:** {conf_str}"))

    # --- 排名概览 (Top 3) ---
    if rankings:
        rank_lines = ["**组合排名 (Top 3):**"]
        for i, rank in enumerate(rankings[:3], 1):
            rid = rank.get("combination_id", rank.get("id", "N/A"))
            rscore = rank.get("score", rank.get("composite_score", "N/A"))
            score_s = (
                f"{rscore:.1f}"
                if isinstance(rscore, (int, float))
                else str(rscore)
            )
            rank_lines.append(f"  {i}. {rid} — {score_s}")
        elements.append(_make_div("\n".join(rank_lines)))

    # --- 查看详情按钮 ---
    elements.append(
        _make_action_button(
            text="查看验证详情",
            value={"action": "view_validation_detail"},
            button_type="primary",
        )
    )

    return {
        "config": {"wide_screen_mode": True},
        "header": _make_header("验证结果播报", template="green"),
        "elements": elements,
    }


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "build_decision_card",
    "build_trend_report_card",
    "build_validation_result_card",
]

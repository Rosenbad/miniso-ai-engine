# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 模拟 SKU 数据生成器 (Task 10)
# ==============================================================================
# 对应 spec §4.5 爆品预测模型 · XGBoost 特征工程:
#   生成 500 条模拟 SKU 训练数据, 含 19 个特征 + is_hit 标签。
#
# 数据设计要点:
#   - 19 个特征分 5 类 (市场5 + 产品3 + IP4 + 受众4 + 情感3)
#   - is_hit 标签与特征相关 (高热度/高IP势能/高Z世代匹配 → 更可能爆品)
#   - 约 20-30% 为爆品 (is_hit=1)
#   - 可复现: random_seed=42
#   - 输出: backend/data/mock_skus.csv
#
# 用法::
#     python backend/data/generate_mock_skus.py
# ==============================================================================

"""
模拟 SKU 数据生成器 (spec §4.5)。

生成 500 条模拟 SKU 记录, 每条含 19 个特征 (snake_case) + is_hit 二分类标签,
用于训练 XGBoost 爆品预测模型。

特征分布 (匹配 spec §4.5):
    市场特征 (5): category_heat / trend_growth_rate / seasonality_index /
                  competitor_density / cross_region_diffusion_speed
    产品特征 (3): price_percentile / material_cost_ratio / design_novelty
    IP 特征  (4): ip_power_score / ip_category_match / ip_license_urgency /
                  ip_region_heat_variance
    受众特征 (4): z_gen_match / aesthetic_tag_heat / audience_spending_power /
                  social_virality
    情感特征 (3): trend_sentiment / social_mentions / positive_review_ratio

标签:
    is_hit (0/1) — 由特征加权组合 + 随机噪声经阈值截断生成, 约 20-30% 为 1。

可复现性:
    使用 numpy.random.default_rng(42) 确保每次生成结果一致。
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

# ==============================================================================
# 常量
# ==============================================================================

RANDOM_SEED: int = 42
"""随机种子, 保证数据可复现。"""

NUM_SKUS: int = 500
"""生成 SKU 记录数量。"""

# 默认输出路径 (backend/data/mock_skus.csv)
DEFAULT_OUTPUT_PATH: Path = Path(__file__).resolve().parent / "mock_skus.csv"

# 19 个特征名 (与 features.py FeatureExtractor.FEATURE_NAMES 完全一致, 顺序一致)
FEATURE_NAMES: List[str] = [
    # 市场特征 (5)
    "category_heat",
    "trend_growth_rate",
    "seasonality_index",
    "competitor_density",
    "cross_region_diffusion_speed",
    # 产品特征 (3)
    "price_percentile",
    "material_cost_ratio",
    "design_novelty",
    # IP 特征 (4)
    "ip_power_score",
    "ip_category_match",
    "ip_license_urgency",
    "ip_region_heat_variance",
    # 受众特征 (4)
    "z_gen_match",
    "aesthetic_tag_heat",
    "audience_spending_power",
    "social_virality",
    # 情感特征 (3)
    "trend_sentiment",
    "social_mentions",
    "positive_review_ratio",
]
"""19 个特征列名, 顺序匹配 spec §4.5。"""

# 品类候选 (用于 product_name / category 可读性)
_CATEGORIES: List[str] = [
    "美妆/个护",
    "家居/香氛",
    "服饰/穿搭",
    "家居/装饰",
    "数码/配件",
    "玩具/文创",
    "食品/零食",
]

# 品类 → 产品名模板 (用于生成可读产品名)
_CATEGORY_PRODUCT_TEMPLATES: Dict[str, List[str]] = {
    "美妆/个护": ["库洛米护手霜", "多巴胺唇釉", "侘寂风面膜", "IP联名洗护套装", "舒缓精华液"],
    "家居/香氛": ["大豆蜡香氛蜡烛", "原木扩香器", "IP联名香薰", "治愈系扩香石", "侘寂风线香"],
    "服饰/穿搭": ["Y2K印花T恤", "IP联名卫衣", "多巴胺配色袜子", "复古牛仔外套", "极简风帆布包"],
    "家居/装饰": ["草莓熊摆件", "手工陶艺花瓶", "IP联名相框", "原木收纳盒", "治愈系毛绒抱枕"],
    "数码/配件": ["IP联名手机壳", "磁吸充电宝", "蓝牙耳机保护套", "机械键盘键帽", "便携数据线"],
    "玩具/文创": ["哈利波特盲盒", "柯南手办", "IP联名徽章套装", "治愈系毛绒挂件", "拼装模型"],
    "食品/零食": ["草莓熊软糖", "IP联名巧克力", "限定口味薯片", "治愈系礼盒", "联名饮料"],
}


# ==============================================================================
# 数据生成核心逻辑
# ==============================================================================


def _generate_sku(idx: int, rng: np.random.Generator) -> Dict[str, Any]:
    """生成单条 SKU 记录 (19 特征 + is_hit + product_name + category)。

    参数:
        idx : SKU 序号 (用于产品名后缀)
        rng : numpy 随机数生成器

    返回:
        含 19 特征 + is_hit + product_name + category 的字典
    """
    # --- 品类与产品名 ---
    category = _CATEGORIES[rng.integers(0, len(_CATEGORIES))]
    name_templates = _CATEGORY_PRODUCT_TEMPLATES[category]
    product_name = f"{name_templates[rng.integers(0, len(name_templates))]}-{idx + 1:03d}"

    # --- 市场特征 (5) ---
    # category_heat: 0-100, 正态分布 around 50
    category_heat = float(np.clip(rng.normal(50, 18), 0, 100))
    # trend_growth_rate: -50 to +100
    trend_growth_rate = float(np.clip(rng.normal(15, 35), -50, 100))
    # seasonality_index: 0-1, 偏向中等
    seasonality_index = float(np.clip(rng.beta(2, 2), 0, 1))
    # competitor_density: 0-1
    competitor_density = float(np.clip(rng.beta(2, 3), 0, 1))
    # cross_region_diffusion_speed: 0-1
    cross_region_diffusion_speed = float(np.clip(rng.beta(2, 4), 0, 1))

    # --- 产品特征 (3) ---
    # price_percentile: 0-1
    price_percentile = float(np.clip(rng.beta(2, 2), 0, 1))
    # material_cost_ratio: 0-1, 偏低 (成本占比通常较低)
    material_cost_ratio = float(np.clip(rng.beta(2, 5), 0, 1))
    # design_novelty: 0-1
    design_novelty = float(np.clip(rng.beta(2, 2), 0, 1))

    # --- IP 特征 (4) ---
    # 约 60% SKU 有 IP 联名
    has_ip = rng.random() < 0.6
    if has_ip:
        # ip_power_score: 0-100
        ip_power_score = float(np.clip(rng.normal(75, 15), 0, 100))
        # ip_category_match: 0-1
        ip_category_match = float(np.clip(rng.beta(4, 2), 0, 1))
        # ip_license_urgency: 0-1 (授权窗口紧迫度)
        ip_license_urgency = float(np.clip(rng.beta(2, 3), 0, 1))
        # ip_region_heat_variance: 0-100
        ip_region_heat_variance = float(np.clip(rng.normal(40, 20), 0, 100))
    else:
        # 无 IP 时 4 个 IP 特征均为 0
        ip_power_score = 0.0
        ip_category_match = 0.0
        ip_license_urgency = 0.0
        ip_region_heat_variance = 0.0

    # --- 受众特征 (4) ---
    # z_gen_match: 0-1
    z_gen_match = float(np.clip(rng.beta(3, 2), 0, 1))
    # aesthetic_tag_heat: 0-100
    aesthetic_tag_heat = float(np.clip(rng.normal(55, 20), 0, 100))
    # audience_spending_power: 0-1
    audience_spending_power = float(np.clip(rng.beta(3, 3), 0, 1))
    # social_virality: 0-1
    social_virality = float(np.clip(rng.beta(2, 3), 0, 1))

    # --- 情感特征 (3) ---
    # trend_sentiment: -1 to 1, 偏正
    trend_sentiment = float(np.clip(rng.normal(0.3, 0.4), -1, 1))
    # social_mentions: 0-100000, 对数正态分布
    social_mentions = float(np.clip(rng.lognormal(8, 1.5), 0, 100000))
    # positive_review_ratio: 0-1, 偏高
    positive_review_ratio = float(np.clip(rng.beta(5, 2), 0, 1))

    # --- is_hit 标签 (与特征相关) ---
    # 爆品潜质 = 特征加权组合 + 随机噪声, 然后阈值截断
    # 归一化各特征到 0-1, 计算加权潜质分
    heat_norm = category_heat / 100.0
    growth_norm = (trend_growth_rate + 50) / 150.0  # -50~100 → 0~1
    ip_norm = ip_power_score / 100.0
    sentiment_norm = (trend_sentiment + 1) / 2.0  # -1~1 → 0~1
    mentions_norm = min(social_mentions / 100000.0, 1.0)

    hit_potential = (
        0.20 * heat_norm
        + 0.15 * growth_norm
        + 0.15 * ip_norm
        + 0.10 * ip_category_match
        + 0.10 * z_gen_match
        + 0.10 * design_novelty
        + 0.05 * social_virality
        + 0.05 * sentiment_norm
        + 0.05 * mentions_norm
        + 0.05 * positive_review_ratio
    )
    # 加随机噪声, 模拟真实数据的不确定性
    hit_potential += rng.normal(0, 0.10)
    # 阈值截断: 约 25% 为爆品
    is_hit = 1 if hit_potential > 0.55 else 0

    return {
        "product_name": product_name,
        "category": category,
        # 市场特征
        "category_heat": round(category_heat, 4),
        "trend_growth_rate": round(trend_growth_rate, 4),
        "seasonality_index": round(seasonality_index, 4),
        "competitor_density": round(competitor_density, 4),
        "cross_region_diffusion_speed": round(cross_region_diffusion_speed, 4),
        # 产品特征
        "price_percentile": round(price_percentile, 4),
        "material_cost_ratio": round(material_cost_ratio, 4),
        "design_novelty": round(design_novelty, 4),
        # IP 特征
        "ip_power_score": round(ip_power_score, 4),
        "ip_category_match": round(ip_category_match, 4),
        "ip_license_urgency": round(ip_license_urgency, 4),
        "ip_region_heat_variance": round(ip_region_heat_variance, 4),
        # 受众特征
        "z_gen_match": round(z_gen_match, 4),
        "aesthetic_tag_heat": round(aesthetic_tag_heat, 4),
        "audience_spending_power": round(audience_spending_power, 4),
        "social_virality": round(social_virality, 4),
        # 情感特征
        "trend_sentiment": round(trend_sentiment, 4),
        "social_mentions": round(social_mentions, 4),
        "positive_review_ratio": round(positive_review_ratio, 4),
        # 标签
        "is_hit": is_hit,
    }


def generate_mock_skus(
    num_skus: int = NUM_SKUS,
    seed: int = RANDOM_SEED,
    output_path: Path | str | None = None,
) -> Path:
    """生成模拟 SKU 数据并写入 CSV 文件。

    参数:
        num_skus    : 生成 SKU 数量, 默认 500
        seed        : 随机种子, 默认 42 (可复现)
        output_path : 输出 CSV 路径, 默认 backend/data/mock_skus.csv

    返回:
        实际写入的 CSV 文件路径 (Path)
    """
    rng = np.random.default_rng(seed)
    resolved_path = Path(output_path) if output_path else DEFAULT_OUTPUT_PATH

    rows: List[Dict[str, Any]] = [
        _generate_sku(i, rng) for i in range(num_skus)
    ]

    # CSV 列顺序: product_name, category, 19 特征, is_hit
    fieldnames = ["product_name", "category"] + FEATURE_NAMES + ["is_hit"]

    with open(resolved_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # 统计爆品比例 (日志输出)
    hit_count = sum(r["is_hit"] for r in rows)
    hit_ratio = hit_count / num_skus
    print(
        f"已生成 {num_skus} 条模拟 SKU → {resolved_path}\n"
        f"  爆品 (is_hit=1): {hit_count} 条 ({hit_ratio:.1%})\n"
        f"  非爆品 (is_hit=0): {num_skus - hit_count} 条 ({1 - hit_ratio:.1%})\n"
        f"  特征数: {len(FEATURE_NAMES)} (市场5+产品3+IP4+受众4+情感3)"
    )

    return resolved_path


# ==============================================================================
# CLI 入口
# ==============================================================================

if __name__ == "__main__":
    generate_mock_skus()

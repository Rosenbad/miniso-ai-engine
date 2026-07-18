# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - Agent 2 产品策划师 (Task 9)
# ==============================================================================
# 对应 spec §4.2 Agent 2: ProductPlanner (产品策划师)
#   职责: 基于产品方向 + Z 世代审美约束, 生成 3-5 个具体产品概念
#   输入: ProductDirection (6 字段, Agent 1 输出)
#   输出: ProductConcept[] (8 字段, 产品概念列表)
#
# ProductPlanner 设计要点:
#   - 规则/模板生成 (Demo 原型, 无需 LLM API 调用)
#   - generate() 方法结构化, 未来可替换为 LLM few-shot 生成
#   - 品类模板: 6 大品类各含 3-4 个产品变体 (名称/材质/价格/卖点)
#   - 未知品类: fallback 通用模板, 仍生成 ≥3 个概念
#   - IP 方向: 品类 → IP 联名建议映射 (参考 IP 数据库)
#   - 设计描述/卖点: 动态融合 direction.styleTone 风格调性
#
# 工具 (未来集成, 当前 stub):
#   - LLM few-shot 生成 (GPT-4 / 通义千问 / 飞书 AI)
#   - IP 联名库 (IPMatchEngine)
#   - 供应链约束校验
# ==============================================================================

"""
Agent 2: 产品策划师 (ProductPlanner)。

决策推理层第二步: 基于产品方向生成具体产品概念。

将 Agent 1 (TrendAnalyst) 输出的 ProductDirection 转化为 3-5 个
具体的 ProductConcept, 每个概念含产品名、品类、设计描述、材质、
价格、IP 方向、卖点与目标受众。

当前实现采用品类模板生成 (Demo 原型), 设计描述与卖点动态融合
direction.styleTone 风格调性。结构设计支持未来替换为 LLM few-shot
生成 (GPT-4 / 通义千问 / 飞书 AI)。

用法::

    planner = ProductPlanner()
    concepts = planner.generate(direction)
    # concepts: List[ProductConcept], len >= 3
    # 每个 concept.category == direction.category
    # 每个 concept.targetAudience == direction.targetAudience
"""

from __future__ import annotations

from typing import Any, Dict, List

from shared.models import ProductConcept, ProductDirection
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 品类 → IP 联名建议映射 (参考 backend/data/ip_database.json)
# ==============================================================================

# 品类 → 推荐 IP (基于 IP 数据库中 matchScore 最高的 IP)
_CATEGORY_IP: Dict[str, str] = {
    "美妆/个护": "三丽鸥·库洛米",
    "家居/香氛": "三丽鸥·库洛米",
    "服饰/穿搭": "华纳·哈利波特",
    "家居/装饰": "迪士尼·草莓熊",
    "数码/配件": "华纳·哈利波特",
    "玩具/文创": "迪士尼·草莓熊",
    "食品/零食": "迪士尼·草莓熊",
}
"""品类 → 推荐 IP 联名方向映射。

基于 IP 数据库 (backend/data/ip_database.json) 中各 IP 的
categoryMatchScores, 选取每个品类匹配度最高的 IP 作为联名建议。
未来可替换为调用 IPMatchEngine.full_match() 动态匹配。
"""

# 默认 IP 方向建议 (品类未匹配时)
_DEFAULT_IP_DIRECTION: str = "适合热门 IP 联名"


# ==============================================================================
# 品类产品模板 (每品类 3-4 个变体)
# ==============================================================================
# 每个变体含:
#   - name          : 产品名 (基础名, 可与风格调性组合)
#   - design_desc   : 设计描述 (含 {style} 占位符, 替换为 direction.styleTone)
#   - material      : 材质
#   - price_range   : 价格区间 (与品类价格带一致)
#   - selling_points: 卖点列表 (可含 {style} 占位符)
# ==============================================================================

_CATEGORY_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    # ---------------------------------------------------------------- 家居/香氛
    "家居/香氛": [
        {
            "name": "原木杯香薰蜡烛",
            "design_desc": "融合{style}美学，原木质感杯身搭配天然大豆蜡，"
            "燃烧时散发淡淡木质香调，营造静谧疗愈氛围",
            "material": "大豆蜡 + 陶瓷",
            "price_range": "49-79",
            "selling_points": [
                "天然大豆蜡，燃烧无黑烟更环保",
                "原木杯身燃烧后可二次利用作收纳",
                "{style}美学设计，社交分享率高",
            ],
        },
        {
            "name": "藤条无火香薰",
            "design_desc": "极简玻璃瓶身搭配天然藤条扩散，{style}风格视觉语言，"
            "持续散发淡雅香韵，适合卧室与办公场景",
            "material": "玻璃 + 藤条 + 香薰液",
            "price_range": "59-89",
            "selling_points": [
                "无火安全设计，无需看护",
                "持久散香 60-90 天",
                "{style}极简瓶身，家居装饰兼用",
            ],
        },
        {
            "name": "陶瓷线香炉",
            "design_desc": "哑光陶瓷材质，{style}留白造型，搭配线香使用，"
            "烟雾流转间营造东方禅意氛围",
            "material": "陶瓷",
            "price_range": "39-69",
            "selling_points": [
                "手工陶瓷，质感细腻",
                "{style}留白设计，百搭家居场景",
                "搭配线香使用，仪式感强",
            ],
        },
        {
            "name": "香薰蜡片挂件",
            "design_desc": "天然蜡基压制花草蜡片，{style}自然系视觉，"
            "可挂衣橱或车内，持久淡香防潮",
            "material": "植物蜡 + 干花",
            "price_range": "29-59",
            "selling_points": [
                "天然花草 embedded，颜值高",
                "衣橱车内多场景适用",
                "{style}自然系，送礼佳品",
            ],
        },
    ],
    # ---------------------------------------------------------------- 家居/装饰
    "家居/装饰": [
        {
            "name": "手作陶瓷花瓶",
            "design_desc": "手工拉坯陶瓷花瓶，{style}不规则造型，"
            "哑光釉面呈现自然质感，单支插花即成景",
            "material": "陶瓷",
            "price_range": "49-89",
            "selling_points": [
                "手工制作，每件独一无二",
                "{style}造型，艺术感强",
                "适配干花与鲜花多种场景",
            ],
        },
        {
            "name": "原木质感挂画",
            "design_desc": "原木边框搭配棉麻画芯，{style}意境画面，"
            "留白构图营造东方美学氛围",
            "material": "原木 + 棉麻",
            "price_range": "69-129",
            "selling_points": [
                "天然原木边框，质感温润",
                "{style}留白构图，提升空间格调",
                "轻量化设计，墙面无负担",
            ],
        },
        {
            "name": "桌面摆件套组",
            "design_desc": "陶瓷与原木结合的桌面摆件，{style}趣味造型，"
            "可作书桌玄关点缀，兼具收纳功能",
            "material": "陶瓷 + 原木",
            "price_range": "39-79",
            "selling_points": [
                " multifunctional 摆件兼收纳",
                "{style}造型，治愈系桌面氛围",
                "送礼自用两相宜",
            ],
        },
    ],
    # ---------------------------------------------------------------- 美妆/个护
    "美妆/个护": [
        {
            "name": "镜面唇釉",
            "design_desc": "高显色镜面唇釉，{style}风格包装设计，"
            "轻盈不黏腻，一抹显色持妆久",
            "material": "植物提取配方",
            "price_range": "29-59",
            "selling_points": [
                "高显色一抹上色",
                "{style}包装，颜值即正义",
                "植物配方温和不刺激",
            ],
        },
        {
            "name": "护手霜礼盒",
            "design_desc": "三支装护手霜礼盒，{style}视觉设计，"
            "轻盈质地速吸收，持久滋润不油腻",
            "material": "植物提取 + 保湿因子",
            "price_range": "39-69",
            "selling_points": [
                "三款香型可选，送礼佳品",
                "速吸收不黏腻",
                "{style}礼盒包装，仪式感满分",
            ],
        },
        {
            "name": "固体香水棒",
            "design_desc": "便携固体香水棒，{style}极简管身，"
            "随点随香，涂抹式设计避免喷洒浪费",
            "material": "植物蜡 + 香精",
            "price_range": "69-99",
            "selling_points": [
                "便携随身，补香方便",
                "固体配方不泄漏",
                "{style}极简设计，随身配饰",
            ],
        },
    ],
    # ---------------------------------------------------------------- 服饰/穿搭
    "服饰/穿搭": [
        {
            "name": "印花帆布托特包",
            "design_desc": "厚实帆布托特包，{style}印花图案，"
            "大容量轻便可折叠，通勤购物多场景适用",
            "material": "棉质帆布",
            "price_range": "59-99",
            "selling_points": [
                "大容量可装电脑",
                "{style}印花，出片率高",
                "可折叠随身携带",
            ],
        },
        {
            "name": "硅胶手机壳",
            "design_desc": "液态硅胶手机壳，{style}视觉设计，"
            "全包防摔，手感细腻不易发黄",
            "material": "液态硅胶",
            "price_range": "49-89",
            "selling_points": [
                "全包防摔保护",
                "{style}设计，颜值担当",
                "液态硅胶手感细腻",
            ],
        },
        {
            "name": "潮流棉袜三双装",
            "design_desc": "精梳棉袜三双装，{style}潮流图案，"
            "透气吸汗，低帮隐形款适配多种鞋型",
            "material": "精梳棉 + 氨纶",
            "price_range": "39-69",
            "selling_points": [
                "精梳棉透气吸汗",
                "{style}图案，穿搭点睛",
                "三双装性价比高",
            ],
        },
    ],
    # ---------------------------------------------------------------- 数码/配件
    "数码/配件": [
        {
            "name": "桌面手机支架",
            "design_desc": "合金桌面手机支架，{style}极简造型，"
            "可调节角度，追剧办公解放双手",
            "material": "合金 + 硅胶垫",
            "price_range": "59-99",
            "selling_points": [
                "可调节多角度",
                "{style}极简设计，桌面美学",
                "硅胶垫防滑防刮",
            ],
        },
        {
            "name": "耳机保护壳",
            "design_desc": "硅胶耳机充电仓保护壳，{style}趣味造型，"
            "全包防摔，附挂绳孔方便携带",
            "material": "液态硅胶",
            "price_range": "49-89",
            "selling_points": [
                "全包防摔保护",
                "{style}造型，趣味颜值",
                "挂绳孔设计便携",
            ],
        },
        {
            "name": "笔记本贴纸套装",
            "design_desc": "防水 PVC 贴纸套装，{style}系列图案，"
            "可装饰笔记本/手机/水杯，撕下无残胶",
            "material": "防水 PVC",
            "price_range": "29-59",
            "selling_points": [
                "防水耐撕耐用",
                "{style}系列图案，DIY 个性表达",
                "撕下无残胶，可重复贴",
            ],
        },
    ],
    # ---------------------------------------------------------------- 玩具/文创
    "玩具/文创": [
        {
            "name": "盲盒系列",
            "design_desc": "原创 IP 盲盒系列，{style}造型设计，"
            "含隐藏款，拆盒惊喜感强，集换社交属性高",
            "material": "环保 PVC",
            "price_range": "39-69",
            "selling_points": [
                "含隐藏款，惊喜感强",
                "{style}造型，治愈系收藏",
                "集换社交属性，复购率高",
            ],
        },
        {
            "name": "萌系钥匙扣",
            "design_desc": "合金烤漆钥匙扣，{style}萌系造型，"
            "挂包挂钥匙皆宜，送礼小物首选",
            "material": "合金 + 烤漆",
            "price_range": "19-39",
            "selling_points": [
                "{style}萌系造型，颜值高",
                "合金烤漆耐用不掉色",
                "送礼小物性价比高",
            ],
        },
        {
            "name": "文创文具套装",
            "design_desc": "笔记本+笔+贴纸文具套装，{style}视觉设计，"
            "学生办公皆宜，包装精美适合送礼",
            "material": "纸张 + 塑料",
            "price_range": "29-59",
            "selling_points": [
                "套装齐全，一站式满足",
                "{style}设计，学习工作好心情",
                "精美包装送礼佳品",
            ],
        },
    ],
    # ---------------------------------------------------------------- 食品/零食
    "食品/零食": [
        {
            "name": "造型软糖礼盒",
            "design_desc": "IP 造型软糖礼盒，{style}包装设计，"
            "果汁软糖口感 Q 弹，造型可爱社交分享率高",
            "material": "果汁软糖",
            "price_range": "19-39",
            "selling_points": [
                "果汁软糖 Q 弹可口",
                "{style}包装，社交出片",
                "造型可爱，吸引 Z 世代",
            ],
        },
        {
            "name": "节庆限定礼盒",
            "design_desc": "节庆限定零食礼盒，{style}视觉设计，"
            "多口味组合，附赠周边小物，送礼自用两相宜",
            "material": "混合零食",
            "price_range": "39-59",
            "selling_points": [
                "节庆限定，稀缺性强",
                "{style}礼盒，仪式感满分",
                "附赠周边小物，附加值高",
            ],
        },
        {
            "name": "趣味造型饼干",
            "design_desc": "IP 造型黄油饼干，{style}包装设计，"
            "酥脆可口，造型趣味适合分享",
            "material": "黄油饼干",
            "price_range": "19-29",
            "selling_points": [
                "酥脆黄油口感",
                "{style}造型趣味，分享率高",
                "性价比高，复购友好",
            ],
        },
    ],
}
"""品类 → 产品模板映射。

6 大品类 (家居/香氛、家居/装饰、美妆/个护、服饰/穿搭、数码/配件、
玩具/文创) + 食品/零食, 每品类含 3-4 个产品变体。

模板中 {style} 占位符在生成时替换为 direction.styleTone 风格调性,
使设计描述与卖点动态贴合趋势风格。
"""

# 未知品类 fallback 模板 (通用创意周边)
_FALLBACK_TEMPLATE: List[Dict[str, Any]] = [
    {
        "name": "创意周边基础款",
        "design_desc": "融合{style}风格的创意周边基础款，"
        "简约设计适配多场景，高性价比入门首选",
        "material": "通用材质",
        "price_range": "39-79",
        "selling_points": [
            "{style}风格设计，百搭实用",
            "高性价比入门款",
            "社交分享友好",
        ],
    },
    {
        "name": "创意周边进阶款",
        "design_desc": "融合{style}风格的创意周边进阶款，"
        "升级材质与工艺，质感与颜值兼备",
        "material": "升级材质",
        "price_range": "59-99",
        "selling_points": [
            "升级材质工艺，质感更佳",
            "{style}风格视觉升级",
            "送礼自用两相宜",
        ],
    },
    {
        "name": "创意周边限定款",
        "design_desc": "融合{style}风格的创意周边限定款，"
        "稀缺设计附赠专属包装，收藏价值高",
        "material": "限定材质",
        "price_range": "79-129",
        "selling_points": [
            "限定稀缺设计",
            "{style}风格专属包装",
            "收藏价值高",
        ],
    },
]
"""未知品类 fallback 通用模板, 生成 ≥3 个概念。

当 direction.category 不在 _CATEGORY_TEMPLATES 中时使用,
确保任何品类都能产出产品概念。
"""


# ==============================================================================
# ProductPlanner 产品策划师
# ==============================================================================


class ProductPlanner:
    """产品策划师 (Agent 2, spec §4.2)。

    基于 ProductDirection 产品方向 + Z 世代审美约束, 生成 3-5 个
    具体的 ProductConcept 产品概念。

    当前采用品类模板生成:
        1. 按 direction.category 查找品类模板 (未知品类用 fallback)
        2. 每个模板变体生成一个 ProductConcept
        3. 设计描述/卖点动态融合 direction.styleTone 风格调性
        4. IP 方向: 品类 → IP 联名建议映射
        5. 目标受众: 透传 direction.targetAudience
        6. 品类: 透传 direction.category

    设计支持未来替换为 LLM few-shot 生成: generate() 方法可改为调用
    GPT-4 / 通义千问 / 飞书 AI, 输入 ProductDirection + few-shot 示例,
    输出 ProductConcept 列表。

    用法::

        planner = ProductPlanner()
        concepts = planner.generate(direction)
        # len(concepts) >= 3
        # concepts[0].category == direction.category
        # concepts[0].targetAudience == direction.targetAudience
    """

    # ==================================================================
    # generate() - 主入口: ProductDirection → List[ProductConcept]
    # ==================================================================

    def generate(
        self,
        direction: ProductDirection,
        trend_topic: str = "",
        trend_keywords: List[str] | None = None,
    ) -> List[ProductConcept]:
        """基于产品方向 + 真实趋势话题生成产品概念列表。

        对应 spec §4.2 Agent 2 核心职责。将 ProductDirection + 真实趋势
        转化为 ≥3 个 ProductConcept, 每个概念含 8 个字段。

        真实数据融合:
            1. 产品名包含趋势话题关键词 (如"寻找卢本伟主题盲盒")
            2. 品类自动推断: 未知品类基于趋势关键词映射到最近品类
            3. 设计描述融入趋势话题
            4. IP 方向基于品类匹配

        参数:
            direction       : 产品方向 (ProductDirection 实例, Agent 1 输出)
            trend_topic     : 真实趋势话题 (来自采集器, 如"寻找卢本伟")
            trend_keywords  : 趋势关联关键词列表

        返回:
            ProductConcept 列表 (≥3 个), 产品名包含趋势话题
        """
        from shared.models import TrendSignal

        logger.info(
            f"ProductPlanner.generate: category='{direction.category}', "
            f"styleTone='{direction.styleTone}', trend_topic='{trend_topic}'"
        )

        # 1. 品类自动推断 (未知品类基于趋势关键词映射)
        effective_category = self._infer_category(
            direction.category, trend_topic, trend_keywords or []
        )

        # 2. 查找品类模板 (未知品类用 fallback)
        template = _CATEGORY_TEMPLATES.get(effective_category, _FALLBACK_TEMPLATE)

        # 3. 查找 IP 方向建议
        ip_direction = _CATEGORY_IP.get(effective_category, _DEFAULT_IP_DIRECTION)

        # 4. 生成 3 个差异化变体 (基础款/进阶款/限定款)
        #    产品名 = [趋势话题] + [变体定位] + [品类产品名]
        tier_suffixes = ["基础款", "进阶款", "限定款"]
        concepts: List[ProductConcept] = []
        style = direction.styleTone

        # 从模板中选取前 3 个变体 (或 fallback 的 3 个)
        variants = template[:3]

        for idx, variant in enumerate(variants):
            # 产品名融合趋势话题
            base_name = variant["name"]
            tier = tier_suffixes[idx] if idx < len(tier_suffixes) else f"变体{idx+1}"

            if trend_topic:
                # 真实趋势话题作为产品名前缀
                product_name = f"{trend_topic}{tier}"
            else:
                product_name = f"{base_name}"

            # 设计描述融合趋势话题 + 风格调性
            design_desc = self._format_text(variant["design_desc"], style)
            if trend_topic:
                design_desc = f"围绕「{trend_topic}」趋势, {design_desc}"

            # 卖点融合
            selling_points = [
                self._format_text(sp, style) for sp in variant["selling_points"]
            ]
            if trend_topic and idx == 0:
                selling_points.insert(0, f"紧贴「{trend_topic}」热门趋势")

            concept = ProductConcept(
                productName=product_name,
                category=effective_category,
                designDesc=design_desc,
                material=variant["material"],
                priceRange=variant["price_range"],
                ipDirection=ip_direction,
                sellingPoints=selling_points,
                targetAudience=dict(direction.targetAudience),
            )
            concepts.append(concept)

        logger.info(
            f"ProductPlanner.generate: 完成 → 生成 {len(concepts)} 个概念, "
            f"category='{effective_category}', ipDirection='{ip_direction}', "
            f"productName[0]='{concepts[0].productName}'"
        )

        return concepts

    # ==================================================================
    # 品类自动推断 (基于趋势关键词)
    # ==================================================================

    def _infer_category(
        self,
        original_category: str,
        trend_topic: str,
        keywords: List[str],
    ) -> str:
        """基于趋势话题和关键词推断最合适的品类。

        当原始品类不在已知模板中时, 基于趋势关键词映射到最近的品类。

        参数:
            original_category : 原始品类 (来自 TrendAnalyst)
            trend_topic       : 趋势话题
            keywords          : 趋势关联关键词

        返回:
            推断的品类 (确保在 _CATEGORY_TEMPLATES 中)
        """
        # 已知品类直接返回
        if original_category in _CATEGORY_TEMPLATES:
            return original_category

        # 合并话题和关键词用于推断
        combined_text = f"{trend_topic} {' '.join(keywords)}".lower()

        # 关键词 → 品类映射规则
        category_rules = [
            (["美妆", "化妆", "唇", "护肤", "香水", "口红", "个护"], "美妆/个护"),
            (["家居", "装饰", "花瓶", "摆件", " candle", "香薰"], "家居/装饰"),
            (["服饰", "穿搭", "服装", "包", "袜", "鞋"], "服饰/穿搭"),
            (["数码", "配件", "手机", "耳机", "支架", "电子"], "数码/配件"),
            (["玩具", "文创", "盲盒", "钥匙扣", "文具"], "玩具/文创"),
            (["食品", "零食", "糖", "饼干", "礼盒"], "食品/零食"),
            (["香氛", "蜡烛", "香薰"], "家居/香氛"),
        ]

        for rule_keywords, mapped_category in category_rules:
            if any(kw.lower() in combined_text for kw in rule_keywords):
                logger.info(
                    f"ProductPlanner._infer_category: '{original_category}' → '{mapped_category}' "
                    f"(matched keywords in '{trend_topic}')"
                )
                return mapped_category

        # 默认映射: 视频/娱乐/社会/热点 → 玩具/文创 (最适合 IP 联名)
        logger.info(
            f"ProductPlanner._infer_category: '{original_category}' → '玩具/文创' (default)"
        )
        return "玩具/文创"

    # ==================================================================
    # 内部辅助: 文本格式化 (替换 {style} 占位符)
    # ==================================================================

    @staticmethod
    def _format_text(text: str, style: str) -> str:
        """替换文本中的 {style} 占位符为风格调性。

        参数:
            text  : 含 {style} 占位符的模板文本
            style : 风格调性 (direction.styleTone)

        返回:
            替换后的文本 (无占位符)
        """
        if not text:
            return text
        return text.replace("{style}", style)


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["ProductPlanner"]

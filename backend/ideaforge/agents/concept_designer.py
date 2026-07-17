# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - Agent 4 概念设计师 (Task 11)
# ==============================================================================
# 对应 spec §4.2 Agent 4: ConceptDesigner (概念设计师)
#   职责: 基于产品概念生成概念设计图 (正面图 + 场景图)
#   输入: ProductConcept (8 字段, Agent 2 输出)
#   输出: List[str] (2 个图片 URL: [url_front, url_scene])
#
# ConceptDesigner 设计要点:
#   - Demo 模式: 使用 placehold.co 生成占位图 URL (含产品名编码)
#   - 未来集成: DALL-E 3 / Stable Diffusion XL API
#   - 降级策略: API 不可用时自动降级为 placehold.co URL
#   - URL 编码: 产品名含中文时使用 urllib.parse.quote 编码
#
# 工具 (未来集成, 当前 placehold.co):
#   - DALL-E 3 API (OpenAI)
#   - Stable Diffusion XL (Stability AI)
#   - 图片存储 (OSS / S3)
# ==============================================================================

"""
Agent 4: 概念设计师 (ConceptDesigner)。

决策推理层第四步: 基于产品概念生成概念设计图。

将 Agent 2 (ProductPlanner) 输出的 ProductConcept 转化为 2 个
概念图 URL: 正面图 (front view) 与场景图 (scene view)。

当前实现采用 placehold.co 占位图 (Demo 模式), 产品名编码在 URL 中。
未来可替换为 DALL-E 3 / Stable Diffusion XL API 调用。

用法::

    designer = ConceptDesigner()
    urls = designer.generate(concept)
    # urls: ["https://placehold.co/600x400?text=...Front",
    #        "https://placehold.co/600x400?text=...Scene"]
"""

from __future__ import annotations

from urllib.parse import quote

from shared.models import ProductConcept
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 常量
# ==============================================================================

# placehold.co 基础 URL
_PLACEHOLDER_BASE: str = "https://placehold.co/600x400"

# 图片尺寸
_IMAGE_SIZE: str = "600x400"

# 正面图标签
_FRONT_LABEL: str = "Front"

# 场景图标签
_SCENE_LABEL: str = "Scene"


# ==============================================================================
# ConceptDesigner 概念设计师
# ==============================================================================


class ConceptDesigner:
    """概念设计师 (Agent 4, spec §4.2)。

    基于产品概念生成 2 个概念图 URL (正面图 + 场景图)。

    当前采用 placehold.co 占位图生成 (Demo 模式):
        1. 正面图 (front view): 产品名 + Front 标签
        2. 场景图 (scene view): 产品名 + Scene 标签

    设计支持未来替换为 DALL-E 3 / SD XL API: generate() 方法可改为
    调用 OpenAI DALL-E 3 或 Stability AI SD XL, 输入 ProductConcept
    的设计描述, 输出真实生成的图片 URL。

    降级策略:
        - DALL-E/SD API 不可用时 → placehold.co 占位图
        - 当前 Demo 模式直接使用 placehold.co

    用法::

        designer = ConceptDesigner()
        urls = designer.generate(concept)
        # urls = [
        #     "https://placehold.co/600x400?text=ProductName+Front",
        #     "https://placehold.co/600x400?text=ProductName+Scene",
        # ]
    """

    def generate(self, concept: ProductConcept) -> list[str]:
        """为产品概念生成 2 个概念图 URL。

        对应 spec §4.2 Agent 4 核心职责。将 ProductConcept 转化为
        [url_front, url_scene] 两个图片 URL。

        参数:
            concept: 产品概念 (ProductConcept 实例, Agent 2 输出)

        返回:
            长度 2 的 URL 列表:
            - [0]: 正面图 URL (含 Front 标识)
            - [1]: 场景图 URL (含 Scene 标识)

        降级模式:
            使用 placehold.co 生成占位图, 产品名编码在 URL text 参数中。
            中文产品名通过 urllib.parse.quote 进行 URL 编码。
        """
        logger.info(
            f"ConceptDesigner.generate: product='{concept.productName}', "
            f"category='{concept.category}'"
        )

        # URL 编码产品名 (处理中文/特殊字符)
        product_encoded = quote(concept.productName, safe="")

        # 生成正面图 URL
        url_front = (
            f"{_PLACEHOLDER_BASE}?text={product_encoded}+{_FRONT_LABEL}"
        )

        # 生成场景图 URL
        url_scene = (
            f"{_PLACEHOLDER_BASE}?text={product_encoded}+{_SCENE_LABEL}"
        )

        urls = [url_front, url_scene]

        logger.info(
            f"ConceptDesigner.generate: 完成 → 生成 {len(urls)} 个概念图 URL"
        )

        return urls


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["ConceptDesigner"]

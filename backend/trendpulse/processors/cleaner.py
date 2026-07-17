# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 数据清洗器 (Task 6)
# ==============================================================================
# 对应 spec §3.2 NLP 处理流水线 - 清洗去噪:
#   去广告、去重、多语言检测 (中/英/日/韩/泰等)
#
# DataCleaner 负责 NLP 流水线的第 1 阶段:
#   1. 正则去广告 (URL / 微信 / 促销 / 联系方式)
#   2. 去重 (精确匹配 + 近重复检测)
#   3. 多语言检测 (基于 Unicode 字符区间的启发式方法)
#
# 设计要点:
#   - 纯正则实现去广告, 无外部依赖, 易于测试与扩展
#   - 去重采用「归一化精确匹配 + 字符集 Jaccard 相似度」双层策略
#   - 语言检测基于 Unicode 字符区间, 轻量快速, 覆盖中/英/日/韩/泰
#   - clean() 主入口将三步串联, 为每条数据添加 language 字段
# ==============================================================================

"""
数据清洗器模块。

NLP 处理流水线第 1 阶段: 清洗去噪。

类:
    DataCleaner - 去广告 + 去重 + 语言检测

用法::

    cleaner = DataCleaner()
    cleaned = cleaner.clean(raw_items)
    # cleaned: [{...原始字段, language: "zh"}, ...]
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# 广告正则模式 (spec §3.2: 去广告)
# ==============================================================================

# URL: http:// 或 https:// 链接 (含常见短链域名)
_URL_PATTERN = re.compile(
    r"https?://[^\s\u4e00-\u9fff]+",  # URL 中的非空白非中文字符
    flags=re.IGNORECASE,
)

# 微信推广: 加微信 / 微信号 / wechat / wx
_WECHAT_PATTERN = re.compile(
    r"(?:加微信|微信号|加微|微信咨询|wechat|weixin|wx)\s*[a-zA-Z0-9_-]*",
    flags=re.IGNORECASE,
)

# 促销关键词: 促销 / 限时 / 折扣 / 秒杀 / 优惠券 / 点击链接
_PROMO_PATTERN = re.compile(
    r"(?:促销|限时|限时抢购|限时秒杀|折扣|打折|秒杀|优惠券|优惠码|"
    r"点击链接|点击购买|立即购买|抢购|满减|包邮|特价)",
)

# 联系方式: 联系QQ / 电话 / 加群 / 扣扣
# 注: 长模式 (联系电话/电话咨询) 优先于短模式 (电话), 避免部分匹配残留
_CONTACT_PATTERN = re.compile(
    r"(?:联系电话|电话咨询|联系QQ|联系qq|加Q群|加群|扣扣|"
    r"QQ咨询|QQ群|微信号咨询|电话)"
)

# 合并所有广告模式 (依次替换)
_AD_PATTERNS: List[re.Pattern] = [
    _URL_PATTERN,
    _WECHAT_PATTERN,
    _PROMO_PATTERN,
    _CONTACT_PATTERN,
]


# ==============================================================================
# 语言检测 Unicode 字符区间
# ==============================================================================

# CJK 统一汉字 (常用中文)
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
# 日文平假名
_HIRAGANA_PATTERN = re.compile(r"[\u3040-\u309f]")
# 日文片假名
_KATAKANA_PATTERN = re.compile(r"[\u30a0-\u30ff]")
# 韩文音节 (Hangul Syllables)
_HANGUL_PATTERN = re.compile(r"[\uac00-\ud7af]")
# 韩文兼容字母 (Hangul Compatibility Jamo + Jamo)
_HANGUL_JAMO_PATTERN = re.compile(r"[\u1100-\u11ff\u3130-\u318f]")
# 泰文
_THAI_PATTERN = re.compile(r"[\u0e00-\u0e7f]")
# 拉丁字母 (英文等)
_LATIN_PATTERN = re.compile(r"[a-zA-Z]")


# ==============================================================================
# DataCleaner 数据清洗器
# ==============================================================================


class DataCleaner:
    """数据清洗器 - NLP 流水线第 1 阶段 (清洗去噪)。

    三大功能 (spec §3.2):
        1. 去广告: 正则匹配 URL / 微信 / 促销 / 联系方式
        2. 去重: 归一化精确匹配 + 字符集 Jaccard 近重复检测
        3. 语言检测: 基于 Unicode 字符区间的启发式方法
           (中/英/日/韩/泰/other)

    用法::

        cleaner = DataCleaner()
        cleaned = cleaner.clean(raw_items)
        # 每条数据被: 去广告 → 去重 → 添加 language 字段
    """

    # 近重复检测的 Jaccard 相似度阈值 (高于此值视为重复)
    NEAR_DUP_THRESHOLD: float = 0.85

    # ==================================================================
    # clean() - 主入口
    # ==================================================================

    def clean(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """清洗主入口 — 去广告 → 去重 → 语言检测。

        流程:
            1. 对每条数据的 content (及 topic) 字段执行去广告
            2. 基于 content 归一化 + 近重复检测去重
            3. 为每条数据添加 language 字段 (基于 content)

        参数:
            items: 原始数据列表, 每条至少含 ``content`` 字段

        返回:
            清洗后的数据列表 (含原始字段 + ``language`` 字段)
            空列表输入返回空列表
        """
        if not items:
            return []

        # Step 1: 去广告 (对 content 与 topic 字段)
        cleaned: List[Dict[str, Any]] = []
        for item in items:
            new_item: Dict[str, Any] = dict(item)  # 浅拷贝, 不修改原始数据
            content = new_item.get("content", "")
            if isinstance(content, str) and content:
                new_item["content"] = self._remove_ads(content)
            topic = new_item.get("topic", "")
            if isinstance(topic, str) and topic:
                new_item["topic"] = self._remove_ads(topic)
            cleaned.append(new_item)

        # Step 2: 去重
        deduplicated = self._deduplicate(cleaned)

        # Step 3: 语言检测 (为每条数据添加 language 字段)
        for item in deduplicated:
            content = item.get("content", "") or item.get("topic", "")
            item["language"] = self._detect_language(
                content if isinstance(content, str) else ""
            )

        logger.info(
            f"DataCleaner: 输入 {len(items)} 条, "
            f"清洗去重后 {len(deduplicated)} 条"
        )
        return deduplicated

    # ==================================================================
    # _remove_ads - 正则去广告
    # ==================================================================

    def _remove_ads(self, text: str) -> str:
        """移除文本中的广告与推广内容。

        使用正则表达式依次移除:
            - URL: ``https?://...``
            - 微信: 加微信 / 微信号 / wechat / wx
            - 促销: 促销 / 限时 / 折扣 / 秒杀 / 优惠券 / 点击链接
            - 联系方式: 联系QQ / 电话 / 加群

        参数:
            text: 原始文本

        返回:
            清理后的文本 (首尾空白已 strip)
            空字符串输入返回空字符串
        """
        if not text:
            return ""
        cleaned = text
        for pattern in _AD_PATTERNS:
            cleaned = pattern.sub("", cleaned)
        # 合并多余空白 (广告移除后可能留下连续空格)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.strip()

    # ==================================================================
    # _deduplicate - 去重
    # ==================================================================

    def _deduplicate(
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """去除重复数据 (精确匹配 + 近重复检测)。

        策略:
            1. 归一化: strip + 移除所有空白 + 转小写
            2. 精确匹配: 归一化后内容相同视为重复
            3. 近重复: 字符集 Jaccard 相似度 > 阈值视为重复
               (应对仅标点/微小差异的近重复)

        保留首次出现的项, 后续重复项被丢弃。

        参数:
            items: 数据列表

        返回:
            去重后的数据列表 (保持原始顺序)
        """
        if not items:
            return []

        seen_normalized: List[str] = []
        seen_char_sets: List[frozenset] = []
        result: List[Dict[str, Any]] = []

        for item in items:
            content = item.get("content", "") or item.get("topic", "")
            if not isinstance(content, str):
                content = str(content) if content else ""

            # 归一化: 移除所有空白 + 标点 (非词字符) + 转小写
            # \W 匹配非词字符 (标点/符号), 中文/字母/数字属于 \w 被保留
            normalized = re.sub(r"[\s\W]+", "", content, flags=re.UNICODE)
            normalized = normalized.lower()

            # 精确匹配检查
            is_dup = False
            if normalized in seen_normalized:
                is_dup = True
            else:
                # 近重复检查: Jaccard 相似度
                current_chars = frozenset(normalized)
                if current_chars:  # 空内容不参与近重复检测
                    for existing in seen_char_sets:
                        if not existing:
                            continue
                        intersection = len(current_chars & existing)
                        union = len(current_chars | existing)
                        if union > 0:
                            similarity = intersection / union
                            if similarity >= self.NEAR_DUP_THRESHOLD:
                                is_dup = True
                                break

            if not is_dup:
                seen_normalized.append(normalized)
                seen_char_sets.append(frozenset(normalized))
                result.append(item)

        return result

    # ==================================================================
    # _detect_language - 语言检测
    # ==================================================================

    def _detect_language(self, text: str) -> str:
        """检测文本语言 (启发式, 基于 Unicode 字符区间)。

        检测优先级 (先匹配先返回):
            1. 日语 (ja): 含平假名/片假名 → 日语
               (注: 日语可能含汉字, 但有假名即可判定为日语)
            2. 韩语 (ko): 含韩文音节/字母 → 韩语
            3. 泰语 (th): 含泰文字符 → 泰语
            4. 中文 (zh): 含 CJK 汉字 → 中文
            5. 英文 (en): 含拉丁字母 → 英文
            6. 其他 (other): 无可识别字符

        参数:
            text: 待检测文本

        返回:
            语言代码: ``zh`` / ``en`` / ``ja`` / ``ko`` / ``th`` / ``other``
        """
        if not text or not text.strip():
            return "other"

        # 优先检测日语 (假名是日语独有标识, 先于中文判定)
        if _HIRAGANA_PATTERN.search(text) or _KATAKANA_PATTERN.search(text):
            return "ja"

        # 韩语
        if _HANGUL_PATTERN.search(text) or _HANGUL_JAMO_PATTERN.search(text):
            return "ko"

        # 泰语
        if _THAI_PATTERN.search(text):
            return "th"

        # 中文 (CJK 汉字)
        if _CJK_PATTERN.search(text):
            return "zh"

        # 英文 (拉丁字母)
        if _LATIN_PATTERN.search(text):
            return "en"

        return "other"


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["DataCleaner"]

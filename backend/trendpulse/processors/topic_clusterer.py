# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 话题聚类器 (Task 6)
# ==============================================================================
# 对应 spec §3.2 NLP 处理流水线 - 话题聚类:
#   BERTopic 主题建模 (多语言模型), 把碎片化内容聚合为趋势主题
#
# 本实现采用 TF-IDF + KMeans 作为生产环境 BERTopic 的轻量替代:
#   - 中文文本先经 jieba 分词, 再用空格连接 (TfidfVectorizer 要求)
#   - TF-IDF 向量化 → KMeans 聚类 → 提取关键词 → 生成话题名
#   - 生产环境可替换为 BERTopic (sentence-transformers 多语言模型)
#
# 设计要点:
#   - 健壮处理边界场景: 空输入 / 单项 / 全部相同 / n_clusters 超过项数
#   - KMeans 使用固定 random_state 保证结果可复现
#   - 关键词提取基于 TF-IDF 权重排序, 取 top_n
#   - 话题名由 top 关键词拼接生成
# ==============================================================================

"""
话题聚类器模块。

NLP 处理流水线第 2 阶段: 话题聚类。

类:
    TopicClusterer - TF-IDF + KMeans 话题聚类

用法::

    clusterer = TopicClusterer()
    clusters = clusterer.cluster(items, n_clusters=5)
    # clusters: [{topic_name, items_count, keywords, representative_text, items}, ...]
"""

from __future__ import annotations

from typing import Any, Dict, List

from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# TopicClusterer 话题聚类器
# ==============================================================================


class TopicClusterer:
    """话题聚类器 - NLP 流水线第 2 阶段 (话题聚类)。

    使用 TF-IDF + KMeans 将碎片化内容聚合为趋势主题。
    生产环境可替换为 BERTopic (spec §3.2)。

    流程:
        1. 提取文本 (content 或 topic 字段)
        2. 中文文本经 jieba 分词后用空格连接
        3. TfidfVectorizer 向量化
        4. KMeans 聚类 (n_clusters = min(传入值, 项数))
        5. 每个聚类提取关键词 + 生成话题名 + 选择代表性文本

    用法::

        clusterer = TopicClusterer()
        clusters = clusterer.cluster(items, n_clusters=3)
    """

    # KMeans 随机种子 (保证可复现)
    RANDOM_STATE: int = 42

    # ==================================================================
    # cluster() - 主入口
    # ==================================================================

    def cluster(
        self,
        items: List[Dict[str, Any]],
        n_clusters: int = 5,
    ) -> List[Dict[str, Any]]:
        """聚类主入口 — TF-IDF + KMeans 话题聚类。

        参数:
            items      : 数据列表, 每条含 ``content`` (或 ``topic``) 字段
            n_clusters : 目标聚类数 (实际会被 min(n_clusters, len(items)) 截断)

        返回:
            聚类摘要列表, 每个摘要包含:
                - topic_name       : 话题名 (由关键词拼接)
                - items_count      : 该聚类的项数
                - keywords         : 关键词列表 (top_n)
                - representative_text: 代表性文本 (聚类中最长的文本)
                - items            : 该聚类的原始数据列表

            空列表输入返回空列表;
            单项输入返回 1 个聚类;
            全部相同内容返回 1 个聚类。
        """
        if not items:
            return []

        # 提取文本 (优先 content, 回退 topic)
        texts: List[str] = []
        for item in items:
            text = item.get("content", "") or item.get("topic", "")
            if not isinstance(text, str):
                text = str(text) if text else ""
            texts.append(text)

        n_items = len(items)
        # 实际聚类数不超过项数
        actual_k = min(max(1, n_clusters), n_items)

        # 边界场景: 单项或全部相同文本 → 直接返回 1 个聚类
        if n_items == 1 or self._all_texts_identical(texts):
            return self._build_single_cluster(items, texts)

        # 延迟导入 sklearn (仅在聚类时需要)
        try:
            from sklearn.cluster import KMeans
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError as exc:
            logger.warning(
                f"scikit-learn 未安装, 降级为单一聚类: {exc}"
            )
            return self._build_single_cluster(items, texts)

        # 分词预处理 (中文用 jieba, 其他用原始文本)
        tokenized_texts = [self._tokenize(t) for t in texts]

        # TF-IDF 向量化
        # analyzer=lambda x: x.split() 使用预分词文本 (jieba 已分词, 空格分隔)
        # 避免默认 token_pattern 对中文分词的干扰
        try:
            vectorizer = TfidfVectorizer(
                analyzer=lambda x: x.split(),
                max_features=1000,
            )
            tfidf_matrix = vectorizer.fit_transform(tokenized_texts)
        except ValueError as exc:
            # 所有文本均为空或词汇表为空时, TfidfVectorizer 抛 ValueError
            logger.warning(f"TF-IDF 向量化失败 (可能文本过短), 降级为单一聚类: {exc}")
            return self._build_single_cluster(items, texts)

        feature_names = vectorizer.get_feature_names_out()

        # KMeans 聚类
        try:
            kmeans = KMeans(
                n_clusters=actual_k,
                random_state=self.RANDOM_STATE,
                n_init=10,
            )
            labels = kmeans.fit_predict(tfidf_matrix)
        except Exception as exc:
            logger.warning(f"KMeans 聚类失败, 降级为单一聚类: {exc}")
            return self._build_single_cluster(items, texts)

        # 构建聚类摘要
        clusters = self._build_cluster_summaries(
            items, texts, labels, tfidf_matrix, feature_names, actual_k
        )

        logger.info(
            f"TopicClusterer: 输入 {n_items} 条, "
            f"聚类为 {len(clusters)} 个话题"
        )
        return clusters

    # ==================================================================
    # _tokenize - 分词预处理
    # ==================================================================

    def _tokenize(self, text: str) -> str:
        """对文本进行分词预处理, 返回空格分隔的词序列。

        中文文本使用 jieba 分词; 其他语言按空格/标点分词。
        TfidfVectorizer 要求输入为空格分隔的词序列。

        参数:
            text: 原始文本

        返回:
            空格分隔的分词结果 (字符串)
        """
        if not text or not text.strip():
            return ""

        # 检测是否含中文 → 用 jieba 分词
        has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in text)
        if has_chinese:
            try:
                import jieba

                words = jieba.lcut(text)
                # 过滤空白和单字符标点
                words = [w.strip() for w in words if w.strip() and len(w.strip()) > 0]
                return " ".join(words)
            except ImportError:
                # jieba 未安装时, 按字符分割中文
                logger.debug("jieba 未安装, 中文按字符分割")
                return " ".join(text)

        # 非中文: 直接返回 (TfidfVectorizer 自带分词)
        return text

    # ==================================================================
    # _extract_keywords - TF-IDF 关键词提取
    # ==================================================================

    def _extract_keywords(
        self,
        texts: List[str],
        top_n: int = 5,
    ) -> List[str]:
        """使用 TF-IDF 提取关键词。

        对多文档计算 TF-IDF, 按权重排序取 top_n 关键词。

        参数:
            texts  : 文本列表
            top_n  : 返回的关键词数量上限

        返回:
            关键词列表 (按 TF-IDF 权重降序)
            空输入返回空列表
        """
        if not texts:
            return []

        # 过滤空文本
        non_empty = [t for t in texts if t and t.strip()]
        if not non_empty:
            return []

        tokenized = [self._tokenize(t) for t in non_empty]

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError:
            # sklearn 未安装时, 退化为词频统计
            logger.warning("scikit-learn 未安装, 关键词提取降级为词频统计")
            return self._fallback_keywords(tokenized, top_n)

        try:
            vectorizer = TfidfVectorizer(
                analyzer=lambda x: x.split(),
                max_features=1000,
            )
            tfidf_matrix = vectorizer.fit_transform(tokenized)
        except ValueError:
            return self._fallback_keywords(tokenized, top_n)

        feature_names = vectorizer.get_feature_names_out()
        if len(feature_names) == 0:
            return []

        # 对所有文档的 TF-IDF 求和, 取 top_n
        import numpy as np

        word_scores = np.asarray(tfidf_matrix.sum(axis=0)).flatten()
        top_indices = word_scores.argsort()[::-1][:top_n]
        keywords = [feature_names[i] for i in top_indices if word_scores[i] > 0]
        return keywords

    # ==================================================================
    # _generate_topic_name - 生成话题名
    # ==================================================================

    def _generate_topic_name(self, keywords: List[str]) -> str:
        """从关键词生成话题名。

        将 top 关键词用 "/" 拼接, 取前 3 个。
        空关键词列表返回默认话题名。

        参数:
            keywords: 关键词列表

        返回:
            话题名字符串 (非空)
        """
        if not keywords:
            return "未命名话题"
        # 取前 3 个关键词拼接
        top_keywords = keywords[:3]
        return "/".join(top_keywords)

    # ==================================================================
    # 辅助方法
    # ==================================================================

    def _all_texts_identical(self, texts: List[str]) -> bool:
        """检查所有文本是否完全相同 (忽略首尾空白)。"""
        if len(texts) <= 1:
            return True
        first = texts[0].strip()
        return all(t.strip() == first for t in texts[1:])

    def _build_single_cluster(
        self,
        items: List[Dict[str, Any]],
        texts: List[str],
    ) -> List[Dict[str, Any]]:
        """将所有项构建为单一聚类 (边界场景降级)。"""
        keywords = self._extract_keywords(texts, top_n=5)
        topic_name = self._generate_topic_name(keywords)
        representative = self._select_representative_text(texts)
        return [
            {
                "topic_name": topic_name,
                "items_count": len(items),
                "keywords": keywords,
                "representative_text": representative,
                "items": list(items),
            }
        ]

    def _build_cluster_summaries(
        self,
        items: List[Dict[str, Any]],
        texts: List[str],
        labels: Any,
        tfidf_matrix: Any,
        feature_names: Any,
        n_clusters: int,
    ) -> List[Dict[str, Any]]:
        """构建聚类摘要列表。"""
        import numpy as np

        summaries: List[Dict[str, Any]] = []

        for cluster_id in range(n_clusters):
            # 收集该聚类的项索引
            member_indices = [
                i for i, label in enumerate(labels) if label == cluster_id
            ]
            if not member_indices:
                continue

            # 提取该聚类的项与文本
            cluster_items = [items[i] for i in member_indices]
            cluster_texts = [texts[i] for i in member_indices]

            # 提取关键词 (基于该聚类的 TF-IDF 子矩阵)
            keywords = self._extract_cluster_keywords(
                tfidf_matrix, member_indices, feature_names, top_n=5
            )

            topic_name = self._generate_topic_name(keywords)
            representative = self._select_representative_text(cluster_texts)

            summaries.append(
                {
                    "topic_name": topic_name,
                    "items_count": len(cluster_items),
                    "keywords": keywords,
                    "representative_text": representative,
                    "items": cluster_items,
                }
            )

        # 按 items_count 降序排列
        summaries.sort(key=lambda x: x["items_count"], reverse=True)
        return summaries

    def _extract_cluster_keywords(
        self,
        tfidf_matrix: Any,
        member_indices: List[int],
        feature_names: Any,
        top_n: int = 5,
    ) -> List[str]:
        """从 TF-IDF 子矩阵提取聚类关键词。"""
        import numpy as np

        # 提取该聚类的 TF-IDF 行, 求均值
        sub_matrix = tfidf_matrix[member_indices]
        word_scores = np.asarray(sub_matrix.mean(axis=0)).flatten()

        if len(word_scores) == 0:
            return []

        top_indices = word_scores.argsort()[::-1][:top_n]
        keywords = [
            feature_names[i] for i in top_indices if word_scores[i] > 0
        ]
        return keywords

    def _select_representative_text(self, texts: List[str]) -> str:
        """选择聚类中的代表性文本 (选择最长的非空文本)。"""
        non_empty = [t for t in texts if t and t.strip()]
        if not non_empty:
            return ""
        return max(non_empty, key=len)

    def _fallback_keywords(
        self,
        tokenized_texts: List[str],
        top_n: int,
    ) -> List[str]:
        """无 sklearn 时的词频降级关键词提取。"""
        from collections import Counter

        word_freq: Counter = Counter()
        for text in tokenized_texts:
            words = text.split()
            word_freq.update(words)
        return [word for word, _ in word_freq.most_common(top_n)]


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["TopicClusterer"]

# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 爆品预测器 (Task 10)
# ==============================================================================
# 对应 spec §4.5 爆品预测模型 · 预测与可解释性:
#   加载训练好的 XGBoost 模型, 对产品进行爆品概率预测,
#   并输出 SHAP Top-3 影响因子 (可解释性)。
#
# HitPredictor 设计要点:
#   - 加载: 从 JSON 文件加载训练好的 XGBoost 模型
#   - 预测: predict_proba → hitScore ∈ [0,1]
#   - 可解释性: SHAP TreeExplainer 输出 Top-3 影响因子
#   - 降级: SHAP 不可用时, 使用 feature_importances_ 作为 Top-3 因子
#   - 批量: predict_batch 支持多产品批量预测
#
# 输出格式 (匹配 spec §4.4 ProductIdeaCard.hitScore + topFactors):
#   {
#       "hitScore": float,              # 爆品概率 0-1
#       "topFactors": [                 # Top-3 影响因子
#           {"feature": str, "shap_value": float},
#           ...
#       ]
#   }
# ==============================================================================

"""
爆品预测器模块 (spec §4.5)。

加载训练好的 XGBoost 模型, 对产品进行爆品概率预测 (hitScore ∈ [0,1]),
并通过 SHAP 值输出 Top-3 影响因子 (可解释性)。

SHAP 集成策略:
    1. 优先使用 ``shap.TreeExplainer`` 计算 SHAP 值 (精确可解释性)
    2. SHAP 不可用或异常时, 降级为 ``model.feature_importances_``
       (全局特征重要性, 非样本级 SHAP, 但保证可用性)

用法::

    predictor = HitPredictor()  # 加载默认模型 backend/data/xgboost_model.json
    result = predictor.predict({"category_heat": 85.0, ...})
    # → {"hitScore": 0.82, "topFactors": [{"feature": "...", "shap_value": ...}, ...]}

    # 批量预测
    results = predictor.predict_batch([raw1, raw2, raw3])
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from xgboost import XGBClassifier

from ideaforge.models.features import FeatureExtractor
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)

# ==============================================================================
# 常量 - 默认路径与 Top-N 因子数
# ==============================================================================

# backend/ 目录 (本文件: backend/ideaforge/models/ → 上两级)
_BACKEND_DIR: Path = Path(__file__).resolve().parent.parent.parent

# 默认模型路径
DEFAULT_MODEL_PATH: Path = _BACKEND_DIR / "data" / "xgboost_model.json"
"""默认模型路径 (backend/data/xgboost_model.json)。"""

# Top-N 影响因子数量 (spec §4.5: Top-3)
_TOP_N_FACTORS: int = 3
"""输出 Top-N 影响因子数量 (spec §4.5 规定为 3)。"""


# ==============================================================================
# HitPredictor 爆品预测器
# ==============================================================================


class HitPredictor:
    """爆品预测器 (spec §4.5)。

    加载训练好的 XGBoost 模型, 对产品进行爆品概率预测,
    并通过 SHAP 值输出 Top-3 影响因子。

    SHAP 降级策略:
        - 优先: ``shap.TreeExplainer`` → 样本级 SHAP 值 (精确可解释性)
        - 降级: ``model.feature_importances_`` → 全局重要性 (保证可用性)
        降级时 topFactors 中使用 ``importance`` 键而非 ``shap_value``。

    用法::

        predictor = HitPredictor()
        result = predictor.predict({"category_heat": 85.0, ...})
        # result = {"hitScore": 0.82, "topFactors": [...]}
    """

    # ==================================================================
    # __init__ - 加载模型
    # ==================================================================

    def __init__(self, model_path: Optional[str] = None) -> None:
        """初始化爆品预测器, 加载 XGBoost 模型。

        参数:
            model_path: 模型 JSON 文件路径。
                        为 None 时使用默认路径 ``backend/data/xgboost_model.json``。

        异常:
            FileNotFoundError: 模型文件不存在时抛出
            XGBoostError: 模型加载失败时抛出
        """
        resolved_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        logger.debug(f"HitPredictor: 加载模型 path={resolved_path}")

        self._model = XGBClassifier()
        self._model.load_model(str(resolved_path))

        # 兼容性修复: xgboost 2.0.3 + scikit-learn >= 1.6
        # load_model() 内部使用 sklearn.base.is_classifier() 判断是否分类器,
        # 但新版 sklearn 对未 fit 的估计器返回 False, 导致 n_classes_ 未被设置。
        # 此处手动设置 n_classes_ = 2 (爆品预测为二分类: is_hit 0/1)。
        if not hasattr(self._model, "n_classes_"):
            self._model.n_classes_ = 2

        self._extractor = FeatureExtractor()
        self._feature_names = FeatureExtractor.FEATURE_NAMES

        # 延迟初始化 SHAP explainer (首次预测时创建)
        self._explainer = None
        self._shap_available: Optional[bool] = None
        """SHAP 可用性标志: None=未检测 / True=可用 / False=降级。"""

        logger.info(f"HitPredictor: 模型已加载 ({resolved_path.name})")

    # ==================================================================
    # predict - 单条预测
    # ==================================================================

    def predict(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """预测单个产品的爆品概率与 Top-3 影响因子。

        流程:
            1. FeatureExtractor 提取 19 维特征
            2. XGBoost predict_proba → hitScore (正类概率)
            3. SHAP / feature_importances_ → Top-3 影响因子

        参数:
            raw_data: 原始产品数据字典 (含 19 特征键, 允许缺失)。

        返回:
            ``{"hitScore": float, "topFactors": [{"feature": str, "shap_value": float}, ...]}``

            - hitScore: 爆品概率 ∈ [0, 1]
            - topFactors: Top-3 影响因子列表, 每项含 feature 名 + shap_value
              (SHAP 不可用时使用 importance 键, 全局特征重要性)
        """
        # 1. 提取特征
        features = self._extractor.extract(raw_data)
        X = np.array([features], dtype=float)

        # 2. 预测爆品概率 (正类 = is_hit=1)
        proba = self._model.predict_proba(X)
        hit_score = float(proba[0, 1])

        # 3. 计算 Top-3 影响因子 (SHAP 优先, 降级 feature_importances_)
        top_factors = self._compute_top_factors(X)

        logger.debug(
            f"predict: hitScore={hit_score:.4f}, "
            f"top_factors={[f['feature'] for f in top_factors]}"
        )

        return {
            "hitScore": hit_score,
            "topFactors": top_factors,
        }

    # ==================================================================
    # predict_batch - 批量预测
    # ==================================================================

    def predict_batch(self, raw_data_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量预测多个产品的爆品概率与 Top-3 影响因子。

        参数:
            raw_data_list: 原始产品数据字典列表。

        返回:
            预测结果列表, 每项格式与 ``predict()`` 一致。
            空输入返回空列表。
        """
        if not raw_data_list:
            return []

        # 批量提取特征矩阵
        features_batch = self._extractor.extract_batch(raw_data_list)
        X = np.array(features_batch, dtype=float)

        # 批量预测爆品概率
        proba = self._model.predict_proba(X)
        hit_scores = proba[:, 1]

        # 批量计算 Top-3 影响因子
        # SHAP 支持批量计算; feature_importances_ 为全局值 (每条相同)
        top_factors_batch = self._compute_top_factors_batch(X)

        results = [
            {
                "hitScore": float(hit_scores[i]),
                "topFactors": top_factors_batch[i],
            }
            for i in range(len(raw_data_list))
        ]

        logger.debug(f"predict_batch: 预测 {len(results)} 条产品")

        return results

    # ==================================================================
    # 内部辅助 - SHAP / feature_importances_ Top-N 因子计算
    # ==================================================================

    def _ensure_explainer(self) -> None:
        """延迟初始化 SHAP TreeExplainer, 检测可用性。

        首次调用时尝试创建 ``shap.TreeExplainer``。
        若 SHAP 不可用或创建失败, 标记 ``_shap_available = False`` (降级模式)。
        """
        if self._shap_available is not None:
            return  # 已检测过

        try:
            import shap

            self._explainer = shap.TreeExplainer(self._model)
            self._shap_available = True
            logger.info("HitPredictor: SHAP TreeExplainer 已启用 (精确可解释性)")
        except Exception as exc:
            # SHAP 不可用: 降级为 feature_importances_
            self._explainer = None
            self._shap_available = False
            logger.warning(
                f"HitPredictor: SHAP 不可用, 降级为 feature_importances_ "
                f"(原因: {exc})"
            )

    def _compute_top_factors(self, X: np.ndarray) -> List[Dict[str, Any]]:
        """计算单条样本的 Top-3 影响因子。

        SHAP 可用时: 返回样本级 SHAP 值 (绝对值最大的 3 个特征)。
        SHAP 不可用时: 返回全局 feature_importances_ (最大的 3 个特征)。

        参数:
            X: 特征矩阵 (单条样本, shape=(1, 19))

        返回:
            Top-3 影响因子列表, 每项:
            - SHAP 模式: ``{"feature": str, "shap_value": float}``
            - 降级模式: ``{"feature": str, "importance": float}``
        """
        self._ensure_explainer()

        if self._shap_available and self._explainer is not None:
            try:
                return self._compute_top_factors_shap(X)
            except Exception as exc:
                # SHAP 计算失败: 降级为 feature_importances_
                self._shap_available = False
                self._explainer = None
                logger.warning(
                    f"HitPredictor: SHAP 计算失败, 降级为 feature_importances_ "
                    f"(原因: {exc})"
                )
        return self._compute_top_factors_importance()

    def _compute_top_factors_batch(
        self, X: np.ndarray
    ) -> List[List[Dict[str, Any]]]:
        """批量计算 Top-3 影响因子。

        SHAP 可用时: 批量计算 SHAP 值 (每条样本独立 Top-3)。
        SHAP 不可用时: 全局 feature_importances_ (每条样本相同 Top-3)。

        参数:
            X: 特征矩阵 (shape=(n, 19))

        返回:
            每条样本的 Top-3 影响因子列表 (list[list[dict]])
        """
        self._ensure_explainer()

        if self._shap_available and self._explainer is not None:
            try:
                # SHAP 批量计算: 一次性计算所有样本的 SHAP 值
                shap_values = self._explainer.shap_values(X)
                shap_arr = np.array(shap_values)  # shape=(n, 19)

                # 兼容 XGBoost 二分类: shap_values 可能返回单数组或列表
                if isinstance(shap_values, list):
                    # 取正类 (index=1) 的 SHAP 值
                    shap_arr = np.array(shap_values[1]) if len(shap_values) > 1 else np.array(shap_values[0])

                results = []
                for i in range(shap_arr.shape[0]):
                    results.append(self._top_n_from_values(shap_arr[i], use_shap=True))
                return results
            except Exception as exc:
                # SHAP 计算失败: 降级为 feature_importances_
                self._shap_available = False
                self._explainer = None
                logger.warning(
                    f"HitPredictor: SHAP 批量计算失败, 降级为 feature_importances_ "
                    f"(原因: {exc})"
                )

        # 降级模式: 全局重要性 (每条样本相同)
        importance_factors = self._compute_top_factors_importance()
        return [importance_factors for _ in range(X.shape[0])]

    def _compute_top_factors_shap(self, X: np.ndarray) -> List[Dict[str, Any]]:
        """使用 SHAP TreeExplainer 计算单条样本的 Top-3 因子。

        参数:
            X: 特征矩阵 (shape=(1, 19))

        返回:
            Top-3 影响因子列表, 每项 ``{"feature": str, "shap_value": float}``。
            按绝对 SHAP 值降序排列 (影响最大的 3 个)。
        """
        assert self._explainer is not None

        shap_values = self._explainer.shap_values(X)
        shap_arr = np.array(shap_values)

        # 兼容二分类: shap_values 可能返回 [class0, class1] 列表
        if isinstance(shap_values, list):
            shap_arr = (
                np.array(shap_values[1])
                if len(shap_values) > 1
                else np.array(shap_values[0])
            )

        # 取第一条样本 (shape=(19,))
        sample_shap = shap_arr[0] if shap_arr.ndim > 1 else shap_arr
        return self._top_n_from_values(sample_shap, use_shap=True)

    def _compute_top_factors_importance(self) -> List[Dict[str, Any]]:
        """使用 model.feature_importances_ 计算全局 Top-3 因子 (降级模式)。

        返回:
            Top-3 影响因子列表, 每项 ``{"feature": str, "importance": float}``。
            按重要性降序排列。
        """
        importances = self._model.feature_importances_
        return self._top_n_from_values(importances, use_shap=False)

    def _top_n_from_values(
        self, values: np.ndarray, use_shap: bool
    ) -> List[Dict[str, Any]]:
        """从数值数组中提取 Top-N 因子 (按绝对值降序)。

        参数:
            values  : SHAP 值或 feature_importances_ 数组 (shape=(19,))
            use_shap: True 时键为 ``shap_value``, False 时键为 ``importance``

        返回:
            Top-N 影响因子列表 (N = _TOP_N_FACTORS = 3)。
            SHAP 模式按绝对值降序; importance 模式按值降序。
        """
        # 按绝对值降序排列的索引
        sorted_indices = np.argsort(np.abs(values))[::-1][:_TOP_N_FACTORS]

        key = "shap_value" if use_shap else "importance"
        return [
            {
                "feature": self._feature_names[idx],
                key: float(values[idx]),
            }
            for idx in sorted_indices
        ]


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["HitPredictor"]

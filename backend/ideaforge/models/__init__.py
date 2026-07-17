"""IdeaForge 模型模块。

包含 XGBoost 评分模型、SHAP 可解释性分析、
决策建议排序与置信度计算等模型逻辑。

子模块:
    - features  : FeatureExtractor 特征提取器 (19 维特征向量)
    - train     : train_model XGBoost 模型训练
    - predict   : HitPredictor 爆品预测器 (hitScore + SHAP Top-3 因子)
"""

from ideaforge.models.features import FeatureExtractor
from ideaforge.models.predict import HitPredictor
from ideaforge.models.train import train_model

__all__ = ["FeatureExtractor", "HitPredictor", "train_model"]

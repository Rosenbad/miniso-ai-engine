# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - XGBoost 爆品预测模型训练 (Task 10)
# ==============================================================================
# 对应 spec §4.5 爆品预测模型:
#   使用 XGBoost 分类器训练爆品预测模型, 评估 AUC, 保存模型。
#
# 训练流程:
#   1. 加载 CSV 数据 (backend/data/mock_skus.csv, 500 条, 19 特征 + is_hit)
#   2. 提取特征矩阵 X (19 维) 与标签 y (0/1)
#   3. 80/20 训练/测试集划分
#   4. 训练 XGBClassifier (n_estimators=100, max_depth=4, learning_rate=0.1)
#   5. 评估 AUC + accuracy (测试集)
#   6. 保存模型为 JSON (xgboost 原生格式)
#   7. 返回指标字典 {auc, accuracy, model_path, feature_importance}
#
# 模型规格 (spec §4.5):
#   - 目标: hitScore ∈ [0,1], 阈值 > 0.7 进入验证池
#   - AUC 目标: > 0.75 (mock 数据可能较低, 确保模型可训练可预测即可)
#   - 可解释性: SHAP 值输出 Top-3 影响因子 (见 predict.py)
# ==============================================================================

"""
XGBoost 爆品预测模型训练模块 (spec §4.5)。

在模拟 SKU 数据 (500 条, 19 特征 + is_hit 标签) 上训练 XGBoost 二分类器,
评估 AUC 与 accuracy, 保存模型为 JSON 格式供 HitPredictor 加载。

训练参数:
    n_estimators=100, max_depth=4, learning_rate=0.1,
    eval_metric='logloss', random_state=42

用法::

    # 使用默认路径训练 (backend/data/mock_skus.csv → backend/data/xgboost_model.json)
    metrics = train_model()
    print(metrics["auc"], metrics["accuracy"])

    # 自定义路径
    metrics = train_model(csv_path="data.csv", model_output_path="model.json")

CLI::

    python backend/ideaforge/models/train.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from ideaforge.models.features import FeatureExtractor
from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)

# ==============================================================================
# 常量 - 默认路径与训练参数
# ==============================================================================

# backend/ 目录 (本文件: backend/ideaforge/models/ → 上两级)
_BACKEND_DIR: Path = Path(__file__).resolve().parent.parent.parent

# 默认 CSV 数据路径
DEFAULT_CSV_PATH: Path = _BACKEND_DIR / "data" / "mock_skus.csv"
"""默认模拟 SKU 数据路径 (backend/data/mock_skus.csv)。"""

# 默认模型输出路径
DEFAULT_MODEL_OUTPUT_PATH: Path = _BACKEND_DIR / "data" / "xgboost_model.json"
"""默认模型输出路径 (backend/data/xgboost_model.json)。"""

# 训练参数 (spec §4.5)
_RANDOM_STATE: int = 42
"""随机种子, 保证训练可复现。"""

_TEST_SIZE: float = 0.2
"""测试集比例 (80/20 划分)。"""

_XGB_PARAMS: Dict[str, Any] = {
    "n_estimators": 100,
    "max_depth": 4,
    "learning_rate": 0.1,
    "eval_metric": "logloss",
    "random_state": _RANDOM_STATE,
    "use_label_encoder": False,
}
"""XGBClassifier 超参数 (spec §4.5)。"""


# ==============================================================================
# 训练核心函数
# ==============================================================================


def train_model(
    csv_path: str | None = None,
    model_output_path: str | None = None,
) -> Dict[str, Any]:
    """训练 XGBoost 爆品分类器并保存模型。

    流程:
        1. 加载 CSV 数据 (19 特征 + is_hit)
        2. 80/20 训练/测试集划分
        3. 训练 XGBClassifier (n_estimators=100, max_depth=4, lr=0.1)
        4. 评估 AUC + accuracy (测试集)
        5. 保存模型为 JSON (xgboost 原生格式)
        6. 返回指标字典

    参数:
        csv_path          : 模拟 SKU 数据 CSV 路径。
                            为 None 时使用默认路径 ``backend/data/mock_skus.csv``。
        model_output_path : 模型输出 JSON 路径。
                            为 None 时使用默认路径 ``backend/data/xgboost_model.json``。

    返回:
        指标字典::
            {
                "auc": float,               # 测试集 AUC (0-1)
                "accuracy": float,          # 测试集 accuracy (0-1)
                "model_path": str,          # 模型保存路径
                "feature_importance": dict, # {feature_name: importance}
            }

    异常:
        FileNotFoundError: CSV 文件不存在时抛出
    """
    resolved_csv = Path(csv_path) if csv_path else DEFAULT_CSV_PATH
    resolved_model_path = (
        Path(model_output_path) if model_output_path else DEFAULT_MODEL_OUTPUT_PATH
    )

    logger.info(f"train_model: 加载数据 csv={resolved_csv}")

    # 1. 加载 CSV 数据
    df = pd.read_csv(resolved_csv)
    logger.info(f"train_model: 已加载 {len(df)} 条 SKU 数据")

    # 2. 提取特征矩阵 X 与标签 y
    feature_names = FeatureExtractor.FEATURE_NAMES
    X = df[feature_names].to_numpy(dtype=float)
    y = df["is_hit"].to_numpy(dtype=int)

    n_hits = int(y.sum())
    logger.info(
        f"train_model: 特征矩阵 shape={X.shape}, "
        f"爆品 {n_hits} ({n_hits / len(y):.1%}) / 非爆品 {len(y) - n_hits}"
    )

    # 3. 训练/测试集划分 (80/20, 分层抽样保持标签比例)
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=_TEST_SIZE,
        random_state=_RANDOM_STATE,
        stratify=y,
    )

    # 4. 训练 XGBoost 分类器
    model = XGBClassifier(**_XGB_PARAMS)
    model.fit(X_train, y_train)

    # 5. 评估 AUC + accuracy (测试集)
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred = model.predict(X_test)

    auc = float(roc_auc_score(y_test, y_pred_proba))
    accuracy = float(accuracy_score(y_test, y_pred))

    logger.info(
        f"train_model: 训练完成 auc={auc:.4f} accuracy={accuracy:.4f} "
        f"(test_size={len(y_test)})"
    )

    # 6. 保存模型 (xgboost 原生 JSON 格式)
    resolved_model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(resolved_model_path))
    logger.info(f"train_model: 模型已保存 → {resolved_model_path}")

    # 7. 提取特征重要性 (供调试与可解释性)
    importance_dict = model.feature_importances_
    feature_importance: Dict[str, float] = {
        name: float(imp) for name, imp in zip(feature_names, importance_dict)
    }

    return {
        "auc": auc,
        "accuracy": accuracy,
        "model_path": str(resolved_model_path),
        "feature_importance": feature_importance,
    }


# ==============================================================================
# CLI 入口
# ==============================================================================

if __name__ == "__main__":
    metrics = train_model()
    print(
        f"\n训练完成:\n"
        f"  AUC      : {metrics['auc']:.4f}\n"
        f"  Accuracy : {metrics['accuracy']:.4f}\n"
        f"  模型路径 : {metrics['model_path']}\n"
        f"  Top-5 特征重要性:"
    )
    for name, imp in sorted(
        metrics["feature_importance"].items(), key=lambda x: x[1], reverse=True
    )[:5]:
        print(f"    {name:40s} {imp:.4f}")

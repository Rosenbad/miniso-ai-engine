# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 趋势预测器 (Task 6)
# ==============================================================================
# 对应 spec §3.2 NLP 处理流水线 - 趋势预测:
#   Prophet 时序预测, 输出未来 2-4 周热度走向
#
# TrendPredictor 负责 NLP 流水线的第 4 阶段:
#   1. Prophet 时序预测 (生产环境, 需安装 prophet + cmdstanpy)
#   2. 线性外推降级 (Prophet 不可用时的兜底方案)
#   3. 生命周期判定 (rising / peak / declining)
#   4. 周环比增长率计算
#
# 设计要点:
#   - Prophet 延迟导入, 不可用时自动降级为线性外推
#   - 线性外推基于最小二乘法拟合历史趋势
#   - 生命周期判定基于预测值线性回归斜率 (相对阈值)
#   - 周环比增长率 = ((本周值 - 上周值) / 上周值) × 100
#   - predict_window 格式: f"{weeks}-{2*weeks}周" (如 14 天 → "2-4周")
# ==============================================================================

"""
趋势预测器模块。

NLP 处理流水线第 4 阶段: 趋势预测。

类:
    TrendPredictor - Prophet 时序预测 + 线性外推降级

用法::

    predictor = TrendPredictor()
    result = predictor.predict(historical_data, forecast_days=14)
    # result: {lifecycle, predict_window, predicted_values, growth_rate}
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from trendpulse.collectors.utils import setup_logger

logger = setup_logger(__name__)


# ==============================================================================
# TrendPredictor 趋势预测器
# ==============================================================================


class TrendPredictor:
    """趋势预测器 - NLP 流水线第 4 阶段 (趋势预测)。

    使用 Prophet 时序预测 (spec §3.2), Prophet 不可用时降级为线性外推。

    输出:
        - lifecycle       : 生命周期阶段 (rising / peak / declining)
        - predict_window  : 预测窗口 (如 "2-4周")
        - predicted_values: 预测值列表 [{date, value}, ...]
        - growth_rate     : 周环比增长率 (%)

    用法::

        predictor = TrendPredictor()
        result = predictor.predict(historical_data, forecast_days=14)
    """

    # 生命周期判定的相对斜率阈值 (预测值每日变化 / 均值)
    # 超过此阈值判定为上升/衰退, 否则为峰值平稳
    LIFECYCLE_SLOPE_THRESHOLD: float = 0.005

    # ==================================================================
    # predict() - 主入口
    # ==================================================================

    def predict(
        self,
        historical_data: List[Dict[str, Any]],
        forecast_days: int = 14,
    ) -> Dict[str, Any]:
        """趋势预测主入口 — Prophet 优先, 线性降级兜底。

        参数:
            historical_data: 历史时序数据, 每条为 ``{date: "YYYY-MM-DD", value: float}``
                             按日期升序排列
            forecast_days  : 预测天数 (默认 14, 对应 "2-4周")

        返回:
            ``{lifecycle, predict_window, predicted_values, growth_rate}``
            - lifecycle       : "rising" / "peak" / "declining"
            - predict_window  : 如 "2-4周"
            - predicted_values: [{date, value}, ...] 共 forecast_days 条
            - growth_rate     : 周环比增长率 (%)
        """
        # 计算 predict_window
        predict_window = self._format_predict_window(forecast_days)

        # 计算周环比增长率
        growth_rate = self._calculate_growth_rate(historical_data)

        # 生成预测值 (Prophet 优先, 线性降级)
        predicted_values = self._generate_predictions(
            historical_data, forecast_days
        )

        # 判定生命周期
        lifecycle = self._determine_lifecycle(
            historical_data, predicted_values
        )

        return {
            "lifecycle": lifecycle,
            "predict_window": predict_window,
            "predicted_values": predicted_values,
            "growth_rate": growth_rate,
        }

    # ==================================================================
    # _prophet_predict - Prophet 时序预测
    # ==================================================================

    def _prophet_predict(
        self,
        df: Any,
        forecast_days: int,
    ) -> List[Dict[str, Any]]:
        """使用 Prophet 进行时序预测。

        Prophet 要求输入 DataFrame 含 ``ds`` (日期) 和 ``y`` (值) 两列。
        本方法延迟导入 prophet, 不可用时抛 ImportError (由调用方降级)。

        参数:
            df            : pandas.DataFrame, 含 ``ds`` 和 ``y`` 列
            forecast_days : 预测天数

        返回:
            预测值列表 [{date, value}, ...]

        异常:
            ImportError: prophet 未安装时抛出
        """
        from prophet import Prophet  # 延迟导入

        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=False,
        )
        model.fit(df)

        # 生成未来 forecast_days 天的日期
        future = model.make_future_dataframe(periods=forecast_days)
        forecast = model.predict(future)

        # 提取预测部分 (最后 forecast_days 行)
        predicted: List[Dict[str, Any]] = []
        tail = forecast.tail(forecast_days)
        for _, row in tail.iterrows():
            date_str = row["ds"].strftime("%Y-%m-%d")
            value = float(row["yhat"])
            predicted.append({"date": date_str, "value": round(value, 2)})

        return predicted

    # ==================================================================
    # _linear_fallback - 线性外推降级
    # ==================================================================

    def _linear_fallback(
        self,
        data: List[Dict[str, Any]],
        forecast_days: int,
    ) -> List[Dict[str, Any]]:
        """线性外推降级预测 (Prophet 不可用时使用)。

        基于最小二乘法拟合历史数据的线性趋势, 外推 forecast_days 天。
        数据不足 (0-1 条) 时, 用最后一个值 (或 0) 作为恒定预测。

        参数:
            data          : 历史时序数据 [{date, value}, ...]
            forecast_days : 预测天数

        返回:
            预测值列表 [{date, value}, ...] 共 forecast_days 条
        """
        if not data:
            # 无历史数据: 返回 0 值预测
            return self._generate_zero_predictions(forecast_days)

        if len(data) == 1:
            # 单条数据: 用该值作为恒定预测
            last_value = float(data[0].get("value", 0))
            last_date = self._parse_date(data[0].get("date", ""))
            return self._generate_constant_predictions(
                last_date, last_value, forecast_days
            )

        # 提取 x (索引) 与 y (值)
        x_values = list(range(len(data)))
        y_values = [float(item.get("value", 0)) for item in data]

        # 最小二乘法线性拟合: y = a + b*x
        slope, intercept = self._linear_fit(x_values, y_values)

        # 从最后一个历史日期的次日开始外推
        last_date = self._parse_date(data[-1].get("date", ""))
        last_x = x_values[-1]

        predicted: List[Dict[str, Any]] = []
        for i in range(1, forecast_days + 1):
            future_x = last_x + i
            future_value = intercept + slope * future_x
            future_date = last_date + timedelta(days=i)
            predicted.append(
                {
                    "date": future_date.strftime("%Y-%m-%d"),
                    "value": round(future_value, 2),
                }
            )

        return predicted

    # ==================================================================
    # _determine_lifecycle - 生命周期判定
    # ==================================================================

    def _determine_lifecycle(
        self,
        historical: List[Dict[str, Any]],
        predicted: List[Dict[str, Any]],
    ) -> str:
        """判定趋势的生命周期阶段。

        基于预测值的线性回归斜率 (相对均值归一化):
            - slope > 阈值 → "rising" (上升期)
            - slope < -阈值 → "declining" (衰退期)
            - |slope| ≤ 阈值 → "peak" (峰值/平稳期)

        参数:
            historical: 历史数据 (本方法未使用, 保留接口供扩展)
            predicted : 预测数据 [{date, value}, ...]

        返回:
            "rising" / "peak" / "declining"
        """
        if not predicted or len(predicted) < 2:
            return "peak"

        values = [float(p.get("value", 0)) for p in predicted]
        n = len(values)

        # 线性回归斜率
        x_values = list(range(n))
        slope, _ = self._linear_fit(x_values, values)

        # 归一化: 斜率 / 均值绝对值 (避免值域影响判定)
        mean_value = sum(abs(v) for v in values) / n if n > 0 else 0
        if mean_value == 0:
            # 均值为 0 时用绝对斜率
            rel_slope = slope
        else:
            rel_slope = slope / mean_value

        if rel_slope > self.LIFECYCLE_SLOPE_THRESHOLD:
            return "rising"
        elif rel_slope < -self.LIFECYCLE_SLOPE_THRESHOLD:
            return "declining"
        else:
            return "peak"

    # ==================================================================
    # _calculate_growth_rate - 周环比增长率
    # ==================================================================

    def _calculate_growth_rate(
        self,
        historical: List[Dict[str, Any]],
    ) -> float:
        """计算周环比增长率。

        公式: ``((本周值 - 上周值) / 上周值) × 100``
        - 本周值 = 最后一个数据点的值
        - 上周值 = 7 天前的数据点值

        数据不足一周 (少于 8 条日数据) 时返回 0.0。

        参数:
            historical: 历史时序数据 [{date, value}, ...]

        返回:
            周环比增长率 (%) , 如 +34.2 表示 +34.2%
            数据不足或上周值为 0 时返回 0.0
        """
        if not historical or len(historical) < 8:
            return 0.0

        current_value = float(historical[-1].get("value", 0))
        week_ago_value = float(historical[-8].get("value", 0))

        if week_ago_value == 0:
            return 0.0

        growth_rate = ((current_value - week_ago_value) / week_ago_value) * 100
        return round(growth_rate, 2)

    # ==================================================================
    # 辅助方法
    # ==================================================================

    def _generate_predictions(
        self,
        historical_data: List[Dict[str, Any]],
        forecast_days: int,
    ) -> List[Dict[str, Any]]:
        """生成预测值 (Prophet 优先, 线性降级)。"""
        if not historical_data:
            return self._linear_fallback(historical_data, forecast_days)

        # 尝试 Prophet 路径
        try:
            import pandas as pd

            df = pd.DataFrame(
                {
                    "ds": [
                        self._parse_date(item.get("date", ""))
                        for item in historical_data
                    ],
                    "y": [float(item.get("value", 0)) for item in historical_data],
                }
            )
            return self._prophet_predict(df, forecast_days)
        except ImportError:
            logger.info("Prophet 未安装, 使用线性外推降级预测")
            return self._linear_fallback(historical_data, forecast_days)
        except Exception as exc:
            logger.warning(f"Prophet 预测异常, 降级为线性外推: {exc}")
            return self._linear_fallback(historical_data, forecast_days)

    def _format_predict_window(self, forecast_days: int) -> str:
        """格式化预测窗口字符串。

        forecast_days=14 → "2-4周" (2 周, 上限 4 周)
        forecast_days=7  → "1-2周"
        forecast_days=28 → "4-8周"

        参数:
            forecast_days: 预测天数

        返回:
            窗口字符串, 如 "2-4周"
        """
        weeks = max(1, forecast_days // 7)
        return f"{weeks}-{weeks * 2}周"

    def _linear_fit(
        self,
        x_values: List[float],
        y_values: List[float],
    ) -> tuple[float, float]:
        """最小二乘法线性拟合, 返回 (slope, intercept)。

        y = intercept + slope * x

        参数:
            x_values: x 坐标列表
            y_values: y 坐标列表

        返回:
            (slope, intercept) — 斜率与截距
        """
        n = len(x_values)
        if n == 0:
            return 0.0, 0.0
        if n == 1:
            return 0.0, float(y_values[0])

        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values))
        sum_x2 = sum(x * x for x in x_values)

        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            # 所有 x 相同 (不应发生), 返回水平线
            return 0.0, sum_y / n

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n
        return slope, intercept

    def _parse_date(self, date_str: str) -> datetime:
        """解析日期字符串, 失败时返回当前日期。

        参数:
            date_str: 日期字符串 (YYYY-MM-DD)

        返回:
            datetime 对象
        """
        if not date_str:
            return datetime.now()
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            return datetime.now()

    def _generate_zero_predictions(
        self,
        forecast_days: int,
    ) -> List[Dict[str, Any]]:
        """生成全 0 预测 (无历史数据时的兜底)。"""
        base = datetime.now()
        return [
            {
                "date": (base + timedelta(days=i + 1)).strftime("%Y-%m-%d"),
                "value": 0.0,
            }
            for i in range(forecast_days)
        ]

    def _generate_constant_predictions(
        self,
        last_date: datetime,
        value: float,
        forecast_days: int,
    ) -> List[Dict[str, Any]]:
        """生成恒定值预测 (单条历史数据时的兜底)。"""
        return [
            {
                "date": (last_date + timedelta(days=i + 1)).strftime(
                    "%Y-%m-%d"
                ),
                "value": round(value, 2),
            }
            for i in range(forecast_days)
        ]


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = ["TrendPredictor"]

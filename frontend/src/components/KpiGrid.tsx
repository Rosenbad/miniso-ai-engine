// ==============================================================================
// KpiGrid - KPI 关键指标卡片网格 (通用组件)
// ==============================================================================
// 展示一行/多行 KPI 指标卡片，常用于仪表盘顶部摘要。
//
// 特性:
//   - 支持自定义列数 (2 / 3 / 4 列响应式)
//   - 支持颜色主题 (default / success / warn / danger)
//   - 支持趋势展示 (up ↑ / down ↓ / flat →) + 趋势数值
//   - 纯展示组件，不含业务逻辑与数据请求
//
// 数据来源由调用方传入 items，可在 store 接入后替换静态值。
// ==============================================================================

export interface KpiItem {
  /** 指标名称 (label, 小字灰色) */
  label: string;
  /** 指标值 (主数值) */
  value: string | number;
  /** 单位 (附在数值右侧，小字浅灰) */
  unit?: string;
  /** 趋势方向 */
  trend?: "up" | "down" | "flat";
  /** 趋势数值文案 (如 "+12.5%") */
  trendValue?: string;
  /** 颜色主题 (作用于数值文本) */
  color?: "default" | "success" | "warn" | "danger";
}

export interface KpiGridProps {
  /** KPI 条目列表 */
  items: KpiItem[];
  /** 每行列数，默认 4 列 (小屏 2 列) */
  columns?: 2 | 3 | 4;
}

/** 列数 -> Tailwind grid 类名映射 */
const COL_CLASS: Record<NonNullable<KpiGridProps["columns"]>, string> = {
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-2 sm:grid-cols-4",
};

/** 颜色主题 -> 数值文本类名映射 */
const COLOR_CLASS: Record<NonNullable<KpiItem["color"]>, string> = {
  default: "text-gray-900",
  success: "text-green-600",
  warn: "text-amber-600",
  danger: "text-red-600",
};

/** 趋势方向 -> 箭头符号映射 */
const TREND_ICON: Record<NonNullable<KpiItem["trend"]>, string> = {
  up: "↑",
  down: "↓",
  flat: "→",
};

/** 趋势方向 -> 文本颜色类名映射 */
const TREND_COLOR_CLASS: Record<NonNullable<KpiItem["trend"]>, string> = {
  up: "text-green-500",
  down: "text-red-500",
  flat: "text-gray-400",
};

/**
 * KPI 关键指标卡片网格
 *
 * 纯展示组件，根据传入的 items 渲染指标卡片。
 */
export function KpiGrid({ items, columns = 4 }: KpiGridProps) {
  const colClass = COL_CLASS[columns];

  return (
    <div className={`grid ${colClass} gap-3`}>
      {items.map((item, idx) => {
        const color = item.color ?? "default";
        const trend = item.trend;
        return (
          <div
            key={idx}
            className="bg-white rounded-lg border border-gray-200 p-3 flex flex-col gap-1"
          >
            <span className="text-xs text-gray-500">{item.label}</span>
            <div className="flex items-baseline gap-1">
              <span className={`text-lg font-bold ${COLOR_CLASS[color]}`}>
                {item.value}
              </span>
              {item.unit && (
                <span className="text-xs text-gray-400">{item.unit}</span>
              )}
            </div>
            {trend && (
              <div className="flex items-center gap-1 text-xs">
                <span className={TREND_COLOR_CLASS[trend]}>
                  {TREND_ICON[trend]} {item.trendValue}
                </span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default KpiGrid;

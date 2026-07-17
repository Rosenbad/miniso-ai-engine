"use client";

// ==============================================================================
// IPMatchPanel - IP 匹配面板 (Task 15)
// ==============================================================================
// 展示 IPMatch 数据:
//   - IP 势能分 (ECharts gauge 仪表盘)
//   - 品类匹配度 (进度条)
//   - 区域热度分布 (ECharts 柱状热力)
//   - 可用性状态徽章 + 独家期
// spec §7.2 中栏: IP match panel
// ==============================================================================

import EChart from "./EChart";
import type { Availability, IPMatch } from "@/lib/types";
import type { EChartsOption } from "echarts";

// 可用性 → 徽章样式与中文标签
const AVAILABILITY_STYLES: Record<Availability, string> = {
  available: "bg-green-100 text-green-700",
  exclusive: "bg-brand-100 text-brand-700",
  expiring: "bg-amber-100 text-amber-700",
  unavailable: "bg-gray-200 text-gray-600",
};

const AVAILABILITY_LABELS: Record<Availability, string> = {
  available: "可授权",
  exclusive: "独家期",
  expiring: "即将到期",
  unavailable: "不可用",
};

// 区域 key → 中文
const REGION_LABELS: Record<string, string> = {
  china: "中国",
  sea: "东南亚",
  us: "美国",
  eu: "欧洲",
  global: "全球",
};

export interface IPMatchPanelProps {
  /** IP 匹配数据 */
  ipMatch: IPMatch;
  /** 是否紧凑模式 */
  compact?: boolean;
}

export default function IPMatchPanel({
  ipMatch,
  compact = false,
}: IPMatchPanelProps) {
  const {
    ipName,
    ipPowerScore,
    matchScore,
    availability,
    exclusiveUntil,
    regionHeatMap,
    recommendedCategories,
  } = ipMatch;

  // ---- 仪表盘配置 (IP 势能分) ----
  const gaugeOption: EChartsOption = {
    series: [
      {
        type: "gauge",
        startAngle: 200,
        endAngle: -20,
        min: 0,
        max: 100,
        progress: {
          show: true,
          width: compact ? 10 : 14,
          roundCap: true,
          itemStyle: {
            color:
              ipPowerScore >= 80
                ? "#16a34a"
                : ipPowerScore >= 60
                  ? "#f59e0b"
                  : "#ef4444",
          },
        },
        axisLine: { lineStyle: { width: compact ? 10 : 14, color: [[1, "#e5e7eb"]] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        pointer: { show: false },
        detail: {
          valueAnimation: true,
          fontSize: compact ? 18 : 24,
          fontWeight: "bold",
          offsetCenter: [0, "10%"],
          formatter: "{value}",
          color: "#374151",
        },
        title: {
          show: true,
          offsetCenter: [0, compact ? "55%" : "45%"],
          fontSize: 10,
          color: "#9ca3af",
        },
        data: [{ value: ipPowerScore, name: "势能分" }],
      },
    ],
  };

  // ---- 区域热度柱状图 ----
  const regionEntries = Object.entries(regionHeatMap ?? {});
  const heatOption: EChartsOption = {
    grid: { left: 4, right: 12, top: 8, bottom: 4, containLabel: true },
    xAxis: {
      type: "category",
      data: regionEntries.map(([k]) => REGION_LABELS[k] ?? k),
      axisLabel: { fontSize: 9, color: "#6b7280" },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#e5e7eb" } },
    },
    yAxis: {
      type: "value",
      show: regionEntries.length > 0,
      axisLabel: { fontSize: 9, color: "#9ca3af" },
      splitLine: { lineStyle: { color: "#f3f4f6" } },
    },
    series: [
      {
        type: "bar",
        data: regionEntries.map(([, v]) => v),
        barWidth: "50%",
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: "#f43f5e",
        },
      },
    ],
    tooltip: { trigger: "axis", confine: true },
  };

  const matchPercent = Math.round(matchScore * 100);

  return (
    <div className="rounded-lg border border-pink-100 bg-pink-50/40 p-3">
      {/* IP 名称 + 可用性徽章 */}
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10px] text-gray-400 font-mono">IP 联名匹配</div>
          <div className="text-sm font-semibold text-gray-900 truncate">
            {ipName}
          </div>
        </div>
        <span
          className={`flex-shrink-0 px-2 py-0.5 rounded-full text-[10px] font-medium ${
            AVAILABILITY_STYLES[availability]
          }`}
        >
          {AVAILABILITY_LABELS[availability]}
        </span>
      </div>

      {exclusiveUntil && (
        <div className="mt-1 text-[10px] text-gray-500">
          独家期至 <span className="font-mono">{exclusiveUntil}</span>
        </div>
      )}

      {/* 势能分仪表盘 + 匹配度进度 */}
      <div className="mt-2 grid grid-cols-2 gap-2">
        <EChart
          option={gaugeOption}
          style={{ height: compact ? 90 : 110 }}
        />
        <div className="flex flex-col justify-center">
          <div className="text-[10px] text-gray-500">品类匹配度</div>
          <div className="text-xl font-bold text-brand-600">{matchPercent}%</div>
          <div className="mt-1 w-full bg-gray-200 rounded-full h-1.5 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-700 transition-all"
              style={{ width: `${matchPercent}%` }}
            />
          </div>
          {recommendedCategories && recommendedCategories.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {recommendedCategories.slice(0, 3).map((c) => (
                <span
                  key={c}
                  className="px-1.5 py-0.5 rounded text-[9px] bg-white text-gray-600 border border-gray-200"
                >
                  {c}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 区域热度分布 */}
      {regionEntries.length > 0 && (
        <div className="mt-2">
          <div className="text-[10px] text-gray-500 mb-1">区域热度分布</div>
          <EChart
            option={heatOption}
            style={{ height: compact ? 70 : 90 }}
          />
        </div>
      )}
    </div>
  );
}

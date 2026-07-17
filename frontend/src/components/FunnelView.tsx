"use client";

// ==============================================================================
// FunnelView - 规模化漏斗图 (Task 15)
// ==============================================================================
// 渲染 万级→千级→百级→Top100 的规模化漏斗 (ECharts funnel)。
// 挂载时通过 store.fetchFunnel() 拉取 FunnelStatus，并展示阈值与 TopN。
// spec §7.1 step6: 切换漏斗模式展示规模化筛选。
// ==============================================================================

import { useEffect, useMemo } from "react";
import EChart from "./EChart";
import { useAppStore } from "@/lib/store";
import type { EChartsOption } from "echarts";

// 漏斗阶段配色 (从宽到窄)
const FUNNEL_COLORS = ["#f43f5e", "#fb7185", "#fda4af", "#fecdd3"];

export default function FunnelView() {
  const funnelStatus = useAppStore((s) => s.funnelStatus);
  const loading = useAppStore((s) => s.loadingFunnel);
  const error = useAppStore((s) => s.errorFunnel);
  const fetchFunnel = useAppStore((s) => s.fetchFunnel);

  useEffect(() => {
    if (!funnelStatus && !loading) {
      void fetchFunnel();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const option = useMemo<EChartsOption>(() => {
    const stages = funnelStatus?.stages ?? [];
    return {
      tooltip: {
        trigger: "item",
        formatter: (params: unknown) => {
          const p = params as { name: string; value: number; data?: { info?: string } };
          const desc = p.data?.info ?? "";
          return `${p.name}<br/>数量: ${p.value.toLocaleString()}<br/>${desc}`;
        },
      },
      series: [
        {
          type: "funnel",
          left: "8%",
          right: "8%",
          top: 8,
          bottom: 8,
          width: "84%",
          min: 0,
          max: stages[0]?.count ?? 10000,
          minSize: "20%",
          maxSize: "100%",
          sort: "descending",
          gap: 2,
          label: {
            show: true,
            position: "inside",
            fontSize: 11,
            fontWeight: "bold",
            color: "#fff",
            formatter: (params: unknown) => {
              const p = params as { name: string; value: number };
              return `${p.name}\n${p.value.toLocaleString()}`;
            },
          },
          itemStyle: {
            borderColor: "#fff",
            borderWidth: 1,
          },
          data: stages.map((s, i) => ({
            name: s.level,
            value: s.count,
            itemStyle: { color: FUNNEL_COLORS[i % FUNNEL_COLORS.length] },
            info: s.description,
          })),
        },
      ],
    };
  }, [funnelStatus]);

  if (loading && !funnelStatus) {
    return (
      <div className="flex flex-col items-center justify-center h-48 gap-2">
        <div className="w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
        <span className="text-xs text-gray-400">漏斗数据加载中…</span>
      </div>
    );
  }

  if (error && !funnelStatus) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-xs text-red-600">
        <div className="font-medium mb-1">漏斗数据加载失败</div>
        <div className="text-[11px] text-red-500/80 break-all">{error}</div>
        <button
          type="button"
          onClick={() => void fetchFunnel()}
          className="mt-2 px-2 py-1 rounded bg-red-100 text-red-700 hover:bg-red-200 transition-colors text-[11px]"
        >
          重试
        </button>
      </div>
    );
  }

  if (!funnelStatus || funnelStatus.stages.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-xs text-gray-400">
        暂无漏斗数据
      </div>
    );
  }

  return (
    <div>
      <EChart option={option} style={{ height: 240 }} />
      {/* 阈值与 TopN 信息 */}
      <div className="mt-2 grid grid-cols-2 gap-2 text-[11px]">
        <div className="rounded bg-gray-50 border border-gray-100 px-2 py-1.5">
          <span className="text-gray-400">hitScore 阈值</span>
          <div className="font-mono font-medium text-brand-600">
            {funnelStatus.threshold}
          </div>
        </div>
        <div className="rounded bg-gray-50 border border-gray-100 px-2 py-1.5">
          <span className="text-gray-400">最终保留 TopN</span>
          <div className="font-mono font-medium text-gray-700">
            {funnelStatus.topN}
          </div>
        </div>
      </div>
    </div>
  );
}

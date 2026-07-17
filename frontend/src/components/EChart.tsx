"use client";

// ==============================================================================
// EChart - SSR 安全的 ECharts 包装组件 (Task 15)
// ==============================================================================
// Next.js App Router 下直接 import echarts-for-react 会在 SSR 阶段触发
// "window is not defined"。使用 next/dynamic + ssr:false 规避，并统一
// 图表容器的 loading 占位与样式。
// ==============================================================================

import dynamic from "next/dynamic";
import type { CSSProperties } from "react";
import type { EChartsOption } from "echarts";

// 动态加载 echarts-for-react，禁用 SSR。
const ReactECharts = dynamic(() => import("echarts-for-react"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full bg-gray-100 rounded animate-pulse flex items-center justify-center text-[10px] text-gray-400">
      图表加载中…
    </div>
  ),
});

export interface EChartProps {
  /** ECharts 配置项 */
  option: EChartsOption;
  /** 容器行内样式 (通常用于设置高度) */
  style?: CSSProperties;
  /** 容器 className */
  className?: string;
}

/**
 * SSR 安全的 ECharts 渲染器。
 *
 * 用法:
 *   <EChart option={barOption} style={{ height: 200 }} />
 */
export default function EChart({ option, style, className }: EChartProps) {
  return (
    <div className={className} style={style}>
      <ReactECharts
        option={option}
        notMerge
        lazyUpdate
        style={{ height: "100%", width: "100%" }}
      />
    </div>
  );
}

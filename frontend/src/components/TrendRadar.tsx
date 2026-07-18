"use client";

// ==============================================================================
// TrendRadar - 趋势雷达 (左栏, Task 15)
// ==============================================================================
// 功能:
//   - 挂载时调用 store.fetchTrends() (getTrends API) 拉取趋势列表
//   - 趋势列表: 生命周期色点 (rising绿 / peak琥珀红 / declining灰) + 热度
//   - Z 世代标签 (来自 trendDetail.signals)
//   - 点击选中 → 拉取详情 / 跨区域对比 → 展开趋势详情卡
// spec §7.1 step1/2: 趋势列表 + 生命周期 + Z世代标签 + 点击展开。
// ==============================================================================

import { useEffect } from "react";
import { useAppStore } from "@/lib/store";
import type { Lifecycle, TrendSignal } from "@/lib/types";

// 生命周期 → 色点 + 徽章样式 + 中文标签
const LIFECYCLE_DOT: Record<Lifecycle, string> = {
  rising: "bg-green-500",
  peak: "bg-amber-500",
  declining: "bg-gray-400",
};

const LIFECYCLE_BADGE: Record<Lifecycle, string> = {
  rising: "bg-green-100 text-green-700",
  peak: "bg-amber-100 text-amber-700",
  declining: "bg-gray-200 text-gray-600",
};

const LIFECYCLE_LABEL: Record<Lifecycle, string> = {
  rising: "上升期",
  peak: "峰值期",
  declining: "衰退期",
};

/** 从 lifecycle_summary (Record<string,string>) 推断主导生命周期 */
function extractLifecycle(
  summary: Record<string, string> | undefined,
): Lifecycle {
  if (!summary) return "rising";
  const text =
    Object.keys(summary).join(" ") + " " + Object.values(summary).join(" ");
  if (text.includes("peak")) return "peak";
  if (text.includes("declining")) return "declining";
  return "rising";
}

export default function TrendRadar() {
  const trends = useAppStore((s) => s.trends);
  const loading = useAppStore((s) => s.loadingTrends);
  const error = useAppStore((s) => s.errorTrends);
  const fetchTrends = useAppStore((s) => s.fetchTrends);
  const collectTrends = useAppStore((s) => s.collectTrends);
  const collecting = useAppStore((s) => s.collecting);
  const collectResult = useAppStore((s) => s.collectResult);
  const errorCollect = useAppStore((s) => s.errorCollect);
  const selectedTopic = useAppStore((s) => s.selectedTopic);
  const selectTopic = useAppStore((s) => s.selectTopic);
  const trendDetail = useAppStore((s) => s.trendDetail);
  const loadingDetail = useAppStore((s) => s.loadingDetail);
  const crossRegion = useAppStore((s) => s.crossRegion);

  // 挂载时拉取趋势列表
  useEffect(() => {
    void fetchTrends();
  }, [fetchTrends]);

  // 取选中趋势的首个 signal 作为详情代表
  const primarySignal: TrendSignal | undefined =
    trendDetail?.signals?.[0] ??
    (trendDetail?.signals?.find((s) => s.region === "china") as
      | TrendSignal
      | undefined);

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* 标题 + 统计 */}
      <div className="flex items-baseline justify-between border-b border-gray-100 pb-2">
        <h2 className="text-sm font-bold text-gray-900">趋势雷达</h2>
        <span className="text-[10px] font-mono text-gray-400 uppercase tracking-wider">
          TrendRadar
        </span>
      </div>

      <div className="mt-2 flex items-center justify-between text-xs text-gray-500">
        <span>
          共 <span className="font-mono text-gray-700">{trends.length}</span> 条趋势
        </span>
        <button
          type="button"
          onClick={() => void collectTrends()}
          disabled={collecting}
          className="px-2 py-1 rounded bg-blue-50 text-blue-600 hover:bg-blue-100 transition-colors disabled:opacity-50 flex items-center gap-1"
        >
          {collecting ? (
            <>
              <span className="w-3 h-3 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
              采集中…
            </>
          ) : (
            "刷新采集"
          )}
        </button>
      </div>

      {/* 采集状态反馈面板 */}
      {collectResult && (
        <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50/50 p-2 space-y-1.5">
          <div className="flex items-center justify-between text-[10px]">
            <span className="font-medium text-gray-700">采集结果</span>
            <span className="font-mono text-gray-400">
              {collectResult.summary?.ok_count ?? 0} 成功 ·{" "}
              {collectResult.summary?.degraded_count ?? 0} 降级 ·{" "}
              {collectResult.summary?.failed_count ?? 0} 失败
            </span>
          </div>
          <div className="grid grid-cols-3 gap-1">
            {collectResult.sources.map((src) => (
              <div
                key={src.name}
                className={`px-1.5 py-1 rounded text-[9px] border ${
                  src.status === "ok"
                    ? "border-green-200 bg-green-50 text-green-700"
                    : src.status === "degraded"
                      ? "border-amber-200 bg-amber-50 text-amber-700"
                      : "border-red-200 bg-red-50 text-red-600"
                }`}
                title={src.error || src.mode}
              >
                <div className="font-mono truncate">{src.name}</div>
                <div className="flex items-center justify-between mt-0.5">
                  <span>{src.count}条</span>
                  <span className="text-[8px] uppercase opacity-70">
                    {src.mode === "real" ? "真实" : src.mode === "simulated" ? "模拟" : "错误"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {errorCollect && (
        <div className="mt-2 rounded-lg border border-red-200 bg-red-50 p-2 text-[11px] text-red-600">
          采集失败: {errorCollect}
        </div>
      )}

      {/* 趋势列表 (可滚动) */}
      <div className="mt-2 space-y-2 overflow-y-auto flex-1 min-h-0 pr-1">
        {loading && trends.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 gap-2">
            <div className="w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs text-gray-400">趋势加载中…</span>
          </div>
        )}

        {error && trends.length === 0 && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-600">
            <div className="font-medium mb-1">趋势加载失败</div>
            <div className="text-[11px] text-red-500/80 break-all">{error}</div>
            <button
              type="button"
              onClick={() => void fetchTrends()}
              className="mt-2 px-2 py-1 rounded bg-red-100 text-red-700 hover:bg-red-200 transition-colors text-[11px]"
            >
              重试
            </button>
          </div>
        )}

        {!loading && !error && trends.length === 0 && (
          <div className="text-center py-8 text-xs text-gray-400">
            暂无趋势数据
          </div>
        )}

        {trends.map((t) => {
          const lifecycle = extractLifecycle(t.lifecycle_summary);
          const isSelected = selectedTopic === t.topic;
          return (
            <div
              key={t.topic}
              onClick={() => selectTopic(isSelected ? null : t.topic)}
              className={`border rounded-lg p-2.5 cursor-pointer transition-all ${
                isSelected
                  ? "border-brand-500 ring-1 ring-brand-300 bg-brand-50/40"
                  : "border-gray-100 hover:border-brand-400 hover:shadow-sm"
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full flex-shrink-0 ${LIFECYCLE_DOT[lifecycle]}`}
                  title={LIFECYCLE_LABEL[lifecycle]}
                />
                <span className="font-medium text-sm text-gray-900 truncate flex-1">
                  {t.topic}
                </span>
                <span className="text-xs font-mono text-brand-600 flex-shrink-0">
                  {t.max_heat}
                </span>
              </div>

              <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                    LIFECYCLE_BADGE[lifecycle]
                  }`}
                >
                  {LIFECYCLE_LABEL[lifecycle]}
                </span>
                <span className="px-1.5 py-0.5 rounded text-[10px] bg-gray-100 text-gray-500">
                  {t.region_count} 区域
                </span>
                {t.regions?.slice(0, 2).map((r) => (
                  <span
                    key={r}
                    className="px-1 py-0.5 rounded text-[9px] bg-blue-50 text-blue-500"
                  >
                    {r}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* 选中趋势的详情卡 */}
      {selectedTopic && (
        <div className="mt-2 border-t border-gray-200 pt-2 max-h-[45%] overflow-y-auto flex-shrink-0">
          {loadingDetail && (
            <div className="flex items-center gap-2 text-xs text-gray-400 py-2">
              <div className="w-4 h-4 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
              详情加载中…
            </div>
          )}

          {primarySignal && (
            <div className="rounded-lg border border-gray-200 p-2.5 space-y-2">
              <div className="text-sm font-semibold text-gray-900">
                {primarySignal.topic}
              </div>

              {/* 热度 / 增长 / 窗口期 */}
              <div className="grid grid-cols-3 gap-1.5 text-[10px]">
                <div className="bg-gray-50 rounded px-1.5 py-1">
                  <div className="text-gray-400">热度</div>
                  <div className="font-mono font-medium text-brand-600">
                    {primarySignal.heatScore}
                  </div>
                </div>
                <div className="bg-gray-50 rounded px-1.5 py-1">
                  <div className="text-gray-400">周增长</div>
                  <div
                    className={`font-mono font-medium ${
                      primarySignal.growthRate >= 0
                        ? "text-green-600"
                        : "text-red-500"
                    }`}
                  >
                    {primarySignal.growthRate >= 0 ? "+" : ""}
                    {primarySignal.growthRate}%
                  </div>
                </div>
                <div className="bg-gray-50 rounded px-1.5 py-1">
                  <div className="text-gray-400">窗口期</div>
                  <div className="font-mono font-medium text-gray-700">
                    {primarySignal.predictWindow}
                  </div>
                </div>
              </div>

              {/* 品类 + 情感 */}
              <div className="flex items-center gap-1.5 flex-wrap text-[10px]">
                <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                  {primarySignal.category}
                </span>
                <span
                  className={`px-1.5 py-0.5 rounded ${
                    primarySignal.sentiment >= 0
                      ? "bg-green-50 text-green-600"
                      : "bg-red-50 text-red-500"
                  }`}
                >
                  情感 {primarySignal.sentiment.toFixed(2)}
                </span>
              </div>

              {/* Z 世代标签 */}
              {primarySignal.zGenTags?.length > 0 && (
                <div>
                  <div className="text-[10px] text-gray-400 mb-1">Z世代标签</div>
                  <div className="flex flex-wrap gap-1">
                    {primarySignal.zGenTags.map((tag) => (
                      <span
                        key={tag}
                        className="px-1.5 py-0.5 rounded text-[10px] bg-purple-50 text-purple-600"
                      >
                        #{tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 关联关键词 */}
              {primarySignal.relatedKeywords?.length > 0 && (
                <div>
                  <div className="text-[10px] text-gray-400 mb-1">关联关键词</div>
                  <div className="flex flex-wrap gap-1">
                    {primarySignal.relatedKeywords.slice(0, 6).map((kw) => (
                      <span
                        key={kw}
                        className="px-1 py-0.5 rounded text-[9px] bg-gray-100 text-gray-500"
                      >
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 来源分布 */}
              {primarySignal.sourceBreakdown &&
                Object.keys(primarySignal.sourceBreakdown).length > 0 && (
                  <div>
                    <div className="text-[10px] text-gray-400 mb-1">来源分布</div>
                    <div className="space-y-1">
                      {Object.entries(primarySignal.sourceBreakdown).map(
                        ([src, pct]) => (
                          <div key={src} className="flex items-center gap-1.5">
                            <span className="text-[10px] text-gray-500 w-16 truncate">
                              {src}
                            </span>
                            <div className="flex-1 bg-gray-100 rounded-full h-1.5 overflow-hidden">
                              <div
                                className="h-full bg-brand-500 rounded-full"
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                            <span className="text-[9px] font-mono text-gray-400 w-7 text-right">
                              {pct}%
                            </span>
                          </div>
                        ),
                      )}
                    </div>
                  </div>
                )}

              {/* 跨区域扩散 */}
              {crossRegion?.diffusion_path &&
                crossRegion.diffusion_path.length > 0 && (
                  <div>
                    <div className="text-[10px] text-gray-400 mb-1">
                      跨区域扩散路径
                    </div>
                    <div className="text-[10px] text-gray-600">
                      {crossRegion.diffusion_path.join(" → ")}
                    </div>
                    {crossRegion.follow_up_window && (
                      <div className="text-[10px] text-gray-400 mt-0.5">
                        跟进窗口: {crossRegion.follow_up_window}
                      </div>
                    )}
                  </div>
                )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

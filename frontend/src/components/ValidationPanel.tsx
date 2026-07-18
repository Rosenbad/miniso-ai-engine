"use client";

// ==============================================================================
// ValidationPanel - 验证反馈 (右栏, Task 15)
// ==============================================================================
// 功能:
//   - 启动销售模拟按钮 (基于 selectedIdea，调用 test-plan → simulate → analyze)
//   - 7 天销售柱状图 (ECharts，A/B 组合分组)
//   - 赢家高亮 (analysis.winner + rankings)
//   - 预测 vs 实际对比 (idea.hitScore vs analysis.score)
//   - 模型校准 (calibrate → weight_changes / strategy_suggestions)
// spec §7.1 step7/8: 验证 → 销售曲线 → 赢家 → 预测对比 → 校准。
// ==============================================================================

import { useMemo } from "react";
import EChart from "./EChart";
import { useAppStore } from "@/lib/store";
import type { EChartsOption } from "echarts";

// 组合配色
const COMBO_COLORS = [
  "#f43f5e",
  "#3b82f6",
  "#a855f7",
  "#f59e0b",
  "#10b981",
];

export default function ValidationPanel() {
  const selectedIdea = useAppStore((s) => s.selectedIdea);
  const validating = useAppStore((s) => s.validating);
  const errorValidation = useAppStore((s) => s.errorValidation);
  const testPlan = useAppStore((s) => s.testPlan);
  const simulation = useAppStore((s) => s.simulation);
  const analysis = useAppStore((s) => s.analysis);
  const calibration = useAppStore((s) => s.calibration);
  const calibrating = useAppStore((s) => s.calibrating);
  const errorCalibration = useAppStore((s) => s.errorCalibration);
  const runValidation = useAppStore((s) => s.runValidation);
  const runCalibration = useAppStore((s) => s.runCalibration);

  const handleStart = () => {
    if (!selectedIdea) return;
    void runValidation({
      product_name: selectedIdea.productName,
      category: selectedIdea.category,
      ip_name: selectedIdea.ipMatch?.ipName ?? null,
      days: 7,
    });
  };

  // ---- 构建 7 天销售柱状图配置 ----
  const barOption = useMemo<EChartsOption>(() => {
    const dailyData = simulation?.daily_data ?? {};
    const combos = Object.keys(dailyData);
    if (combos.length === 0) return {};

    // 取最大天数作为 x 轴
    const maxDays = Math.max(
      ...combos.map((c) => dailyData[c]?.length ?? 0),
      0,
    );
    const days = Array.from({ length: maxDays }, (_, i) => `D${i + 1}`);

    return {
      tooltip: { trigger: "axis", confine: true },
      legend: {
        show: combos.length > 1,
        type: "scroll",
        top: 0,
        textStyle: { fontSize: 9, color: "#6b7280" },
        itemWidth: 8,
        itemHeight: 8,
      },
      grid: { left: 4, right: 8, top: combos.length > 1 ? 24 : 8, bottom: 4, containLabel: true },
      xAxis: {
        type: "category",
        data: days,
        axisLabel: { fontSize: 9, color: "#9ca3af" },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: "#e5e7eb" } },
      },
      yAxis: {
        type: "value",
        axisLabel: { fontSize: 9, color: "#9ca3af" },
        splitLine: { lineStyle: { color: "#f3f4f6" } },
      },
      series: combos.map((combo, i) => {
        const isWinner = analysis?.winner?.combination_id === combo;
        return {
          name: combo,
          type: "bar",
          barMaxWidth: 14,
          data: dailyData[combo].map((d) => d.sales),
          itemStyle: {
            color: COMBO_COLORS[i % COMBO_COLORS.length],
            opacity: analysis && !isWinner ? 0.5 : 1,
            borderRadius: [3, 3, 0, 0],
          },
          emphasis: { focus: "series" },
        };
      }),
    };
  }, [simulation, analysis]);

  const hasSimulation = !!simulation && Object.keys(simulation.daily_data ?? {}).length > 0;
  const predictedScore = selectedIdea?.hitScore;
  const actualScore = analysis?.winner?.composite_score;

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* 标题 */}
      <div className="flex items-baseline justify-between border-b border-gray-100 pb-2">
        <h2 className="text-sm font-bold text-gray-900">验证反馈</h2>
        <span className="text-[10px] font-mono text-gray-400 uppercase tracking-wider">
          ValidationPanel
        </span>
      </div>

      {/* 当前验证对象 */}
      <div className="mt-2 text-xs text-gray-500 min-w-0">
        验证对象:
        <span className="ml-1 font-medium text-gray-800 truncate">
          {selectedIdea?.productName ?? "未选择创意"}
        </span>
      </div>

      {/* 启动模拟按钮 */}
      <div className="mt-2">
        <button
          type="button"
          onClick={handleStart}
          disabled={!selectedIdea || validating}
          className="w-full px-4 py-1.5 rounded-md bg-green-600 text-white text-sm font-medium hover:bg-green-700 transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {validating ? "模拟运行中…" : "启动销售模拟 (7天)"}
        </button>
        {!selectedIdea && (
          <div className="mt-1 text-[10px] text-gray-400 text-center">
            请先在中栏选择/展开一个创意卡
          </div>
        )}
      </div>

      {/* 验证进度 (链路: test-plan → simulate → analyze) */}
      {validating && (
        <div className="mt-3 rounded-lg border border-green-200 bg-green-50/40 p-3">
          <div className="text-xs font-medium text-gray-700 mb-2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-ping" />
            验证链路执行中…
          </div>
          <div className="space-y-1 text-[11px]">
            <StepRow label="1. 生成测试计划 (test-plan)" done={!!testPlan} />
            <StepRow label="2. 运行销售模拟 (simulate)" done={!!simulation} />
            <StepRow label="3. 分析结果 (analyze)" done={!!analysis} />
          </div>
        </div>
      )}

      {/* 验证错误 */}
      {errorValidation && !validating && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-600">
          <div className="font-medium mb-1">验证失败</div>
          <div className="text-[11px] text-red-500/80 break-all">
            {errorValidation}
          </div>
        </div>
      )}

      <div className="mt-3 flex-1 min-h-0 overflow-y-auto pr-1 space-y-3">
        {/* 7 天销售柱状图 */}
        {hasSimulation ? (
          <div>
            <div className="text-xs font-medium text-gray-700 mb-1">
              销售模拟曲线 ({simulation?.days ?? 7} 天)
            </div>
            <EChart option={barOption} style={{ height: 150 }} />
          </div>
        ) : (
          !validating && (
            <div className="h-32 bg-gray-50 rounded-lg border border-dashed border-gray-200 flex items-center justify-center text-[11px] text-gray-400">
              点击上方按钮启动模拟
            </div>
          )
        )}

        {/* 赢家高亮 */}
        {analysis && (
          <div>
            <div className="text-xs font-medium text-gray-700 mb-1">
              验证赢家
            </div>
            <div className="border-2 border-green-400 bg-green-50 rounded-lg p-2.5">
              <div className="flex items-center gap-2">
                <span className="text-base">🏆</span>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-900 truncate">
                    {analysis.winner?.combination_id ?? "-"}
                  </div>
                  <div className="text-[10px] text-gray-500">
                    综合评分{" "}
                    <span className="font-mono">
                      {analysis.winner?.composite_score?.toFixed(2) ?? "-"}
                    </span>{" "}
                    · 置信度{" "}
                    <span className="font-mono">
                      {analysis.confidence?.toFixed(2) ?? "-"}
                    </span>
                  </div>
                </div>
              </div>
              {/* 排名列表 */}
              {analysis.rankings && analysis.rankings.length > 1 && (
                <div className="mt-2 space-y-1">
                  {analysis.rankings.slice(0, 3).map((r, i) => (
                    <div
                      key={r.combination_id}
                      className="flex items-center justify-between text-[10px] bg-white/60 rounded px-1.5 py-0.5"
                    >
                      <span className="text-gray-600 truncate">
                        {i + 1}. {r.combination_id}
                      </span>
                      <span className="font-mono text-gray-700">
                        {r.score.toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 预测 vs 实际对比 */}
        {analysis && predictedScore != null && (
          <div>
            <div className="text-xs font-medium text-gray-700 mb-1">
              预测 vs 实际
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="rounded bg-blue-50 border border-blue-100 px-2 py-1.5">
                <div className="text-blue-400">预测爆品概率</div>
                <div className="font-mono font-bold text-blue-600">
                  {(predictedScore * 100).toFixed(0)}%
                </div>
              </div>
              <div className="rounded bg-green-50 border border-green-100 px-2 py-1.5">
                <div className="text-green-500">实际验证评分</div>
                <div className="font-mono font-bold text-green-600">
                  {actualScore != null
                    ? (actualScore * 100).toFixed(0) + "%"
                    : "-"}
                </div>
              </div>
            </div>
            {predictedScore != null && actualScore != null && (
              <div className="mt-1 text-[10px] text-gray-500">
                误差:{" "}
                <span
                  className={`font-mono ${
                    Math.abs(predictedScore - actualScore) > 0.1
                      ? "text-amber-600"
                      : "text-green-600"
                  }`}
                >
                  {(actualScore - predictedScore >= 0 ? "+" : "")}
                  {((actualScore - predictedScore) * 100).toFixed(1)}%
                </span>
              </div>
            )}
          </div>
        )}

        {/* 因子贡献 */}
        {analysis?.factor_contribution &&
          Object.keys(analysis.factor_contribution).length > 0 && (
            <div>
              <div className="text-xs font-medium text-gray-700 mb-1">
                因子贡献
              </div>
              <div className="space-y-1">
                {Object.entries(analysis.factor_contribution)
                  .slice(0, 4)
                  .map(([factor, val]) => (
                    <div key={factor} className="flex items-center gap-1.5">
                      <span className="text-[10px] text-gray-500 w-20 truncate">
                        {factor}
                      </span>
                      <div className="flex-1 bg-gray-100 rounded-full h-1.5 overflow-hidden">
                        <div
                          className="h-full bg-brand-500 rounded-full"
                          style={{
                            width: `${Math.min(Math.abs(val) * 100, 100)}%`,
                          }}
                        />
                      </div>
                      <span className="text-[9px] font-mono text-gray-400 w-8 text-right">
                        {val.toFixed(2)}
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}

        {/* 模型校准 */}
        {analysis && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <div className="text-xs font-medium text-gray-700">模型校准</div>
              <button
                type="button"
                onClick={() => void runCalibration()}
                disabled={calibrating}
                className="px-2 py-0.5 rounded text-[10px] bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors disabled:opacity-50"
              >
                {calibrating ? "校准中…" : "触发校准"}
              </button>
            </div>
            {errorCalibration && (
              <div className="text-[10px] text-red-500 break-all">
                {errorCalibration}
              </div>
            )}
            {calibration ? (
              <div className="text-[11px] text-gray-600 bg-gray-50 rounded p-2 border border-gray-100 space-y-1">
                <div>
                  新版本:{" "}
                  <span className="font-mono text-blue-600">
                    {calibration.new_version}
                  </span>
                </div>
                {calibration.prediction_errors &&
                  Object.keys(calibration.prediction_errors).length > 0 && (
                    <div>
                      预测误差:{" "}
                      <span className="font-mono text-amber-600">
                        {Object.values(calibration.prediction_errors)[0]?.toFixed(3)}
                      </span>
                    </div>
                  )}
                {calibration.strategy_suggestions &&
                  calibration.strategy_suggestions.length > 0 && (
                    <div className="text-[10px] text-gray-500">
                      建议: {calibration.strategy_suggestions[0]}
                    </div>
                  )}
              </div>
            ) : (
              !calibrating && (
                <div className="text-[10px] text-gray-400 italic">
                  验证完成后可触发模型反哺校准
                </div>
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------
// 验证步骤行
// ------------------------------------------------------------------------------
function StepRow({ label, done }: { label: string; done: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[8px] ${
          done
            ? "bg-green-500 text-white"
            : "bg-gray-200 text-gray-400 animate-pulse"
        }`}
      >
        {done ? "✓" : "·"}
      </span>
      <span className={done ? "text-gray-700" : "text-gray-400"}>{label}</span>
    </div>
  );
}

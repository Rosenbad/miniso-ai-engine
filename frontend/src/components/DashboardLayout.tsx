// ==============================================================================
// DashboardLayout - 可复用三栏仪表盘布局组件
// ==============================================================================
// 提取自 app/page.tsx 的布局结构，便于多个仪表盘页面复用。
//
// 布局规范 (spec §7):
//   - Header  : sticky top-0 z-10, bg-white border-b，左侧标题/副标题，右侧 headerExtra
//   - Main    : grid-cols-1 lg:grid-cols-[300px_1fr_300px] gap-4 p-4
//       左栏 300px  -> leftPanel
//       中栏 1fr    -> centerPanel (含 min-w-0 防溢出)
//       右栏 300px  -> rightPanel
//   - Footer  : bg-white border-t (可选)
//
// 各栏样式: bg-white rounded-lg shadow-sm border border-gray-200 p-4
//           flex flex-col min-h-0 lg:max-h-[calc(100vh-140px)]
//
// 通用约束: 组件不包含任何业务逻辑，仅负责布局编排与样式。
// ==============================================================================

import type { ReactNode } from "react";

export interface DashboardLayoutProps {
  /** 主标题 (h1) */
  title: string;
  /** 副标题 (标题下方说明文字) */
  subtitle?: string;
  /** 左栏内容 (300px) */
  leftPanel: ReactNode;
  /** 中栏内容 (1fr) */
  centerPanel: ReactNode;
  /** 右栏内容 (300px) */
  rightPanel: ReactNode;
  /** Header 右侧额外内容 (如 ServiceHealthBadge) */
  headerExtra?: ReactNode;
  /** Header 左侧 logo/图标节点 (可选，默认不渲染) */
  headerLogo?: ReactNode;
  /** Footer 内容 (可选，不传则不渲染 footer) */
  footer?: ReactNode;
  /** 左栏 aria-label (可选) */
  leftLabel?: string;
  /** 中栏 aria-label (可选) */
  centerLabel?: string;
  /** 右栏 aria-label (可选) */
  rightLabel?: string;
}

/**
 * 可复用三栏仪表盘布局组件
 *
 * 不包含业务逻辑，仅负责 Header / Main(三栏) / Footer 的结构与样式。
 */
export function DashboardLayout({
  title,
  subtitle,
  leftPanel,
  centerPanel,
  rightPanel,
  headerExtra,
  headerLogo,
  footer,
  leftLabel,
  centerLabel,
  rightLabel,
}: DashboardLayoutProps) {
  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* ============================ Header ============================ */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 sticky top-0 z-10">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            {headerLogo}
            <div>
              <h1 className="text-lg font-bold text-gray-900">{title}</h1>
              {subtitle && (
                <p className="text-xs text-gray-500">{subtitle}</p>
              )}
            </div>
          </div>
          {headerExtra && (
            <div className="flex items-center gap-4 text-xs">{headerExtra}</div>
          )}
        </div>
      </header>

      {/* ============================ Main 三栏 ============================ */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[300px_1fr_300px] gap-4 p-4 min-h-0">
        {/* ----------------------- 左栏 ----------------------- */}
        <section
          className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 flex flex-col min-h-0 lg:max-h-[calc(100vh-140px)]"
          aria-label={leftLabel}
        >
          {leftPanel}
        </section>

        {/* ----------------------- 中栏 ----------------------- */}
        <section
          className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 flex flex-col min-w-0 min-h-0 lg:max-h-[calc(100vh-140px)]"
          aria-label={centerLabel}
        >
          {centerPanel}
        </section>

        {/* ----------------------- 右栏 ----------------------- */}
        <section
          className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 flex flex-col min-h-0 lg:max-h-[calc(100vh-140px)]"
          aria-label={rightLabel}
        >
          {rightPanel}
        </section>
      </main>

      {/* ============================ Footer ============================ */}
      {footer && (
        <footer className="bg-white border-t border-gray-200 px-6 py-3">
          {footer}
        </footer>
      )}
    </div>
  );
}

export default DashboardLayout;

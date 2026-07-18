"use client";

// ==============================================================================
// 服务健康状态徽章 (Phase 2 修复 — 接入真实健康检查 API)
// ==============================================================================
// 替代原来硬编码绿色的 ServiceBadge, 实际调用 /health 端点:
//   - 绿色脉冲: 服务在线 (status === "ok" / "healthy")
//   - 红色静态: 服务离线 (请求失败或状态异常)
//   - 灰色脉冲: 检查中 (首次加载)
//
// 每 30 秒自动轮询一次, 失败时立即显示红色, 不阻塞页面渲染。
// ==============================================================================

import { useEffect, useState } from "react";
import type { HealthStatus } from "@/lib/types";

type HealthState = "checking" | "online" | "offline";

interface ServiceHealthBadgeProps {
  name: string;
  url: string;
}

/** 从 URL 中提取端口号 */
function extractPort(url: string): string {
  try {
    const parsed = new URL(url);
    if (parsed.port) return parsed.port;
    return parsed.protocol === "https:" ? "443" : "80";
  } catch {
    return "";
  }
}

/** 服务健康状态徽章 — 实时调用 /health API */
export function ServiceHealthBadge({ name, url }: ServiceHealthBadgeProps) {
  const [state, setState] = useState<HealthState>("checking");
  const port = extractPort(url);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    async function checkHealth() {
      try {
        const res = await fetch(`${url}/health`, {
          signal: AbortSignal.timeout(5000),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: HealthStatus = await res.json();
        if (cancelled) return;
        const isOnline =
          data.status === "ok" ||
          data.status === "healthy" ||
          data.status === "UP";
        setState(isOnline ? "online" : "offline");
      } catch {
        if (!cancelled) setState("offline");
      }
    }

    // 首次立即检查
    void checkHealth();

    // 每 30 秒轮询
    timer = setInterval(() => void checkHealth(), 30_000);

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [url]);

  const dotClass =
    state === "online"
      ? "bg-green-500 animate-pulse"
      : state === "offline"
        ? "bg-red-500"
        : "bg-gray-400 animate-pulse";

  const labelClass =
    state === "online"
      ? "text-gray-600"
      : state === "offline"
        ? "text-red-600"
        : "text-gray-400";

  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${dotClass}`} />
      <span className={labelClass}>{name}</span>
      {port && <span className="text-gray-400 font-mono">:{port}</span>}
    </div>
  );
}

# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 前端 Dockerfile（生产多阶段构建）
# ==============================================================================
# Next.js 决策工作台（三栏布局）
# 基于 Next.js 官方 Docker 示例，使用 standalone 输出模式
# 三阶段构建：deps -> builder -> runner
# ==============================================================================

# ===== Stage 1: deps =====
# 安装全量依赖（含 devDependencies，供构建阶段使用）
FROM node:18-alpine AS deps
ENV NODE_ENV=production
ENV TZ=Asia/Shanghai
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev=false

# ===== Stage 2: builder =====
# 执行生产构建，生成 standalone 自包含输出
FROM node:18-alpine AS builder
ENV NODE_ENV=production
ENV TZ=Asia/Shanghai
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ===== Stage 3: runner =====
# 最小化生产运行时镜像，使用非 root 用户运行
FROM node:18-alpine AS runner
ENV NODE_ENV=production
ENV TZ=Asia/Shanghai
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs
# 复制 standalone 输出
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]

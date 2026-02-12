# ─── Stage 1: Install dependencies ───────────────────────
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* yarn.lock* ./
RUN if [ -f package-lock.json ]; then npm ci --legacy-peer-deps; \
    elif [ -f yarn.lock ]; then yarn install --frozen-lockfile; \
    else npm install --legacy-peer-deps; fi

# ─── Stage 2: Build the app ─────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time env vars (empty API URL = use same-origin rewrites)
ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_TELEMETRY_DISABLED=1

# Ensure public dir exists (Next.js needs it)
RUN mkdir -p public

RUN npm run build

# ─── Stage 3: Production runner ─────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy built app — standalone output from next.config.js output: "standalone"
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]

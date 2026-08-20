# AetherLab frontend — production Dockerfile (npm).
#
# Build context is the `frontend/` directory (the Dockerfile lives next to the
# Next.js app), so every COPY uses paths relative to `frontend/`:
#
#   cd frontend
#   docker build -f Dockerfile -t aetherlab-frontend \
#     --build-arg NEXT_PUBLIC_API_URL=http://host.docker.internal:8000 .
#   docker run -p 3000:3000 aetherlab-frontend
#
# NOTES
#  * NEXT_PUBLIC_* vars are inlined by Next at BUILD time. Override them with
#    `--build-arg` rather than at `docker run` time.
#  * The auth token cookie (see ../middleware.ts) is SameSite=Lax and is not
#    httpOnly — only a backend-managed httpOnly cookie would survive a
#    cross-origin production deployment.

# ── Shared base ──────────────────────────────────────────────
FROM node:20-alpine AS base
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# ── Dependencies (prod only) ─────────────────────────────────
FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# ── Builder ──────────────────────────────────────────────────
FROM base AS builder
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Defaults let `docker build` work with zero args in a local/dev setting.
ARG NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
ARG NEXT_PUBLIC_MAPBOX_TOKEN=
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_MAPBOX_TOKEN=${NEXT_PUBLIC_MAPBOX_TOKEN}
RUN npm run build

# ── Runner ----------------------------------------------------------------
FROM base AS runner
WORKDIR /app

# Run as a non-root user — Next.js refuses/ warns when `next start` runs as
# root and it's also just good hygiene for a listening server process.
RUN apk add --no-cache ca-certificates \
    && addgroup -g 1001 -S nextjs \
    && adduser -D -u 1001 -G nextjs nextjs

USER nextjs

# NOTE: do not install devDependencies in the runtime image.
COPY --from=deps --chown=nextjs:nextjs /app/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nextjs /app/.next ./.next
COPY --from=builder --chown=nextjs:nextjs /app/public ./public
COPY --from=builder --chown=nextjs:nextjs /app/package.json ./package.json
COPY --from=builder --chown=nextjs:nextjs /app/next.config.mjs ./next.config.mjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "const http=require('http');const req=http.get('http://127.0.0.1:3000/',{timeout:3000},(res)=>{process.exit(res.statusCode===200?0:1)});req.on('error',()=>process.exit(1))"

CMD ["node", "node_modules/next/dist/bin/next", "start", "-p", "3000", "-H", "0.0.0.0"]

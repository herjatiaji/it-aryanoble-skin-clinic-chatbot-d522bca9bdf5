# Stage 1: Base image with Corepack enabled for PNPM support
FROM node:22-alpine AS base
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@11.9.0  --activate 

# Stage 2: Dependencies layer
FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml* ./
RUN pnpm config set fetch-timeout 600000 && pnpm config set fetch-retries 5 && pnpm install --frozen-lockfile

# Stage 3: Development target
FROM base AS development
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV PORT=3000
EXPOSE 3000
CMD ["pnpm", "dev"]

# Stage 4: Production builder
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

# Stage 5: Production target
FROM base AS production
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY pnpm-lock.yaml pnpm-workspace.yaml* ./

ENV PORT=3000
EXPOSE 3000
CMD ["pnpm", "start"]

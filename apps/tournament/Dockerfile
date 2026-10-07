# Phase 1 retains the legacy Node runtime until the FastAPI compatibility exit.
FROM node:22-alpine AS build
WORKDIR /workspace/apps/tournament
RUN apk add --no-cache python3 make g++
COPY apps/tournament/package.json apps/tournament/package-lock.json ./
RUN npm ci
COPY apps/tournament/ ./
COPY packages/crr-brand/ /workspace/packages/crr-brand/
ARG VITE_BASE_PATH=/jogo/
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
RUN npm run build && npm prune --omit=dev

FROM node:22-alpine AS runtime
ENV NODE_ENV=production DATABASE_PATH=/data/tournament.sqlite CLIENT_DIST_PATH=/app/dist/client APP_BASE_PATH=/jogo/
WORKDIR /app
COPY --from=build --chown=node:node /workspace/apps/tournament/package.json ./
COPY --from=build --chown=node:node /workspace/apps/tournament/node_modules ./node_modules
COPY --from=build --chown=node:node /workspace/apps/tournament/dist ./dist
RUN mkdir /data && chown node:node /data
USER node
EXPOSE 8080
CMD ["node", "dist/server/main.js"]

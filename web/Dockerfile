# Build context is the repo root (see docker-compose.yml: `context: .`), not web/, because this
# image embeds poc-planner/index.html -- a vendored, point-in-time copy (see
# poc-planner/README-VENDORED.md), not a live sibling project like in the suse-poc-toolkit
# monorepo this was synced from (see "Sync note" in CLAUDE.md / README.md).
FROM docker.io/library/node:20-alpine AS build
WORKDIR /app
# package-lock.json + `npm ci`: the exact versions the lockfile pins, and a persistent npm cache so a release
# (which changes "version" in package.json and so re-runs this layer) re-installs from cache, not the network.
COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY web/ .
COPY poc-planner/index.html ./public/planner/index.html
RUN npm run build

FROM docker.io/library/nginx:alpine
# Pinned to patch CVE-2026-92392 (nginx:alpine's base curl was 8.22.0-r0, vulnerable).
RUN apk add --no-cache curl=8.23.0-r0
COPY --from=build /app/dist /usr/share/nginx/html
COPY web/nginx.conf /etc/nginx/conf.d/default.conf

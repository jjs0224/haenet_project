# docker/frontend.Dockerfile
# Frontend 애플리케이션 이미지 (베이스 이미지 사용)

# BASE_IMAGE가 제공되면 베이스 이미지 사용, 아니면 Node.js 이미지로 폴백
ARG BASE_IMAGE
ARG NODE_IMAGE=node:20-alpine

# ═══════════════════════════════════════════════════════════
# 폴백: 베이스 이미지가 없을 때 사용
# ═══════════════════════════════════════════════════════════
FROM ${NODE_IMAGE} AS fallback-base
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci --prefer-offline --no-audit

# ═══════════════════════════════════════════════════════════
# 빌드 스테이지: 베이스 이미지 또는 폴백 사용
# ═══════════════════════════════════════════════════════════
FROM ${BASE_IMAGE:-fallback-base} AS build
WORKDIR /app

ARG REACT_APP_API_BASE_URL=/api
ENV REACT_APP_API_BASE_URL=${REACT_APP_API_BASE_URL}

# 베이스 이미지에 이미 node_modules가 있으므로 npm ci 스킵!
# 애플리케이션 코드만 복사
COPY frontend/ ./

# React 빌드
RUN npm run build && \
    if [ -d dist ]; then cp -r dist /out; \
    elif [ -d build ]; then cp -r build /out; \
    else echo "No build output (dist/build) found"; ls -la; exit 1; fi

# ═══════════════════════════════════════════════════════════
# 최종 런타임 이미지
# ═══════════════════════════════════════════════════════════
FROM nginx:alpine AS runtime
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /out /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

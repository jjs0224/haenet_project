# syntax=docker/dockerfile:1.7
# docker/base.frontend.Dockerfile
# Frontend용 베이스 이미지: Node.js 의존성만 포함 (애플리케이션 코드 제외)
# package.json이 변경될 때만 재빌드 필요

FROM node:20-alpine AS base
WORKDIR /app

# package.json과 package-lock.json만 복사
COPY frontend/package*.json ./

# 의존성 설치 (node_modules)
RUN npm ci --prefer-offline --no-audit

# 여기까지가 베이스 이미지!
# node_modules만 포함, 애플리케이션 코드는 포함하지 않음

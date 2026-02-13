# Frontend 빌드 최적화 아이디어

## 현재 상황
- Frontend 빌드: ~5-6분 (전체의 50-60%)
- 매번 npm ci + npm run build 실행
- 베이스 이미지 미사용

## 최적화 옵션

### 옵션 1: Node_modules 베이스 이미지 (가장 효과적)

```dockerfile
# docker/base.frontend.Dockerfile
FROM node:20-alpine AS base
WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci

# 여기까지가 베이스 이미지
# node_modules만 포함
```

```dockerfile
# docker/frontend.Dockerfile (수정)
ARG BASE_IMAGE
FROM ${BASE_IMAGE:-node:20-alpine} AS build
WORKDIR /app

# 베이스 이미지를 사용하면 node_modules 이미 설치됨
# npm ci 스킵 가능!

COPY frontend/ ./
RUN npm run build && ...
```

**예상 효과:**
- npm ci 스킵: -2-3분
- 총 빌드 시간: ~2-3분 (현재 대비 50% 단축)

### 옵션 2: Docker BuildKit 캐시 마운트

```dockerfile
# docker/frontend.Dockerfile (수정)
FROM node:20-alpine AS build
WORKDIR /app

COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY frontend/ ./
RUN --mount=type=cache,target=/root/.npm \
    npm run build && ...
```

**예상 효과:**
- npm 다운로드 시간 단축
- ~1-2분 단축

### 옵션 3: 캐시 최적화만 (현재 방식)

```yaml
# .github/workflows/build-push-update-values.yaml
- name: Build Frontend
  uses: docker/build-push-action@v6
  with:
    cache-from: type=gha,scope=frontend
    cache-to: type=gha,mode=max,scope=frontend
```

**예상 효과:**
- 이미 적용 중
- 추가 개선 미미

## 권장 사항

**Frontend 베이스 이미지 생성 (옵션 1)**

장점:
- 가장 효과적 (~50% 단축)
- Backend/Worker와 동일한 패턴
- package.json 변경 시에만 베이스 재빌드

단점:
- 초기 설정 필요
- 베이스 이미지 관리 필요

## 예상 최종 빌드 시간

```
현재:
- Frontend: 5-6분
- Worker: 3-4분
- Backend: 1분
- 총: 9-10분

Frontend 베이스 이미지 적용 후:
- Frontend: 2-3분 ✅
- Worker: 3-4분
- Backend: 1분
- 총: 6-7분 ✨ (30% 추가 단축!)
```

## 다음 단계

1. `docker/base.frontend.Dockerfile` 생성
2. `docker/frontend.Dockerfile` 수정
3. `build-base-images.yaml`에 Frontend 베이스 추가
4. 테스트 빌드
5. 성능 측정

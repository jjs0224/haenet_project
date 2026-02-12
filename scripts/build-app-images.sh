#!/bin/bash
# scripts/build-app-images.sh
# 베이스 이미지를 사용하여 애플리케이션 이미지를 빌드하는 스크립트

set -e

AWS_REGION="ap-northeast-2"
ECR_REGISTRY="690641653744.dkr.ecr.ap-northeast-2.amazonaws.com"

# 베이스 이미지
BACKEND_BASE_IMAGE="${ECR_REGISTRY}/haenet-backend-base:latest"
WORKER_BASE_IMAGE="${ECR_REGISTRY}/haenet-worker-base:latest"

# 애플리케이션 이미지
API_IMAGE="${ECR_REGISTRY}/haenet-api"
WORKER_IMAGE="${ECR_REGISTRY}/haenet-worker-gpu"

# 태그 생성 (타임스탬프 사용)
TAG="local-$(date +%Y%m%d-%H%M%S)"

# 색상
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   Application Images Build Script (Using Base Images)${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# ECR 로그인
echo -e "${YELLOW}🔐 Logging into Amazon ECR...${NC}"
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${ECR_REGISTRY}
echo -e "${GREEN}✅ Logged in successfully!${NC}"
echo ""

# 베이스 이미지 Pull (최신 버전 확인)
echo -e "${YELLOW}📥 Pulling base images from ECR...${NC}"
docker pull ${BACKEND_BASE_IMAGE}
docker pull ${WORKER_BASE_IMAGE}
echo -e "${GREEN}✅ Base images pulled!${NC}"
echo ""

# Backend 애플리케이션 빌드
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}1️⃣  Building Backend Application (using base)...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
START_TIME=$(date +%s)

docker build \
  -f docker/backend.Dockerfile \
  --build-arg BASE_IMAGE=${BACKEND_BASE_IMAGE} \
  -t ${API_IMAGE}:${TAG} \
  -t ${API_IMAGE}:latest \
  --progress=plain \
  .

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo -e "${GREEN}✅ Backend application built in ${DURATION}s${NC}"
echo ""

# Worker 애플리케이션 빌드
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}2️⃣  Building Worker Application (using base)...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
START_TIME=$(date +%s)

docker build \
  -f docker/worker.Dockerfile \
  --build-arg BASE_IMAGE=${WORKER_BASE_IMAGE} \
  -t ${WORKER_IMAGE}:${TAG} \
  -t ${WORKER_IMAGE}:latest \
  --progress=plain \
  .

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo -e "${GREEN}✅ Worker application built in ${DURATION}s${NC}"
echo ""

# 이미지 확인
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📦 Built Images:${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
docker images | grep -E "haenet-(api|worker-gpu)" | grep -E "${TAG}|latest"
echo ""

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🎉 Application images built successfully!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}📋 Images built:${NC}"
echo "   - ${API_IMAGE}:${TAG}"
echo "   - ${WORKER_IMAGE}:${TAG}"
echo ""
echo -e "${YELLOW}🚀 To push to ECR:${NC}"
echo "   docker push ${API_IMAGE}:${TAG}"
echo "   docker push ${WORKER_IMAGE}:${TAG}"
echo ""
echo -e "${YELLOW}🧪 To test locally:${NC}"
echo "   docker run --rm -p 8000:8000 ${API_IMAGE}:${TAG}"

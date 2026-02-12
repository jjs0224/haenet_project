#!/bin/bash
# scripts/build-base-images.sh
# 베이스 이미지를 로컬에서 빌드하고 ECR에 푸시하는 스크립트

set -e

AWS_REGION="ap-northeast-2"
ECR_REGISTRY="690641653744.dkr.ecr.ap-northeast-2.amazonaws.com"
BACKEND_BASE_IMAGE="${ECR_REGISTRY}/haenet-backend-base"
WORKER_BASE_IMAGE="${ECR_REGISTRY}/haenet-worker-base"

# 색상 코드
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   Docker Base Images Build & Push Script${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# ECR 로그인
echo -e "${YELLOW}🔐 Logging into Amazon ECR...${NC}"
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${ECR_REGISTRY}
echo -e "${GREEN}✅ Logged in successfully!${NC}"
echo ""

# Backend Base 이미지 빌드
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}1️⃣  Building Backend Base Image...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
START_TIME=$(date +%s)

docker build \
  -f docker/base.backend.Dockerfile \
  -t ${BACKEND_BASE_IMAGE}:latest \
  -t ${BACKEND_BASE_IMAGE}:$(date +%Y%m%d-%H%M%S) \
  --progress=plain \
  .

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo -e "${GREEN}✅ Backend base image built in ${DURATION}s${NC}"
echo ""

# Worker Base 이미지 빌드
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}2️⃣  Building Worker Base Image...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
START_TIME=$(date +%s)

docker build \
  -f docker/base.worker.Dockerfile \
  -t ${WORKER_BASE_IMAGE}:latest \
  -t ${WORKER_BASE_IMAGE}:$(date +%Y%m%d-%H%M%S) \
  --progress=plain \
  .

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo -e "${GREEN}✅ Worker base image built in ${DURATION}s${NC}"
echo ""

# 이미지 확인
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📦 Built Images:${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
docker images | grep -E "haenet-(backend|worker)-base"
echo ""

# ECR에 푸시
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}3️⃣  Pushing Backend Base Image to ECR...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
docker push ${BACKEND_BASE_IMAGE}:latest
docker push ${BACKEND_BASE_IMAGE}:$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
echo -e "${GREEN}✅ Backend base image pushed!${NC}"
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}4️⃣  Pushing Worker Base Image to ECR...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
docker push ${WORKER_BASE_IMAGE}:latest
docker push ${WORKER_BASE_IMAGE}:$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
echo -e "${GREEN}✅ Worker base image pushed!${NC}"
echo ""

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}🎉 All base images built and pushed successfully!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}📋 Next Steps:${NC}"
echo "   1. Build application images using these base images"
echo "   2. Test the application images locally"
echo "   3. Deploy to your environment"
echo ""
echo -e "${YELLOW}💡 Quick Build Command:${NC}"
echo "   docker build -f docker/backend.Dockerfile \\"
echo "     --build-arg BASE_IMAGE=${BACKEND_BASE_IMAGE}:latest \\"
echo "     -t haenet-backend:test ."

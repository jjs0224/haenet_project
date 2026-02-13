#!/bin/bash
# scripts/benchmark-build.sh
# 베이스 이미지 사용 전후 빌드 시간 비교

set -e

ECR_REGISTRY="690641653744.dkr.ecr.ap-northeast-2.amazonaws.com"
BACKEND_BASE="${ECR_REGISTRY}/haenet-backend-base:latest"

echo "═══════════════════════════════════════════════════════════"
echo "   Docker Build Benchmark (Base Image vs Traditional)"
echo "═══════════════════════════════════════════════════════════"
echo ""

# 캐시 정리
echo "🧹 Clearing Docker build cache..."
docker builder prune -af > /dev/null 2>&1
echo "✅ Cache cleared"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 1: 기존 방식 (멀티스테이지, 베이스 이미지 없음)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Test 1: Traditional Multi-Stage Build (NO base image)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
START=$(date +%s)
docker build \
  -f docker/backend.Dockerfile \
  -t backend-traditional:test \
  . > /dev/null 2>&1
END=$(date +%s)
TRADITIONAL_TIME=$((END - START))
echo "⏱️  Time: ${TRADITIONAL_TIME}s"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 2: 베이스 이미지 사용 (첫 빌드)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Test 2: Using Base Image (first build)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📥 Pulling base image..."
docker pull ${BACKEND_BASE} > /dev/null 2>&1
echo "✅ Base image pulled"
echo ""
START=$(date +%s)
docker build \
  -f docker/backend.Dockerfile \
  --build-arg BASE_IMAGE=${BACKEND_BASE} \
  -t backend-with-base:test1 \
  . > /dev/null 2>&1
END=$(date +%s)
BASE_TIME_1=$((END - START))
echo "⏱️  Time: ${BASE_TIME_1}s"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test 3: 베이스 이미지 사용 (코드 변경 후 재빌드)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Test 3: Using Base Image (code change, rebuild)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 Simulating code change..."
echo "# test comment" >> backend/app/main.py
echo "✅ Code modified"
echo ""
START=$(date +%s)
docker build \
  -f docker/backend.Dockerfile \
  --build-arg BASE_IMAGE=${BACKEND_BASE} \
  -t backend-with-base:test2 \
  . > /dev/null 2>&1
END=$(date +%s)
BASE_TIME_2=$((END - START))
echo "⏱️  Time: ${BASE_TIME_2}s"
echo ""

# 변경 사항 되돌리기
git checkout backend/app/main.py 2>/dev/null || sed -i '$ d' backend/app/main.py

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Results Summary
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "═══════════════════════════════════════════════════════════"
echo "   📊 Build Time Comparison"
echo "═══════════════════════════════════════════════════════════"
echo ""
printf "%-40s %10s\n" "Method" "Time (s)"
echo "───────────────────────────────────────────────────────────"
printf "%-40s %10s\n" "Traditional Multi-Stage (no cache)" "${TRADITIONAL_TIME}"
printf "%-40s %10s\n" "Base Image (first build)" "${BASE_TIME_1}"
printf "%-40s %10s\n" "Base Image (code change rebuild)" "${BASE_TIME_2}"
echo "───────────────────────────────────────────────────────────"
echo ""

# Calculate improvements
IMPROVEMENT_1=$((TRADITIONAL_TIME - BASE_TIME_1))
IMPROVEMENT_2=$((TRADITIONAL_TIME - BASE_TIME_2))
PCT_1=$(awk "BEGIN {printf \"%.1f\", ($IMPROVEMENT_1 / $TRADITIONAL_TIME) * 100}")
PCT_2=$(awk "BEGIN {printf \"%.1f\", ($IMPROVEMENT_2 / $TRADITIONAL_TIME) * 100}")

echo "📈 Performance Gains:"
echo "   First build:  -${IMPROVEMENT_1}s (-${PCT_1}%)"
echo "   Rebuild:      -${IMPROVEMENT_2}s (-${PCT_2}%) ✨"
echo ""

# Image sizes
echo "═══════════════════════════════════════════════════════════"
echo "   📦 Image Sizes"
echo "═══════════════════════════════════════════════════════════"
docker images | grep -E "backend-(traditional|with-base)|haenet-backend-base" | grep -v none
echo ""

echo "✅ Benchmark complete!"
echo ""
echo "💡 Key Takeaway:"
echo "   With base images, code changes require only ${BASE_TIME_2}s to rebuild"
echo "   vs ${TRADITIONAL_TIME}s with traditional approach."
echo "   That's ${PCT_2}% faster! 🚀"

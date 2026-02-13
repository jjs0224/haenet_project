#!/bin/bash
# scripts/create-ecr-repos.sh
# ECR 베이스 이미지 레포지토리 생성 스크립트

set -e

AWS_REGION="ap-northeast-2"
AWS_ACCOUNT_ID="690641653744"

echo "🚀 Creating ECR repositories for base images..."
echo ""

# Backend Base Repository
echo "1️⃣  Creating haenet-backend-base repository..."
aws ecr create-repository \
  --repository-name haenet-backend-base \
  --region ${AWS_REGION} \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256 \
  2>/dev/null || echo "   ℹ️  Repository already exists"

# Worker Base Repository
echo "2️⃣  Creating haenet-worker-base repository..."
aws ecr create-repository \
  --repository-name haenet-worker-base \
  --region ${AWS_REGION} \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256 \
  2>/dev/null || echo "   ℹ️  Repository already exists"

echo ""
echo "✅ ECR repositories created/verified!"
echo ""
echo "📋 Repository URLs:"
echo "   Backend Base: ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/haenet-backend-base"
echo "   Worker Base:  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/haenet-worker-base"
echo ""

# Set lifecycle policy to keep only recent images
echo "🗑️  Setting lifecycle policies (keep last 10 images)..."

cat > /tmp/ecr-lifecycle-policy.json <<'EOF'
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Keep last 10 images",
      "selection": {
        "tagStatus": "any",
        "countType": "imageCountMoreThan",
        "countNumber": 10
      },
      "action": {
        "type": "expire"
      }
    }
  ]
}
EOF

aws ecr put-lifecycle-policy \
  --repository-name haenet-backend-base \
  --lifecycle-policy-text file:///tmp/ecr-lifecycle-policy.json \
  --region ${AWS_REGION} \
  >/dev/null 2>&1 || true

aws ecr put-lifecycle-policy \
  --repository-name haenet-worker-base \
  --lifecycle-policy-text file:///tmp/ecr-lifecycle-policy.json \
  --region ${AWS_REGION} \
  >/dev/null 2>&1 || true

rm -f /tmp/ecr-lifecycle-policy.json

echo "✅ Lifecycle policies set!"
echo ""
echo "🎉 Setup complete! You can now build and push base images."

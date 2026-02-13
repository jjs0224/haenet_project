# Makefile for Docker Base Images
# 베이스 이미지 빌드 및 관리를 위한 편의 명령어

AWS_REGION := ap-northeast-2
ECR_REGISTRY := 690641653744.dkr.ecr.ap-northeast-2.amazonaws.com
BACKEND_BASE := $(ECR_REGISTRY)/haenet-backend-base
WORKER_BASE := $(ECR_REGISTRY)/haenet-worker-base
API_IMAGE := $(ECR_REGISTRY)/haenet-api
WORKER_IMAGE := $(ECR_REGISTRY)/haenet-worker-gpu

.PHONY: help login create-repos build-base push-base build-app test-backend test-worker clean

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

login: ## Login to ECR
	@echo "🔐 Logging into ECR..."
	@aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(ECR_REGISTRY)

create-repos: ## Create ECR repositories for base images
	@echo "🚀 Creating ECR repositories..."
	@bash scripts/create-ecr-repos.sh

build-base: ## Build base images (backend + worker)
	@echo "🏗️  Building base images..."
	@docker build -f docker/base.backend.Dockerfile -t $(BACKEND_BASE):latest .
	@docker build -f docker/base.worker.Dockerfile -t $(WORKER_BASE):latest .
	@echo "✅ Base images built!"

push-base: login build-base ## Build and push base images to ECR
	@echo "📤 Pushing base images to ECR..."
	@docker push $(BACKEND_BASE):latest
	@docker push $(WORKER_BASE):latest
	@echo "✅ Base images pushed!"

build-app: login ## Build application images using base images
	@echo "🏗️  Building application images..."
	@docker pull $(BACKEND_BASE):latest
	@docker pull $(WORKER_BASE):latest
	@docker build -f docker/backend.Dockerfile --build-arg BASE_IMAGE=$(BACKEND_BASE):latest -t $(API_IMAGE):test .
	@docker build -f docker/worker.Dockerfile --build-arg BASE_IMAGE=$(WORKER_BASE):latest -t $(WORKER_IMAGE):test .
	@echo "✅ Application images built!"

test-backend: ## Run backend container locally for testing
	@echo "🧪 Starting backend container..."
	@docker run --rm -p 8000:8000 -e DATABASE_URL=sqlite:///./test.db $(API_IMAGE):test

test-worker: ## Test worker container
	@echo "🧪 Testing worker container..."
	@docker run --rm $(WORKER_IMAGE):test python -c "import sys; print(f'Python {sys.version}'); import torch; print(f'PyTorch {torch.__version__}')"

benchmark: ## Benchmark build times
	@echo "⏱️  Running build benchmark..."
	@bash scripts/benchmark-build.sh

clean: ## Remove local Docker images
	@echo "🧹 Cleaning up local images..."
	@docker images | grep haenet | awk '{print $$3}' | xargs docker rmi -f || true
	@echo "✅ Cleaned up!"

all: create-repos push-base build-app ## Complete setup (create repos, build and push base, build app)
	@echo "🎉 All done!"

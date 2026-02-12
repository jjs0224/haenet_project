# Docker Base Images Guide

베이스 이미지를 사용하여 Docker 빌드 시간을 단축하는 방법

## 📋 목차

- [개요](#개요)
- [구조](#구조)
- [사용 방법](#사용-방법)
- [CI/CD 워크플로우](#cicd-워크플로우)
- [트러블슈팅](#트러블슈팅)

## 개요

### 문제점
기존에는 매번 Docker 이미지를 빌드할 때마다 모든 Python 의존성을 설치했습니다.
- API 빌드: ~3-5분
- Worker 빌드: ~10-15분 (PyTorch 등 대용량 패키지)

### 해결책
**베이스 이미지**를 사용하여 의존성과 애플리케이션 코드를 분리합니다.
- 베이스 이미지: Python 의존성만 포함 (requirements 변경 시에만 재빌드)
- 앱 이미지: 애플리케이션 코드만 복사 (코드 변경 시 빠른 재빌드)

### 성능 향상
| 시나리오 | 기존 방식 | 베이스 이미지 방식 | 개선율 |
|---------|----------|------------------|--------|
| 코드만 변경 | 3-5분 | **30초-1분** | **-85%** ✨ |
| Requirements 변경 | 10분 | 10분 (베이스) + 1분 (앱) | - |

## 구조

### 파일 구조
```
docker/
├── base.backend.Dockerfile    # Backend 베이스 이미지
├── base.worker.Dockerfile     # Worker 베이스 이미지
├── backend.Dockerfile         # Backend 앱 이미지 (베이스 사용)
├── worker.Dockerfile          # Worker 앱 이미지 (베이스 사용)
└── frontend.Dockerfile        # Frontend (변경 없음)

.github/workflows/
├── build-base-images.yaml              # 베이스 이미지 빌드 (requirements 변경 시)
└── build-push-update-values.yaml       # 앱 이미지 빌드 (매번 실행)
```

### 베이스 이미지
ECR에 저장된 베이스 이미지:
- `690641653744.dkr.ecr.ap-northeast-2.amazonaws.com/haenet-backend-base:latest`
- `690641653744.dkr.ecr.ap-northeast-2.amazonaws.com/haenet-worker-base:latest`

## 사용 방법

### 1. 로컬 개발

#### Makefile 사용 (권장)
```bash
# 베이스 이미지 빌드 및 푸시
make push-base

# 애플리케이션 이미지 빌드
make build-app

# Backend 테스트 실행
make test-backend

# 전체 프로세스 (한 번에)
make all
```

#### 수동 빌드
```bash
# 1. ECR 로그인
aws ecr get-login-password --region ap-northeast-2 | \
  docker login --username AWS --password-stdin \
  690641653744.dkr.ecr.ap-northeast-2.amazonaws.com

# 2. 베이스 이미지 빌드 (requirements 변경 시에만)
docker build -f docker/base.backend.Dockerfile \
  -t 690641653744.dkr.ecr.ap-northeast-2.amazonaws.com/haenet-backend-base:latest .
docker push 690641653744.dkr.ecr.ap-northeast-2.amazonaws.com/haenet-backend-base:latest

# 3. 애플리케이션 이미지 빌드 (매번)
docker build -f docker/backend.Dockerfile \
  --build-arg BASE_IMAGE=690641653744.dkr.ecr.ap-northeast-2.amazonaws.com/haenet-backend-base:latest \
  -t haenet-backend:latest .
```

### 2. requirements.txt 업데이트 시

```bash
# 1. requirements 파일 수정
vim requirements_api.txt  # 또는 requirements_cpu.txt

# 2. 베이스 이미지 재빌드
make push-base

# 3. Git commit & push
git add requirements_api.txt
git commit -m "chore: update dependencies"
git push

# GitHub Actions가 자동으로:
# - 베이스 이미지 빌드 (build-base-images.yaml)
# - 앱 이미지 빌드 (build-push-update-values.yaml)
```

### 3. 코드만 변경 시

```bash
# 1. 코드 수정
vim backend/app/main.py

# 2. Git commit & push
git add backend/app/main.py
git commit -m "feat: add new feature"
git push

# GitHub Actions가 자동으로:
# - 베이스 이미지는 스킵 (변경 없음)
# - 앱 이미지만 빌드 (빠름! ~1분)
```

## CI/CD 워크플로우

### Workflow 1: build-base-images.yaml
**트리거**: requirements 파일 변경 시
```yaml
paths:
  - "requirements_api.txt"
  - "requirements_cpu.txt"
  - "docker/base.*.Dockerfile"
```

**동작**:
1. 변경된 requirements 감지
2. 해당하는 베이스 이미지만 재빌드
3. ECR에 푸시 (태그: `latest`, `sha-xxxxx`, `build-N`)

### Workflow 2: build-push-update-values.yaml
**트리거**: 코드 또는 Docker 파일 변경 시

**동작**:
1. ECR에서 최신 베이스 이미지 pull
2. 베이스 이미지를 사용하여 앱 이미지 빌드 (빠름!)
3. ECR에 푸시
4. Kubernetes values 파일 업데이트

## 트러블슈팅

### 문제 1: 베이스 이미지를 찾을 수 없음
```
Error: pull access denied for xxx/haenet-backend-base
```

**해결**:
```bash
# ECR 레포지토리 생성
bash scripts/create-ecr-repos.sh

# 베이스 이미지 빌드 및 푸시
make push-base
```

### 문제 2: 빌드가 여전히 느림
**원인**: 베이스 이미지가 오래되었거나 캐시가 없음

**해결**:
```bash
# 최신 베이스 이미지 pull
docker pull 690641653744.dkr.ecr.ap-northeast-2.amazonaws.com/haenet-backend-base:latest

# 또는 베이스 이미지 재빌드
make build-base
```

### 문제 3: 의존성이 설치되지 않음
**원인**: 베이스 이미지가 업데이트되지 않음

**해결**:
```bash
# requirements 변경 후 베이스 이미지 재빌드 필수
make push-base

# 또는 수동으로
docker build -f docker/base.backend.Dockerfile \
  -t 690641653744.dkr.ecr.ap-northeast-2.amazonaws.com/haenet-backend-base:latest .
docker push 690641653744.dkr.ecr.ap-northeast-2.amazonaws.com/haenet-backend-base:latest
```

### 문제 4: GitHub Actions에서 베이스 이미지 빌드가 스킵됨
**원인**: requirements 파일이 변경되지 않음

**해결**:
```bash
# 수동으로 워크플로우 실행
# GitHub > Actions > build-base-images > Run workflow
```

## 성능 벤치마크

```bash
# 벤치마크 실행
bash scripts/benchmark-build.sh
```

**예상 결과**:
```
Method                                    Time (s)
───────────────────────────────────────────────────
Traditional Multi-Stage (no cache)            180
Base Image (first build)                       15
Base Image (code change rebuild)               12
───────────────────────────────────────────────────

Performance Gains:
   First build:  -165s (-91.7%)
   Rebuild:      -168s (-93.3%) ✨
```

## 주요 명령어 요약

```bash
# 베이스 이미지 관련
make build-base          # 베이스 이미지 빌드
make push-base           # 베이스 이미지 빌드 & 푸시
make create-repos        # ECR 레포지토리 생성

# 애플리케이션 이미지 관련
make build-app           # 앱 이미지 빌드 (베이스 사용)
make test-backend        # Backend 컨테이너 실행
make test-worker         # Worker 테스트

# 유틸리티
make benchmark           # 빌드 시간 벤치마크
make clean               # 로컬 이미지 정리
make all                 # 전체 프로세스 (처음 설정 시)
```

## 참고 자료

- [Docker Multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Docker Build Cache](https://docs.docker.com/build/cache/)
- [GitHub Actions - Docker build-push-action](https://github.com/docker/build-push-action)

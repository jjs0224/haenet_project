# 빌드 시간 검증 체크리스트

## 현재 빌드 (#32) 완료 후 확인

### 1. Worker 베이스 이미지 확인
```bash
# 새 Worker 베이스가 ECR에 있는지 확인
aws ecr describe-images \
  --repository-name haenet-worker-base \
  --region ap-northeast-2 \
  --query 'imageDetails[?contains(imageTags, `build-2`)]'
```

### 2. 다음 빌드로 테스트 (진짜 성능 확인)

작은 코드 변경:
```bash
echo "# test fast build" >> backend/README.md
git add .
git commit -m "test: verify fast worker build with new GPU base"
git push
```

**예상 결과:**
- Frontend: ~4분
- Backend: ~1분
- Worker: **~1-2분** ✅ (새 GPU 베이스 사용!)
- **총: ~6-7분**

### 3. 만약 여전히 느리다면?

원인 확인:
1. GitHub Actions 로그에서 Worker 빌드 단계 확인
2. "Pulling worker base image" 성공 여부
3. Dockerfile의 어느 스테이지가 실행되는지

### 4. 최종 확인 명령어

```bash
# ECR의 최신 Worker 베이스 확인
aws ecr describe-images \
  --repository-name haenet-worker-base \
  --region ap-northeast-2 \
  --query 'imageDetails[0].[imagePushedAt, imageTags]'

# 로컬에서 테스트
docker pull 690641653744.dkr.ecr.ap-northeast-2.amazonaws.com/haenet-worker-base:latest
docker run --rm 690641653744.dkr.ecr.ap-northeast-2.amazonaws.com/haenet-worker-base:latest \
  python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.version.cuda}')"

# 예상 출력:
# PyTorch: 2.6.0+cu126
# CUDA: 12.6
```

## 타임라인 비교

### 현재까지
- build #30 (base test): 16분 18초 (CPU 베이스)
- build #31: 8분 30초 (CPU 베이스)
- build #32: 진행 중... (타이밍 이슈?)

### 다음 빌드 (예상)
- build #33: **6-7분** ✅ (GPU 베이스 사용!)

---

**결론**: 현재 빌드(#32)는 타이밍 이슈로 인해 여전히 느릴 수 있습니다.
**진짜 테스트는 다음 빌드(#33)에서 확인!**

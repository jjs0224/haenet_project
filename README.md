# Backend API + MySQL (Docker Compose)

이 저장소는 Docker Compose로 **MySQL(DB)** 과 **FastAPI(API)** 를 함께 실행하도록 구성되어 있습니다.  
최초 실행 시 DB 컨테이너가 `backend/db` 아래의 초기화 스크립트(`schema.sql`, `seed.sql`)를 자동 실행합니다. fileciteturn1file0L14-L18

---

## 1) 요구사항

- Docker Desktop (Windows/Mac) 또는 Docker Engine (Linux)
- `docker compose` 사용 가능

---

## 2) 빠른 시작 (팀원용: clone 후 1분 실행)

### 2.1 환경변수 파일 준비

`.env`는 커밋하지 않는 것이 안전합니다(`.gitignore`에 포함 권장).  
대신 예시 파일을 복사해 사용하세요.
(!!! 현재는 개발 편의상 .env 파일을 그대로 사용하고 있습니다. !!!)

- macOS / Linux

```bash
cp env.example .env
```

- Windows (CMD)

```bat
copy env.example .env
```

> Compose는 `env_file: - .env`를 사용합니다. fileciteturn1file0L32-L36  
> 예시로는 `DB_HOST=mysql`, `DB_PORT=3306`, `DB_NAME=app_db`, `DB_USER=app_user`, `DB_PASSWORD=app_password` 형태입니다. fileciteturn2file2L5-L10

### 2.2 실행

프로젝트 루트(= `docker-compose.yml` 위치)에서:

```bash
docker compose up --build
```

### 2.3 접속/확인

- Health Check: http://localhost:8000/health fileciteturn4file7L20-L22
- Swagger UI: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json

---

## 3) 구성 요약

### 3.1 컨테이너 2개가 정상입니다

- `mysql` (MySQL 8) : `3306:3306` fileciteturn4file1L2-L13
- `api` (FastAPI/Uvicorn) : `8000:8000` fileciteturn4file1L25-L46

### 3.2 DB 초기화 스크립트

MySQL 공식 이미지 동작 방식에 따라, **DB 볼륨이 비어 있는 “최초 1회”만** 아래 경로의 SQL이 자동 실행됩니다.

- 호스트 경로: `./backend/db`
- 컨테이너 경로: `/docker-entrypoint-initdb.d` fileciteturn1file0L14-L18

> 만약 SQL 파일을 루트의 `./db`로 옮길 경우, compose의 마운트 경로도 함께 수정해야 합니다. fileciteturn1file0L16-L18

---

## 4) 자주 쓰는 명령어

### 4.1 상태 확인

```bash
docker compose ps
```

### 4.2 로그 확인

```bash
docker compose logs -f mysql
docker compose logs -f api
```

### 4.3 종료

```bash
docker compose down
```

### 4.4 DB까지 완전 초기화(주의: 데이터 삭제)

초기화 SQL을 다시 적용하고 싶을 때:

```bash
docker compose down -v
docker compose up --build
```

---

## 5) 로컬 개발 모드 (선택)

test

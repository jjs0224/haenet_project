# Dev → Prod Promotion Rules (Auto-Apply)

This document defines the replacement rules used to promote dev values into prod
while preserving prod-specific endpoints, credentials, and domains.

## Core Rules (Prod Overrides)
- APP_ENV: prod
- Ingress host: app.example.com
- Redis URL (prod): redis://redis.app-prod.svc.cluster.local:6379/0
- S3 bucket: prod-bucket-name
- Secrets placeholders: PROD_* (GEMINI_API_KEY / DB_PASSWORD / JWT_SECRET_KEY)

## File-Specific Rules
### k8s/env/prod/api-values.yaml
- DB_HOST: database-1.c7oeqq6c6a58.ap-northeast-2.rds.amazonaws.com
- REDIS_URL: redis://redis.app-prod.svc.cluster.local:6379/0
- secret.dbPassword/secret.jwtSecretKey: PROD_DB_PASSWORD_CHANGE_ME / PROD_JWT_CHANGE_ME
- ingress.host: app.example.com

### k8s/env/prod/frontend-values.yaml
- ingress.host: app.example.com

### k8s/env/prod/platform-values.yaml
- host: app.example.com
- apiServiceName: api-prod
- frontendServiceName: frontend-prod

### k8s/env/prod/worker-*-values.yaml
- APP_ENV: prod
- redisUrl: redis://redis.app-prod.svc.cluster.local:6379/0
- S3_BUCKET: prod-bucket-name
- GEMINI_API_KEY / DB_PASSWORD / JWT_SECRET_KEY: PROD_* placeholders

## Notes
- prod 최신 파일(platform/redis/worker-menu-assistant)은 그대로 두고,
  위 규칙으로 prod-specific 값만 고정합니다.
- dev 최신 파일(api/frontend/worker-journal/worker-review)은 dev 변경을 반영하되
  prod-specific 값은 반드시 덮어씌웁니다.

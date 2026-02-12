# Environment and Runtime Configuration

## API (chart: k8s/charts/api)
Deployment env keys:
- APP_ENV
- DB_HOST, DB_PORT, DB_NAME, DB_USER
- REDIS_URL
- QUEUE_NAME_MENU_ASSISTANT
- QUEUE_NAME_JOURNAL
- QUEUE_NAME_REVIEW
- DB_PASSWORD, JWT_SECRET_KEY
- GEMINI_API_KEY, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET

Values sources:
- k8s/env/dev/api-values.yaml
- k8s/env/prod/api-values.yaml

## Worker (chart: k8s/charts/worker)
ConfigMap keys (envFrom):
- APP_ENV, LOG_LEVEL
- QUEUE_TYPE, REDIS_URL, QUEUE_NAME, QUEUE_PROCESSING_NAME
- AWS_REGION, SQS_QUEUE_URL
- S3_BUCKET, S3_PREFIX

Secret env keys (envFrom secretRef):
- GEMINI_API_KEY, DB_PASSWORD, JWT_SECRET_KEY

Values sources:
- k8s/env/dev/worker-menu-assistant-values.yaml
- k8s/env/dev/worker-journal-values.yaml
- k8s/env/dev/worker-review-values.yaml
- k8s/env/prod/worker-menu-assistant-values.yaml
- k8s/env/prod/worker-journal-values.yaml
- k8s/env/prod/worker-review-values.yaml

## S3 Storage Switch
Code paths:
- backend/app/common/utils/util.py -> get_storage()
- backend/app/common/storage/s3.py
- backend/app/common/storage/local.py

Switch to S3:
- STORAGE_DRIVER=s3
- S3_BUCKET=<bucket>
- S3_REGION=<region> (optional)
- S3_PREFIX=<prefix>

Notes:
- boto3 must be available in the runtime image
- ensure IAM permissions for s3:PutObject, s3:GetObject, s3:DeleteObject

## Redis Job Queue Naming
API routes enqueue tasks by prefix (backend/app/core/job_queue.py):
- menu_assistant_* -> QUEUE_NAME_MENU_ASSISTANT
- journal_* -> QUEUE_NAME_JOURNAL
- review_* -> QUEUE_NAME_REVIEW

Workers consume QUEUE_NAME from their own values:
- menu assistant: cicdex:jobs:menu_assistant
- journal: cicdex:jobs:journal
- review: cicdex:jobs:review

Check:
- API values match worker values for each queue name

## Redis Connection (API)
API reads REDIS_URL and derives host/port/db for redis_client.
If REDIS_URL is not set, it falls back to REDIS_HOST/REDIS_PORT/REDIS_DB.

## DB Environment Switch (local -> RDS)
Local:
- DB_HOST=127.0.0.1 (or docker host)
- DB_USER/DB_PASSWORD from .env

RDS:
- DB_HOST=<rds-endpoint>
- DB_PORT=3306
- DB_NAME=<db-name>
- DB_USER/DB_PASSWORD=<rds credentials>

Notes:
- Update secrets in AWS Secrets Manager for prod/dev
- Ensure security group allows app-dev/app-prod to reach RDS

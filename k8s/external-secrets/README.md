# External Secrets Layout

Structure:
- app-dev/
  - secretstore.yaml
  - externalsecret-api.yaml
  - externalsecret-worker.yaml
- app-prod/
  - secretstore.yaml
  - externalsecret-api.yaml
  - externalsecret-worker.yaml

Naming:
- AWS secret: app-<env>-secrets
- API secret target: api-<env>-secrets
- Worker secret target: worker-secrets (shared across worker apps in namespace)

Notes:
- API chart fullname includes release name, so secret name must match release.
- Worker chart fullname is fixed to "worker" (no release in name).
- ExternalSecret data keys map to AWS secret properties (DB_PASSWORD, JWT_SECRET_KEY, GEMINI_API_KEY).
- One AWS secret per environment: app-dev-secrets, app-prod-secrets.

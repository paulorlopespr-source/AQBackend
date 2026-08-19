# Publicação no Railway

## Serviço 1 — PostgreSQL
Crie um PostgreSQL no projeto.

Use a URL fornecida pelo Railway em:

`DATABASE_URL`

Se a URL vier como `postgresql://...`, prefira no app:

`postgresql+psycopg://...`

## Serviço 2 — AQ Backend
Suba este repositório como serviço.

Variáveis mínimas:

- `DATABASE_URL`
- `JWT_SECRET`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `SPORTS_API_KEY`
- `INTERNAL_CRON_TOKEN`
- `ENVIRONMENT=production`
- `SYNC_MODE=cron`

A futura chave de IA:

- `OPENAI_API_KEY`

## Healthcheck

Path:

`/health`

## Cron
Crie uma chamada periódica ao endpoint:

`POST /api/v1/internal/sync`

Header:

`X-Cron-Token: <INTERNAL_CRON_TOKEN>`

Não use `SYNC_MODE=loop` se houver mais de uma réplica do backend.

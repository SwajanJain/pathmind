# PathMind local runbook

## Prerequisites

- Python 3.11
- Node 20 + pnpm
- Docker

## Start local infra

`docker compose -f infra/docker/docker-compose.yml up -d`

## API

```
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn pathmind_api.main:app --reload
```

## Nightly ETL + privacy jobs

Run manually:

```
cd apps/api
source .venv/bin/activate
python -m pathmind_api.etl run-reactome-etl --mode nightly
python -m pathmind_api.etl purge-api-logs --retention-days 90
```

Cron-compatible examples:

```
0 2 * * * cd /Users/swajanjain/Documents/Projects/Pathway-Impact/apps/api && source .venv/bin/activate && python -m pathmind_api.etl run-reactome-etl --mode nightly >> /tmp/pathmind-etl.log 2>&1
15 2 * * * cd /Users/swajanjain/Documents/Projects/Pathway-Impact/apps/api && source .venv/bin/activate && python -m pathmind_api.etl purge-api-logs --retention-days 90 >> /tmp/pathmind-retention.log 2>&1
```

## Web

```
corepack pnpm install
corepack pnpm contracts:generate
cd apps/web
corepack pnpm dev
```

## Smoke checks

- `GET /api/health`
- search for `erlotinib`
- run comparison `erlotinib` vs `lapatinib`
- open generated share link

## Full local validation checklist

```
cd /Users/swajanjain/Documents/Projects/Pathway-Impact
corepack pnpm contracts:generate
corepack pnpm validate:local
corepack pnpm --filter @pathmind/web test:e2e
```

# PathMind V1 Monorepo

PathMind is a drug-to-pathway impact analysis tool.

## Workspaces

- `apps/api` - FastAPI backend, scoring engine, persistence, and API clients
- `apps/web` - Next.js frontend with search, analysis dashboard, compare, and share pages
- `packages/contracts` - generated TypeScript contracts from FastAPI OpenAPI schema
- `infra/docker` - local Postgres + Redis
- `docs` - architecture decisions, attribution, and runbook

## Quick start

1. Start infra:
   - `docker compose -f infra/docker/docker-compose.yml up -d`
2. Run API:
   - `cd apps/api && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && uvicorn pathmind_api.main:app --reload`
3. Generate contracts:
   - `corepack pnpm install && corepack pnpm contracts:generate`
4. Run web:
   - `cd apps/web && corepack pnpm dev`

## Notes

- V1 is Reactome-only for pathway mapping.
- V1 provides target-level directionality, not pathway-level directionality.
- Share links are immutable frozen snapshots.
- Nightly ETL command: `python -m pathmind_api.etl run-reactome-etl --mode nightly` (from `apps/api`).
- Privacy retention command: `python -m pathmind_api.etl purge-api-logs --retention-days 90` (from `apps/api`).

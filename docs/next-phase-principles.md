# Next-Phase Principles (Applies to Phases 2A–4)

This project is built first for you and a small group of trusted collaborators, but it must behave like a world-class scientific tool:

## Non-Negotiables

1. **Never imply certainty you don’t have**
   - Every non-trivial claim must surface *evidence type* and *unknown state* (measured vs predicted vs missing).
2. **Reproducible outputs**
   - Every analysis/export/job stores a `version_snapshot` of relevant data sources (Reactome release, gene-set version, mapping version, etc.).
   - If results change across time, users can see *what changed*.
3. **Three-state evidence everywhere**
   - Any “risk/flag” or “absence of flag” is one of: `positive` (evidence of concern), `negative` (evidence of no concern), `unknown` (not tested / not available).
   - “Unknown” must be explicit and visually distinct. Silence is not allowed.
4. **Defaults beat options**
   - Pick one deterministic default pipeline per feature; keep other methods as optional cross-checks.
5. **Local-first privacy for sensitive uploads**
   - For genomics (VCF) and other sensitive uploads, default to local-only processing or ephemeral storage with explicit deletion controls.
6. **Simple async, not infrastructure theater**
   - Prefer a minimal `jobs` table + polling endpoints before introducing brokers/queues.

## Minimal Job Model (when needed)

When phases introduce long-running tasks (enrichment, PharmCAT, bulk dataset ingestion), use:

- `POST /api/v1/jobs` → returns `job_id`
- `GET /api/v1/jobs/{job_id}` → status/progress/result pointer

Job record (minimum):
- `job_id`, `job_type`, `status` (`queued|running|succeeded|failed|canceled`)
- `created_at`, `started_at`, `finished_at`
- `progress` (0–1 or stage string)
- `error` (if failed)
- `result_ref` (DB row id or file path)
- `version_snapshot`

## Version Snapshot (minimum)

Store a single JSON object that can answer “what data did we use?”:

- Reactome release (or “unknown” if live lookup)
- HGNC mapping version/date (if used)
- GMT gene sets version/date (if used)
- DoRothEA/decoupler version (if used)
- GTEx/HPA dataset versions (if used)
- PharmCAT/CPIC/PharmGKB versions (if used)

## Data Source Policy

- Do not bundle datasets with restrictive redistribution terms inside the repo by default.
- Prefer “download on first run” with explicit user action + cached local copy.
- Always include attribution in UI and exports.

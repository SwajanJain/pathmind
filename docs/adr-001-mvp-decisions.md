# ADR 001 - PathMind V1 MVP decisions

## Status

Accepted

## Decisions

- V1 uses Reactome-only pathway mapping for commercial safety.
- V1 shows directionality at the drug->target edge only.
- Share links store immutable snapshots in PostgreSQL.
- Pathway scoring:
  - `(targets_hit / pathway_size) * median_pchembl`
- Umbrella pathways (depth <= 1) are excluded.
- Default display depth is Reactome levels 3-5 with child-over-parent dedup.

## Consequences

- KEGG/DrugBank/STRING integrations are deferred to V2+.
- Pathway-level up/down claims are deferred to V2 signed-topology support.


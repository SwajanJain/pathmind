# Data source attribution

Every analysis page and export should include a “Data sources” section and a `version_snapshot` (what releases/dates were used).

See `/Users/swajanjain/Documents/Projects/Pathway-Impact/docs/next-phase-principles.md:1`.

## Core V1 runtime sources

- ChEMBL (bioactivity; license/terms: confirm current ChEMBL terms, historically CC BY-SA)
- Reactome (pathways; license/terms: confirm current Reactome terms, historically CC0)
- UniProt (protein identifiers/annotations; license/terms: confirm current UniProt terms, historically CC BY)
- Open Targets (mechanism/directionality; license/terms: confirm current Open Targets terms)
- PubChem (compound identity/structure; license/terms: confirm current PubChem terms, historically public domain)

V1 explicitly excludes KEGG, DrugBank, and STRING from default/live product paths.

## Cross-phase data source table (Phases 2A–4)

This table is intentionally pragmatic: it records what we use by default, how we store it, and what to snapshot for reproducibility. If any row is “confirm”, treat it as a *pre-implementation check* before you bundle or redistribute anything.

| Source | Used in | Default? | Storage posture | License/terms (verify) | What to attribute | Version snapshot key |
|---|---|---:|---|---|---|---|
| ChEMBL | V1–3 | Yes | Live API + cached summaries | Confirm current terms (historically CC BY-SA) | ChEMBL + EMBL‑EBI | `chembl_release` |
| Reactome | V1–4 | Yes | Live API and/or local ETL tables | Confirm current terms (historically CC0) | Reactome | `reactome_release` |
| UniProt | V1–4 | Yes | API/cache; optionally local mapping tables | Confirm current terms (historically CC BY) | UniProt | `uniprot_release` |
| Open Targets | V1 | Yes | API/cache | Confirm current terms | Open Targets | `opentargets_release` |
| PubChem | V1–2A | Yes | API/cache | Confirm current terms (historically public domain) | PubChem | `pubchem_release` or `pubchem_fetched_at` |
| HGNC complete set | 2B–4 | Yes | Download-on-first-run + local copy | Confirm current terms | HGNC | `hgnc_version_or_date` |
| Reactome gene sets (GMT) | 2B | Yes | Download-on-first-run + local copy | Confirm redistribution terms for the exact GMT source | Reactome (and the distributor if applicable) | `reactome_gmt_version_or_date` |
| Reactome Analysis Service | 2B | No (cross-check) | Online request only | Confirm current terms | Reactome Analysis Service | `reactome_analysis_service_date` |
| DoRothEA regulons (via decoupler) | 2B | Optional | Pin package + record model version | Confirm current terms | DoRothEA + decoupler | `dorothea_version` / `decoupler_version` |
| LINCS L1000 / CMap | 2B | Optional | Online query (don’t bundle) | Confirm terms for each endpoint | LINCS/CMap endpoint used | `lincs_endpoint_date` |
| GTEx | 3–4 | Optional | Download-on-first-run + local copy | Confirm current terms | GTEx | `gtex_version_or_date` |
| Human Protein Atlas (HPA) | 3 | Optional | Download-on-first-run + local copy | Confirm current terms (often CC BY‑SA) | HPA | `hpa_version_or_date` |
| DILIrank | 3 | Optional | Download-on-first-run + local copy | Confirm current terms | DILIrank (source org) | `dilirank_version_or_date` |
| AOP-Wiki | 3 | Optional | Download-on-first-run + local copy | Confirm current terms | AOP‑Wiki | `aopwiki_version_or_date` |
| ToxCast/Tox21 (EPA) | 3 | Optional | API query or curated local copy | Confirm current terms | EPA ToxCast/Tox21 | `toxcast_version_or_date` |
| PharmCAT | 4 | Yes | Local JAR + pinned version | Confirm current terms | PharmCAT + PharmGKB/CPIC | `pharmcat_version` |
| CPIC guidelines | 4 | Yes | Online fetch or local tables | Confirm current terms | CPIC | `cpic_version_or_date` |
| PharmGKB | 4 | Optional (if used) | Online fetch or local tables | Confirm current terms | PharmGKB | `pharmgkb_version_or_date` |

## Non-negotiable UX rule

For any safety/toxicity/PGx panel: “no data” must render as **unknown**. Silence is not allowed.

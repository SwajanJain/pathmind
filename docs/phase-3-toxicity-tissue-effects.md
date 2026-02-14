# Phase 3: Toxicity Prediction & Tissue-Specific Effects

> Adds tissue expression overlays, toxicity pathway flagging, dose-toxicity modeling, and adverse outcome pathway (AOP) chain display.

## Phase 3 Defaults (P0)

- **Tri-state evidence everywhere:** `positive` | `negative` | `unknown` (never treat missing data as “safe”).
- **Versioning:** store dataset versions/dates in `version_snapshot` for GTEx/HPA/DILIrank/AOP-Wiki and any assay-derived metrics.
- **Local-first datasets:** preload GTEx/HPA/DILIrank/AOP-Wiki locally for fast, deterministic lookups.
- **Scope posture:** this phase produces *risk flags with evidence*, not clinical predictions.

See `/Users/swajanjain/Documents/Projects/Pathway-Impact/docs/next-phase-principles.md:1`.

---

## 1. Tissue-Specific Expression Overlay

### 1.1 Goal

Show where drug targets are expressed across human tissues, enabling predictions like "This drug target is highly expressed in liver but low in brain."

### 1.2 Data Sources

**GTEx (Genotype-Tissue Expression Project):**

| Detail | Value |
|--------|-------|
| Coverage | ~20,000 genes x 54 tissues |
| Units | TPM (Transcripts Per Million) |
| API | `https://gtexportal.org/api/v2/` |
| Auth | None (rate-limited) |
| Key endpoint | `GET /expression/medianGeneExpression?geneSymbol={symbol}` |
| Bulk download | Full median expression matrix (~100MB) |
| License | Open access |

**Human Protein Atlas (HPA):**

| Detail | Value |
|--------|-------|
| Unique value | Protein-level expression (immunohistochemistry) |
| RNA data | Consensus (integrates HPA + GTEx + FANTOM5) in NX units |
| Protein levels | Not detected / Low / Medium / High |
| Access | Individual gene JSON: `https://www.proteinatlas.org/{ENSG_ID}.json` |
| Bulk downloads | `normal_tissue.tsv.zip` (~5MB), `rna_tissue_consensus.tsv.zip` (~5MB) |
| License | CC BY-SA 3.0 |

### 1.3 Recommended Approach

Preload both datasets into the local database (~150MB total). This avoids per-gene API calls and enables fast lookups.

```sql
CREATE TABLE tissue_expression (
    gene_symbol TEXT NOT NULL,
    uniprot_id TEXT,
    tissue TEXT NOT NULL,
    tpm FLOAT,                    -- GTEx median TPM
    hpa_protein_level TEXT,       -- 'Not detected' | 'Low' | 'Medium' | 'High'
    rna_consensus_nx FLOAT,       -- HPA consensus NX
    PRIMARY KEY (gene_symbol, tissue)
);
```

### 1.4 Visualization Options

| View | Best For | Implementation |
|------|----------|---------------|
| Horizontal bar chart | Single gene, ranked tissues | Recharts BarChart, 1-2 days |
| Body map / anatomical SVG | Visual impact, single gene | Custom SVG + D3.js, 1-2 weeks |
| Heatmap matrix | Multiple genes x tissues | D3 heatmap or Recharts, 3-5 days |

**Start with:** Horizontal bar chart for single-gene views (simplest, most readable). Add heatmap matrix for pathway-level analysis showing all targets across key tissues.

### 1.5 Required Missing-Data & Uncertainty Rules

This feature is a *measurement overlay*, but any *derived claim* like “expressed in liver” must follow explicit unknown-state rules.

- **Identifier mapping first:** map `target → gene_symbol → Ensembl/UniProt` using a recorded mapping version (see Phase 2B). If mapping fails, expression is `unknown` (do not assume 0).
- **GTEx values are measured only when present:** if the dataset lookup returns no row for the gene, render `unknown` and show why (“gene not present in GTEx matrix” vs “mapping failed”).
- **Do not convert missing to zero:** a missing tissue value is `unknown`, not “not expressed”.
- **Keep “low” separate from “unknown”:** low TPM / HPA “Not detected” is *measured low*, not missing.
- **Surface scope caveats:** GTEx is healthy tissue; HPA has antibody/assay limitations. Display “dataset scope” beside plots.

---

## 2. Toxicity Pathway Flagging

### 2.1 Key Toxicity Pathway Categories

| Category | Reactome Pathway(s) | Key Genes |
|----------|---------------------|-----------|
| CYP metabolism | R-HSA-211859 (CYP arranged by substrate) | CYP3A4, CYP2D6, CYP2C9, CYP1A2 |
| Phase II conjugation | R-HSA-156580 | UGT1A1, GSTA1-5, GSTP1 |
| Oxidative stress / NRF2 | R-HSA-3299685 (Detox of ROS) | NFE2L2, KEAP1, HMOX1, NQO1 |
| Glutathione defense | R-HSA-156590 (GSH conjugation) | GCLC, GCLM, GSR, GPX1-8 |
| Mitochondrial toxicity | R-HSA-611105 (Respiratory ETC) | NDUFA*, SDHA-D, COX4-8, CYCS |
| Mitochondrial apoptosis | R-HSA-109606 (Intrinsic apoptosis) | BAX, BAK1, BCL2, APAF1 |
| DNA damage/repair | R-HSA-73894 (DNA Repair umbrella) | TP53, BRCA1/2, RAD51, PARP1, MLH1, MSH2 |
| Cellular stress | R-HSA-2262752 | HSF1, ATF4, DDIT3 (CHOP) |
| Bile acid metabolism | R-HSA-194068 | ABCB11 (BSEP), SLC10A1 (NTCP) |
| Nuclear receptors (PXR/CAR) | R-HSA-9006931 | NR1I2 (PXR), NR1I3 (CAR), AHR |

### 2.2 Flagging Logic

When a drug's target or off-target list overlaps with any toxicity pathway gene:

```python
toxicity_flags = []
for pathway_id, pathway_genes in TOXICITY_PATHWAYS.items():
    overlap = set(drug_target_genes) & set(pathway_genes)
    if overlap:
        toxicity_flags.append({
            "pathway": pathway_id,
            "risk_type": PATHWAY_RISK_MAP[pathway_id],  # "mitochondrial", "oxidative_stress", etc.
            "overlapping_genes": list(overlap),
            "severity": len(overlap) / len(pathway_genes),  # fraction hit
        })
```

**Traffic light display:**
- Red: evidence of concern (tested positive or strong mechanistic overlap)
- Yellow: moderate concern (single signal or weaker evidence)
- Green: evidence of no concern (tested negative)
- Gray/“?”: **unknown** (not tested / not available / insufficient evidence)

**Rule:** if evidence is missing, the UI must show `unknown`. Do not show nothing.

---

## 3. hERG / Cardiotoxicity Assessment

### 3.1 Why It Matters

hERG (KCNH2, ChEMBL target `CHEMBL240`) blockade causes QT prolongation and potentially fatal arrhythmias. Most common reason for drug market withdrawal.

### 3.2 Data Source

ChEMBL contains thousands of hERG IC50 measurements:
```
GET https://www.ebi.ac.uk/chembl/api/data/activity.json?target_chembl_id=CHEMBL240&molecule_chembl_id={drug_id}
```

### 3.3 Safety Margin Calculation

```
hERG Safety Margin = hERG_IC50 / Cmax_free
```

| Margin | Risk Level |
|--------|-----------|
| < 30x | High risk (red flag) |
| 30-100x | Moderate risk (yellow flag) |
| > 100x | Low risk (green) |

### 3.4 Implementation

For every analyzed drug:
1. Check if any target is KCNH2 or cardiac ion channels
2. Query ChEMBL for compound's hERG IC50 data
3. If hERG data exists, calculate safety margin against known/predicted Cmax
4. Display prominently in toxicity summary

**Tri-state requirement:**
- If hERG assays exist: `positive` or `negative` based on IC50/margin thresholds with provenance (assay count, summary stat).
- If no hERG assays exist: `unknown` (explicitly rendered; not green).
- If Cmax_free is missing: margin is `unknown` even if IC50 exists; show IC50-only with `unknown` margin.

---

## 4. DILI (Drug-Induced Liver Injury) Risk

### 4.1 DILIrank Dataset (FDA)

| Detail | Value |
|--------|-------|
| Source | FDA NCTR |
| Coverage | ~1,000 FDA-approved drugs |
| Categories | Most-DILI-concern, Less-DILI-concern, No-DILI-concern, Ambiguous |
| Format | Downloadable flat file |
| Size | ~1MB |

### 4.2 DILI Risk Scoring

Combine multiple signals:
1. **DILIrank lookup:** Direct classification if drug is in the dataset
2. **Pathway analysis:** Does the drug interact with CYP metabolism, GSH conjugation, or bile acid pathways?
3. **Reactive metabolite risk:** CYP2E1 or CYP3A4 metabolism can generate reactive metabolites
4. **BSEP inhibition:** If the drug inhibits bile salt export pump (ABCB11), flag cholestatic risk

**Tri-state requirement:**
- If the drug is found in DILIrank: `positive`/`negative` according to category with dataset version recorded.
- If the drug is not found: `unknown` (do not imply “no DILI risk”; it only means “not in this dataset”).
- If DILIrank dataset is unavailable/stale: `unknown` with explicit error state.

### 4.3 LiverTox (NIH/NLM)

Comprehensive clinical hepatotoxicity info for ~1,000 drugs. Provides likelihood scores (A-E), injury patterns (hepatocellular, cholestatic, mixed), and clinical features.

---

## 5. ToxCast / Tox21 (EPA) Integration

### 5.1 Data Access

| Detail | Value |
|--------|-------|
| API | `https://api-ccte.epa.gov/` (CCTE APIs) |
| Auth | API key required (free registration) |
| Coverage | ~9,000 chemicals x ~700 HTS assays |
| Key endpoints | `/chemical/search/`, `/bioactivity/`, `/hazard/` |

### 5.2 Relevant Assay Categories

| Assay Pattern | Toxicity Type |
|--------------|--------------|
| `TOX21_MitoMembranePotential_*` | Mitochondrial toxicity |
| `TOX21_ARE_BLA_*` | Oxidative stress (Antioxidant Response Element) |
| `TOX21_p53_*` | DNA damage / genotoxicity |
| `TOX21_ERa_*`, `TOX21_AR_*` | Endocrine disruption |
| `TOX21_NFkB_*` | Inflammatory response |
| Cell viability assays | General cytotoxicity |
| CYP inhibition assays | Drug-drug interaction potential |

### 5.3 Integration

For each analyzed compound:
1. Search CompTox by compound name/CAS/InChIKey
2. Fetch bioactivity results (AC50, hit-call) across ToxCast assays
3. Map positive hits to toxicity categories
4. Display as a toxicity profile panel

**Tri-state requirement:**
- If assay results exist: render `positive` or `negative` per assay/category thresholds with provenance (assay ids, AC50 summary).
- If no mapping to CompTox / no assay coverage: `unknown`.
- If API key/config missing: `unknown` (and explain the missing dependency).

---

## 6. Adverse Outcome Pathways (AOP-Wiki)

### 6.1 What AOPs Provide

Structured causal chains: Molecular Initiating Event (MIE) -> Key Events (KEs) -> Adverse Outcome (AO).

### 6.2 API Access

```
GET https://aopwiki.org/aops.json          # All AOPs
GET https://aopwiki.org/aops/{id}.json     # Individual AOP
GET https://aopwiki.org/events/{id}.json   # Key Events
GET https://aopwiki.org/stressors.json     # Chemical stressors
```

### 6.3 Key AOPs for Drug Toxicity

| AOP ID | MIE | Adverse Outcome |
|--------|-----|----------------|
| 17 | hERG blockade | Sudden cardiac death |
| 18 | PPARa activation | Liver steatosis |
| 3 | Protein alkylation (reactive metabolites) | Liver fibrosis |
| 38 | ETC inhibition | Kidney failure |
| 220 | BSEP inhibition | Cholestatic liver injury |
| 32 | ER binding | Reproductive toxicity |

### 6.4 Implementation

1. Download AOP-Wiki data (JSON, ~10MB, ~200-300 well-documented AOPs)
2. Extract MIE -> KE -> AO chains with associated genes/proteins
3. When analyzing a drug, check if targets match any MIE
4. If matched, display the full causal chain:

```
Drug X --inhibits--> hERG (MIE)
  --> Delayed ventricular repolarization (KE)
  --> QT prolongation (KE)
  --> Torsades de Pointes (AO)
```

### 6.5 Tri-state Requirement (AOP Chains)

AOP-Wiki is not a comprehensive “all hazards” database. Therefore:

- If one or more targets match an MIE/KE with a traceable chain: render `positive` with the exact matched node(s) and AOP-Wiki version/date.
- If no AOP match is found for the targets: render `unknown` (not `negative`). Absence of a chain in AOP-Wiki is not evidence of safety.
- If dataset is unavailable/stale: render `unknown` with explicit error state.

---

## 7. Multi-Tissue Impact View

### 7.1 Tissue-Specific Pharmacological Impact

Combine tissue distribution with target expression:

```
Impact_tissue = Kp_tissue * TPM_target_tissue * potency
```

Where:
- `Kp_tissue`: tissue:plasma partition coefficient (from Rodgers-Rowland equations using logP, pKa, fu_p)
- `TPM_target_tissue`: target gene expression in that tissue (from GTEx)
- `potency`: binding affinity from ChEMBL (1/IC50 or pChEMBL)

### 7.2 Simplified Kp Estimation

Using physicochemical properties only (no PBPK simulation needed):

| Input | Source |
|-------|--------|
| logP (lipophilicity) | ChEMBL or RDKit calculation |
| pKa (ionization) | ChEMBL or predicted |
| fu_p (fraction unbound in plasma) | ChEMBL ADME data |
| Blood:plasma ratio | ChEMBL or default = 1.0 |

Key tissue distribution rules:
- High logP -> concentrates in adipose tissue
- Hepatic metabolism -> concentrates in liver
- Low polar surface area + moderate logP -> crosses BBB (brain)

### 7.3 Minimum Viable Tissue View

A table with 6-8 key tissues:

| Tissue | Drug Exposure | Target Expression | Impact Score | Key Risk |
|--------|-------------|-------------------|-------------|----------|
| Liver | High (Kp=15) | CYP3A4: High | Critical | DILI risk |
| Heart | Moderate (Kp=3) | hERG: Moderate | Moderate | QT risk |
| Brain | Low (Kp=0.2) | Target: Low | Low | -- |
| Kidney | Moderate (Kp=5) | OAT1: High | Moderate | Nephrotoxicity |

Color-coded cells with expandable detail view per tissue.

**Missing-data rule:** if any required inputs for an impact cell are missing (Kp estimate inputs, expression, or potency), mark that cell as `unknown` and show what is missing.

---

## 8. ADME Data Sources

| Source | Provides | Access |
|--------|----------|--------|
| ChEMBL | In vitro ADME (Caco-2, microsomal clearance, PPB, CYP inhibition) | REST API (free) |
| pkCSM | Predicted ADME from SMILES | Web tool |
| SwissADME | ADME property prediction | Web tool |
| ADMET-AI | ML-predicted ADME/Tox properties | Python package |

**Note:** DrugBank is intentionally excluded from the default Phase 3 build path unless you explicitly obtain and document a license compatible with your intended distribution.

---

## 9. Data to Preload

| Dataset | Size | Update Frequency |
|---------|------|-----------------|
| GTEx median expression matrix | ~100MB | Annually |
| HPA tissue expression (RNA + protein) | ~50MB | Annually |
| DILIrank | ~1MB | Rarely |
| AOP-Wiki full JSON | ~10MB | Quarterly |
| Reactome toxicity pathway gene lists | ~5MB | Quarterly |
| ToxCast/InVitroDB summary | ~200MB | Annually |

---

## 10. New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/tissue-expression/{gene}` | Get expression across tissues |
| `GET` | `/api/v1/tissue-expression/pathway/{id}` | Get expression for all pathway genes |
| `GET` | `/api/v1/toxicity/{drug_id}` | Get toxicity flags, hERG, DILI risk |
| `GET` | `/api/v1/toxicity/{drug_id}/aop` | Get matching adverse outcome pathways |
| `GET` | `/api/v1/tissue-impact/{drug_id}` | Get multi-tissue impact matrix |
| `GET` | `/api/v1/herg/{drug_id}` | Get hERG safety margin |

---

## 11. Implementation Priority

1. **Tissue expression overlay (GTEx/HPA)** -- highest data quality, most straightforward
2. **Toxicity pathway flagging** -- well-defined gene lists, mechanistic
3. **DILI risk scoring** -- high clinical relevance, DILIrank is a simple lookup
4. **AOP chain display** -- provides mechanistic narrative, straightforward API
5. **hERG safety margin** -- critical safety signal, ChEMBL data available
6. **ToxCast integration** -- rich data but needs API key + larger data processing
7. **Tissue distribution modeling (Kp)** -- requires more computational infrastructure

---

## 12. What Is Realistic vs. Requires Clinical Data

| Predictable In Silico | Requires Clinical/In Vivo Data |
|----------------------|-------------------------------|
| hERG IC50 / QT risk | Actual QT prolongation in humans |
| CYP inhibition/induction | Clinical DDI magnitude |
| Reactive metabolite likelihood | Idiosyncratic DILI |
| Mitochondrial toxicity (ToxCast) | Immune-mediated toxicity |
| Tissue distribution (Kp estimates) | Actual human PK parameters |
| Off-target binding prediction | Rare adverse events (1:10,000+) |
| Genotoxicity (Ames prediction) | Teratogenicity |
| Hepatocellular toxicity | Kidney toxicity (limited models) |

**Principle:** Present computational predictions as risk flags with confidence levels, not definitive predictions.

---

## 13. Success Criteria

1. Every drug target shows tissue expression profile (bar chart across 54 tissues)
2. Toxicity pathway overlap is flagged with traffic-light severity
3. hERG safety margin is calculated and displayed when ChEMBL data exists
4. DILI risk category shown for drugs in the DILIrank dataset
5. At least 3 AOP chains are traceable from drug targets to adverse outcomes
6. Multi-tissue impact table shows relative risk across 6-8 key organs
7. Every risk/flag panel renders `positive|negative|unknown` explicitly (no silent missing data), and surfaces the relevant `version_snapshot`

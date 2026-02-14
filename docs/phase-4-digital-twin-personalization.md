# Phase 4: Digital Twin & Personalized Medicine

> Accepts patient-specific genomic/transcriptomic data, provides pharmacogenomic predictions, patient-specific pathway activity, and lays groundwork for mechanistic simulation.

---

## 1. Multi-Omics Integration

### 1.1 Patient Profile Schema

```
Patient Profile
  |-- Genomics Layer (VCF file)
  |   |-- Pharmacogenomic variants (star alleles, diplotypes)
  |   |-- Actionable somatic mutations (if oncology)
  |   +-- Structural variants affecting drug targets
  |
  |-- Transcriptomics Layer (expression matrix, optional)
  |   |-- Gene expression (TPM values)
  |   |-- Pathway activity scores (via PROGENy/decoupler)
  |   +-- Drug target expression levels
  |
  |-- Proteomics Layer (optional, future)
  |   |-- Protein abundances
  |   +-- Phosphorylation status of signaling nodes
  |
  +-- Metabolomics Layer (optional, future)
      |-- Metabolite concentrations
      +-- Drug metabolite levels
```

**Graceful degradation:** Most patients will only have VCF + (optionally) expression data. PGx from VCF alone is already valuable. Each additional layer enriches predictions but is not required.

### 1.2 Multi-Omics Integration Tools (Future)

| Tool | Purpose | Language |
|------|---------|----------|
| MOFA+ | Multi-Omics Factor Analysis, finds shared variation patterns | R/Python |
| COSMOS (Saez-Rodriguez lab) | Integrates phosphoproteomics + transcriptomics + metabolomics using prior knowledge | Python |
| PROGENy | Pathway activity from expression (footprint-based) | R/Python (via decoupler) |
| DIABLO (mixOmics) | Supervised multi-omics integration | R |

**Practical note:** MOFA+ and COSMOS are designed for cohort analysis, not individual patients. Applying them to single patients is an active research problem. For MVP, use simpler per-layer analysis (PGx from VCF, pathway activity from expression) rather than attempting multi-omics integration algorithms.

---

## 2. Pharmacogenomics Pipeline

### 2.1 Goal

Given a patient's VCF file, determine pharmacogenomic metabolizer status and generate drug-specific dosing recommendations using CPIC guidelines.

### 2.2 Core Tool: PharmCAT

| Detail | Value |
|--------|-------|
| Full name | Pharmacogenomics Clinical Annotation Tool |
| Developer | PharmGKB / CPIC |
| Language | Java (open source) |
| Input | VCF file |
| Output | JSON report with star alleles, diplotypes, phenotypes, CPIC recommendations |
| Genes covered | CYP2D6, CYP2C19, CYP2C9, CYP3A5, DPYD, TPMT, UGT1A1, SLCO1B1, HLA-B, HLA-A, ~25 total |

**Integration approach:** Wrap PharmCAT as a subprocess or REST microservice. Parse its JSON output and map to your drug database.

### 2.3 PGx Workflow

```
Step 1: VCF Upload
  |-- Validate VCF format (VCFv4.1+)
  |-- Check for required PGx regions (warn if low coverage)
  v
Step 2: Star Allele Calling (PharmCAT)
  |-- Calls star alleles for all covered PGx genes
  |-- Handles multi-allelic sites, phasing heuristics
  |-- CYP2D6: limited structural variant detection from VCF only
  v
Step 3: Phenotype Translation (CPIC tables)
  |-- Diplotype -> Activity Score -> Metabolizer Status
  |-- Example: CYP2D6 *1/*4 -> AS=1.0 -> Intermediate Metabolizer
  v
Step 4: Clinical Recommendations (CPIC guidelines)
  |-- Drug-specific dosing adjustments or therapeutic alternatives
  |-- Evidence level: 1A (strongest) to 4 (preliminary)
```

### 2.4 Example Outputs

| PGx Result | Drug Impact |
|-----------|------------|
| CYP2D6 Poor Metabolizer (*4/*4) | Codeine: will NOT be converted to morphine, ineffective. Consider alternative analgesic. |
| CYP2D6 Ultrarapid Metabolizer (*1/*1xN) | Codeine: rapid conversion to morphine, toxicity risk. Avoid codeine. |
| CYP2C19 Poor Metabolizer (*2/*2) | Clopidogrel: will NOT be activated, ineffective. Consider prasugrel or ticagrelor. |
| DPYD Intermediate Metabolizer (*1/*2A) | 5-fluorouracil: toxicity risk. Dose reduction required. |
| SLCO1B1 *5/*5 | Simvastatin: increased myopathy risk. Use lower dose or alternative statin. |
| HLA-B*57:01 positive | Abacavir: DO NOT prescribe. Hypersensitivity reaction risk. |

### 2.5 Supplementary Star Allele Callers (for CYP2D6)

CYP2D6 is the most complex PGx gene (100+ alleles, structural variants, gene deletions/duplications). VCF-only calling misses structural variants.

| Tool | Input | Advantage |
|------|-------|-----------|
| PharmCAT | VCF | Comprehensive, handles most PGx genes |
| Cyrius (Illumina) | BAM/CRAM | Best CYP2D6 accuracy with structural variants |
| Stargazer (St. Jude) | BAM/CRAM | CYP2D6 + other complex genes, copy number detection |
| StellarPGx | WGS BAM | CYP2D6 structural variants from short reads |

**Recommendation:** Use PharmCAT as primary. Offer Cyrius/Stargazer as optional upgrade if user provides BAM files.

---

## 3. PharmGKB Knowledge Base

### 3.1 Data Access

| Method | Details |
|--------|---------|
| REST API | `https://api.pharmgkb.org/v1/data/` |
| Bulk download | TSV files of all annotations (academic license) |
| Coverage | ~1,000 drugs, ~600 genes, ~5,000 variant annotations |

### 3.2 Evidence Levels

| Level | Meaning | Use In Tool |
|-------|---------|------------|
| 1A | CPIC guideline or FDA PGx label | Show prominently, actionable |
| 1B | Strong evidence | Show prominently |
| 2A | Known pharmacogene, moderate evidence | Show in detail view |
| 2B | Moderate evidence | Show in detail view |
| 3 | Low evidence | Optional display |
| 4 | Preliminary | Hide by default |

### 3.3 Key Data Types

- Clinical annotations: (variant, drug) -> (phenotype, dosing recommendation)
- Drug-gene relationships: which genes affect which drugs
- VIP (Very Important Pharmacogene) pathways: curated PGx pathways with diagrams
- CPIC guidelines: machine-readable dosing tables
- FDA drug labels with PGx information

---

## 4. Patient-Specific Pathway Activity

### 4.1 Goal

Given patient RNA-seq data, compute per-pathway activity scores and overlay on existing drug-pathway visualizations.

### 4.2 Tools

**PROGENy (via decoupler):**
- Estimates pathway activity from gene expression using footprint-based analysis
- Pre-trained on perturbation experiments
- Covers 14 cancer-relevant pathways (EGFR, MAPK, PI3K, TNFa, NFkB, JAK-STAT, etc.)
- Fast, validated, production-ready

```python
import decoupler as dc

# Get PROGENy model
progeny = dc.get_progeny(organism='human', top=500)

# Run pathway activity inference
estimate, pvalue = dc.run_mlm(mat=patient_expression, net=progeny)
```

**Full enrichment (from Phase 2B):**
- GSEApy + Reactome GMT for broader pathway coverage
- Not limited to PROGENy's 14 pathways

### 4.3 Patient vs Population Comparison

For each pathway:
1. Compute patient-specific activity score
2. Compare against reference distribution (e.g., GTEx healthy tissue or TCGA cohort)
3. Report as z-score or percentile: "EGFR pathway activity is in the 95th percentile compared to normal tissue"
4. Flag pathways that are abnormally active AND targeted by the drug

---

## 5. Drug Response Prediction

### 5.1 Combining PGx + Pathway Activity

```
Drug Response Score = f(PGx_status, pathway_activity, target_expression)
```

**Rule-based component (high confidence):**
- CPIC 1A guidelines: definitive dosing recommendations
- HLA allele contraindications: absolute no-prescribe rules

**Score-based component (moderate confidence):**
- Pathway activity: if the drug's target pathway is highly active, the drug may be more effective
- Target expression: if the drug's target protein is not expressed, the drug will be ineffective
- Combined: weight pathway activity and target expression into a drug relevance score

### 5.2 Output

```python
class DrugResponsePrediction:
    drug_name: str
    pgx_recommendations: list[PGxRecommendation]  # From CPIC
    pathway_activity_context: list[PathwayActivity]  # Patient-specific
    target_expression_status: dict[str, float]  # Gene -> TPM in relevant tissue
    overall_suitability: str  # "recommended" | "use_with_caution" | "avoid" | "insufficient_data"
    evidence_level: str       # "high" (CPIC 1A) | "moderate" | "low"
    confidence_reasons: list[str]
```

---

## 6. Pathway Simulation (Stretch Goal)

### 6.1 QSP Modeling Tools

| Tool | Language | Strength | Limitation |
|------|----------|----------|-----------|
| Tellurium + libRoadRunner | Python | Fastest SBML ODE solver, loads Reactome/BioModels SBML | Requires model construction |
| COPASI (via BasiCO) | Python wrapper | Full simulation + parameter estimation | Desktop-oriented |
| PySB | Python-native | Rule-based modeling, models are code | Requires manual model building |
| PK-Sim (OSP Suite) | C#/.NET, R interface | Gold standard open-source PBPK, 15+ tissue compartments | Windows/.NET dependency |

### 6.2 The Parameter Problem

Reactome SBML exports have qualitative structure (which reactions connect which species) but lack quantitative kinetic parameters. Solutions:

1. **BioModels database:** ~1,000 curated, parameterized SBML models. Pick 5-10 drug-relevant ones (EGFR, PI3K/AKT/mTOR, MAPK, apoptosis)
2. **SABIO-RK:** Database of biochemical reaction kinetics (~7,000 reactions with parameters)
3. **Parameter estimation:** Use `pyPESTO` or COPASI parameter estimation with experimental data
4. **Default parameters:** Order-of-magnitude estimates for qualitative behavior

### 6.3 Patient-Specific Parameterization

| Omics Layer | Model Parameter Mapping |
|-------------|------------------------|
| VCF (mutations) | Loss-of-function -> protein activity = 0; gain-of-function -> increased activity |
| RNA-seq (expression) | Gene expression -> scale initial protein concentrations (mRNA ~ protein assumption) |
| Proteomics | Direct protein abundance -> set initial concentrations |
| Metabolomics | Metabolite concentrations -> initial conditions for metabolic models |

**Practical workflow:**
1. Start with reference parameterized model (from BioModels)
2. Scale parameters based on patient omics data relative to reference
3. Simulate drug perturbation (add drug as inhibitor/activator)
4. Compare patient simulation to reference simulation

### 6.4 Feasibility Assessment

| Aspect | Assessment |
|--------|-----------|
| Single pre-built pathway simulation | Achievable (6-12 months) |
| Patient-parameterized simulation | Achievable for curated models (6-12 months) |
| Arbitrary pathway simulation | Not feasible (parameter problem) |
| Genome-scale simulation | Research frontier, not feasible for small team |

---

## 7. RNA Target Expansion (Future)

### 7.1 Types of RNA Drug Targets

| RNA Type | Drug Examples | Relevance |
|----------|-------------|-----------|
| mRNA | ASOs (nusinersen, eteplirsen) | Splice-switching, knockdown |
| siRNA targets | Patisiran, givosiran, inclisiran | Gene silencing |
| miRNA | Miravirsen (anti-miR-122) | miRNA inhibition |
| Pre-mRNA (splice sites) | Risdiplam (small molecule!) | Splice modification |
| lncRNA | Emerging targets | Regulatory modulation |

### 7.2 Databases

| Database | Content |
|----------|---------|
| miRTarBase | Validated miRNA-target interactions |
| miRBase | miRNA sequences and annotations |
| TargetScan | Predicted miRNA-target pairs |
| R-BIND | Small molecules that bind RNA |
| RNAcentral | Unified ncRNA database |
| LNCipedia / NONCODE | lncRNA annotation |

### 7.3 Practical Approach

Model RNA targets at the expression level (RNA-seq quantification) rather than attempting full mechanistic RNA biology. Use miRNA-target edges from miRTarBase as regulatory modifiers on existing pathway models.

---

## 8. Architecture

```
Phase 4 Architecture

User Input:
  |-- VCF file (required for PGx)
  |-- Gene expression matrix (optional)
  +-- Drug of interest (from Phase 1-3)

Backend Services:
  |-- PGx Service
  |   |-- PharmCAT (Java subprocess or REST wrapper)
  |   |-- CPIC recommendation engine
  |   +-- PharmGKB annotation lookup
  |
  |-- Pathway Activity Service
  |   |-- decoupler/PROGENy (Python)
  |   |-- Patient-specific pathway scores
  |   +-- Overlay on Reactome pathway maps
  |
  |-- Drug Response Predictor
  |   |-- PGx status + pathway activity -> prediction
  |   |-- Rule-based (CPIC) + score-based (pathway activity)
  |   +-- Confidence levels
  |
  +-- (Future) Simulation Service
      |-- Tellurium/libRoadRunner for ODE models
      |-- Pre-selected BioModels curated models
      +-- Patient-parameterized simulations

Frontend:
  |-- Patient profile dashboard
  |-- PGx report (metabolizer status, drug recommendations)
  |-- Pathway visualization with patient-specific coloring
  +-- Drug response prediction with evidence levels
```

---

## 9. New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/patient/upload-vcf` | Upload and process VCF file |
| `POST` | `/api/v1/patient/upload-expression` | Upload expression matrix |
| `GET` | `/api/v1/patient/{id}/pgx` | Get pharmacogenomic results |
| `GET` | `/api/v1/patient/{id}/pgx/drug/{drug_id}` | Get drug-specific PGx recommendation |
| `GET` | `/api/v1/patient/{id}/pathway-activity` | Get patient pathway activity scores |
| `GET` | `/api/v1/patient/{id}/drug-response/{drug_id}` | Get combined drug response prediction |
| `POST` | `/api/v1/simulate` | Run pathway simulation (stretch) |

---

## 10. Data Model Changes

```sql
-- Patient profiles
CREATE TABLE patient_profiles (
    id UUID PRIMARY KEY,
    user_id UUID,
    label TEXT,                    -- User-friendly name
    has_vcf BOOLEAN DEFAULT FALSE,
    has_expression BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- PGx results
CREATE TABLE pgx_results (
    id UUID PRIMARY KEY,
    patient_id UUID REFERENCES patient_profiles(id),
    gene TEXT NOT NULL,            -- CYP2D6, CYP2C19, etc.
    diplotype TEXT,                -- *1/*4
    activity_score FLOAT,
    phenotype TEXT,                -- 'Poor Metabolizer'
    source TEXT DEFAULT 'pharmcat',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Drug-specific PGx recommendations
CREATE TABLE pgx_drug_recommendations (
    id UUID PRIMARY KEY,
    pgx_result_id UUID REFERENCES pgx_results(id),
    drug_name TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    evidence_level TEXT,           -- '1A', '1B', '2A', etc.
    cpic_guideline_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Patient pathway activity
CREATE TABLE patient_pathway_activity (
    id UUID PRIMARY KEY,
    patient_id UUID REFERENCES patient_profiles(id),
    pathway_id TEXT NOT NULL,
    activity_score FLOAT NOT NULL,
    p_value FLOAT,
    percentile FLOAT,              -- vs reference population
    method TEXT DEFAULT 'progeny',
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## 11. New Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| PharmCAT | Star allele calling + CPIC recommendations | Java JAR download |
| `decoupler` | PROGENy pathway activity | `pip install decoupler` |
| `pysam` | VCF file parsing | `pip install pysam` |
| `cyvcf2` | Fast VCF parsing (alternative) | `pip install cyvcf2` |
| Tellurium (stretch) | ODE pathway simulation | `pip install tellurium` |

---

## 12. Key Technical Risks

1. **CYP2D6 complexity:** 100+ star alleles, structural variants. VCF-only calling misses copy number changes. Budget extra time.
2. **Model validation:** Without clinical validation, pathway simulation outputs are hypotheses, not predictions. Be explicit in UI.
3. **VCF format heterogeneity:** Every sequencing provider outputs different VCF conventions. Budget significant input parsing time.
4. **Regulatory considerations:** If used clinically, falls under medical device regulation. "Research use only" disclaimer needed.
5. **Database currency:** PharmGKB, CPIC, ClinVar update regularly. Build update mechanism from day one.

---

## 13. Honest Assessment

| Level | Description | Achievable? |
|-------|-------------|------------|
| Simple | PGx from VCF (PharmCAT) + CPIC recommendations | Yes, 3-6 months |
| Middle | + Pathway activity from expression + drug response scoring | Yes, 6-12 months |
| Aspirational | Fully mechanistic patient simulation predicting arbitrary drug outcomes | No (research frontier) |

**Recommended framing:** "Personalized drug-pathway analysis informed by your genomic and transcriptomic data" rather than "digital twin that predicts exactly how you'll respond."

---

## 14. Implementation Priority

1. **PGx pipeline (VCF -> PharmCAT -> CPIC)** -- highest value, most tractable, 3-6 months
2. **Patient pathway activity scoring (expression -> PROGENy)** -- second priority, builds on Phase 2B
3. **Combined drug response prediction** -- integrates PGx + pathway activity
4. **Patient profile dashboard** -- UI to view all patient-specific results
5. **PBPK-based exposure prediction (PK-Sim, stretch)** -- patient demographics + PGx -> drug levels
6. **ODE pathway simulation (stretch)** -- curated BioModels only, patient-parameterized

---

## 15. Success Criteria

1. User uploads VCF and receives PGx metabolizer status for all major genes within 2 minutes
2. Drug-specific CPIC recommendations displayed with evidence levels
3. Patient pathway activity scores overlay on existing pathway visualizations (if expression data provided)
4. Combined drug response prediction shows suitability with clear confidence indicators
5. System degrades gracefully: VCF-only still provides full PGx value without expression data

# Phase 2B: Gene Expression & Transcriptomics Integration

> Accepts user-uploaded differential expression data, performs pathway enrichment, infers transcription factor activity, and connects drug-target effects to downstream expression changes.

## Phase 2B Defaults (P0)

- **Default enrichment:** local/offline Reactome gene sets + GSEApy (deterministic and reproducible).
- **Cross-check (optional):** Reactome Analysis Service as validation, not the default.
- **Mapping default:** HGNC complete set as primary mapping; UniProt API fallback for misses/ambiguity.
- **Async model:** uploads/enrichment/TF activity become `job_id` workflows only when request time exceeds practical HTTP limits.
- **Versioning:** store `version_snapshot` including gene-set version/date and mapping version/date.

See `/Users/swajanjain/Documents/Projects/Pathway-Impact/docs/next-phase-principles.md:1`.

---

## 1. DEG Upload & Parsing

### 1.1 Goal

Accept a table of differentially expressed genes (DEGs) from RNA-seq or microarray experiments. Map gene identifiers, run enrichment analysis, and overlay expression changes on existing pathway visualizations.

### 1.2 Supported Input Formats

| Format | Columns Required | Source |
|--------|-----------------|--------|
| CSV/TSV | `gene`, `log2FC`, `padj` (minimum) | DESeq2, edgeR, limma |
| CSV/TSV extended | + `baseMean`, `lfcSE`, `pvalue`, `stat` | DESeq2 full output |
| Excel (.xlsx) | Same columns as CSV | Common user format |

**Auto-detection logic:**
1. Detect delimiter (comma, tab, or Excel)
2. Scan header row for known column patterns (case-insensitive):
   - Gene: `gene`, `gene_symbol`, `Gene.symbol`, `SYMBOL`, `gene_name`, `ensembl_gene_id`, `ENTREZID`
   - log2FC: `log2FoldChange`, `log2FC`, `logFC`, `log2_fold_change`
   - Adjusted p-value: `padj`, `adj.P.Val`, `FDR`, `q_value`, `p_adjusted`
3. Validate: reject if any required column is missing or if < 10 genes pass significance threshold

### 1.3 Gene ID Mapping

Users may upload HGNC symbols, Ensembl IDs, or Entrez IDs. The system must map to UniProt accessions (used by Reactome).

**Mapping pipeline:**
1. Detect input ID type (regex patterns: `ENSG\d+` = Ensembl, `^\d+$` = Entrez, else HGNC symbol)
2. Map via **HGNC complete set** (symbol/alias → canonical symbol → UniProt) as the primary path
3. For misses/ambiguity, fallback to **UniProt API** lookups and cache the result
4. Resolve ambiguous mappings with clear rules:
   - prefer reviewed (Swiss-Prot) when available
   - prefer canonical isoform (no dash suffix) unless user explicitly requests isoforms
5. Store mapping outcomes with explicit `unknown` state when unresolved (do not drop silently)

**Data files to maintain:**
| File | Source | Size | Update Frequency |
|------|--------|------|-----------------|
| `hgnc_complete_set.txt` | EBI/HGNC | ~15MB | Monthly |
| Reactome gene sets (GMT) | MSigDB / Reactome exports | ~MBs | Per Reactome release |
| (Optional) UniProt idmapping dump | UniProt | large | Only if you need fully offline mapping |

---

## 2. Pathway Enrichment Analysis

### 2.1 Methods

**Over-Representation Analysis (ORA):**
- Input: list of significant DEGs (padj < 0.05, |log2FC| > 1)
- Test: Fisher's exact / hypergeometric test per pathway
- Tool: `gseapy.enrichr()` or `scipy.stats.hypergeom`
- Correction: Benjamini-Hochberg FDR via `statsmodels.stats.multitest.multipletests`

**Gene Set Enrichment Analysis (GSEA) -- Preranked:**
- Input: all genes ranked by `-log10(pvalue) * sign(log2FC)` (or just log2FC)
- Test: permutation-based enrichment score
- Tool: `gseapy.prerank()`
- Output: Normalized Enrichment Score (NES), FDR q-value, leading edge genes

### 2.2 Pathway Gene Sets

**Primary (default): Local Reactome gene sets (GMT)**
- Run enrichment offline via GSEApy for speed and reproducibility.
- Record the gene-set version/date in `version_snapshot`.
- Avoid bundling restricted datasets in the repo; prefer “download on first run” + cached local copy.

**Secondary: Reactome Analysis Service (server-side)**
```
POST https://reactome.org/AnalysisService/identifiers/projection
Content-Type: text/plain

UniProt_ID_1
UniProt_ID_2
...
```
Returns pathway enrichment with p-values, FDR, entity counts, and a visualization token.

### 2.3 Standard Output Schema

```python
class EnrichmentResult:
    pathway_id: str          # R-HSA-1640170
    pathway_name: str
    p_value: float           # Raw p-value
    fdr: float               # BH-adjusted
    enrichment_score: float  # NES (GSEA) or odds ratio (ORA)
    genes_in_pathway: int
    overlap_count: int
    overlap_genes: list[str] # Gene symbols
    direction: str           # "up" | "down" | "mixed"
    leading_edge_genes: list[str]  # GSEA only
```

### 2.4 Integration with Existing Pathway Scoring

**Combined scoring:**
```
combined = w1 * normalize(drug_target_score) + w2 * normalize(expression_score)
```

**Concordance flags:**
- "Concordant": drug targets this pathway AND expression data confirms perturbation
- "Discordant-silent": drug targets pathway BUT no expression changes (compensatory mechanisms?)
- "Discordant-indirect": no drug targets BUT strong expression changes (off-target/indirect effects)

### 2.5 Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `gseapy` | ORA + GSEA preranked | `pip install gseapy` |
| `decoupler` | Multi-method enrichment + TF activity | `pip install decoupler` |

---

## 3. Transcription Factor Activity Inference

### 3.1 Goal

Infer which transcription factors (TFs) are activated or repressed based on the user's DEG data, using curated TF-target regulatory networks.

### 3.2 DoRothEA Regulons

DoRothEA provides curated TF-target gene interactions with confidence levels:

| Level | Evidence | Coverage |
|-------|----------|----------|
| A | Curated from literature | ~100 TFs |
| B | ChIP-seq + motif | ~200 TFs |
| C | ChIP-seq OR motif + co-expression | ~500 TFs |
| D | Motif + co-expression | ~800 TFs |
| E | Co-expression only | ~1,400 TFs |

**Recommended filter:** Levels A + B + C for balanced coverage and confidence.

**Access via decoupler:**
```python
import decoupler as dc
dorothea = dc.get_dorothea(organism='human', levels=['A', 'B', 'C'])
# Returns DataFrame: source (TF), target (gene), weight (+1/-1), confidence
```

### 3.3 Activity Inference Pipeline

```python
import pandas as pd
import decoupler as dc

# Step 1: Prepare input (1-row matrix of log2FC values indexed by gene)
mat = pd.DataFrame({'contrast': deg_df.set_index('gene')['log2FC']}).T

# Step 2: Load regulons
net = dc.get_dorothea(organism='human', levels=['A', 'B', 'C'])

# Step 3: Run inference (multiple methods for robustness)
ulm_estimate, ulm_pvalue = dc.run_ulm(mat=mat, net=net)
mlm_estimate, mlm_pvalue = dc.run_mlm(mat=mat, net=net)

# Step 4: Consensus across methods
consensus_estimate, consensus_pvalue = dc.run_consensus(mat=mat, net=net)
```

**Interpretation:**
- Positive activity score = TF is more active (targets follow expected regulation pattern)
- Negative activity score = TF is less active
- Sort by absolute score or p-value to find most significantly altered TFs

### 3.4 Output Schema

```python
class TFActivityResult:
    tf_name: str              # e.g., "STAT3"
    activity_score: float     # From consensus method
    p_value: float
    direction: str            # "activated" | "repressed"
    n_targets: int            # Number of regulon targets in user data
    concordant_targets: int   # Targets matching expected direction
    top_target_genes: list[str]
```

---

## 4. Indirect Effects: Drug -> Target -> TF -> Downstream Expression

### 4.1 The Causal Chain

```
Drug --[binds]--> Protein Target --[signals via pathway]--> TF --[regulates]--> Genes (expression)
```

| Link | Data Source | Status |
|------|------------|--------|
| Drug -> Protein Target | ChEMBL binding data | Phase 1 (built) |
| Protein -> Pathway | Reactome | Phase 1 (built) |
| Pathway -> TF | Reactome participants + TF list cross-reference | New |
| TF -> Target Genes | DoRothEA regulons | New |
| Gene Expression | User DEG upload | New |

### 4.2 Building the Pathway -> TF Link

**Option 1: Cross-reference pathway participants with known TFs.**
For each Reactome pathway, get all protein participants. Check which are known TFs (from DoRothEA source list or TFClass/AnimalTFDB). This identifies TFs that are within signaling cascades.

**Option 2: OmniPath signed directed PPI.**
```
https://omnipathdb.org/interactions?datasets=omnipath&types=post_translational&fields=is_stimulation,is_inhibition
```
Trace shortest sign-consistent paths from drug targets to TFs. Each interaction has `is_stimulation` and `is_inhibition` flags for sign propagation.

### 4.3 Visualization: Multi-Layer Sankey

```
Layer 1: Drug (single node)
Layer 2: Direct protein targets (from binding data)
Layer 3: Pathways affected (from Reactome)
Layer 4: Transcription factors (from TF activity analysis)
Layer 5: Downstream regulated genes (from DoRothEA + user DEG data)
```

Edges colored: green = activation, red = inhibition. Each connection carries confidence score.

### 4.4 "Explained" vs "Unexplained" DEGs

- **Explained:** DEGs whose expression change is consistent with predicted TF activity from the drug's known targets (sign-consistent through the causal chain)
- **Unexplained:** Significant DEGs not traceable to any drug target through the network

Report: "42% of your DEGs can be mechanistically explained by the drug's known targets. 58% may represent off-target effects, compensatory mechanisms, or gaps in pathway databases."

---

## 5. LINCS L1000 / CMap Integration

### 5.1 Goal

Cross-reference the drug being analyzed with known drug-induced gene expression signatures from the LINCS L1000 dataset (~20,000 compounds, ~978 landmark genes).

### 5.2 Data Access

| Source | URL | Auth | Best For |
|--------|-----|------|----------|
| clue.io API | `https://api.clue.io/api/` | API key (free registration) | Query by drug name |
| SigCom LINCS | `https://maayanlab.cloud/sigcom-lincs/` | None | Query by gene signature |
| iLINCS | `http://www.ilincs.org/api/` | None | Simple signature search |
| GEO (bulk) | GSE92742, GSE70138 | None | Local analysis via `cmapPy` |

### 5.3 Use Cases

**"What does my drug do to expression?"**
Query clue.io by drug name to get its known L1000 expression signature. Display alongside user's DEG data.

**"What drugs match my expression profile?"**
Submit user's top up/down genes to CMap query API. Find drugs that mimic (positive connectivity score) or reverse (negative score) the pattern. Enables drug repurposing.

**Cross-validation:**
"Your expression data shows 67% agreement with the known L1000 signature of this drug in MCF7 cells."

### 5.4 Caveats to Surface to Users

- L1000 data is cell-line specific (primarily cancer lines: MCF7, A549, HT29, etc.)
- Only 978 landmark genes measured directly; rest are inferred
- Most data uses a single high dose (10 uM)
- Time point matters: 6h = immediate response, 24h = downstream/adaptive

---

## 6. Expression Overlay on Pathway Visualization

### 6.1 Node Color Mapping

Map log2FC to a diverging color scale on pathway nodes:
- Blue (downregulated, log2FC < 0) -> White (no change) -> Red (upregulated, log2FC > 0)
- Use `d3.scaleDiverging(d3.interpolateRdBu)`

### 6.2 Significance Indicators

- Solid border: padj < 0.05 (significant)
- Dashed border: padj >= 0.05 (not significant)
- Border thickness: `-log10(padj)`

### 6.3 Dual-Effect Nodes

When a protein is BOTH a drug target AND has expression changes:
- Split node or donut chart: outer ring = expression, inner = binding
- Tooltip: "EGFR: Drug target (Ki = 0.3 nM) | mRNA: log2FC = -1.2, padj = 0.003"

### 6.4 Explicit Unknown States (Required)

Do not let missing data masquerade as “no effect”:

- **Unmapped genes:** show counts and a downloadable list (`unknown` mapping state).
- **Ambiguous genes/IDs:** surface the ambiguity and the rule chosen (or require user selection for high-impact cases).
- **Missing statistics:** if `padj` is missing, mark significance as `unknown` and avoid rendering “non-significant” styling.
- **Cell-line caveats:** when using LINCS signatures, label the cell line, dose, and timepoint; absence of agreement is `unknown`, not “discordant”.

---

## 7. New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/upload-deg` | Upload DEG file, return parsed gene list |
| `POST` | `/api/v1/enrichment` | Run ORA/GSEA on uploaded DEG data |
| `GET` | `/api/v1/enrichment/{id}` | Get enrichment results |
| `POST` | `/api/v1/tf-activity` | Run TF activity inference |
| `GET` | `/api/v1/tf-activity/{id}` | Get TF activity results |
| `POST` | `/api/v1/causal-chain/{drug_id}` | Trace drug -> target -> TF -> gene chain |
| `GET` | `/api/v1/lincs/drug/{name}` | Get L1000 expression signature for drug |
| `POST` | `/api/v1/lincs/query` | Query CMap with user signature |

---

## 8. Data Model Changes

```sql
-- User-uploaded DEG datasets
CREATE TABLE deg_uploads (
    id UUID PRIMARY KEY,
    user_id UUID,
    filename TEXT NOT NULL,
    gene_count INT NOT NULL,
    sig_gene_count INT NOT NULL,  -- padj < 0.05
    id_type TEXT NOT NULL,         -- 'hgnc' | 'ensembl' | 'entrez'
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Individual DEG entries
CREATE TABLE deg_genes (
    id UUID PRIMARY KEY,
    upload_id UUID REFERENCES deg_uploads(id),
    gene_symbol TEXT NOT NULL,
    uniprot_id TEXT,
    log2fc FLOAT NOT NULL,
    padj FLOAT,
    base_mean FLOAT
);

-- Enrichment analysis results
CREATE TABLE enrichment_results (
    id UUID PRIMARY KEY,
    upload_id UUID REFERENCES deg_uploads(id),
    method TEXT NOT NULL,         -- 'ora' | 'gsea_prerank'
    pathway_id TEXT NOT NULL,
    pathway_name TEXT NOT NULL,
    p_value FLOAT,
    fdr FLOAT,
    enrichment_score FLOAT,
    overlap_count INT,
    overlap_genes TEXT[],
    direction TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- TF activity results
CREATE TABLE tf_activity_results (
    id UUID PRIMARY KEY,
    upload_id UUID REFERENCES deg_uploads(id),
    tf_name TEXT NOT NULL,
    activity_score FLOAT NOT NULL,
    p_value FLOAT,
    direction TEXT,
    n_targets INT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## 9. New Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `gseapy` | ORA + GSEA enrichment | `pip install gseapy` |
| `decoupler` | TF activity inference + multi-method enrichment | `pip install decoupler` |
| `omnipath` | Signed directed PPI network (optional) | `pip install omnipath` |
| `cmapPy` | Local L1000 data reading (optional) | `pip install cmapPy` |
| `openpyxl` | Excel file parsing | `pip install openpyxl` |

---

## 10. Success Criteria

1. User uploads a DEG CSV/TSV and sees enriched pathways within 60s
2. Enrichment results integrate with existing pathway scores (combined view, concordance flags)
3. TF activity analysis returns top activated/repressed TFs with regulon evidence
4. At least one visualization shows the drug -> target -> TF -> gene causal chain
5. Expression overlay colors pathway nodes by log2FC with significance indicators
6. L1000 cross-reference shows known drug expression profile when available
7. Given the same input and `version_snapshot`, enrichment/TF outputs are deterministic (golden fixtures enforced in CI)

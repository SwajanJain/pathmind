# Phase 2A: Novel Compounds, Pathway Topology & Dose-Response

> Extends PathMind beyond known drugs to arbitrary molecules, adds pathway wiring diagrams, and introduces dose-aware target profiling.

---

## 1. Novel Compound Support (SMILES Input)

### 1.1 Goal

Accept any small molecule via SMILES string, predict its likely protein targets, and feed those predictions into the existing pathway-impact pipeline.

### 1.2 Input Handling

| Step | Tool | Details |
|------|------|---------|
| Parse & validate SMILES | RDKit (`Chem.MolFromSmiles`) | Returns `None` for invalid input |
| Canonicalize | RDKit (`Chem.MolToSmiles`) | Ensures consistent representation |
| Salt-strip / neutralize | `rdMolStandardize.LargestFragmentChooser` + `Uncharger` | Remove counterions, neutralize charges |
| Generate fingerprint | `AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)` | ECFP4 equivalent |

**Dependency:** `pip install rdkit` (v2024.03+)

### 1.3 Target Prediction Strategy

**Primary method -- ChEMBL Tanimoto Similarity Search (API-based):**

```
GET https://www.ebi.ac.uk/chembl/api/data/similarity/{SMILES}/{threshold}.json
```

- Threshold: 70% Tanimoto similarity
- Returns similar ChEMBL compounds with similarity scores
- Chain to activity endpoint to inherit targets from similar compounds
- Aggregate: for each predicted target, weight by similarity score and activity confidence
- Python client: `chembl_webresource_client`

**Secondary method -- PIDGINv4 (local, optional):**

- Naive Bayes / Random Forest classifiers trained on ChEMBL bioactivity
- Predicts probability of activity against ~2,700 human targets
- Fully local, no API dependency
- GitHub: `BenderGroup/PIDGINv4`
- Uses RDKit fingerprints internally

**Not viable for backend:**
- SwissTargetPrediction: web-only, no public API
- SEA: web-only, no public API (algorithm is reimplementable but effort ~2-3 weeks)

### 1.4 Confidence Tiers for Predicted Targets

| Tier | Criteria | UI Treatment |
|------|----------|-------------|
| Measured | Actual ChEMBL activity data for this exact compound | Solid border, full confidence |
| High predicted | Tanimoto > 0.85 to a known active with measured activity | Solid border, "predicted" badge |
| Medium predicted | Tanimoto 0.6-0.85, or model probability > 0.7 | Dashed border, "predicted" badge |
| Low / speculative | Tanimoto < 0.6 or model probability < 0.5 | Dotted border, grayed, collapsed by default |

Always show evidence: most similar known compound(s), their measured activities, and the similarity score.

### 1.5 Effort Estimate

| Component | Effort |
|-----------|--------|
| SMILES input + RDKit validation/standardization | 1-2 days |
| ChEMBL similarity search integration | 2-3 days |
| Target aggregation + confidence scoring | 2-3 days |
| PIDGINv4 integration (stretch) | 1-2 weeks |

---

## 2. Pathway Topology View

### 2.1 Goal

Show the internal wiring of a pathway (proteins, reactions, compartments) rather than just the flat association graph from Phase 1.

### 2.2 Tiered Approach

**Tier 1 -- Reactome Link-Out (MVP, 1 day):**

```
https://reactome.org/PathwayBrowser/#/{stableId}&FLG={uniprotId1,uniprotId2}
```

The `FLG` parameter highlights drug target entities directly in the Reactome viewer. Open in new tab or iframe.

**Tier 2 -- Reactome Diagram Widget (3-5 days):**

```html
<script src="https://reactome.org/DiagramJs/diagram/diagram.nocache.js"></script>
<div id="diagramHolder"></div>
<script>
  function onReactomeDiagramReady() {
    var diagram = Reactome.Diagram.create({
      placeHolder: "diagramHolder", width: 900, height: 600
    });
    diagram.loadDiagram("R-HSA-109582");
    diagram.flagItems("UniProt:P04637,UniProt:P38398");
  }
</script>
```

Limitations: GWT-compiled, heavyweight, limited React integration and custom styling.

**Tier 3 -- Custom Cytoscape.js Rendering (2-4 weeks, defer to later):**

Fetch pathway layout from Reactome Content Service:
```
GET https://reactome.org/ContentService/diagram/layout/{stId}
```

Returns JSON with nodes (proteins, complexes, small molecules) with x/y coordinates, edges (reactions), and compartments. Transform to Cytoscape.js elements format. Use `cytoscape-sbgn-stylesheet` plugin for SBGN-compliant shapes.

Challenges: hyperedge handling (reactions have multiple inputs/outputs), compartment nesting, large pathway performance.

### 2.3 Reactome Data Endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /data/pathway/{id}/containedEvents` | Sub-events (reactions) hierarchy |
| `GET /data/event/{id}/participants` | Input/output/catalyst/regulator entities |
| `GET /diagram/layout/{stId}` | Full diagram JSON with coordinates |
| `GET /exporter/sbgn2/{stId}.sbgn` | SBGN-ML XML (standardized format) |
| `POST /AnalysisService/identifiers/` | Analysis overlay token |

### 2.4 Recommendation

Start with Tier 1 (link-out with FLG) for the Phase 2A release. Evaluate Tier 2 (widget) as a stretch goal. Plan Tier 3 (Cytoscape.js) for Phase 2B or later when custom rendering of expression overlays is needed.

---

## 3. Dose-Response Explorer

### 3.1 Potency Band Binning

| Band | pChEMBL | Concentration | Pharmacological Meaning |
|------|---------|---------------|------------------------|
| Ultra-potent | >= 9 | <= 1 nM | Primary pharmacological target |
| Potent | 7-9 | 1-100 nM | Strong engagement at therapeutic doses |
| Moderate | 6-7 | 100 nM - 1 uM | Engaged at higher doses, may drive side effects |
| Weak | 5-6 | 1-10 uM | Marginal, supratherapeutic doses only |
| Very weak | < 5 | > 10 uM | Unlikely relevant in vivo |

### 3.2 Selectivity Waterfall Plot

A bar chart showing all targets ordered by potency (most potent on left):

- X-axis: targets, sorted descending by median pIC50
- Y-axis: pIC50 value
- Horizontal line: clinical Cmax (draggable for user exploration)
- Color by target class (kinase, GPCR, ion channel, etc.)
- Whiskers: IQR of reported IC50 values per target
- Interactive: hover for assay details, click to open ChEMBL

**Libraries:** Recharts (React), Plotly.js, or D3.js.

### 3.3 Interactive Concentration Explorer

User provides a concentration (slider or input). Display all targets where `median_IC50 <= concentration`.

**Occupancy model** for nuance beyond binary hit/miss:
```
Occupancy = [C] / ([C] + IC50)
```
At [C] = IC50, occupancy = 50%. At [C] = 10x IC50, occupancy = 91%.

### 3.4 Simulated Dose-Response Curves

ChEMBL does not store full dose-response curves (only summary IC50). Generate simulated sigmoids:

```
Response = Bottom + (Top - Bottom) / (1 + (IC50/[C])^n)
```

Where Bottom=0, Top=100, n=1 (standard Hill slope). Show as detail view when user clicks a specific drug-target pair. Overlay multiple targets on one plot for comparison.

### 3.5 Data Aggregation

- Use **median pChEMBL** across all measurements per drug-target pair
- Filter: `standard_relation = '='`, `data_validity_comment IS NULL`
- Require N >= 2 measurements for "measured" confidence
- Separate binding (Ki) vs functional (IC50/EC50) assay types in display

### 3.6 Effort Estimate

| Component | Effort |
|-----------|--------|
| Potency band binning | 1-2 days |
| Selectivity waterfall plot | 2-3 days |
| Concentration slider + occupancy model | 1 week |
| Simulated dose-response curves | 3-5 days |

---

## 4. New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/predict-targets` | Accept SMILES, return predicted targets with confidence |
| `GET` | `/api/v1/pathway/{id}/topology` | Return Reactome topology data for embedding |
| `GET` | `/api/v1/drug/{id}/selectivity` | Return sorted target list with potency bands |
| `GET` | `/api/v1/drug/{id}/occupancy?concentration=100nM` | Return targets engaged at given concentration |

---

## 5. New Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `rdkit` | SMILES parsing, fingerprints, standardization | `pip install rdkit` |
| `chembl_webresource_client` | ChEMBL API Python client | `pip install chembl_webresource_client` |
| Recharts or Plotly.js | Waterfall + dose-response charts | `npm install recharts` |

---

## 6. Data Model Changes

```sql
-- Novel compound analysis
CREATE TABLE compound_analyses (
    id UUID PRIMARY KEY,
    smiles TEXT NOT NULL,
    canonical_smiles TEXT NOT NULL,
    inchikey TEXT,
    prediction_method TEXT NOT NULL,  -- 'chembl_similarity' | 'pidgin'
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Predicted targets (linked to existing target pipeline)
CREATE TABLE predicted_targets (
    id UUID PRIMARY KEY,
    compound_analysis_id UUID REFERENCES compound_analyses(id),
    target_chembl_id TEXT NOT NULL,
    prediction_confidence FLOAT NOT NULL,  -- 0.0 - 1.0
    evidence_type TEXT NOT NULL,            -- 'tanimoto' | 'model'
    similar_compound_id TEXT,               -- ChEMBL ID of most similar known compound
    tanimoto_score FLOAT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

---

## 7. Success Criteria

1. User pastes a valid SMILES string and receives predicted targets within 30s
2. Each predicted target shows confidence tier, evidence (similar compounds), and feeds into existing pathway scoring
3. Pathway topology view shows at least Reactome link-out with highlighted drug targets
4. Selectivity waterfall plot renders for any analyzed drug with 2+ targets
5. Concentration slider dynamically filters displayed targets by occupancy threshold

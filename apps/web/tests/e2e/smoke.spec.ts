import { expect, test } from "@playwright/test";

const analysisFixture = {
  analysis_id: "analysis-1",
  created_at: "2026-02-14T00:00:00Z",
  drug_name: "erlotinib",
  canonical_drug_id: "CHEMBL553",
  params: { pchembl_threshold: 5, min_assays: 2, include_low_confidence: false, top_pathways: 20 },
  resolution: {
    query: "erlotinib",
    display_name: "Erlotinib",
    chembl_parent_id: "CHEMBL553",
    canonical_inchikey: "AAKEY",
    synonyms: [],
    clinical_phase: 4,
    mechanism_of_action: "EGFR inhibitor",
  },
  targets: [
    {
      target_chembl_id: "CHEMBL203",
      target_name: "EGFR",
      uniprot_id: "P00533",
      action_type: "INHIBITOR",
      median_pchembl: 9.1,
      assay_count: 4,
      confidence_score: 9,
      confidence_tier: "high",
      low_confidence: false,
      source_assay_ids: ["A1"],
      pchembl_min: 8.7,
      pchembl_max: 9.3,
      pchembl_iqr: 0.2,
      confidence_reasons: ["assay_count>=2", "median_pchembl>=6.0", "target_confidence>=9"],
      mapping_status: "mapped",
      mapping_notes: ["etl_target_pathway_map"],
    },
  ],
  pathways: [
    {
      pathway_id: "R-HSA-177929",
      pathway_name: "EGFR signaling",
      depth: 3,
      pathway_size: 100,
      targets_hit: 1,
      median_pchembl: 9.1,
      score: 0.091,
      target_ids: ["CHEMBL203"],
      reactome_url: "https://reactome.org/content/detail/R-HSA-177929",
      ancestor_pathway_ids: [],
      coverage_ratio: 0.01,
    },
  ],
  graph: {
    nodes: [
      { id: "drug:CHEMBL553", label: "Erlotinib", kind: "drug", metadata: {} },
      { id: "target:CHEMBL203", label: "EGFR", kind: "target", metadata: {} },
      { id: "pathway:R-HSA-177929", label: "EGFR signaling", kind: "pathway", metadata: {} },
    ],
    edges: [
      { id: "e1", source: "drug:CHEMBL553", target: "target:CHEMBL203", kind: "drug_target", weight: 9.1, metadata: {} },
      {
        id: "e2",
        source: "target:CHEMBL203",
        target: "pathway:R-HSA-177929",
        kind: "target_pathway",
        weight: 0.091,
        metadata: {},
      },
    ],
  },
  source_versions: { chembl: "test" },
  version_snapshot: { chembl: "test" },
  analysis_flags: {
    direction_unknown: false,
    limited_data: false,
    partial_mapping: false,
    high_variability: false,
  },
  export_manifest: {
    layout_engine: "dagre",
    layout_seed: 42,
    attribution_text: "Data sources: test",
    parameter_snapshot: { pchembl_threshold: 5, min_assays: 2, include_low_confidence: false, top_pathways: 20 },
  },
  degraded_messages: [],
  attribution: "Data sources: test",
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/drugs/suggest**", async (route) => {
    await route.fulfill({
      json: { query: "erlotinib", suggestions: [{ display_name: "Erlotinib", chembl_id: "CHEMBL553" }] },
    });
  });
  await page.route("**/api/drugs/resolve", async (route) => {
    await route.fulfill({
      json: {
        query: "erlotinib",
        status: "resolved",
        resolution: analysisFixture.resolution,
        candidates: [],
      },
    });
  });
  await page.route("**/api/analysis/run", async (route) => {
    await route.fulfill({ json: analysisFixture });
  });
  await page.route("**/api/analysis/analysis-1", async (route) => {
    await route.fulfill({ json: analysisFixture });
  });
  await page.route("**/api/analysis/analysis-1/share", async (route) => {
    await route.fulfill({ json: { share_id: "share-1", analysis_id: "analysis-1", public_url: "http://localhost:8000/api/share/share-1", created_at: "2026-02-14T00:00:00Z" } });
  });
  await page.route("**/api/share/share-1", async (route) => {
    await route.fulfill({ json: analysisFixture });
  });
  await page.route("**/api/compare/run", async (route) => {
    await route.fulfill({
      json: {
        analysis_a: analysisFixture,
        analysis_b: { ...analysisFixture, analysis_id: "analysis-2", drug_name: "lapatinib", resolution: { ...analysisFixture.resolution, display_name: "Lapatinib" } },
        rows: [{ pathway_id: "R-HSA-177929", pathway_name: "EGFR signaling", score_a: 0.091, score_b: 0.08, delta: 0.011, shared: true }],
        metrics: {
          target_jaccard: 0.5,
          pathway_cosine_similarity: 0.87,
          shared_pathway_count: 1,
          unique_pathway_count_a: 0,
          unique_pathway_count_b: 0,
        },
      },
    });
  });
});

test("search -> analysis render -> graph visible", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Type a drug name, e.g. erlotinib").fill("erlotinib");
  await page.getByRole("button", { name: "Analyze" }).click();
  await expect(page).toHaveURL(/\/analysis\/analysis-1/);
  await expect(page.getByTestId("association-graph")).toBeVisible();
  await expect(page.getByText("EGFR signaling")).toBeVisible();
});

test("compare two drugs -> metrics and rows visible", async ({ page }) => {
  await page.goto("/compare");
  await page.getByRole("button", { name: "Compare" }).click();
  await expect(page.getByText("Target overlap (Jaccard):")).toBeVisible();
  await expect(page.getByText("Shared pathways", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "EGFR signaling" })).toBeVisible();
});

test("open share link -> frozen snapshot visible", async ({ page }) => {
  await page.goto("/share/share-1");
  await expect(page.getByText("Frozen snapshot")).toBeVisible();
  await expect(page.getByText("Erlotinib")).toBeVisible();
});

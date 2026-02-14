export type AnalysisParams = {
  pchembl_threshold: number;
  min_assays: number;
  include_low_confidence: boolean;
  top_pathways: number;
};

export type DrugResolutionCandidate = {
  chembl_parent_id: string;
  display_name: string;
  canonical_inchikey: string;
  match_reasons: string[];
};

export type PathwayScore = {
  pathway_id: string;
  pathway_name: string;
  depth: number;
  pathway_size: number;
  targets_hit: number;
  median_pchembl: number;
  score: number;
  target_ids: string[];
  reactome_url: string;
  coverage_ratio: number;
};

export type TargetHit = {
  target_chembl_id: string;
  target_name: string;
  uniprot_id?: string | null;
  action_type: string;
  median_pchembl: number;
  assay_count: number;
  confidence_score?: number | null;
  confidence_tier: "high" | "medium" | "low";
  low_confidence: boolean;
  source_assay_ids: string[];
  pchembl_min?: number | null;
  pchembl_max?: number | null;
  pchembl_iqr?: number | null;
  confidence_reasons: string[];
  mapping_status: "mapped" | "partial" | "unmapped";
  mapping_notes: string[];
};

export type AnalysisFlags = {
  direction_unknown: boolean;
  limited_data: boolean;
  partial_mapping: boolean;
  high_variability: boolean;
};

export type AnalysisResult = {
  analysis_id: string;
  created_at: string;
  drug_name: string;
  canonical_drug_id: string;
  params: AnalysisParams;
  resolution: {
    query: string;
    display_name: string;
    chembl_parent_id: string;
    canonical_inchikey: string;
    pubchem_cid?: string | null;
    structure_smiles?: string | null;
    clinical_phase?: number | null;
    mechanism_of_action?: string | null;
    synonyms: string[];
  };
  targets: TargetHit[];
  pathways: PathwayScore[];
  graph: {
    nodes: Array<{ id: string; label: string; kind: "drug" | "target" | "pathway"; metadata: Record<string, unknown> }>;
    edges: Array<{
      id: string;
      source: string;
      target: string;
      kind: "drug_target" | "target_pathway";
      weight: number;
      metadata: Record<string, unknown>;
    }>;
  };
  source_versions: Record<string, string>;
  version_snapshot: Record<string, string>;
  analysis_flags: AnalysisFlags;
  export_manifest: Record<string, unknown>;
  degraded_messages: string[];
  attribution: string;
};

export type DrugResolveResponse = {
  query: string;
  status: "resolved" | "ambiguous" | "not_found";
  resolution?: AnalysisResult["resolution"] | null;
  candidates: DrugResolutionCandidate[];
};

export type CompareResult = {
  analysis_a: AnalysisResult;
  analysis_b: AnalysisResult;
  rows: Array<{
    pathway_id: string;
    pathway_name: string;
    score_a?: number | null;
    score_b?: number | null;
    delta?: number | null;
    shared: boolean;
  }>;
  metrics: {
    target_jaccard: number;
    pathway_cosine_similarity: number;
    shared_pathway_count: number;
    unique_pathway_count_a: number;
    unique_pathway_count_b: number;
  };
};

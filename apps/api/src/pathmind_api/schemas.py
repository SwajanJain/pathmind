from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisParams(BaseModel):
    pchembl_threshold: float = Field(default=5.0, ge=4.0, le=10.0)
    min_assays: int = Field(default=2, ge=1, le=20)
    include_low_confidence: bool = False
    top_pathways: int = Field(default=20, ge=1, le=100)


class DrugSuggestItem(BaseModel):
    display_name: str
    chembl_id: str | None = None


class DrugSuggestResponse(BaseModel):
    query: str
    suggestions: list[DrugSuggestItem]


class DrugResolutionCandidate(BaseModel):
    chembl_parent_id: str
    display_name: str
    canonical_inchikey: str
    match_reasons: list[str] = Field(default_factory=list)


class DrugResolution(BaseModel):
    query: str
    display_name: str
    chembl_parent_id: str
    canonical_inchikey: str
    pubchem_cid: str | None = None
    structure_smiles: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    clinical_phase: int | None = None
    mechanism_of_action: str | None = None


class TargetHit(BaseModel):
    target_chembl_id: str
    target_name: str
    gene_symbol: str | None = None
    uniprot_id: str | None = None
    action_type: str = "UNKNOWN"
    median_pchembl: float
    assay_count: int
    confidence_score: int | None = None
    confidence_tier: Literal["high", "medium", "low"]
    low_confidence: bool
    source_assay_ids: list[str] = Field(default_factory=list)
    pchembl_min: float | None = None
    pchembl_max: float | None = None
    pchembl_iqr: float | None = None
    confidence_reasons: list[str] = Field(default_factory=list)
    mapping_status: Literal["mapped", "partial", "unmapped"] = "mapped"
    mapping_notes: list[str] = Field(default_factory=list)


class PathwayScore(BaseModel):
    pathway_id: str
    pathway_name: str
    depth: int
    pathway_size: int
    targets_hit: int
    median_pchembl: float
    score: float
    target_ids: list[str]
    reactome_url: str
    ancestor_pathway_ids: list[str] = Field(default_factory=list)
    coverage_ratio: float = 0.0


class GraphNode(BaseModel):
    id: str
    label: str
    kind: Literal["drug", "target", "pathway"]
    metadata: dict = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: Literal["drug_target", "target_pathway"]
    weight: float
    metadata: dict = Field(default_factory=dict)


class AssociationGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class AnalysisFlags(BaseModel):
    direction_unknown: bool = False
    limited_data: bool = False
    partial_mapping: bool = False
    high_variability: bool = False


class AnalysisResult(BaseModel):
    analysis_id: str
    created_at: datetime
    drug_name: str
    canonical_drug_id: str
    params: AnalysisParams
    resolution: DrugResolution
    targets: list[TargetHit]
    pathways: list[PathwayScore]
    graph: AssociationGraph
    source_versions: dict[str, str]
    version_snapshot: dict[str, str] = Field(default_factory=dict)
    analysis_flags: AnalysisFlags = Field(default_factory=AnalysisFlags)
    export_manifest: dict = Field(default_factory=dict)
    degraded_messages: list[str] = Field(default_factory=list)
    attribution: str


class AnalysisRunRequest(BaseModel):
    drug_name: str = Field(min_length=2, max_length=255)
    params: AnalysisParams = Field(default_factory=AnalysisParams)
    do_not_log: bool = False
    resolution_choice: str | None = None


class DrugResolveRequest(BaseModel):
    query: str = Field(min_length=2, max_length=255)
    resolution_choice: str | None = None


class DrugResolveResponse(BaseModel):
    query: str
    status: Literal["resolved", "ambiguous", "not_found"]
    resolution: DrugResolution | None = None
    candidates: list[DrugResolutionCandidate] = Field(default_factory=list)


class ShareResponse(BaseModel):
    share_id: str
    analysis_id: str
    public_url: str
    created_at: datetime


class CompareRunRequest(BaseModel):
    drug_a: str = Field(min_length=2, max_length=255)
    drug_b: str = Field(min_length=2, max_length=255)
    params: AnalysisParams = Field(default_factory=AnalysisParams)


class PathwayComparisonRow(BaseModel):
    pathway_id: str
    pathway_name: str
    score_a: float | None = None
    score_b: float | None = None
    delta: float | None = None
    shared: bool


class CompareMetrics(BaseModel):
    target_jaccard: float
    pathway_cosine_similarity: float
    shared_pathway_count: int
    unique_pathway_count_a: int
    unique_pathway_count_b: int


class CompareResult(BaseModel):
    analysis_a: AnalysisResult
    analysis_b: AnalysisResult
    rows: list[PathwayComparisonRow]
    metrics: CompareMetrics


class ApiDependencyHealth(BaseModel):
    status: Literal["up", "down"]
    latency_ms: int | None = None
    error: str | None = None


class ApiHealthStatus(BaseModel):
    status: Literal["healthy", "degraded", "down"]
    apis: dict[str, ApiDependencyHealth]
    cache_hit_rate: float
    etl_last_run: datetime | None = None


class ExportMetadata(BaseModel):
    analysis_id: str
    created_at: datetime
    params: AnalysisParams
    attribution: str
    source_versions: dict[str, str] = Field(default_factory=dict)
    version_snapshot: dict[str, str] = Field(default_factory=dict)
    analysis_flags: AnalysisFlags = Field(default_factory=AnalysisFlags)
    export_manifest: dict = Field(default_factory=dict)


class JsonExportResponse(BaseModel):
    metadata: ExportMetadata
    analysis: AnalysisResult


class AnalyticsEventRequest(BaseModel):
    event_name: str = Field(min_length=2, max_length=64)
    page_path: str = Field(min_length=1, max_length=512)

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from statistics import median
from uuid import uuid4

from sqlalchemy.orm import Session

from pathmind_api.clients import ChEMBLClient, OpenTargetsClient, PubChemClient, ReactomeClient, UniProtClient
from pathmind_api.clients.base import DownstreamError
from pathmind_api.repositories import (
    get_pathways_for_uniprot,
    latest_source_release_versions,
    upsert_target_pathway_rows,
)
from pathmind_api.schemas import (
    AnalysisFlags,
    AnalysisParams,
    AnalysisResult,
    AssociationGraph,
    CompareResult,
    DrugResolution,
    DrugResolutionCandidate,
    DrugSuggestItem,
    GraphEdge,
    GraphNode,
    PathwayScore,
    TargetHit,
)
from pathmind_api.scoring import (
    assay_spread,
    compare_metrics,
    compare_rows,
    confidence_reasons,
    confidence_tier,
    dedupe_child_over_parent,
    meets_assay_filters,
    pathway_impact_score,
)

ATTRIBUTION = (
    "Data sources: ChEMBL (CC BY-SA 3.0, EMBL-EBI), Reactome (CC0), UniProt (CC BY 4.0), "
    "OpenTargets (Open Access), PubChem (Public Domain)."
)
MAX_TARGETS_DEFAULT = 50


class FatalAnalysisError(RuntimeError):
    pass


class AmbiguousDrugError(ValueError):
    def __init__(self, candidates: list[DrugResolutionCandidate]):
        super().__init__("Drug identity is ambiguous. Please select a specific compound.")
        self.candidates = candidates


class AnalysisService:
    def __init__(
        self,
        chembl: ChEMBLClient,
        pubchem: PubChemClient,
        uniprot: UniProtClient,
        reactome: ReactomeClient,
        opentargets: OpenTargetsClient,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.chembl = chembl
        self.pubchem = pubchem
        self.uniprot = uniprot
        self.reactome = reactome
        self.opentargets = opentargets
        self.session_factory = session_factory

    async def suggest(self, query: str) -> list[DrugSuggestItem]:
        suggestions = await self.chembl.suggest_drugs(query)
        return [DrugSuggestItem(**item) for item in suggestions]

    async def resolve_drug_identity(
        self,
        query: str,
        resolution_choice: str | None = None,
    ) -> tuple[DrugResolution, list[DrugResolutionCandidate]]:
        candidates_raw = await self.chembl.resolve_drug_candidates(query, limit=8)
        if not candidates_raw:
            raise ValueError(f"No ChEMBL molecule found for '{query}'")

        pubchem_inchikeys: set[str] = set()
        try:
            for candidate in await self.pubchem.resolve_candidates(query, limit=5):
                inchikey = candidate.get("canonical_inchikey")
                if inchikey:
                    pubchem_inchikeys.add(str(inchikey))
        except DownstreamError:
            pubchem_inchikeys = set()

        candidates: list[DrugResolutionCandidate] = []
        for candidate in candidates_raw:
            reasons = ["chembl_parent_match"]
            if candidate.get("canonical_inchikey") in pubchem_inchikeys:
                reasons.append("pubchem_inchikey_match")
            candidates.append(
                DrugResolutionCandidate(
                    chembl_parent_id=candidate["chembl_parent_id"],
                    display_name=candidate["display_name"],
                    canonical_inchikey=candidate["canonical_inchikey"],
                    match_reasons=reasons,
                )
            )

        selected = None
        if resolution_choice:
            selected = next((candidate for candidate in candidates_raw if candidate["chembl_parent_id"] == resolution_choice), None)
            if selected is None:
                raise ValueError(f"Resolution choice '{resolution_choice}' is invalid for query '{query}'.")
        elif len(candidates_raw) == 1:
            selected = candidates_raw[0]
        else:
            raise AmbiguousDrugError(candidates=candidates)

        resolution = DrugResolution(
            query=query,
            display_name=selected["display_name"],
            chembl_parent_id=selected["chembl_parent_id"],
            canonical_inchikey=selected["canonical_inchikey"],
            synonyms=selected.get("synonyms", []),
        )
        return resolution, candidates

    async def run_analysis(self, drug_name: str, params: AnalysisParams, resolution_choice: str | None = None) -> AnalysisResult:
        degraded_messages: list[str] = []
        created_at = datetime.now(timezone.utc)

        try:
            resolution, _ = await self.resolve_drug_identity(drug_name, resolution_choice=resolution_choice)
            activities = await self.chembl.fetch_activities(resolution.chembl_parent_id)
        except DownstreamError as exc:
            raise FatalAnalysisError(f"ChEMBL is temporarily unavailable: {exc}") from exc

        if not activities:
            raise FatalAnalysisError("No ChEMBL activity records found for this drug.")

        pubchem_data = {}
        try:
            pubchem_data = await self.pubchem.resolve_name(drug_name)
        except DownstreamError:
            degraded_messages.append("Drug structure image unavailable.")

        opentargets_data = {}
        try:
            opentargets_data = await self.opentargets.fetch_drug_info(resolution.chembl_parent_id)
        except DownstreamError:
            degraded_messages.append("Drug mechanism data unavailable. Direction information may be missing.")

        target_ids = sorted({activity.get("target_chembl_id") for activity in activities if activity.get("target_chembl_id")})
        target_details = {}
        try:
            target_details = await self.chembl.fetch_target_details(target_ids)
        except DownstreamError:
            target_details = {target_id: {"target_name": target_id, "uniprot_id": None, "target_confidence_score": None} for target_id in target_ids}

        resolution.canonical_inchikey = pubchem_data.get("canonical_inchikey") or resolution.canonical_inchikey
        resolution.pubchem_cid = pubchem_data.get("pubchem_cid")
        resolution.structure_smiles = pubchem_data.get("structure_smiles")
        resolution.clinical_phase = opentargets_data.get("clinical_phase")
        resolution.mechanism_of_action = opentargets_data.get("mechanism_of_action")

        aggregated: dict[str, dict] = defaultdict(
            lambda: {
                "target_name": "",
                "gene_symbol": None,
                "uniprot_id": None,
                "pchembl_values": [],
                "assay_count": 0,
                "source_assay_ids": [],
                "confidence_score": None,
            }
        )

        for activity in activities:
            if not meets_assay_filters(activity):
                continue
            pchembl_raw = activity.get("pchembl_value")
            if pchembl_raw is None:
                continue
            pchembl_value = float(pchembl_raw)
            if pchembl_value < params.pchembl_threshold:
                continue

            target_id = activity.get("target_chembl_id")
            if not target_id:
                continue
            details = target_details.get(target_id, {})
            # Filter non-human targets at target level (organism often missing from activity records)
            target_organism = details.get("target_organism", "")
            if target_organism and target_organism != "Homo sapiens":
                continue
            confidence = details.get("target_confidence_score")
            if confidence is None:
                confidence = 8

            entry = aggregated[target_id]
            entry["target_name"] = details.get("target_name") or target_id
            entry["gene_symbol"] = details.get("gene_symbol")
            entry["uniprot_id"] = details.get("uniprot_id")
            entry["confidence_score"] = int(confidence) if isinstance(confidence, (int, float)) else 8
            entry["pchembl_values"].append(pchembl_value)
            entry["assay_count"] += 1
            assay_id = activity.get("assay_chembl_id")
            if assay_id:
                entry["source_assay_ids"].append(assay_id)

        target_hits: list[TargetHit] = []
        action_types = opentargets_data.get("actions_by_symbol", {})
        for target_id, entry in aggregated.items():
            if entry["assay_count"] < params.min_assays:
                continue
            spread = assay_spread(entry["pchembl_values"])
            median_pchembl = spread["median"]
            tier = confidence_tier(entry["assay_count"], median_pchembl, entry["confidence_score"])
            if not params.include_low_confidence and tier == "low":
                continue
            symbol = (entry.get("gene_symbol") or entry["target_name"].split(" ")[0]).upper()
            action = action_types.get(symbol, "UNKNOWN")
            target_hits.append(
                TargetHit(
                    target_chembl_id=target_id,
                    target_name=entry["target_name"],
                    gene_symbol=entry["gene_symbol"],
                    uniprot_id=entry["uniprot_id"],
                    action_type=action,
                    median_pchembl=median_pchembl,
                    assay_count=entry["assay_count"],
                    confidence_score=entry["confidence_score"],
                    confidence_tier=tier,
                    low_confidence=tier == "low",
                    source_assay_ids=entry["source_assay_ids"][:50],
                    pchembl_min=spread["min"],
                    pchembl_max=spread["max"],
                    pchembl_iqr=spread["iqr"],
                    confidence_reasons=confidence_reasons(entry["assay_count"], median_pchembl, entry["confidence_score"]),
                )
            )

        target_hits.sort(key=lambda item: item.median_pchembl, reverse=True)
        if len(target_hits) > MAX_TARGETS_DEFAULT:
            target_hits = target_hits[:MAX_TARGETS_DEFAULT]
            degraded_messages.append(f"Showing top {MAX_TARGETS_DEFAULT} targets by potency for performance.")

        pathways_by_target: dict[str, list[dict]] = {}
        reactome_down = False
        uniprot_down = False
        partial_mapping = False
        etl_session = self.session_factory() if self.session_factory else None
        for hit in target_hits:
            mapped, notes, mapping_down = await self._map_uniprot_with_fallback(hit)
            if mapping_down:
                uniprot_down = True
            hit.mapping_notes = notes
            if mapped:
                hit.uniprot_id = mapped
            else:
                hit.mapping_status = "unmapped"
                hit.mapping_notes.append("unmapped_target")
                partial_mapping = True
                pathways_by_target[hit.target_chembl_id] = []
                continue

            pathways: list[dict] = []
            etl_mapped = False
            if etl_session is not None:
                try:
                    pathways = get_pathways_for_uniprot(etl_session, hit.uniprot_id)
                    if pathways:
                        etl_mapped = True
                        hit.mapping_notes.append("etl_target_pathway_map")
                except Exception:
                    pathways = []

            if not pathways:
                try:
                    pathways = await self.reactome.pathways_for_uniprot(hit.uniprot_id)
                    if etl_session is not None and pathways:
                        upsert_target_pathway_rows(etl_session, hit.uniprot_id, pathways)
                    hit.mapping_notes.append("reactome_live_lookup")
                except DownstreamError:
                    reactome_down = True
                    hit.mapping_status = "partial"
                    hit.mapping_notes.append("reactome_unavailable")
                    partial_mapping = True
                    pathways = []

            if pathways and etl_mapped:
                hit.mapping_status = "mapped"
            elif pathways:
                hit.mapping_status = "mapped"
            elif not reactome_down:
                hit.mapping_status = "partial"
                partial_mapping = True
            if not hit.uniprot_id:
                hit.mapping_status = "unmapped"
            pathways_by_target[hit.target_chembl_id] = pathways

        if etl_session is not None:
            etl_session.close()

        if uniprot_down:
            degraded_messages.append("Some target annotations may be incomplete.")
        if reactome_down:
            degraded_messages.append("Pathway data temporarily unavailable. Showing target binding data only.")
        if partial_mapping and not reactome_down:
            degraded_messages.append("Some targets have limited pathway mapping coverage.")

        pathway_agg: dict[str, dict] = defaultdict(
            lambda: {
                "pathway_id": "",
                "pathway_name": "",
                "depth": 3,
                "pathway_size": 1,
                "target_ids": [],
                "target_values": [],
                "ancestor_pathway_ids": [],
                "reactome_url": "",
            }
        )
        hit_map = {hit.target_chembl_id: hit for hit in target_hits}
        for target_id, pathways in pathways_by_target.items():
            hit = hit_map.get(target_id)
            if hit is None:
                continue
            for pathway in pathways:
                if pathway["depth"] <= 1:
                    continue
                bucket = pathway_agg[pathway["pathway_id"]]
                bucket["pathway_id"] = pathway["pathway_id"]
                bucket["pathway_name"] = pathway["pathway_name"]
                bucket["depth"] = pathway["depth"]
                bucket["pathway_size"] = max(pathway["pathway_size"], 1)
                bucket["ancestor_pathway_ids"] = pathway.get("ancestor_pathway_ids", [])
                bucket["reactome_url"] = pathway["reactome_url"]
                bucket["target_ids"].append(target_id)
                bucket["target_values"].append(hit.median_pchembl)

        pathway_entries: list[dict] = []
        for pathway in pathway_agg.values():
            unique_targets = sorted(set(pathway["target_ids"]))
            unique_values = [hit_map[target_id].median_pchembl for target_id in unique_targets if target_id in hit_map]
            score = pathway_impact_score(unique_values, pathway["pathway_size"])
            pathway_entries.append(
                {
                    "pathway_id": pathway["pathway_id"],
                    "pathway_name": pathway["pathway_name"],
                    "depth": pathway["depth"],
                    "pathway_size": pathway["pathway_size"],
                    "targets_hit": len(unique_targets),
                    "median_pchembl": float(median(unique_values)) if unique_values else 0.0,
                    "score": score,
                    "target_ids": unique_targets,
                    "reactome_url": pathway["reactome_url"],
                    "ancestor_pathway_ids": pathway["ancestor_pathway_ids"],
                    "coverage_ratio": round(len(unique_targets) / max(pathway["pathway_size"], 1), 6),
                }
            )

        deduped = dedupe_child_over_parent(pathway_entries)
        deduped.sort(key=lambda item: item["score"], reverse=True)
        top_pathways = deduped[: params.top_pathways]
        pathways = [PathwayScore(**entry) for entry in top_pathways]

        graph = self._build_graph(resolution, target_hits, pathways)

        source_versions = {"chembl": "unknown", "reactome": "unknown", "uniprot": "unknown", "opentargets": "unknown", "pubchem": "unknown"}
        db_versions = self._load_source_versions()
        source_versions.update(db_versions)

        direction_unknown = any(target.action_type == "UNKNOWN" for target in target_hits)
        limited_data = len(target_hits) < 3 or sum(target.assay_count for target in target_hits) < 10
        high_variability = any((target.pchembl_iqr or 0) >= 1.0 and target.assay_count >= 3 for target in target_hits)
        if limited_data:
            degraded_messages.append("Limited target data available for this compound.")

        analysis_flags = AnalysisFlags(
            direction_unknown=direction_unknown,
            limited_data=limited_data,
            partial_mapping=partial_mapping or uniprot_down or reactome_down,
            high_variability=high_variability,
        )

        return AnalysisResult(
            analysis_id=str(uuid4()),
            created_at=created_at,
            drug_name=drug_name,
            canonical_drug_id=resolution.chembl_parent_id,
            params=params,
            resolution=resolution,
            targets=target_hits,
            pathways=pathways,
            graph=graph,
            source_versions=source_versions,
            version_snapshot=source_versions,
            analysis_flags=analysis_flags,
            export_manifest={
                "layout_engine": "dagre",
                "layout_seed": 42,
                "attribution_text": ATTRIBUTION,
                "parameter_snapshot": params.model_dump(mode="json"),
            },
            degraded_messages=sorted(set(degraded_messages)),
            attribution=ATTRIBUTION,
        )

    def _load_source_versions(self) -> dict[str, str]:
        if self.session_factory is None:
            return {}
        session = self.session_factory()
        try:
            return latest_source_release_versions(session)
        except Exception:
            return {}
        finally:
            session.close()

    async def _map_uniprot_with_fallback(self, hit: TargetHit) -> tuple[str | None, list[str], bool]:
        notes: list[str] = []
        if hit.uniprot_id:
            notes.append("chembl_target_accession")
            return hit.uniprot_id, notes, False

        source_down = False
        try:
            mapped = await self.uniprot.map_target(hit.target_chembl_id)
            if mapped:
                notes.append("uniprot_chembl_accession")
                return mapped, notes, False
        except DownstreamError:
            source_down = True

        try:
            mapped = await self.uniprot.map_target_xref(hit.target_chembl_id)
            if mapped:
                notes.append("uniprot_xref_lookup")
                return mapped, notes, source_down
        except DownstreamError:
            source_down = True

        if hit.gene_symbol:
            try:
                mapped = await self.uniprot.map_by_gene_symbol(hit.gene_symbol)
                if mapped:
                    notes.append("uniprot_gene_symbol")
                    return mapped, notes, source_down
            except DownstreamError:
                source_down = True

        notes.append("uniprot_unmapped")
        return None, notes, source_down

    def _build_graph(self, resolution: DrugResolution, targets: list[TargetHit], pathways: list[PathwayScore]) -> AssociationGraph:
        pathway_ids = {pathway.pathway_id for pathway in pathways}
        pathway_by_id = {pathway.pathway_id: pathway for pathway in pathways}
        nodes: list[GraphNode] = [
            GraphNode(
                id=f"drug:{resolution.chembl_parent_id}",
                label=resolution.display_name,
                kind="drug",
                metadata={"chembl_id": resolution.chembl_parent_id},
            )
        ]
        edges: list[GraphEdge] = []
        for target in targets:
            nodes.append(
                GraphNode(
                    id=f"target:{target.target_chembl_id}",
                    label=target.target_name,
                    kind="target",
                    metadata={
                        "pchembl": target.median_pchembl,
                        "confidence_tier": target.confidence_tier,
                        "action_type": target.action_type,
                        "uniprot_id": target.uniprot_id,
                        "mapping_status": target.mapping_status,
                        "mapping_notes": target.mapping_notes,
                        "assay_range": {"min": target.pchembl_min, "max": target.pchembl_max, "iqr": target.pchembl_iqr},
                    },
                )
            )
            edges.append(
                GraphEdge(
                    id=f"edge:drug:{target.target_chembl_id}",
                    source=f"drug:{resolution.chembl_parent_id}",
                    target=f"target:{target.target_chembl_id}",
                    kind="drug_target",
                    weight=target.median_pchembl,
                    metadata={"action_type": target.action_type},
                )
            )

        for pathway in pathways:
            nodes.append(
                GraphNode(
                    id=f"pathway:{pathway.pathway_id}",
                    label=pathway.pathway_name,
                    kind="pathway",
                    metadata={"score": pathway.score, "reactome_url": pathway.reactome_url, "coverage_ratio": pathway.coverage_ratio, "source": "reactome"},
                )
            )

        for pathway in pathways:
            for target_id in pathway.target_ids:
                if pathway.pathway_id not in pathway_ids:
                    continue
                edges.append(
                    GraphEdge(
                        id=f"edge:{target_id}:{pathway.pathway_id}",
                        source=f"target:{target_id}",
                        target=f"pathway:{pathway.pathway_id}",
                        kind="target_pathway",
                        weight=pathway_by_id[pathway.pathway_id].score,
                        metadata={},
                    )
                )
        return AssociationGraph(nodes=nodes, edges=edges)

    async def compare(self, drug_a: str, drug_b: str, params: AnalysisParams) -> CompareResult:
        analysis_a = await self.run_analysis(drug_a, params)
        analysis_b = await self.run_analysis(drug_b, params)
        rows = compare_rows(
            [item.model_dump(mode="json") for item in analysis_a.pathways],
            [item.model_dump(mode="json") for item in analysis_b.pathways],
        )
        metrics = compare_metrics(
            targets_a=[target.target_chembl_id for target in analysis_a.targets],
            targets_b=[target.target_chembl_id for target in analysis_b.targets],
            pathways_a={pathway.pathway_id: pathway.score for pathway in analysis_a.pathways},
            pathways_b={pathway.pathway_id: pathway.score for pathway in analysis_b.pathways},
        )
        return CompareResult(analysis_a=analysis_a, analysis_b=analysis_b, rows=rows, metrics=metrics)

    async def health(self) -> dict:
        checks = {
            "chembl": await self.chembl.ping(),
            "reactome": await self.reactome.ping(),
            "opentargets": await self.opentargets.ping(),
            "pubchem": await self.pubchem.ping(),
            "uniprot": await self.uniprot.ping(),
        }
        if checks["chembl"].status == "down":
            status = "down"
        elif any(value.status == "down" for value in checks.values()):
            status = "degraded"
        else:
            status = "healthy"
        return {"status": status, "checks": checks}

from collections import defaultdict
from statistics import median

from pathmind_api.schemas import CompareMetrics, PathwayComparisonRow


def meets_assay_filters(activity: dict) -> bool:
    # NOTE: assay_organism is often None on ChEMBL activity records.
    # Organism filtering is applied at the target level instead
    # (target_organism == "Homo sapiens" checked during target detail fetch).
    organism = activity.get("assay_organism")
    organism_ok = organism is None or organism == "Homo sapiens"
    return (
        activity.get("standard_relation") == "="
        and activity.get("assay_type") in {"B", "F"}
        and organism_ok
        and activity.get("data_validity_comment") in {None, ""}
        and activity.get("pchembl_value") is not None
    )


def confidence_tier(assay_count: int, median_pchembl: float, confidence_score: int | None) -> str:
    score = confidence_score or 0
    if assay_count >= 5 and median_pchembl >= 6.0 and score >= 9:
        return "high"
    if assay_count >= 2 and median_pchembl >= 5.0 and score >= 8:
        return "medium"
    return "low"


def pathway_impact_score(target_values: list[float], pathway_size: int) -> float:
    if not target_values or pathway_size <= 0:
        return 0.0
    targets_hit = len(target_values)
    return round((targets_hit / pathway_size) * float(median(target_values)), 6)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    if upper == lower:
        return float(ordered[lower])
    weight = pos - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def assay_spread(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "median": 0.0, "max": 0.0, "iqr": 0.0}
    ordered = sorted(values)
    return {
        "min": float(ordered[0]),
        "median": float(median(ordered)),
        "max": float(ordered[-1]),
        "iqr": round(percentile(ordered, 0.75) - percentile(ordered, 0.25), 6),
    }


def confidence_reasons(assay_count: int, median_pchembl: float, confidence_score: int | None) -> list[str]:
    reasons: list[str] = []
    if assay_count >= 5:
        reasons.append("assay_count>=5")
    elif assay_count >= 2:
        reasons.append("assay_count>=2")
    else:
        reasons.append("assay_count<2")

    if median_pchembl >= 6.0:
        reasons.append("median_pchembl>=6.0")
    elif median_pchembl >= 5.0:
        reasons.append("median_pchembl>=5.0")
    else:
        reasons.append("median_pchembl<5.0")

    if (confidence_score or 0) >= 9:
        reasons.append("target_confidence>=9")
    elif (confidence_score or 0) >= 8:
        reasons.append("target_confidence>=8")
    else:
        reasons.append("target_confidence<8")
    return reasons


def dedupe_child_over_parent(pathways: list[dict]) -> list[dict]:
    ancestor_ids = set()
    for pathway in pathways:
        ancestor_ids.update(pathway.get("ancestor_pathway_ids", []))
    return [pathway for pathway in pathways if pathway["pathway_id"] not in ancestor_ids]


def compare_rows(pathways_a: list[dict], pathways_b: list[dict]) -> list[PathwayComparisonRow]:
    by_id: dict[str, dict[str, dict]] = defaultdict(dict)
    for item in pathways_a:
        by_id[item["pathway_id"]]["a"] = item
    for item in pathways_b:
        by_id[item["pathway_id"]]["b"] = item

    rows: list[PathwayComparisonRow] = []
    for pathway_id, values in by_id.items():
        a = values.get("a")
        b = values.get("b")
        score_a = a["score"] if a else None
        score_b = b["score"] if b else None
        delta = None if score_a is None or score_b is None else round(score_a - score_b, 6)
        rows.append(
            PathwayComparisonRow(
                pathway_id=pathway_id,
                pathway_name=(a or b)["pathway_name"],
                score_a=score_a,
                score_b=score_b,
                delta=delta,
                shared=bool(a and b),
            )
        )
    rows.sort(key=lambda row: abs(row.delta or 0.0), reverse=True)
    return rows


def compare_metrics(targets_a: list[str], targets_b: list[str], pathways_a: dict[str, float], pathways_b: dict[str, float]) -> CompareMetrics:
    set_a = set(targets_a)
    set_b = set(targets_b)
    union = set_a | set_b
    intersection = set_a & set_b
    target_jaccard = 0.0 if not union else len(intersection) / len(union)

    all_pathways = sorted(set(pathways_a) | set(pathways_b))
    vec_a = [pathways_a.get(pathway_id, 0.0) for pathway_id in all_pathways]
    vec_b = [pathways_b.get(pathway_id, 0.0) for pathway_id in all_pathways]
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    cosine = 0.0 if norm_a == 0 or norm_b == 0 else dot / (norm_a * norm_b)

    shared_pathway_count = len(set(pathways_a) & set(pathways_b))
    unique_pathway_count_a = len(set(pathways_a) - set(pathways_b))
    unique_pathway_count_b = len(set(pathways_b) - set(pathways_a))

    return CompareMetrics(
        target_jaccard=round(target_jaccard, 6),
        pathway_cosine_similarity=round(cosine, 6),
        shared_pathway_count=shared_pathway_count,
        unique_pathway_count_a=unique_pathway_count_a,
        unique_pathway_count_b=unique_pathway_count_b,
    )

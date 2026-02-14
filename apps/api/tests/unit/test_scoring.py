from pathmind_api.scoring import (
    assay_spread,
    confidence_reasons,
    confidence_tier,
    dedupe_child_over_parent,
    meets_assay_filters,
    pathway_impact_score,
)


def test_pathway_score_formula_coverage_weighted():
    # score = (targets_hit / pathway_size) * median_pchembl
    score = pathway_impact_score([8.0, 6.0], pathway_size=100)
    assert score == 0.14


def test_assay_filter_rules():
    good = {
        "standard_relation": "=",
        "assay_type": "B",
        "assay_organism": "Homo sapiens",
        "data_validity_comment": None,
        "pchembl_value": 6.2,
    }
    bad = {**good, "standard_relation": ">"}
    assert meets_assay_filters(good) is True
    assert meets_assay_filters(bad) is False


def test_confidence_tier_classification():
    assert confidence_tier(5, 6.2, 9) == "high"
    assert confidence_tier(2, 5.1, 8) == "medium"
    assert confidence_tier(1, 4.9, 7) == "low"


def test_assay_spread_iqr():
    spread = assay_spread([5.0, 6.0, 7.0, 9.0])
    assert spread["min"] == 5.0
    assert spread["max"] == 9.0
    assert spread["median"] == 6.5
    assert spread["iqr"] > 0


def test_confidence_reasons_content():
    reasons = confidence_reasons(5, 6.1, 9)
    assert "assay_count>=5" in reasons
    assert "median_pchembl>=6.0" in reasons
    assert "target_confidence>=9" in reasons


def test_hierarchy_exclusion_child_over_parent():
    pathways = [
        {
            "pathway_id": "R-HSA-PARENT",
            "pathway_name": "Parent",
            "ancestor_pathway_ids": [],
        },
        {
            "pathway_id": "R-HSA-CHILD",
            "pathway_name": "Child",
            "ancestor_pathway_ids": ["R-HSA-PARENT"],
        },
    ]
    deduped = dedupe_child_over_parent(pathways)
    assert len(deduped) == 1
    assert deduped[0]["pathway_id"] == "R-HSA-CHILD"

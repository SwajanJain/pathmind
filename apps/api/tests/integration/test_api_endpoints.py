def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["apis"]["chembl"]["status"] == "up"
    assert "etl_last_run" in payload


def test_happy_path_erlotinib(client):
    response = client.post("/api/analysis/run", json={"drug_name": "erlotinib"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["drug_name"] == "erlotinib"
    assert len(payload["targets"]) >= 1
    assert len(payload["pathways"]) >= 1
    assert "analysis_flags" in payload
    assert "version_snapshot" in payload


def test_fatal_chembl_down(client):
    response = client.post("/api/analysis/run", json={"drug_name": "chembl_down"})
    assert response.status_code == 503
    assert "ChEMBL" in response.json()["detail"]


def test_degraded_reactome_fallback(client):
    response = client.post("/api/analysis/run", json={"drug_name": "reactome_down"})
    assert response.status_code == 200
    payload = response.json()
    assert "Pathway data temporarily unavailable. Showing target binding data only." in payload["degraded_messages"]


def test_degraded_opentargets_fallback(client):
    response = client.post("/api/analysis/run", json={"drug_name": "opentargets_down"})
    assert response.status_code == 200
    payload = response.json()
    assert "Drug mechanism data unavailable. Direction information may be missing." in payload["degraded_messages"]


def test_degraded_pubchem_fallback(client):
    response = client.post("/api/analysis/run", json={"drug_name": "pubchem_down"})
    assert response.status_code == 200
    payload = response.json()
    assert "Drug structure image unavailable." in payload["degraded_messages"]


def test_degraded_uniprot_fallback(client):
    response = client.post("/api/analysis/run", json={"drug_name": "uniprot_down"})
    assert response.status_code == 200
    payload = response.json()
    assert "Some target annotations may be incomplete." in payload["degraded_messages"]


def test_share_snapshot_immutable(client):
    created = client.post("/api/analysis/run", json={"drug_name": "erlotinib"}).json()
    share = client.post(f"/api/analysis/{created['analysis_id']}/share", json={}).json()
    shared_payload = client.get(f"/api/share/{share['share_id']}").json()
    assert shared_payload["analysis_id"] == created["analysis_id"]
    assert shared_payload["drug_name"] == "erlotinib"


def test_do_not_log_still_fetchable_via_cache(client):
    created = client.post("/api/analysis/run", json={"drug_name": "erlotinib", "do_not_log": True}).json()
    read_back = client.get(f"/api/analysis/{created['analysis_id']}")
    assert read_back.status_code == 200
    assert read_back.json()["analysis_id"] == created["analysis_id"]
    share_attempt = client.post(f"/api/analysis/{created['analysis_id']}/share", json={})
    assert share_attempt.status_code == 404


def test_drug_resolve_ambiguous_candidates(client):
    response = client.post("/api/drugs/resolve", json={"query": "ambiguous_drug"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ambiguous"
    assert len(payload["candidates"]) >= 1


def test_analysis_ambiguous_requires_choice(client):
    response = client.post("/api/analysis/run", json={"drug_name": "ambiguous_drug"})
    assert response.status_code == 409
    assert "candidates" in response.json()["detail"]


def test_export_csv_and_json_have_metadata(client):
    created = client.post("/api/analysis/run", json={"drug_name": "erlotinib"}).json()
    analysis_id = created["analysis_id"]

    csv_response = client.get(f"/api/analysis/{analysis_id}/export.csv")
    assert csv_response.status_code == 200
    assert "# analysis_id:" in csv_response.text
    assert "pathway_id,pathway_name,score" in csv_response.text

    json_response = client.get(f"/api/analysis/{analysis_id}/export.json")
    assert json_response.status_code == 200
    export_payload = json_response.json()
    assert export_payload["metadata"]["analysis_id"] == analysis_id
    assert export_payload["analysis"]["analysis_id"] == analysis_id


def test_compare_metrics(client):
    response = client.post(
        "/api/compare/run",
        json={"drug_a": "erlotinib", "drug_b": "lapatinib"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "metrics" in payload
    assert "target_jaccard" in payload["metrics"]
    assert "pathway_cosine_similarity" in payload["metrics"]
    assert isinstance(payload["rows"], list)


def test_openapi_includes_contract_fields(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert "/api/analysis/{analysis_id}/export.csv" in payload["paths"]
    assert "/api/drugs/resolve" in payload["paths"]
    analysis_result_schema = payload["components"]["schemas"]["AnalysisResult"]
    properties = analysis_result_schema["properties"]
    assert "analysis_flags" in properties
    assert "version_snapshot" in properties

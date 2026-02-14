from collections import defaultdict

from pathmind_api.clients.base import BaseHttpClient


class ChEMBLClient(BaseHttpClient):
    async def suggest_drugs(self, query: str) -> list[dict]:
        response = await self.request("GET", "/molecule/search.json", params={"q": query, "limit": 10})
        payload = response.json()
        suggestions = []
        for molecule in payload.get("molecules", []):
            suggestions.append(
                {
                    "display_name": molecule.get("pref_name") or molecule.get("molecule_chembl_id"),
                    "chembl_id": molecule.get("molecule_chembl_id"),
                }
            )
        return suggestions

    async def resolve_drug(self, query: str) -> dict:
        candidates = await self.resolve_drug_candidates(query, limit=5)
        if not candidates:
            raise ValueError(f"No ChEMBL molecule found for '{query}'")
        return candidates[0]

    async def resolve_drug_candidates(self, query: str, limit: int = 8) -> list[dict]:
        response = await self.request("GET", "/molecule/search.json", params={"q": query, "limit": limit})
        molecules = response.json().get("molecules", [])
        by_parent: dict[str, dict] = {}
        rank = 0
        for molecule in molecules:
            hierarchy = molecule.get("molecule_hierarchy") or {}
            parent_chembl = hierarchy.get("parent_chembl_id") or molecule.get("molecule_chembl_id")
            if not parent_chembl or parent_chembl in by_parent:
                continue
            details = await self.request("GET", f"/molecule/{parent_chembl}.json")
            details_payload = details.json()
            structure = details_payload.get("molecule_structures") or {}
            synonyms = [
                name.get("molecule_synonym")
                for name in details_payload.get("molecule_synonyms", [])
                if name.get("molecule_synonym")
            ][:10]
            by_parent[parent_chembl] = {
                "display_name": details_payload.get("pref_name") or parent_chembl,
                "chembl_parent_id": parent_chembl,
                "canonical_inchikey": structure.get("standard_inchi_key") or parent_chembl,
                "synonyms": synonyms,
                "match_score": max(0.0, 1.0 - (rank * 0.1)),
            }
            rank += 1
        return list(by_parent.values())

    async def fetch_activities(self, chembl_parent_id: str) -> list[dict]:
        all_records: list[dict] = []
        offset = 0
        limit = 1000
        while True:
            response = await self.request(
                "GET",
                "/activity.json",
                params={
                    "molecule_chembl_id": chembl_parent_id,
                    "standard_type__in": "IC50,EC50,Ki,Kd",
                    "limit": limit,
                    "offset": offset,
                },
            )
            payload = response.json()
            records = payload.get("activities", [])
            all_records.extend(records)
            if len(records) < limit:
                break
            offset += limit
            if offset >= 5000:
                break
        return all_records

    async def fetch_target_details(self, target_ids: list[str]) -> dict[str, dict]:
        target_details: dict[str, dict] = defaultdict(dict)
        for target_id in target_ids:
            response = await self.request("GET", f"/target/{target_id}.json")
            payload = response.json()
            components = payload.get("target_components", [])
            accession = None
            gene_symbol = None
            if components:
                accession = components[0].get("accession")
                for synonym in components[0].get("target_component_synonyms", []):
                    if (synonym.get("syn_type") or "").upper() in {"GENE_SYMBOL", "GENE SYMBOL"}:
                        gene_symbol = synonym.get("component_synonym")
                        break
            target_type = (payload.get("target_type") or "").lower()
            confidence_score = 9 if target_type == "single protein" else 8 if target_type else None
            target_organism = payload.get("organism") or ""
            target_details[target_id] = {
                "target_name": payload.get("pref_name") or target_id,
                "gene_symbol": gene_symbol,
                "uniprot_id": accession,
                "target_confidence_score": confidence_score,
                "target_organism": target_organism,
            }
        return target_details

    async def ping(self):
        return await super().ping("/status")

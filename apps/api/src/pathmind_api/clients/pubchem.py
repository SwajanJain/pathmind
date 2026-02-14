from pathmind_api.clients.base import BaseHttpClient


class PubChemClient(BaseHttpClient):
    async def resolve_candidates(self, query: str, limit: int = 5) -> list[dict]:
        cids_response = await self.request("GET", f"/compound/name/{query}/cids/JSON")
        payload = cids_response.json()
        cids = (payload.get("IdentifierList") or {}).get("CID", [])[:limit]
        candidates: list[dict] = []
        for cid in cids:
            resolved = await self.resolve_cid(str(cid))
            if resolved:
                candidates.append(resolved)
        return candidates

    async def resolve_cid(self, cid: str) -> dict:
        response = await self.request("GET", f"/compound/cid/{cid}/property/CanonicalSMILES,InChIKey/JSON")
        payload = response.json()
        properties = payload.get("PropertyTable", {}).get("Properties", [])
        if not properties:
            return {}
        first = properties[0]
        return {
            "pubchem_cid": str(cid),
            "canonical_inchikey": first.get("InChIKey"),
            "structure_smiles": first.get("CanonicalSMILES"),
        }

    async def resolve_name(self, query: str) -> dict:
        candidates = await self.resolve_candidates(query, limit=1)
        if not candidates:
            return {}
        return candidates[0]

    async def ping(self):
        return await super().ping("/compound/name/ibuprofen/cids/JSON")

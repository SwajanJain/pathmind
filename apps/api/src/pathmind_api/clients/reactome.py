from pathmind_api.clients.base import BaseHttpClient


class ReactomeClient(BaseHttpClient):
    async def pathways_for_uniprot(self, uniprot_id: str) -> list[dict]:
        response = await self.request("GET", f"/data/mapping/UniProt/{uniprot_id}/pathways")
        payload = response.json()
        # The /data/mapping/UniProt/{id}/pathways endpoint returns a list
        # but may return a 404 dict if not found
        if isinstance(payload, dict):
            return []
        normalized = []
        for pathway in payload:
            pathway_id = pathway.get("stId") or pathway.get("dbId")
            if not pathway_id:
                continue
            # maxDepth = depth of this pathway in the Reactome hierarchy (1 = top-level umbrella)
            depth = int(pathway.get("maxDepth") or pathway.get("level") or 3)
            # entitiesSize is NOT returned by the mapping endpoint; use a reasonable default
            pathway_size = int(pathway.get("entitiesSize") or pathway.get("entitiesCount") or 50)
            # parents is NOT returned by the mapping endpoint
            ancestor_ids = [parent.get("stId") for parent in pathway.get("parents", []) if parent.get("stId")]
            normalized.append(
                {
                    "pathway_id": str(pathway_id),
                    "pathway_name": pathway.get("displayName") or str(pathway_id),
                    "depth": depth,
                    "pathway_size": pathway_size,
                    "ancestor_pathway_ids": ancestor_ids,
                    "reactome_url": f"https://reactome.org/content/detail/{pathway_id}",
                }
            )
        return normalized

    async def fetch_release_version(self) -> str:
        response = await self.request("GET", "/data/database/version")
        payload = response.text.strip()
        if not payload:
            return "unknown"
        return payload

    async def ping(self):
        return await super().ping("/data/query/R-HSA-162582")

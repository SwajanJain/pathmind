from pathmind_api.clients.base import BaseHttpClient


class UniProtClient(BaseHttpClient):
    async def map_target(self, target_chembl_id: str) -> str | None:
        query = f"xref:ChEMBL-{target_chembl_id}"
        response = await self.request(
            "GET",
            "/uniprotkb/search",
            params={"query": query, "fields": "accession", "size": 1, "format": "json"},
        )
        payload = response.json()
        results = payload.get("results", [])
        if not results:
            return None
        return results[0].get("primaryAccession")

    async def map_target_xref(self, target_chembl_id: str) -> str | None:
        response = await self.request(
            "GET",
            "/uniprotkb/search",
            params={
                "query": f"xref:ChEMBL:{target_chembl_id} AND organism_id:9606",
                "fields": "accession",
                "size": 1,
                "format": "json",
            },
        )
        payload = response.json()
        results = payload.get("results", [])
        if not results:
            return None
        return results[0].get("primaryAccession")

    async def map_by_gene_symbol(self, gene_symbol: str) -> str | None:
        response = await self.request(
            "GET",
            "/uniprotkb/search",
            params={"query": f"gene:{gene_symbol} AND organism_id:9606", "fields": "accession", "size": 1, "format": "json"},
        )
        payload = response.json()
        results = payload.get("results", [])
        if not results:
            return None
        return results[0].get("primaryAccession")

    async def ping(self):
        return await super().ping("/uniprotkb/P00533.json")

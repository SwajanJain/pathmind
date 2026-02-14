import time

from pathmind_api.clients.base import BaseHttpClient, DownstreamError, HealthResult


class OpenTargetsClient(BaseHttpClient):
    async def fetch_drug_info(self, chembl_id: str) -> dict:
        query = """
        query Drug($chemblId: String!) {
          drug(chemblId: $chemblId) {
            id
            name
            maximumClinicalTrialPhase
            mechanismsOfAction {
              rows {
                actionType
                description
                targets {
                  approvedSymbol
                  id
                }
              }
            }
          }
        }
        """
        response = await self.request(
            "POST",
            "/graphql",
            json={"query": query, "variables": {"chemblId": chembl_id}},
        )
        payload = response.json().get("data", {}).get("drug", {})
        rows = payload.get("mechanismsOfAction", {}).get("rows", [])
        actions_by_symbol: dict[str, str] = {}
        descriptions: list[str] = []
        for row in rows:
            action_type = row.get("actionType") or "UNKNOWN"
            if row.get("description"):
                descriptions.append(row.get("description"))
            for target in row.get("targets", []):
                symbol = target.get("approvedSymbol")
                if symbol:
                    actions_by_symbol[symbol.upper()] = action_type.upper()
        return {
            "actions_by_symbol": actions_by_symbol,
            "clinical_phase": payload.get("maximumClinicalTrialPhase"),
            "mechanism_of_action": descriptions[0] if descriptions else None,
        }

    async def ping(self):
        start = time.perf_counter()
        try:
            await self.request("POST", "/graphql", json={"query": "query { __typename }"})
            latency_ms = int((time.perf_counter() - start) * 1000)
            return HealthResult(status="up", latency_ms=latency_ms)
        except DownstreamError as exc:
            return HealthResult(status="down", error=str(exc))

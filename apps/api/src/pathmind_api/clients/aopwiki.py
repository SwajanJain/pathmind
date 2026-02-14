from __future__ import annotations

import logging

from pathmind_api.clients.base import BaseHttpClient

log = logging.getLogger(__name__)


class AOPWikiClient(BaseHttpClient):
    """Client for the AOPWiki REST API."""

    async def fetch_all_aops(self) -> list[dict]:
        """Fetch all Adverse Outcome Pathways and normalise to the DB schema.

        Returns dicts matching ``upsert_aop_chains`` format:
        ``[{aop_id, mie, adverse_outcome, key_events, matched_genes, source_url}, ...]``
        """
        response = await self.request("GET", "/aops.json")
        payload = response.json()

        if isinstance(payload, dict):
            items = payload.get("aops") or payload.get("items") or payload.get("data") or []
        elif isinstance(payload, list):
            items = payload
        else:
            items = []

        rows: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            aop_id = str(item.get("id") or item.get("aop_id") or "").strip()
            if not aop_id:
                continue

            mie = _extract_mie(item)
            adverse_outcome = _extract_ao(item)
            key_events = _extract_key_events(item)
            matched_genes = _extract_genes(item)

            rows.append(
                {
                    "aop_id": aop_id,
                    "mie": mie,
                    "adverse_outcome": adverse_outcome,
                    "key_events": key_events,
                    "matched_genes": matched_genes,
                    "source_url": f"https://aopwiki.org/aops/{aop_id}",
                }
            )

        log.info("AOPWiki returned %d AOP chains", len(rows))
        return rows


def _extract_mie(item: dict) -> str:
    """Extract Molecular Initiating Event text."""
    mie = item.get("mie") or item.get("molecular_initiating_event") or ""
    if isinstance(mie, dict):
        return str(mie.get("title") or mie.get("name") or "")
    if isinstance(mie, list) and mie:
        first = mie[0]
        if isinstance(first, dict):
            return str(first.get("title") or first.get("name") or "")
        return str(first)
    return str(mie)


def _extract_ao(item: dict) -> str:
    """Extract Adverse Outcome text."""
    ao = item.get("adverse_outcome") or item.get("ao") or ""
    if isinstance(ao, dict):
        return str(ao.get("title") or ao.get("name") or "")
    if isinstance(ao, list) and ao:
        first = ao[0]
        if isinstance(first, dict):
            return str(first.get("title") or first.get("name") or "")
        return str(first)
    return str(ao)


def _extract_key_events(item: dict) -> list[str]:
    """Extract key event names/titles."""
    raw = item.get("key_events") or item.get("kes") or []
    if not isinstance(raw, list):
        return []
    events: list[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            text = str(entry.get("title") or entry.get("name") or entry.get("id") or "")
        else:
            text = str(entry)
        text = text.strip()
        if text:
            events.append(text)
    return events


def _extract_genes(item: dict) -> list[str]:
    """Extract gene symbols linked to the AOP."""
    raw = item.get("matched_genes") or item.get("genes") or item.get("gene_targets") or []
    if not isinstance(raw, list):
        return []
    genes: list[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            text = str(entry.get("symbol") or entry.get("gene_symbol") or entry.get("name") or "")
        else:
            text = str(entry)
        text = text.strip().upper()
        if text:
            genes.append(text)
    return sorted(set(genes))

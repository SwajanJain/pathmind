from __future__ import annotations

import logging

from pathmind_api.clients.base import BaseHttpClient

log = logging.getLogger(__name__)


class HPAClient(BaseHttpClient):
    """Client for the Human Protein Atlas (proteinatlas.org) JSON API."""

    async def fetch_tissue_expression(self, gene_symbol: str) -> list[dict]:
        """Fetch RNA + protein tissue data for *gene_symbol*.

        Returns rows matching the ``_merge_expression_rows`` format:
        ``[{gene_symbol, tissue, hpa_rna_nx, hpa_protein_level, hpa_present, ...}, ...]``
        """
        gene_key = gene_symbol.strip().upper()
        if not gene_key:
            return []

        response = await self.request("GET", f"/{gene_key}.json")
        payload = response.json()

        # HPA returns a list with one element per gene entry
        if isinstance(payload, list):
            gene_entry = payload[0] if payload else {}
        else:
            gene_entry = payload

        rna_tissues = gene_entry.get("rna_tissue") or []
        protein_tissues = gene_entry.get("tissue") or []

        # Build lookup of protein levels keyed by tissue name
        protein_by_tissue: dict[str, str] = {}
        for item in protein_tissues:
            tissue_raw = (item.get("tissue") or item.get("name") or "").strip()
            level = (item.get("level") or "").strip()
            if tissue_raw and level:
                canonical = _normalise_tissue(tissue_raw)
                # Keep the highest level if multiple entries per tissue
                if canonical not in protein_by_tissue or _level_rank(level) > _level_rank(protein_by_tissue[canonical]):
                    protein_by_tissue[canonical] = level

        rows: list[dict] = []
        seen_tissues: set[str] = set()

        for item in rna_tissues:
            tissue_raw = (item.get("tissue") or item.get("name") or "").strip()
            if not tissue_raw:
                continue
            tissue = _normalise_tissue(tissue_raw)
            if tissue in seen_tissues:
                continue
            seen_tissues.add(tissue)

            raw_nx = item.get("value") or item.get("nx") or item.get("tpm")
            try:
                nx = float(raw_nx) if raw_nx not in {None, ""} else None
            except (ValueError, TypeError):
                nx = None

            protein_level = protein_by_tissue.get(tissue)

            rows.append(
                {
                    "gene_symbol": gene_key,
                    "uniprot_id": None,
                    "tissue": tissue,
                    "gtex_tpm": None,
                    "hpa_rna_nx": nx,
                    "hpa_protein_level": protein_level,
                    "gtex_present": False,
                    "hpa_present": nx is not None or protein_level is not None,
                }
            )

        # Add any protein-only tissues not already in RNA list
        for tissue, level in protein_by_tissue.items():
            if tissue in seen_tissues:
                continue
            seen_tissues.add(tissue)
            rows.append(
                {
                    "gene_symbol": gene_key,
                    "uniprot_id": None,
                    "tissue": tissue,
                    "gtex_tpm": None,
                    "hpa_rna_nx": None,
                    "hpa_protein_level": level,
                    "gtex_present": False,
                    "hpa_present": True,
                }
            )

        log.debug("HPA returned %d tissue rows for %s", len(rows), gene_key)
        return rows


def _level_rank(level: str) -> int:
    return {"Not detected": 0, "Low": 1, "Medium": 2, "High": 3}.get(level, -1)


def _normalise_tissue(raw: str) -> str:
    """Map HPA tissue names to canonical short names."""
    _MAP = {
        "liver": "Liver",
        "heart muscle": "Heart",
        "heart": "Heart",
        "cerebral cortex": "Brain",
        "cerebellum": "Brain",
        "hippocampus": "Brain",
        "hypothalamus": "Brain",
        "caudate": "Brain",
        "brain": "Brain",
        "kidney": "Kidney",
        "lung": "Lung",
        "small intestine": "Intestine",
        "duodenum": "Intestine",
        "colon": "Intestine",
        "rectum": "Intestine",
        "bone marrow": "Blood",
        "blood": "Blood",
        "adipose tissue": "Adipose Tissue",
    }
    lower = raw.lower()
    return _MAP.get(lower, raw.title())

from __future__ import annotations

import logging

from pathmind_api.clients.base import BaseHttpClient

log = logging.getLogger(__name__)


class HPAClient(BaseHttpClient):
    """Client for the Human Protein Atlas (proteinatlas.org) JSON API.

    The HPA gene-page JSON is served at ``/{ENSEMBL_ID}.json``.
    Use the GTEx ``resolve_gene`` helper to obtain the Ensembl ID from a
    gene symbol before calling :meth:`fetch_tissue_expression`.
    """

    async def fetch_tissue_expression(self, ensembl_id: str, gene_symbol: str = "") -> list[dict]:
        """Fetch RNA tissue nTPM for the given Ensembl gene ID.

        Returns rows matching the ``_merge_expression_rows`` format:
        ``[{gene_symbol, tissue, hpa_rna_nx, hpa_protein_level, hpa_present, ...}, ...]``
        """
        ensembl_key = ensembl_id.strip()
        if not ensembl_key:
            return []

        response = await self.request("GET", f"/{ensembl_key}.json")
        payload = response.json()

        # HPA may return a list with one element
        if isinstance(payload, list):
            gene_entry = payload[0] if payload else {}
        else:
            gene_entry = payload

        gene_key = (
            gene_symbol.strip().upper()
            or (gene_entry.get("Gene") or "").strip().upper()
            or ensembl_key
        )

        rows: list[dict] = []

        # Primary data source: "RNA tissue specific nTPM" — a dict of {tissue: nTPM}
        rna_ntpm = gene_entry.get("RNA tissue specific nTPM") or {}
        if isinstance(rna_ntpm, dict):
            for tissue_raw, ntpm_value in rna_ntpm.items():
                tissue = _normalise_tissue(str(tissue_raw).strip())
                if not tissue:
                    continue
                try:
                    nx = float(ntpm_value) if ntpm_value is not None else None
                except (ValueError, TypeError):
                    nx = None

                rows.append(
                    {
                        "gene_symbol": gene_key,
                        "uniprot_id": None,
                        "tissue": tissue,
                        "gtex_tpm": None,
                        "hpa_rna_nx": nx,
                        "hpa_protein_level": None,
                        "gtex_present": False,
                        "hpa_present": nx is not None,
                    }
                )

        # Fallback: older HPA format with "rna_tissue" array
        if not rows:
            rna_tissues = gene_entry.get("rna_tissue") or []
            seen: set[str] = set()
            for item in rna_tissues:
                tissue_raw = (item.get("tissue") or item.get("name") or "").strip()
                if not tissue_raw:
                    continue
                tissue = _normalise_tissue(tissue_raw)
                if tissue in seen:
                    continue
                seen.add(tissue)
                raw_nx = item.get("value") or item.get("nx") or item.get("tpm")
                try:
                    nx = float(raw_nx) if raw_nx not in {None, ""} else None
                except (ValueError, TypeError):
                    nx = None
                rows.append(
                    {
                        "gene_symbol": gene_key,
                        "uniprot_id": None,
                        "tissue": tissue,
                        "gtex_tpm": None,
                        "hpa_rna_nx": nx,
                        "hpa_protein_level": None,
                        "gtex_present": False,
                        "hpa_present": nx is not None,
                    }
                )

        log.debug("HPA returned %d tissue rows for %s (%s)", len(rows), gene_key, ensembl_key)
        return rows


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

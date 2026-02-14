from __future__ import annotations

import logging

from pathmind_api.clients.base import BaseHttpClient

log = logging.getLogger(__name__)


class GTExClient(BaseHttpClient):
    """Client for the GTEx Portal REST API v2."""

    async def resolve_gene(self, gene_symbol: str) -> dict | None:
        """Resolve a gene symbol to its GTEx gencodeId and Ensembl ID.

        Returns ``{"gencodeId": "ENSG00000160868.14", "ensemblId": "ENSG00000160868",
        "geneSymbol": "CYP3A4"}`` or ``None`` if not found.
        """
        gene_key = gene_symbol.strip().upper()
        if not gene_key:
            return None

        response = await self.request(
            "GET",
            "/reference/gene",
            params={
                "geneId": gene_key,
                "gencodeVersion": "v26",
                "genomeBuild": "GRCh38/hg38",
            },
        )
        payload = response.json()
        items = payload.get("data") or []
        if not items:
            return None

        item = items[0]
        gencode_id = item.get("gencodeId", "")
        ensembl_id = gencode_id.split(".")[0] if gencode_id else ""
        return {
            "gencodeId": gencode_id,
            "ensemblId": ensembl_id,
            "geneSymbol": item.get("geneSymbol") or gene_key,
        }

    async def fetch_median_expression(self, gencode_id: str, gene_symbol: str = "") -> list[dict]:
        """Return median gene-level TPM per tissue from GTEx v8.

        *gencode_id* should be a versioned Gencode ID (e.g. ``ENSG00000160868.14``).
        Use :meth:`resolve_gene` to obtain it from a gene symbol.

        Returns a list of dicts ready for ``_merge_expression_rows``.
        """
        if not gencode_id:
            return []

        response = await self.request(
            "GET",
            "/expression/medianGeneExpression",
            params={
                "gencodeId": gencode_id,
                "datasetId": "gtex_v8",
            },
        )
        payload = response.json()
        items = payload.get("data") or []

        gene_key = gene_symbol.strip().upper() or gencode_id

        rows: list[dict] = []
        for item in items:
            tissue_id = item.get("tissueSiteDetailId") or ""
            tissue = _normalise_tissue(str(tissue_id).strip())
            if not tissue:
                continue
            raw_tpm = item.get("median")
            try:
                tpm = float(raw_tpm) if raw_tpm is not None else None
            except (ValueError, TypeError):
                tpm = None

            # Use geneSymbol from response if available
            symbol = item.get("geneSymbol") or gene_key

            rows.append(
                {
                    "gene_symbol": symbol.strip().upper(),
                    "uniprot_id": None,
                    "tissue": tissue,
                    "gtex_tpm": tpm,
                    "hpa_rna_nx": None,
                    "hpa_protein_level": None,
                    "gtex_present": tpm is not None,
                    "hpa_present": False,
                }
            )

        log.debug("GTEx returned %d tissue rows for %s", len(rows), gene_key)
        return rows


def _normalise_tissue(raw: str) -> str:
    """Map GTEx tissue-site-detail IDs to canonical short names."""
    _MAP = {
        "Liver": "Liver",
        "Heart_Left_Ventricle": "Heart",
        "Heart_Atrial_Appendage": "Heart",
        "Brain_Cortex": "Brain",
        "Brain_Cerebellum": "Brain",
        "Brain_Frontal_Cortex_BA9": "Brain",
        "Brain_Hippocampus": "Brain",
        "Brain_Hypothalamus": "Brain",
        "Brain_Caudate_basal_ganglia": "Brain",
        "Brain_Putamen_basal_ganglia": "Brain",
        "Brain_Nucleus_accumbens_basal_ganglia": "Brain",
        "Brain_Cerebellar_Hemisphere": "Brain",
        "Brain_Anterior_cingulate_cortex_BA24": "Brain",
        "Brain_Spinal_cord_cervical_c-1": "Brain",
        "Brain_Substantia_nigra": "Brain",
        "Brain_Amygdala": "Brain",
        "Kidney_Cortex": "Kidney",
        "Kidney_Medulla": "Kidney",
        "Lung": "Lung",
        "Small_Intestine_Terminal_Ileum": "Intestine",
        "Colon_Transverse": "Intestine",
        "Colon_Sigmoid": "Intestine",
        "Whole_Blood": "Blood",
        "Adipose_Subcutaneous": "Adipose Tissue",
        "Adipose_Visceral_Omentum": "Adipose Tissue",
    }
    return _MAP.get(raw, raw.replace("_", " "))

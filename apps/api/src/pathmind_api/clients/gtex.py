from __future__ import annotations

import logging

from pathmind_api.clients.base import BaseHttpClient

log = logging.getLogger(__name__)


class GTExClient(BaseHttpClient):
    """Client for the GTEx Portal REST API v2."""

    async def fetch_median_expression(self, gene_symbol: str) -> list[dict]:
        """Return median gene-level TPM per tissue from GTEx v8.

        Returns a list of dicts ready for ``_merge_expression_rows``:
        ``[{gene_symbol, tissue, gtex_tpm, gtex_present, ...}, ...]``
        """
        gene_key = gene_symbol.strip().upper()
        if not gene_key:
            return []

        response = await self.request(
            "GET",
            "/expression/medianGeneExpression",
            params={
                "geneSymbol": gene_key,
                "datasetId": "gtex_v8",
            },
        )
        payload = response.json()

        # The API wraps results under a "medianGeneExpression" key
        items = payload.get("medianGeneExpression") or payload.get("data") or []
        if isinstance(payload, list):
            items = payload

        rows: list[dict] = []
        for item in items:
            tissue = (
                item.get("tissueSiteDetailId")
                or item.get("tissue")
                or item.get("tissueSiteDetail")
                or ""
            )
            tissue = _normalise_tissue(str(tissue).strip())
            if not tissue:
                continue
            raw_tpm = item.get("median") or item.get("medianTpm") or item.get("tpm")
            try:
                tpm = float(raw_tpm) if raw_tpm not in {None, ""} else None
            except (ValueError, TypeError):
                tpm = None

            rows.append(
                {
                    "gene_symbol": gene_key,
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

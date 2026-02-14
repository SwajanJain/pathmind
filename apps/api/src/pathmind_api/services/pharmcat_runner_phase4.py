import json
import subprocess
import tempfile
from pathlib import Path

from pathmind_api.schemas_phase4 import PgxGeneCallParsed


def _parse_inline_call(payload: str) -> PgxGeneCallParsed | None:
    raw = payload.strip()
    if not raw:
        return None
    if raw.startswith("{") and raw.endswith("}"):
        try:
            parsed = json.loads(raw)
            gene = str(parsed.get("gene", "")).strip().upper()
            if not gene:
                return None
            activity = parsed.get("activity_score")
            try:
                activity_value = float(activity) if activity not in {None, ""} else None
            except Exception:
                activity_value = None
            return PgxGeneCallParsed(
                gene=gene,
                diplotype=parsed.get("diplotype"),
                phenotype=parsed.get("phenotype"),
                activity_score=activity_value,
                state="unknown",
                reason_code="parsed_from_vcf_annotation",
                provenance={"source": "vcf_annotation_json"},
            )
        except Exception:
            return None

    parts = [item.strip() for item in raw.split("|")]
    if not parts:
        return None
    gene = parts[0].upper()
    if not gene:
        return None
    activity_value = None
    if len(parts) > 3 and parts[3]:
        try:
            activity_value = float(parts[3])
        except Exception:
            activity_value = None
    return PgxGeneCallParsed(
        gene=gene,
        diplotype=parts[1] or None if len(parts) > 1 else None,
        phenotype=parts[2] or None if len(parts) > 2 else None,
        activity_score=activity_value,
        state="unknown",
        reason_code="parsed_from_vcf_annotation",
        provenance={"source": "vcf_annotation_pipe"},
    )


class PharmcatRunnerPhase4:
    def __init__(
        self,
        *,
        phase4_data_dir: str,
        java_bin: str = "java",
        pharmcat_jar_path: str | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.phase4_data_dir = Path(phase4_data_dir)
        self.java_bin = java_bin
        self.pharmcat_jar_path = pharmcat_jar_path
        self.timeout_seconds = max(10, timeout_seconds)

    def run_from_vcf(self, vcf_path: Path) -> list[PgxGeneCallParsed]:
        if self.pharmcat_jar_path:
            jar = Path(self.pharmcat_jar_path)
            if jar.exists():
                jar_output = self._run_pharmcat_subprocess(vcf_path, jar)
                if jar_output:
                    return jar_output
        return self._fallback_parse_vcf(vcf_path)

    def _run_pharmcat_subprocess(self, vcf_path: Path, jar_path: Path) -> list[PgxGeneCallParsed]:
        with tempfile.TemporaryDirectory(prefix="pathmind-pharmcat-") as temp_dir:
            output_dir = Path(temp_dir)
            command = [
                self.java_bin,
                "-jar",
                str(jar_path),
                "-vcf",
                str(vcf_path),
                "-o",
                str(output_dir),
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )
            except Exception:
                return []

            candidates = [
                output_dir / "report.json",
                output_dir / "pharmcat_report.json",
                output_dir / "results.json",
            ]
            payload_file = next((path for path in candidates if path.exists()), None)
            if payload_file is None:
                return []
            try:
                payload = json.loads(payload_file.read_text(encoding="utf-8"))
            except Exception:
                return []

            calls: list[PgxGeneCallParsed] = []
            gene_rows = payload.get("gene_calls") if isinstance(payload, dict) else None
            if not isinstance(gene_rows, list):
                return []
            for row in gene_rows:
                if not isinstance(row, dict):
                    continue
                gene = str(row.get("gene", "")).strip().upper()
                if not gene:
                    continue
                activity = row.get("activity_score")
                try:
                    activity_value = float(activity) if activity not in {None, ""} else None
                except Exception:
                    activity_value = None
                calls.append(
                    PgxGeneCallParsed(
                        gene=gene,
                        diplotype=row.get("diplotype"),
                        phenotype=row.get("phenotype"),
                        activity_score=activity_value,
                        state="unknown",
                        reason_code="parsed_from_pharmcat",
                        provenance={"source": "pharmcat_subprocess", "output_file": str(payload_file.name)},
                    )
                )
            return calls

    def _fallback_parse_vcf(self, vcf_path: Path) -> list[PgxGeneCallParsed]:
        calls_by_gene: dict[str, PgxGeneCallParsed] = {}
        with vcf_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("##PATHMIND_GENE_CALL="):
                    payload = line.split("=", 1)[1]
                    parsed = _parse_inline_call(payload)
                    if parsed:
                        calls_by_gene[parsed.gene] = parsed
                    continue
                if line.startswith("#"):
                    continue
                parts = line.strip().split("\t")
                if len(parts) < 8:
                    continue
                info = parts[7]
                gene = None
                for token in info.split(";"):
                    if token.startswith("GENE="):
                        gene = token.replace("GENE=", "", 1).strip().upper()
                        break
                if not gene:
                    continue
                if gene not in calls_by_gene:
                    calls_by_gene[gene] = PgxGeneCallParsed(
                        gene=gene,
                        state="unknown",
                        reason_code="gene_not_called",
                        provenance={"source": "vcf_info_gene_tag"},
                    )

        if not calls_by_gene:
            return []
        return sorted(calls_by_gene.values(), key=lambda item: item.gene)

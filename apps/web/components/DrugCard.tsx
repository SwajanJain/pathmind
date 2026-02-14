import type { AnalysisResult } from "@/lib/types";

export function DrugCard({ analysis }: { analysis: AnalysisResult }) {
  return (
    <div className="panel">
      <h2 style={{ marginTop: 0 }}>{analysis.resolution.display_name}</h2>
      <div className="muted" style={{ marginBottom: "0.8rem" }}>
        ChEMBL: {analysis.resolution.chembl_parent_id}
      </div>
      <div>Targets: {analysis.targets.length}</div>
      <div>Clinical phase: {analysis.resolution.clinical_phase ?? "Unknown"}</div>
      <div>MoA: {analysis.resolution.mechanism_of_action ?? "Not available"}</div>
      <div style={{ marginTop: "0.7rem" }}>
        <span className="chip">InChIKey: {analysis.resolution.canonical_inchikey}</span>
      </div>
    </div>
  );
}


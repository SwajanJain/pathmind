"use client";

import { FormEvent, useState } from "react";

import { CompareOverlayGraph } from "@/components/CompareOverlayGraph";
import { ResearchBanner } from "@/components/ResearchBanner";
import { runCompare } from "@/lib/api";
import type { AnalysisParams, CompareResult } from "@/lib/types";

export default function ComparePage() {
  const [drugA, setDrugA] = useState("erlotinib");
  const [drugB, setDrugB] = useState("lapatinib");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<CompareResult | null>(null);
  const [showOverlay, setShowOverlay] = useState(false);
  const [params, setParams] = useState<AnalysisParams>({
    pchembl_threshold: 5,
    min_assays: 2,
    include_low_confidence: false,
    top_pathways: 20,
  });

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      setResult(await runCompare(drugA, drugB, params));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Compare failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="container">
      <ResearchBanner />
      <div className="panel" style={{ marginBottom: "1rem" }}>
        <h1 style={{ marginTop: 0 }}>Compare Drug Profiles</h1>
        <form onSubmit={onSubmit} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <input value={drugA} onChange={(event) => setDrugA(event.target.value)} style={{ padding: "0.5rem", border: "1px solid var(--line)", borderRadius: 8 }} />
          <input value={drugB} onChange={(event) => setDrugB(event.target.value)} style={{ padding: "0.5rem", border: "1px solid var(--line)", borderRadius: 8 }} />
          <button type="submit" style={{ border: 0, borderRadius: 8, padding: "0.5rem 0.8rem", background: "var(--brand)", color: "white" }}>
            {loading ? "Comparing..." : "Compare"}
          </button>
        </form>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: "0.6rem", marginTop: "0.8rem" }}>
          <label className="muted" style={{ display: "grid", gap: "0.2rem" }}>
            pChEMBL threshold
            <input
              type="number"
              min={4}
              max={10}
              step={0.1}
              value={params.pchembl_threshold}
              onChange={(event) => setParams((prev) => ({ ...prev, pchembl_threshold: Number(event.target.value) }))}
            />
          </label>
          <label className="muted" style={{ display: "grid", gap: "0.2rem" }}>
            Min assays
            <input
              type="number"
              min={1}
              max={20}
              step={1}
              value={params.min_assays}
              onChange={(event) => setParams((prev) => ({ ...prev, min_assays: Number(event.target.value) }))}
            />
          </label>
          <label className="muted" style={{ display: "grid", gap: "0.2rem" }}>
            Top pathways
            <input
              type="number"
              min={1}
              max={100}
              step={1}
              value={params.top_pathways}
              onChange={(event) => setParams((prev) => ({ ...prev, top_pathways: Number(event.target.value) }))}
            />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "1.2rem" }}>
            <input
              type="checkbox"
              checked={params.include_low_confidence}
              onChange={(event) => setParams((prev) => ({ ...prev, include_low_confidence: event.target.checked }))}
            />
            <span className="muted">Include low-confidence targets</span>
          </label>
        </div>
        {error && <div style={{ color: "#b91c1c", marginTop: "0.5rem" }}>{error}</div>}
      </div>
      {result && (
        <>
          <div className="panel" style={{ marginBottom: "1rem" }}>
            <strong>Target overlap (Jaccard):</strong> {result.metrics.target_jaccard.toFixed(3)} | <strong>Pathway cosine:</strong>{" "}
            {result.metrics.pathway_cosine_similarity.toFixed(3)}
            <label style={{ marginLeft: "1rem" }}>
              <input type="checkbox" checked={showOverlay} onChange={(event) => setShowOverlay(event.target.checked)} /> Show overlay graph
            </label>
            <div className="muted" style={{ marginTop: "0.4rem" }}>
              Shared pathways: {result.metrics.shared_pathway_count} | Unique A: {result.metrics.unique_pathway_count_a} | Unique B:{" "}
              {result.metrics.unique_pathway_count_b}
            </div>
          </div>
          {showOverlay && (
            <>
              <div className="panel" style={{ marginBottom: "0.8rem" }} aria-live="polite">
                <strong>Overlay legend:</strong> Blue nodes = {result.analysis_a.resolution.display_name}, orange nodes ={" "}
                {result.analysis_b.resolution.display_name}.
              </div>
              <CompareOverlayGraph result={result} />
            </>
          )}
          <div className="panel" style={{ marginBottom: "1rem" }}>
            <strong>Shared pathways</strong>
            <div className="muted">
              {result.rows
                .filter((row) => row.shared)
                .map((row) => row.pathway_name)
                .join(", ") || "None"}
            </div>
            <strong style={{ display: "block", marginTop: "0.7rem" }}>Unique pathways</strong>
            <div className="muted">
              {result.rows
                .filter((row) => !row.shared)
                .map((row) => row.pathway_name)
                .join(", ") || "None"}
            </div>
          </div>
          <div className="panel">
            <table>
              <thead>
                <tr>
                  <th>Pathway</th>
                  <th>{result.analysis_a.resolution.display_name}</th>
                  <th>{result.analysis_b.resolution.display_name}</th>
                  <th>Delta</th>
                  <th>Shared</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row) => (
                  <tr key={row.pathway_id}>
                    <td>{row.pathway_name}</td>
                    <td>{row.score_a?.toFixed(3) ?? "-"}</td>
                    <td>{row.score_b?.toFixed(3) ?? "-"}</td>
                    <td>{row.delta?.toFixed(3) ?? "-"}</td>
                    <td>{row.shared ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}

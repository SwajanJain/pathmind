"use client";

import { useState } from "react";

import { exportAnalysisCsv, exportAnalysisJson, shareAnalysis } from "@/lib/api";
import type { AnalysisResult } from "@/lib/types";

import { AssociationGraph } from "./AssociationGraph";
import { DrugCard } from "./DrugCard";
import { PathwayTable } from "./PathwayTable";
import { ResearchBanner } from "./ResearchBanner";
import { TargetScatter } from "./TargetScatter";

export function AnalysisDashboard({ analysis }: { analysis: AnalysisResult }) {
  const [shareUrl, setShareUrl] = useState<string>("");
  const [shareError, setShareError] = useState<string>("");

  const onShare = async () => {
    setShareError("");
    try {
      const response = await shareAnalysis(analysis.analysis_id);
      setShareUrl(response.public_url);
    } catch (error) {
      setShareError(error instanceof Error ? error.message : "Failed to create share link");
    }
  };

  return (
    <div className="container">
      <ResearchBanner />
      {(analysis.analysis_flags.limited_data || analysis.analysis_flags.partial_mapping || analysis.analysis_flags.high_variability) && (
        <div className="panel" style={{ marginBottom: "1rem", borderColor: "#d97706", background: "#fffbeb" }}>
          {analysis.analysis_flags.limited_data && <div>Limited target data detected for this compound.</div>}
          {analysis.analysis_flags.partial_mapping && <div>Partial target-to-pathway mapping; some targets are unmapped.</div>}
          {analysis.analysis_flags.high_variability && <div>High assay variability detected; review confidence details.</div>}
        </div>
      )}
      {analysis.degraded_messages.length > 0 && (
        <div className="panel" style={{ marginBottom: "1rem", borderColor: "#d97706", background: "#fffbeb" }}>
          {analysis.degraded_messages.map((message) => (
            <div key={message}>{message}</div>
          ))}
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 3fr", gap: "1rem", marginBottom: "1rem" }}>
        <DrugCard analysis={analysis} />
        <PathwayTable pathways={analysis.pathways} />
      </div>
      <AssociationGraph analysis={analysis} />
      <div style={{ display: "grid", gridTemplateColumns: "3fr 2fr", gap: "1rem", marginTop: "1rem" }}>
        <TargetScatter targets={analysis.targets} />
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Actions</h3>
          <button onClick={onShare} style={{ border: 0, borderRadius: 8, padding: "0.5rem 0.8rem", background: "#0f766e", color: "white" }}>
            Create share link
          </button>
          <div style={{ display: "flex", gap: "0.4rem", marginTop: "0.7rem" }}>
            <a href={exportAnalysisCsv(analysis.analysis_id)} style={{ borderRadius: 8, border: "1px solid var(--line)", background: "white", padding: "0.4rem 0.7rem" }}>
              Export CSV
            </a>
            <a href={exportAnalysisJson(analysis.analysis_id)} style={{ borderRadius: 8, border: "1px solid var(--line)", background: "white", padding: "0.4rem 0.7rem" }}>
              Export JSON
            </a>
          </div>
          {shareUrl && (
            <div style={{ marginTop: "0.8rem", wordBreak: "break-all" }}>
              <a href={shareUrl}>{shareUrl}</a>
            </div>
          )}
          {shareError && <div style={{ color: "#b91c1c", marginTop: "0.7rem" }}>{shareError}</div>}
          <hr style={{ borderColor: "#d7dee8", margin: "1rem 0" }} />
          <div className="muted" style={{ fontSize: "0.85rem" }}>
            {analysis.attribution}
          </div>
        </div>
      </div>
    </div>
  );
}

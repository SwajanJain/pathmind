"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useParams } from "next/navigation";

import { AnalysisDashboard } from "@/components/AnalysisDashboard";
import { getShare, runAnalysis } from "@/lib/api";
import type { AnalysisResult } from "@/lib/types";

export default function SharePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState("");
  const [rerunning, setRerunning] = useState(false);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const result = await getShare(String(params.id));
        if (active) setAnalysis(result);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load share");
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [params.id]);

  const rerun = async () => {
    if (!analysis) return;
    setRerunning(true);
    try {
      const rerunResult = await runAnalysis(analysis.drug_name, analysis.params);
      router.push(`/analysis/${rerunResult.analysis_id}`);
    } finally {
      setRerunning(false);
    }
  };

  if (error) {
    return (
      <main className="container">
        <div className="panel" style={{ color: "#b91c1c" }}>
          {error}
        </div>
      </main>
    );
  }

  if (!analysis) {
    return (
      <main className="container">
        <div className="panel">Loading frozen share snapshot...</div>
      </main>
    );
  }

  return (
    <>
      <main className="container">
        <div className="panel" style={{ marginBottom: "1rem" }}>
          <strong>Frozen snapshot</strong> from {new Date(analysis.created_at).toLocaleString()}.
          <button
            onClick={rerun}
            style={{ marginLeft: "0.8rem", border: 0, borderRadius: 8, padding: "0.4rem 0.7rem", background: "var(--accent)", color: "white" }}
          >
            {rerunning ? "Re-running..." : "Re-run with latest data"}
          </button>
        </div>
      </main>
      <AnalysisDashboard analysis={analysis} />
    </>
  );
}


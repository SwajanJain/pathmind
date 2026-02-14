"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { AnalysisDashboard } from "@/components/AnalysisDashboard";
import { getAnalysis } from "@/lib/api";
import type { AnalysisResult } from "@/lib/types";

export default function AnalysisPage() {
  const params = useParams<{ id: string }>();
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const result = await getAnalysis(String(params.id));
        if (active) {
          setAnalysis(result);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load analysis");
        }
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [params.id]);

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
        <div className="panel">Loading analysis...</div>
      </main>
    );
  }
  return <AnalysisDashboard analysis={analysis} />;
}


"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { ResearchBanner } from "@/components/ResearchBanner";
import { resolveDrug, runAnalysis, suggestDrugs } from "@/lib/api";
import type { AnalysisParams, DrugResolutionCandidate } from "@/lib/types";

export default function HomePage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [doNotLog, setDoNotLog] = useState(false);
  const [params, setParams] = useState<AnalysisParams>({
    pchembl_threshold: 5,
    min_assays: 2,
    include_low_confidence: false,
    top_pathways: 20,
  });
  const [suggestions, setSuggestions] = useState<Array<{ display_name: string; chembl_id?: string }>>([]);
  const [candidates, setCandidates] = useState<DrugResolutionCandidate[]>([]);
  const [resolutionChoice, setResolutionChoice] = useState<string>("");
  const canSearch = useMemo(() => query.trim().length >= 2 && !loading, [query, loading]);

  const onSuggest = async (value: string) => {
    setQuery(value);
    setError("");
    setCandidates([]);
    setResolutionChoice("");
    if (value.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    try {
      const response = await suggestDrugs(value);
      setSuggestions(response.suggestions);
    } catch {
      setSuggestions([]);
    }
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSearch) return;
    setLoading(true);
    setError("");
    try {
      const resolution = await resolveDrug(query.trim(), resolutionChoice || undefined);
      if (resolution.status === "ambiguous") {
        setCandidates(resolution.candidates);
        if (!resolutionChoice && resolution.candidates.length > 0) {
          setResolutionChoice(resolution.candidates[0].chembl_parent_id);
        }
        setError("Multiple compounds matched. Select one candidate and run again.");
        return;
      }
      if (resolution.status === "not_found") {
        setError("No matching compound found.");
        return;
      }
      const analysis = await runAnalysis(
        query.trim(),
        params,
        doNotLog,
        (resolution.resolution?.chembl_parent_id ?? resolutionChoice) || undefined,
      );
      router.push(`/analysis/${analysis.analysis_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="container">
      <ResearchBanner />
      <div className="panel" style={{ marginTop: "2rem" }}>
        <div style={{ fontFamily: "var(--font-heading)", fontSize: "2rem", marginBottom: "0.5rem" }}>PathMind</div>
        <p className="muted" style={{ marginTop: 0 }}>
          What does your drug do at the molecular level?
        </p>
        <form onSubmit={onSubmit}>
          <input
            value={query}
            onChange={(event) => onSuggest(event.target.value)}
            placeholder="Type a drug name, e.g. erlotinib"
            style={{ width: "100%", padding: "0.75rem", borderRadius: 10, border: "1px solid var(--line)" }}
          />
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
            <button
              disabled={!canSearch}
              style={{
                border: 0,
                borderRadius: 8,
                padding: "0.55rem 1rem",
                background: canSearch ? "var(--brand)" : "#94a3b8",
                color: "white",
              }}
            >
              {loading ? "Running..." : "Analyze"}
            </button>
            <a href="/compare" style={{ padding: "0.55rem 1rem" }}>
              Compare two drugs
            </a>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.8rem" }}>
            <input type="checkbox" checked={doNotLog} onChange={(event) => setDoNotLog(event.target.checked)} />
            <span className="muted">Don’t log my query</span>
          </label>
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
        </form>
        {error && <div style={{ color: "#b91c1c", marginTop: "0.75rem" }}>{error}</div>}
        {suggestions.length > 0 && (
          <div style={{ marginTop: "0.8rem" }}>
            {suggestions.map((item) => (
              <button
                key={`${item.display_name}-${item.chembl_id ?? "unknown"}`}
                type="button"
                onClick={() => setQuery(item.display_name)}
                className="chip"
                style={{ marginRight: "0.4rem", marginBottom: "0.3rem", background: "white" }}
              >
                {item.display_name}
              </button>
            ))}
          </div>
        )}
        {candidates.length > 0 && (
          <div className="panel" style={{ marginTop: "0.8rem", background: "#f8fafc" }}>
            <div style={{ fontWeight: 600, marginBottom: "0.4rem" }}>Select compound identity</div>
            {candidates.map((candidate) => (
              <label key={candidate.chembl_parent_id} style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "0.35rem" }}>
                <input
                  type="radio"
                  name="resolution-choice"
                  checked={resolutionChoice === candidate.chembl_parent_id}
                  onChange={() => setResolutionChoice(candidate.chembl_parent_id)}
                />
                <span>
                  {candidate.display_name} ({candidate.chembl_parent_id})
                </span>
              </label>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

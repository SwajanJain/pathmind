import type { AnalysisParams, AnalysisResult, CompareResult, DrugResolveResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function suggestDrugs(query: string) {
  return apiFetch<{ query: string; suggestions: Array<{ display_name: string; chembl_id?: string }> }>(
    `/api/drugs/suggest?q=${encodeURIComponent(query)}`,
  );
}

export function resolveDrug(query: string, resolutionChoice?: string) {
  return apiFetch<DrugResolveResponse>("/api/drugs/resolve", {
    method: "POST",
    body: JSON.stringify({ query, resolution_choice: resolutionChoice ?? null }),
  });
}

export function runAnalysis(
  drugName: string,
  params?: Partial<AnalysisParams>,
  doNotLog?: boolean,
  resolutionChoice?: string,
) {
  return apiFetch<AnalysisResult>("/api/analysis/run", {
    method: "POST",
    body: JSON.stringify({
      drug_name: drugName,
      do_not_log: Boolean(doNotLog),
      resolution_choice: resolutionChoice ?? null,
      params: {
        pchembl_threshold: 5.0,
        min_assays: 2,
        include_low_confidence: false,
        top_pathways: 20,
        ...(params ?? {}),
      },
    }),
  });
}

export function getAnalysis(analysisId: string) {
  return apiFetch<AnalysisResult>(`/api/analysis/${analysisId}`);
}

export function shareAnalysis(analysisId: string) {
  return apiFetch<{ share_id: string; analysis_id: string; public_url: string; created_at: string }>(
    `/api/analysis/${analysisId}/share`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

export function getShare(shareId: string) {
  return apiFetch<AnalysisResult>(`/api/share/${shareId}`);
}

export function exportAnalysisCsv(analysisId: string) {
  return `${API_BASE}/api/analysis/${analysisId}/export.csv`;
}

export function exportAnalysisJson(analysisId: string) {
  return `${API_BASE}/api/analysis/${analysisId}/export.json`;
}

export function runCompare(drugA: string, drugB: string, params?: Partial<AnalysisParams>) {
  return apiFetch<CompareResult>("/api/compare/run", {
    method: "POST",
    body: JSON.stringify({
      drug_a: drugA,
      drug_b: drugB,
      params: {
        pchembl_threshold: 5.0,
        min_assays: 2,
        include_low_confidence: false,
        top_pathways: 20,
        ...(params ?? {}),
      },
    }),
  });
}

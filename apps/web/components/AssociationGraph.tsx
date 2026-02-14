"use client";

import { useEffect, useRef } from "react";
import { useState } from "react";

import cytoscape, { Core } from "cytoscape";
import dagre from "cytoscape-dagre";

import type { AnalysisResult } from "@/lib/types";

cytoscape.use(dagre);

type Props = { analysis: AnalysisResult };

export function AssociationGraph({ analysis }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Core | null>(null);
  const [selectedNode, setSelectedNode] = useState<{ id: string; label: string; kind: string; metadata: Record<string, unknown> } | null>(null);

  const downloadFile = (filename: string, data: string, mimeType: string) => {
    const blob = new Blob([data], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  };

  const exportPng = () => {
    const cy = graphRef.current;
    if (!cy) return;
    const base64 = cy.png({ full: true, bg: "#ffffff", scale: 2 });
    const link = document.createElement("a");
    link.href = base64;
    link.download = `${analysis.analysis_id}-network.png`;
    link.click();
  };

  const exportSvg = () => {
    const cy = graphRef.current as Core & { svg?: (options?: object) => string };
    if (!cy) return;
    if (typeof cy.svg === "function") {
      const svg = cy.svg({ full: true, scale: 1 });
      downloadFile(`${analysis.analysis_id}-network.svg`, svg, "image/svg+xml");
      return;
    }
    const fallback = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="60"><text x="12" y="34" font-size="16">SVG export requires cytoscape-svg plugin.</text></svg>`;
    downloadFile(`${analysis.analysis_id}-network.svg`, fallback, "image/svg+xml");
  };

  useEffect(() => {
    if (!containerRef.current) return;
    graphRef.current?.destroy();
    const nodes = [...analysis.graph.nodes].sort((a, b) => a.id.localeCompare(b.id));
    const edges = [...analysis.graph.edges].sort((a, b) => a.id.localeCompare(b.id));
    graphRef.current = cytoscape({
      container: containerRef.current,
      elements: [
        ...nodes.map((node) => ({
          data: {
            id: node.id,
            label: node.label,
            kind: node.kind,
          },
        })),
        ...edges.map((edge) => ({
          data: {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            kind: edge.kind,
            weight: edge.weight,
          },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "font-size": 11,
            "text-wrap": "wrap",
            "background-color": "#c7d2fe",
            "text-max-width": "120px",
          } as never,
        },
        {
          selector: "node[kind='drug']",
          style: { "background-color": "#0f766e", color: "#111827", "font-weight": 700 } as never,
        },
        {
          selector: "node[kind='target']",
          style: { "background-color": "#f59e0b" },
        },
        {
          selector: "node[kind='pathway']",
          style: { "background-color": "#93c5fd" },
        },
        {
          selector: "edge",
          style: {
            width: "mapData(weight, 0, 10, 1, 6)",
            "line-color": "#94a3b8",
            "target-arrow-color": "#94a3b8",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
          },
        },
      ],
      layout: { name: "dagre", rankDir: "LR", nodeSep: 45, rankSep: 140 } as never,
    });
    graphRef.current.on("tap", "node", (event) => {
      const node = event.target;
      const nodeId = String(node.id());
      const sourceNode = analysis.graph.nodes.find((entry) => entry.id === nodeId);
      setSelectedNode(
        sourceNode
          ? {
              id: sourceNode.id,
              label: sourceNode.label,
              kind: sourceNode.kind,
              metadata: sourceNode.metadata,
            }
          : {
              id: nodeId,
              label: String(node.data("label") ?? nodeId),
              kind: String(node.data("kind") ?? "unknown"),
              metadata: {},
            },
      );
    });
    return () => {
      graphRef.current?.destroy();
      graphRef.current = null;
    };
  }, [analysis]);

  return (
    <div className="panel">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.6rem" }}>
        <h3 style={{ margin: 0 }}>Association Graph</h3>
        <div style={{ display: "flex", gap: "0.4rem" }}>
          <button type="button" onClick={exportPng} style={{ borderRadius: 8, border: "1px solid var(--line)", background: "white", padding: "0.3rem 0.6rem" }}>
            Export PNG
          </button>
          <button type="button" onClick={exportSvg} style={{ borderRadius: 8, border: "1px solid var(--line)", background: "white", padding: "0.3rem 0.6rem" }}>
            Export SVG
          </button>
        </div>
      </div>
      <div data-testid="association-graph" ref={containerRef} style={{ width: "100%", minHeight: 420, border: "1px solid var(--line)", borderRadius: 12 }} />
      <div style={{ marginTop: "0.8rem", borderTop: "1px solid var(--line)", paddingTop: "0.7rem" }}>
        <strong>Detail Panel</strong>
        {!selectedNode ? (
          <div className="muted" style={{ marginTop: "0.4rem" }}>
            Click any node to inspect metadata.
          </div>
        ) : (
          <div style={{ marginTop: "0.4rem" }}>
            <div>
              <strong>{selectedNode.label}</strong> <span className="chip">{selectedNode.kind}</span>
            </div>
            <div className="muted" style={{ marginTop: "0.25rem" }}>
              {selectedNode.id}
            </div>
            {selectedNode.kind === "pathway" && typeof selectedNode.metadata.reactome_url === "string" && (
              <div style={{ marginTop: "0.35rem" }}>
                <a href={selectedNode.metadata.reactome_url} target="_blank" rel="noreferrer">
                  Open Reactome reference
                </a>
              </div>
            )}
            <div className="muted" style={{ marginTop: "0.35rem", fontSize: "0.85rem" }}>
              Source: Reactome/ChEMBL/OpenTargets/UniProt/PubChem (see attribution in panel).
            </div>
            <pre style={{ marginTop: "0.5rem", background: "#f8fafc", padding: "0.6rem", borderRadius: 8, overflowX: "auto" }}>
              {JSON.stringify(selectedNode.metadata, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

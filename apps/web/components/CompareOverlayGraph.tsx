"use client";

import { useEffect, useRef } from "react";

import cytoscape, { Core } from "cytoscape";
import dagre from "cytoscape-dagre";

import type { CompareResult } from "@/lib/types";

cytoscape.use(dagre);

export function CompareOverlayGraph({ result }: { result: CompareResult }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    cyRef.current?.destroy();
    const addPrefixed = (analysis: CompareResult["analysis_a"], prefix: "a" | "b") => {
      const nodeColor = prefix === "a" ? "#2563eb" : "#f97316";
      return {
        nodes: analysis.graph.nodes.map((node) => ({
          data: {
            id: `${prefix}:${node.id}`,
            label: `${node.label}${node.kind === "drug" ? ` (${prefix.toUpperCase()})` : ""}`,
            kind: node.kind,
            group: prefix,
            color: nodeColor,
          },
        })),
        edges: analysis.graph.edges.map((edge) => ({
          data: {
            id: `${prefix}:${edge.id}`,
            source: `${prefix}:${edge.source}`,
            target: `${prefix}:${edge.target}`,
            group: prefix,
            weight: edge.weight,
          },
        })),
      };
    };
    const a = addPrefixed(result.analysis_a, "a");
    const b = addPrefixed(result.analysis_b, "b");
    cyRef.current = cytoscape({
      container: ref.current,
      elements: [...a.nodes, ...a.edges, ...b.nodes, ...b.edges],
      style: [
        { selector: "node", style: { label: "data(label)", "font-size": 10, "background-color": "data(color)" } },
        { selector: "edge", style: { width: "mapData(weight, 0, 10, 1, 5)", "line-color": "#94a3b8", "curve-style": "bezier" } },
      ],
      layout: { name: "dagre", rankDir: "LR", nodeSep: 30, rankSep: 100 } as never,
    });
    return () => {
      cyRef.current?.destroy();
      cyRef.current = null;
    };
  }, [result]);

  return <div className="panel" data-testid="compare-overlay-graph" aria-label="Drug overlay graph" style={{ minHeight: 380 }} ref={ref} />;
}

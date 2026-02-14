import type { TargetHit } from "@/lib/types";

export function TargetScatter({ targets }: { targets: TargetHit[] }) {
  const width = 480;
  const height = 220;
  const minX = 0;
  const maxX = Math.max(targets.length - 1, 1);
  const minY = 4;
  const maxY = 10;

  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>Target Binding Profile</h3>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`}>
        <line x1={20} y1={20} x2={20} y2={height - 20} stroke="#94a3b8" />
        <line x1={20} y1={height - 20} x2={width - 20} y2={height - 20} stroke="#94a3b8" />
        {targets.slice(0, 40).map((target, index) => {
          const x = 20 + ((width - 40) * (index - minX)) / (maxX - minX);
          const yMedian = height - 20 - ((height - 40) * (target.median_pchembl - minY)) / (maxY - minY);
          const yMin = height - 20 - ((height - 40) * ((target.pchembl_min ?? target.median_pchembl) - minY)) / (maxY - minY);
          const yMax = height - 20 - ((height - 40) * ((target.pchembl_max ?? target.median_pchembl) - minY)) / (maxY - minY);
          return (
            <g key={target.target_chembl_id}>
              <line x1={x} x2={x} y1={yMin} y2={yMax} stroke="#94a3b8" strokeWidth={2} />
              <circle cx={x} cy={yMedian} r={4} fill={target.confidence_tier === "high" ? "#0f766e" : "#f59e0b"} />
            </g>
          );
        })}
      </svg>
      <div className="muted" style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>
        Vertical bars show assay min/max range; dots show median pChEMBL.
      </div>
      <div style={{ marginTop: "0.6rem" }}>
        {targets.slice(0, 5).map((target) => (
          <div key={target.target_chembl_id} className="muted" style={{ fontSize: "0.82rem" }}>
            {target.target_name}: {target.confidence_reasons.join(", ")} ({target.mapping_status})
          </div>
        ))}
      </div>
    </div>
  );
}

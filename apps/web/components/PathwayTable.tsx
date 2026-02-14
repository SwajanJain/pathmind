import type { PathwayScore } from "@/lib/types";

export function PathwayTable({ pathways }: { pathways: PathwayScore[] }) {
  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>Pathway Impact Ranking</h3>
      <table>
        <thead>
          <tr>
            <th>Pathway</th>
            <th>Score</th>
            <th>Targets</th>
            <th>Coverage</th>
            <th>Depth</th>
          </tr>
        </thead>
        <tbody>
          {pathways.map((pathway) => (
            <tr key={pathway.pathway_id}>
              <td>
                <a href={pathway.reactome_url} target="_blank" rel="noreferrer">
                  {pathway.pathway_name}
                </a>
              </td>
              <td>{pathway.score.toFixed(3)}</td>
              <td>{pathway.targets_hit}</td>
              <td>{(pathway.coverage_ratio * 100).toFixed(1)}%</td>
              <td>{pathway.depth}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

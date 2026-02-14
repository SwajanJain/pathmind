export default function PrivacyPage() {
  return (
    <main className="container">
      <div className="panel">
        <h1 style={{ marginTop: 0 }}>Privacy Posture (V1)</h1>
        <p className="muted">
          PathMind stores query analytics for product reliability and usage analysis. No accounts are required in V1.
        </p>
        <ul>
          <li>Query log retention: 90 days.</li>
          <li>IP addresses are masked at ingestion (IPv4 last octet, IPv6 suffix blocks).</li>
          <li>Share links contain analysis data only, no user profile data.</li>
          <li>Cookie consent controls analytics events; declined consent sends no analytics page events.</li>
          <li>No clinical decision support intent. Research use only.</li>
          <li>Use the “Don’t log my query” toggle on the search page to disable analysis storage for a run.</li>
        </ul>
      </div>
    </main>
  );
}

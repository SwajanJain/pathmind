const CONSENT_KEY = "pathmind_cookie_consent";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function trackPageView(pagePath: string): Promise<void> {
  if (typeof window === "undefined") return;
  const consent = window.localStorage.getItem(CONSENT_KEY);
  if (consent !== "accepted") return;
  await fetch(`${API_BASE}/api/analytics/event`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_name: "page_view", page_path: pagePath }),
  }).catch(() => undefined);
}

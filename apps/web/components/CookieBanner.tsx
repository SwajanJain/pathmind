"use client";

import { useEffect, useState } from "react";

const CONSENT_KEY = "pathmind_cookie_consent";

export function CookieBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const existing = window.localStorage.getItem(CONSENT_KEY);
    if (!existing) {
      setVisible(true);
    }
  }, []);

  if (!visible) {
    return null;
  }

  const save = (value: "accepted" | "declined") => {
    window.localStorage.setItem(CONSENT_KEY, value);
    setVisible(false);
  };

  return (
    <div style={{ position: "fixed", right: 16, bottom: 16, maxWidth: 420, zIndex: 40 }} className="panel">
      <div style={{ fontWeight: 600, marginBottom: "0.4rem" }}>Cookie preferences</div>
      <div className="muted" style={{ fontSize: "0.9rem" }}>
        PathMind uses minimal analytics cookies. You can decline and continue using the app.
      </div>
      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.7rem" }}>
        <button type="button" onClick={() => save("declined")} style={{ borderRadius: 8, border: "1px solid var(--line)", background: "white", padding: "0.35rem 0.7rem" }}>
          Decline
        </button>
        <button type="button" onClick={() => save("accepted")} style={{ borderRadius: 8, border: 0, background: "var(--brand)", color: "white", padding: "0.35rem 0.7rem" }}>
          Accept
        </button>
      </div>
    </div>
  );
}


import type { Metadata } from "next";
import { IBM_Plex_Sans, Space_Grotesk } from "next/font/google";

import { AnalyticsTracker } from "@/components/AnalyticsTracker";
import { CookieBanner } from "@/components/CookieBanner";

import "./globals.css";

const heading = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-heading",
});

const body = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-body",
});

export const metadata: Metadata = {
  title: "PathMind",
  description: "Drug-to-pathway impact analysis",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${heading.variable} ${body.variable}`}>
      <body>
        <AnalyticsTracker />
        {children}
        <footer className="container" style={{ paddingTop: 0 }}>
          <div className="muted" style={{ fontSize: "0.85rem", paddingBottom: "1rem" }}>
            <a href="/">Home</a> | <a href="/compare">Compare</a> | <a href="/privacy">Privacy</a>
          </div>
        </footer>
        <CookieBanner />
      </body>
    </html>
  );
}

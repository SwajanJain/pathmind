"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

import { trackPageView } from "@/lib/analytics";

export function AnalyticsTracker() {
  const pathname = usePathname();

  useEffect(() => {
    if (!pathname) return;
    void trackPageView(pathname);
  }, [pathname]);

  return null;
}

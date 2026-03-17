"use client";

import { useState, useEffect, useCallback } from "react";

const API_BASE = "http://localhost:8000";

export function useSeen() {
  const [seenIds, setSeenIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetch(`${API_BASE}/api/seen`)
      .then((r) => r.json())
      .then((d) => setSeenIds(new Set(d.seen_ids)))
      .catch(() => {});
  }, []);

  const markSeen = useCallback((ids: string[]) => {
    setSeenIds((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.add(id));
      return next;
    });
    fetch(`${API_BASE}/api/seen`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    }).catch(() => {});
  }, []);

  return { seenIds, markSeen };
}

"use client";

import { useEffect, useState } from "react";
import type { SyncStatusResponse } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import {
  getSyncStatusCache,
  subscribeSyncStatus,
} from "@/lib/sync-status-store";

export function SyncStatusBar({ compact = false }: { compact?: boolean }) {
  const [status, setStatus] = useState<SyncStatusResponse | null>(() =>
    typeof window === "undefined" ? null : getSyncStatusCache(),
  );
  const [, setMinuteTick] = useState(0);

  useEffect(() => subscribeSyncStatus(() => setStatus(getSyncStatusCache())), []);

  useEffect(() => {
    const id = window.setInterval(() => setMinuteTick((t) => t + 1), 60_000);
    return () => window.clearInterval(id);
  }, []);

  if (!status) {
    return null;
  }

  if (compact) {
    return (
      <p className="min-w-0 truncate text-xs text-bb-muted">
        Synced{" "}
        <span className="font-medium text-white">
          {timeAgo(status.last_success_at)}
        </span>
        {status.has_recent_failure ? (
          <span className="ml-1 text-red-300">· failed</span>
        ) : null}
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
      <span className="text-bb-muted">
        Last sync{" "}
        <span className="font-medium text-white">
          {timeAgo(status.last_success_at)}
        </span>
      </span>
      {status.has_recent_failure ? (
        <span className="text-red-300">Recent sync failure</span>
      ) : null}
      {status.sync_cron ? (
        <span className="hidden text-xs text-bb-muted sm:inline" title="External cron cadence">
          cron {status.sync_cron}
        </span>
      ) : null}
    </div>
  );
}

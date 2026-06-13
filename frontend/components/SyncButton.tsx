"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { postSyncAll } from "@/lib/api";
import { SYNC_FINISHED_EVENT, SYNC_STARTED_EVENT } from "@/lib/sync-events";

export function SyncButton({ compact = false }: { compact?: boolean }) {
  const router = useRouter();
  const [status, setStatus] = useState<"idle" | "syncing" | "done" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleSync(forceRefresh = false) {
    setStatus("syncing");
    setMessage(null);
    window.dispatchEvent(new Event(SYNC_STARTED_EVENT));
    try {
      const result = await postSyncAll(forceRefresh);
      const failed = result.results.filter((r) => r.status !== "success");
      if (failed.length) {
        setStatus("error");
        setMessage(`${failed.length} league(s) failed`);
      } else {
        setStatus("done");
        setMessage(forceRefresh ? "Metrics rebuilt" : "Synced");
        router.refresh();
        setTimeout(() => setStatus("idle"), 3000);
      }
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "Sync failed");
    } finally {
      window.dispatchEvent(new Event(SYNC_FINISHED_EVENT));
    }
  }

  if (compact) {
    return (
      <button
        type="button"
        onClick={() => handleSync(false)}
        disabled={status === "syncing"}
        title={status === "syncing" ? "Syncing…" : "Sync now"}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-bb-gold/40 bg-bb-gold/10 text-sm text-bb-gold transition hover:bg-bb-gold/20 disabled:opacity-50"
      >
        {status === "syncing" ? "…" : "↻"}
      </button>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => handleSync(false)}
        disabled={status === "syncing"}
        className="rounded-lg border border-bb-gold/40 bg-bb-gold/10 px-3 py-1.5 text-sm font-medium text-bb-gold transition hover:bg-bb-gold/20 disabled:opacity-50"
      >
        {status === "syncing" ? "Syncing…" : "Sync Now"}
      </button>
      <button
        type="button"
        onClick={() => handleSync(true)}
        disabled={status === "syncing"}
        className="rounded-lg border border-bb-border/60 px-3 py-1.5 text-sm font-medium text-bb-muted transition hover:border-bb-gold/40 hover:text-white disabled:opacity-50"
        title="Bypass projection/HPPG/opportunity caches and recompute snapshots"
      >
        Rebuild Metrics
      </button>
      {message ? (
        <span
          className={`text-sm ${status === "error" ? "text-red-300" : "text-bb-muted"}`}
        >
          {message}
        </span>
      ) : null}
    </div>
  );
}

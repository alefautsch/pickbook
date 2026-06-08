"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { postSyncAll } from "@/lib/api";

export function SyncButton() {
  const router = useRouter();
  const [status, setStatus] = useState<"idle" | "syncing" | "done" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleSync() {
    setStatus("syncing");
    setMessage(null);
    try {
      const result = await postSyncAll();
      const failed = result.results.filter((r) => r.status !== "success");
      if (failed.length) {
        setStatus("error");
        setMessage(`${failed.length} league(s) failed`);
      } else {
        setStatus("done");
        setMessage("Synced");
        router.refresh();
        setTimeout(() => setStatus("idle"), 3000);
      }
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "Sync failed");
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={handleSync}
        disabled={status === "syncing"}
        className="rounded-lg border border-bb-gold/40 bg-bb-gold/10 px-3 py-1.5 text-sm font-medium text-bb-gold transition hover:bg-bb-gold/20 disabled:opacity-50"
      >
        {status === "syncing" ? "Syncing…" : "Sync Now"}
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

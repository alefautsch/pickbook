import { getSyncStatus, type SyncStatusResponse } from "@/lib/api";
import { timeAgo } from "@/lib/format";

export async function SyncStatusBar() {
  let status: SyncStatusResponse | null = null;
  try {
    status = await getSyncStatus();
  } catch {
    status = null;
  }

  if (!status) {
    return null;
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
        <span className="text-xs text-bb-muted" title="External cron cadence">
          cron {status.sync_cron}
        </span>
      ) : null}
    </div>
  );
}

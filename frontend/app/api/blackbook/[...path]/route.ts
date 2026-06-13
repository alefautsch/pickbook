import { appendFileSync } from "node:fs";
import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SYNC_STATUS_HIT_LOG = "/tmp/bb-sync-status-hits.log";
const SYNC_STATUS_MIN_GAP_MS = 5_000;

let syncStatusCache: { body: string; at: number } | null = null;

function logSyncStatusHit(
  request: NextRequest,
  path: string[],
  callerOverride?: string,
) {
  if (path.join("/") !== "sync/status" || request.method !== "GET") return;
  const caller =
    callerOverride ?? request.headers.get("x-bb-sync-caller") ?? "unknown";
  const source =
    request.headers.get("referer") ??
    request.headers.get("user-agent") ??
    "unknown";
  try {
    appendFileSync(SYNC_STATUS_HIT_LOG, `${Date.now()} ${caller} ${source}\n`);
  } catch {
    // ignore logging failures
  }
}

const BACKEND_URL =
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000";

function backendUrl(path: string[], search: string): string {
  const suffix = path.map(encodeURIComponent).join("/");
  return `${BACKEND_URL.replace(/\/$/, "")}/${suffix}${search}`;
}

function cachedSyncStatusResponse(): Response | null {
  if (!syncStatusCache) return null;
  return new Response(syncStatusCache.body, {
    status: 200,
    headers: {
      "content-type": "application/json",
      "x-bb-sync-status-cache": "hit",
    },
  });
}

async function proxy(request: NextRequest, path: string[]): Promise<Response> {
  const isSyncStatusGet =
    request.method === "GET" && path.join("/") === "sync/status";

  if (isSyncStatusGet && syncStatusCache) {
    const age = Date.now() - syncStatusCache.at;
    if (age < SYNC_STATUS_MIN_GAP_MS) {
      logSyncStatusHit(request, path, "cached");
      return cachedSyncStatusResponse()!;
    }
  }

  const url = backendUrl(path, request.nextUrl.search);
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    redirect: "manual",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
    init.duplex = "half";
  }

  const upstream = await fetch(url, init);
  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete("content-encoding");

  if (isSyncStatusGet && upstream.ok) {
    const body = await upstream.text();
    syncStatusCache = { body, at: Date.now() };
    return new Response(body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

type RouteContext = { params: Promise<{ path: string[] }> };

async function handle(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  logSyncStatusHit(request, path);
  return proxy(request, path);
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
export const OPTIONS = handle;

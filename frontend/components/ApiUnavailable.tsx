export function ApiUnavailable() {
  return (
    <div className="mx-auto flex min-h-[50vh] max-w-lg flex-col justify-center gap-4 px-6 py-12">
      <h1 className="text-xl font-semibold text-white">Backend not reachable</h1>
      <p className="text-sm leading-relaxed text-bb-muted">
        The Next.js app is running, but it could not reach the Blackbook API at{" "}
        <code className="text-white/90">http://127.0.0.1:8000</code>. Pages load
        league data through that API — without it you will see blank or 404 pages.
      </p>
      <div className="rounded-lg border border-white/10 bg-black/30 p-4 text-sm text-white/85">
        <p className="mb-2 font-medium text-white">Start local dev (two terminals):</p>
        <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-bb-muted">
{`# Terminal 1 — Postgres should already be up on :5444
just bb-api

# Terminal 2
just bb-web`}
        </pre>
        <p className="mt-3 text-xs text-bb-muted">
          Or run both together: <code className="text-white/80">just bb-dev</code>
        </p>
      </div>
    </div>
  );
}

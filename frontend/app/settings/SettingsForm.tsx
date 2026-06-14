"use client";

import { useEffect, useState } from "react";
import { FontPicker } from "@/components/FontPicker";
import { getSettings, putSettings, type UserSettings } from "@/lib/api";

export default function SettingsPageClient() {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const [username, setUsername] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getSettings()
      .then((data) => {
        setSettings(data);
        setUsername(data.sleeper_username);
      })
      .catch((err) => setStatus(err instanceof Error ? err.message : "Load failed"))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave(event: React.FormEvent) {
    event.preventDefault();
    setStatus(null);
    try {
      const updated = await putSettings({ sleeper_username: username });
      setSettings(updated);
      setStatus("Saved.");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Save failed");
    }
  }

  if (loading) {
    return <p className="text-bb-muted">Loading settings…</p>;
  }

  return (
    <form onSubmit={handleSave} className="max-w-xl space-y-6">
      <section className="bb-card p-5">
        <h2 className="text-lg font-medium text-white">Account</h2>
        <label className="mt-4 block text-sm">
          <span className="text-bb-muted">Sleeper username</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1 w-full rounded-lg border border-bb-border bg-black/30 px-3 py-2 text-white"
          />
        </label>
      </section>

      <section className="bb-card p-5">
        <h2 className="text-lg font-medium text-white">Appearance</h2>
        <p className="mt-1 text-sm text-bb-muted">
          Try different UI fonts — saved in this browser only, applied instantly.
        </p>
        <FontPicker />
      </section>

      {settings ? (
        <section className="bb-card p-5">
          <h2 className="text-lg font-medium text-white">Dynasty weights</h2>
          <p className="mt-1 text-sm text-bb-muted">
            Read-only in UI — edit via API or seed for now.
          </p>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            {Object.entries(settings.dynasty_weights).map(([key, value]) => (
              <div key={key}>
                <dt className="text-bb-muted">{key}</dt>
                <dd className="font-medium text-white">{value}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      <div className="flex items-center gap-4">
        <button
          type="submit"
          className="rounded-lg bg-bb-gold/90 px-4 py-2 text-sm font-medium text-black hover:bg-bb-gold"
        >
          Save
        </button>
        {status ? <p className="text-sm text-bb-muted">{status}</p> : null}
      </div>
    </form>
  );
}

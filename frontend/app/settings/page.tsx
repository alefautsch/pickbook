import { AppShell } from "@/components/AppShell";
import { getLeagues } from "@/lib/api";
import SettingsForm from "./SettingsForm";

export default async function SettingsPage() {
  const leagues = await getLeagues().catch(() => []);

  return (
    <AppShell leagues={leagues}>
      <div className="flex flex-1 flex-col px-6 py-10 sm:px-10">
        <header className="mb-8">
          <h1 className="text-3xl font-semibold text-white">Settings</h1>
          <p className="mt-2 text-sm text-bb-muted">
            Global knobs migrated from config.json — changes apply on next sync.
          </p>
        </header>
        <SettingsForm />
      </div>
    </AppShell>
  );
}

import type { AgeProfile } from "@/lib/api";

type AgeProfileSidebarProps = {
  profiles: AgeProfile[];
};

const BUCKETS = [
  { label: "≤24", test: (age: number) => age <= 24 },
  { label: "25–27", test: (age: number) => age >= 25 && age <= 27 },
  { label: "28–30", test: (age: number) => age >= 28 && age <= 30 },
  { label: "31+", test: (age: number) => age >= 31 },
];

export function AgeProfileSidebar({ profiles }: AgeProfileSidebarProps) {
  const mine = profiles.find((p) => p.is_me);
  if (!mine?.starter_ages.length) {
    return null;
  }

  const ages = mine.starter_ages.map((s) => s.age);
  const avg =
    mine.starter_avg_age ??
    ages.reduce((sum, age) => sum + age, 0) / ages.length;

  const bucketCounts = BUCKETS.map((bucket) => ({
    ...bucket,
    count: ages.filter(bucket.test).length,
  }));
  const total = ages.length || 1;

  return (
    <section className="bb-panel p-4">
      <h2 className="bb-panel-title">Age Profile</h2>
      <p className="mt-1 text-xs text-bb-muted">Starters · avg {avg.toFixed(1)}</p>
      <div className="mt-4 flex items-center justify-center">
        <div className="relative flex h-24 w-24 items-center justify-center rounded-full border-4 border-bb-border/60">
          <div className="text-center">
            <p className="text-xl font-bold text-white">{avg.toFixed(1)}</p>
            <p className="text-[10px] uppercase text-bb-muted">avg age</p>
          </div>
        </div>
      </div>
      <ul className="mt-4 space-y-1.5 text-xs">
        {bucketCounts.map((bucket) => (
          <li key={bucket.label} className="flex items-center justify-between">
            <span className="text-bb-muted">{bucket.label}</span>
            <span className="text-white">
              {Math.round((bucket.count / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

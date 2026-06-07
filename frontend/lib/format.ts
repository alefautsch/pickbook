export function formatPpg(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toFixed(1);
}

export function formatDecimal(value: number | null | undefined, digits = 2): string {
  if (value == null) return "—";
  return value.toFixed(digits);
}

export function formatTv(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(Math.round(value));
}

export function formatActv(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  const seconds = Math.floor((Date.now() - then) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

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

export function formatWorpPpg(value: number | null | undefined): string {
  if (value == null || value === 0) return "—";
  return value.toFixed(3);
}

export function formatActv(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}

export function formatActvGames(
  healthyGames: number | null | undefined,
  totalGames: number | null | undefined,
  availability: number | null | undefined,
): string {
  if (healthyGames != null && totalGames != null) {
    return `${healthyGames} / ${totalGames} games`;
  }
  if (availability != null) {
    const total = 17;
    return `${Math.round(availability * total)} / ${total} games`;
  }
  return "—";
}

export function formatHeight(inches: string | null | undefined): string {
  if (!inches) return "—";
  const n = Number(inches);
  if (Number.isNaN(n)) return inches;
  const feet = Math.floor(n / 12);
  const rem = n % 12;
  return `${feet}'${rem}"`;
}

export function formatExp(yearsExp: number | null | undefined, dynastyRookie?: boolean): string {
  if (dynastyRookie || yearsExp === 0) return "R";
  if (yearsExp == null) return "—";
  return String(yearsExp);
}

export function ordinal(n: number | null | undefined): string {
  if (n == null) return "—";
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  const mod10 = n % 10;
  if (mod10 === 1) return `${n}st`;
  if (mod10 === 2) return `${n}nd`;
  if (mod10 === 3) return `${n}rd`;
  return `${n}th`;
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

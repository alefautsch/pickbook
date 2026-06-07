const API_URL =
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

export type HealthResponse = {
  status: string;
  service: string;
};

export type DynastyComponents = {
  tv: number | null;
  worp: number | null;
  per_game: number | null;
  upside: number | null;
  age: number | null;
  trajectory: number | null;
};

export type PlayerLenses = {
  flex_rating: number | null;
  win_now_rating: number | null;
};

export type PlayerCard = {
  player_id: string;
  player_name: string | null;
  position: string | null;
  nfl_team: string | null;
  age: number | null;
  ovr: number | null;
  tier: string | null;
  dynasty_rookie: boolean;
  components: DynastyComponents;
  lenses: PlayerLenses;
  hppg: number | null;
  worp_ppg: number | null;
  availability: number | null;
  hppg_expected: boolean;
  trade_value: number | null;
  headshot_url: string;
  league_id: string;
  league_name: string;
  computed_at: string | null;
};

export type LeagueTile = {
  league_id: string;
  name: string;
  season: string;
  total_rosters: number;
  superflex: boolean;
  my_team_name: string | null;
  my_dynasty_rank: number | null;
  my_roster_ovr: number | null;
  my_starter_ppg: number | null;
  my_roster_ovr_delta: number | null;
  last_synced: string | null;
};

export type PlayerHistoryPoint = {
  computed_at: string;
  ovr: number | null;
  ovr_original: number | null;
  ovr_recomputed: number | null;
  formula_version: string;
  recomputed_formula_version: string | null;
  dynasty_score: number | null;
  hppg: number | null;
  worp_ppg: number | null;
  availability: number | null;
  trade_value: number | null;
  components: DynastyComponents;
};

export type PlayerHistorySeries = {
  player_id: string;
  league_id: string;
  current_formula_version: string;
  points: PlayerHistoryPoint[];
};

export type SyncStatusResponse = {
  last_success_at: string | null;
  last_failure_at: string | null;
  has_recent_failure: boolean;
  sync_cron: string | null;
  leagues: {
    league_id: string;
    league_name: string | null;
    last_synced: string | null;
    last_status: string | null;
    last_error: string | null;
  }[];
};

export type LeagueTeamSummary = {
  roster_id: string;
  team_name: string | null;
  owner: string | null;
  is_me: boolean;
  avg_dynasty_rating: number | null;
  starter_total_ppg: number | null;
  total_trade_value: number | null;
  dynasty_rank: number | null;
  starter_ppg_rank: number | null;
  tv_rank: number | null;
  win_rank: number | null;
};

export type LeagueDetail = {
  league_id: string;
  name: string;
  season: string;
  total_rosters: number;
  superflex: boolean;
  last_synced: string | null;
  teams: LeagueTeamSummary[];
};

export type RankingRow = {
  roster_id: string;
  team_name: string | null;
  owner: string | null;
  is_me: boolean;
  avg_dynasty_rating: number | null;
  starter_total_ppg: number | null;
  total_trade_value: number | null;
  win_now_score: number | null;
  dynasty_rank?: number;
  starter_ppg_rank?: number;
  tv_rank?: number;
  win_rank?: number;
};

export type LeagueRankings = {
  league_id: string;
  league_name: string;
  computed_at: string | null;
  by_dynasty: RankingRow[];
  by_starter_ppg: RankingRow[];
  by_tv: RankingRow[];
  by_win_now: RankingRow[];
};

export type LineupSlot = {
  slot: string;
  player: PlayerCard | null;
};

export type TeamDetail = {
  league_id: string;
  league_name: string;
  roster_id: string;
  team_name: string | null;
  owner: string | null;
  is_me: boolean;
  avg_dynasty_rating: number | null;
  starter_avg_dynasty_rating: number | null;
  starter_total_ppg: number | null;
  total_trade_value: number | null;
  dynasty_rank: number | null;
  starters: LineupSlot[];
  bench: PlayerCard[];
};

export type SyncLeagueResult = {
  league_id: string;
  league_name: string | null;
  status: string;
  errors: string[];
};

export type SyncAllResponse = {
  results: SyncLeagueResult[];
  total_duration_ms: number | null;
};

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API ${path} failed: ${response.status} ${text}`);
  }

  return response.json() as Promise<T>;
}

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

export function getLeagues(): Promise<LeagueTile[]> {
  return apiFetch<LeagueTile[]>("/leagues");
}

export function getLeague(leagueId: string): Promise<LeagueDetail> {
  return apiFetch<LeagueDetail>(`/leagues/${leagueId}`);
}

export function getLeagueRankings(leagueId: string): Promise<LeagueRankings> {
  return apiFetch<LeagueRankings>(`/leagues/${leagueId}/rankings`);
}

export function getTeam(leagueId: string, rosterId: string): Promise<TeamDetail> {
  return apiFetch<TeamDetail>(`/leagues/${leagueId}/teams/${rosterId}`);
}

export function getPlayer(playerId: string, leagueId: string): Promise<PlayerCard> {
  return apiFetch<PlayerCard>(`/players/${playerId}?league_id=${leagueId}`);
}

export function getPlayerHistory(
  playerId: string,
  leagueId: string,
  limit = 90,
): Promise<PlayerHistorySeries> {
  return apiFetch<PlayerHistorySeries>(
    `/players/${playerId}/history?league_id=${leagueId}&limit=${limit}`,
  );
}

export function getSyncStatus(): Promise<SyncStatusResponse> {
  return apiFetch<SyncStatusResponse>("/sync/status");
}

export function postSyncAll(): Promise<SyncAllResponse> {
  return apiFetch<SyncAllResponse>("/sync", { method: "POST" });
}

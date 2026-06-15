/** Browser uses same-origin proxy; server components hit the API directly. */
export function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    return "/api/blackbook";
  }
  return (
    process.env.API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://127.0.0.1:8000"
  );
}

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

export type PeakWindow = {
  years_to_peak: number | null;
  peak_window_end: number | null;
};

export type StatisticalPercentiles = {
  hppg_pct: number | null;
  worp_ppg_pct: number | null;
  tv_pct: number | null;
};

export type PlayerOutlook = {
  archetype: string | null;
  peak_window: PeakWindow;
  opportunity_score: number | null;
  percentiles: StatisticalPercentiles;
};

export type PlayerBio = {
  height: string | null;
  weight: string | null;
  college: string | null;
  years_exp: number | null;
};

export type PlayerRanks = {
  position_rank: number | null;
  overall_rank: number | null;
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
  bio: PlayerBio;
  ranks: PlayerRanks;
  hppg: number | null;
  worp_ppg: number | null;
  availability: number | null;
  healthy_games: number | null;
  total_games: number | null;
  hppg_expected: boolean;
  trade_value: number | null;
  season_worp: number | null;
  porp: number | null;
  injury_status: string | null;
  injury_body_part: string | null;
  projected_ppg: number | null;
  projection_source: string | null;
  outlook: PlayerOutlook;
  headshot_url: string;
  league_id: string;
  league_name: string;
  computed_at: string | null;
  expendability_score: number | null;
  depth_rank: number | null;
  trade_tag: "core" | "trade" | null;
  lineup_delta_ppg: number | null;
  tv_vs_production_gap: number | null;
  production_ppg: number | null;
};

export type LeagueTile = {
  league_id: string;
  name: string;
  season: string;
  total_rosters: number;
  superflex: boolean;
  my_roster_id: string | null;
  my_team_name: string | null;
  my_dynasty_rank: number | null;
  my_roster_ovr: number | null;
  my_starter_ppg: number | null;
  my_total_trade_value: number | null;
  my_draft_pick_value: number | null;
  my_starter_ppg_rank: number | null;
  my_tv_rank: number | null;
  my_contender_tier: string | null;
  my_contender_score: number | null;
  my_roster_ovr_delta: number | null;
  last_synced: string | null;
};

export type PlayerHistoryPoint = {
  computed_at: string;
  snapshot_date: string;
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

export type PlayerGameLogEntry = {
  season: number;
  week: number;
  team: string | null;
  opponent: string | null;
  points: number;
  healthy: boolean;
  included: boolean;
  offense_snaps: number | null;
  offense_pct: number | null;
  targets: number;
  receptions: number;
  receiving_yards: number;
  receiving_tds: number;
  carries: number;
  rushing_yards: number;
  rushing_tds: number;
  attempts: number;
  passing_yards: number;
  passing_tds: number;
  interceptions: number;
};

export type PlayerGameLog = {
  player_id: string;
  league_id: string;
  player_name: string | null;
  seasons: number[];
  entries: PlayerGameLogEntry[];
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
  draft_pick_value: number | null;
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
  draft_pick_value: number | null;
  win_now_score: number | null;
  dynasty_rank?: number;
  starter_ppg_rank?: number;
  tv_rank?: number;
  win_rank?: number;
  contender_tier?: string | null;
  contender_rank?: number | null;
  contender_score?: number | null;
};

export type ContenderInputs = {
  starter_avg_ovr: number | null;
  starter_total_ppg: number | null;
  age_depth_score: number | null;
  starter_ovr_norm: number | null;
  starter_ppg_norm: number | null;
  age_depth_norm: number | null;
};

export type ContenderTeam = {
  roster_id: string;
  team_name: string | null;
  is_me: boolean;
  tier: string;
  composite_score: number;
  contender_rank: number;
  inputs: ContenderInputs;
};

export type ContenderIndex = {
  weights: Record<string, number>;
  teams: ContenderTeam[];
};

export type PositionStrengthTeam = {
  roster_id: string;
  team_name: string | null;
  is_me: boolean;
  by_position: Record<string, number | null>;
};

export type PositionStrengthMap = {
  positions: string[];
  teams: PositionStrengthTeam[];
};

export type AgeProfile = {
  roster_id: string;
  team_name: string | null;
  is_me: boolean;
  starter_avg_age: number | null;
  bench_avg_age: number | null;
  league_avg_starter_age: number | null;
  age_delta: number | null;
  window: string | null;
  starter_ages: {
    player_id: string;
    name: string;
    pos: string;
    age: number;
    ovr: number | null;
    slot: string;
  }[];
};

export type TradeSurplusItem = {
  position: string;
  avg_ovr: number | null;
  league_rank: number;
  league_size: number;
};

export type TradeCounterparty = {
  position: string;
  direction: string;
  roster_id: string;
  team_name: string | null;
  my_rank: number;
  their_rank: number;
  their_avg_ovr: number | null;
};

export type TradeSurplus = {
  roster_id: string;
  team_name: string | null;
  surplus: TradeSurplusItem[];
  needs: TradeSurplusItem[];
  counterparties: TradeCounterparty[];
};

export type LeagueAnalysis = {
  league_id: string;
  league_name: string;
  computed_at: string | null;
  contender_index: ContenderIndex | null;
  position_strength: PositionStrengthMap | null;
  age_profiles: AgeProfile[];
  trade_surplus: TradeSurplus | null;
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

export type TeamTrait = {
  label: string;
  value: string;
};

export type DepthChartPlayer = {
  player_id: string;
  player_name: string | null;
  ovr: number | null;
  depth_rank: number;
};

export type DepthChartGroup = {
  position: string;
  players: DepthChartPlayer[];
};

export type InjuryWatchItem = {
  player_id: string;
  player_name: string | null;
  position: string | null;
  injury_status: string | null;
  injury_body_part: string | null;
};

export type DraftPickAsset = {
  season: string;
  round: number;
  original_roster_id: string;
  owner_roster_id: string;
  slot_tier: string;
  slot_in_round: number | null;
  trade_value: number | null;
  label: string | null;
  is_own_slot: boolean;
  trade_tag: "core" | "trade" | null;
};

export type TradeCandidate = {
  asset_type: "player" | "pick" | string;
  player_id: string | null;
  player_name: string | null;
  position: string | null;
  trade_value: number | null;
  expendability_score: number | null;
  depth_rank: number | null;
  trade_tag: "core" | "trade" | null;
  lineup_delta_ppg: number | null;
  season: string | null;
  round: number | null;
  original_roster_id: string | null;
  slot_tier: string | null;
  is_own_slot: boolean | null;
};

export type TeamDetail = {
  league_id: string;
  league_name: string;
  roster_id: string;
  team_name: string | null;
  owner: string | null;
  avatar_url: string | null;
  is_me: boolean;
  avg_dynasty_rating: number | null;
  starter_avg_dynasty_rating: number | null;
  avg_win_now_rating: number | null;
  starter_avg_win_now_rating: number | null;
  starter_total_ppg: number | null;
  total_trade_value: number | null;
  draft_pick_value: number | null;
  dynasty_rank: number | null;
  starter_ppg_rank: number | null;
  tv_rank: number | null;
  win_rank: number | null;
  contender_tier: string | null;
  contender_score: number | null;
  component_breakdown: DynastyComponents;
  traits: TeamTrait[];
  starters: LineupSlot[];
  bench: PlayerCard[];
  roster: PlayerCard[];
  depth_chart: DepthChartGroup[];
  injuries: InjuryWatchItem[];
  draft_picks: DraftPickAsset[];
  trade_candidates: TradeCandidate[];
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
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
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

export function getLeagueAnalysis(leagueId: string): Promise<LeagueAnalysis> {
  return apiFetch<LeagueAnalysis>(`/leagues/${leagueId}/analysis`);
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

export function getPlayerGameLog(
  playerId: string,
  leagueId: string,
): Promise<PlayerGameLog> {
  return apiFetch<PlayerGameLog>(
    `/players/${playerId}/game-log?league_id=${leagueId}`,
  );
}

let syncStatusClientCache: SyncStatusResponse | null = null;
let syncStatusClientInflight: Promise<SyncStatusResponse> | null = null;
let syncStatusClientLastFetch = 0;
const SYNC_STATUS_MIN_GAP_MS = 5_000;

export function invalidateSyncStatusCache(): void {
  syncStatusClientCache = null;
  syncStatusClientLastFetch = 0;
}

export function getSyncStatus(): Promise<SyncStatusResponse> {
  const isBrowser = typeof window !== "undefined";
  const headers = { "x-bb-sync-caller": isBrowser ? "browser" : "server" };

  if (isBrowser) {
    const now = Date.now();
    if (syncStatusClientInflight) {
      return syncStatusClientInflight;
    }
    if (
      syncStatusClientCache &&
      now - syncStatusClientLastFetch < SYNC_STATUS_MIN_GAP_MS
    ) {
      return Promise.resolve(syncStatusClientCache);
    }

    syncStatusClientInflight = apiFetch<SyncStatusResponse>("/sync/status", {
      headers,
    })
      .then((data) => {
        syncStatusClientCache = data;
        syncStatusClientLastFetch = Date.now();
        return data;
      })
      .finally(() => {
        syncStatusClientInflight = null;
      });
    return syncStatusClientInflight;
  }

  return apiFetch<SyncStatusResponse>("/sync/status", { headers });
}

export function postSyncAll(forceRefresh = false): Promise<SyncAllResponse> {
  const query = forceRefresh ? "?force_refresh=true" : "";
  return apiFetch<SyncAllResponse>(`/sync${query}`, { method: "POST" });
}

export type PortfolioLeagueHolding = {
  league_id: string;
  league_name: string;
  ovr: number | null;
  tier: string | null;
  team_name: string | null;
};

export type PortfolioPlayer = {
  player_id: string;
  player_name: string | null;
  position: string | null;
  nfl_team: string | null;
  age: number | null;
  headshot_url: string;
  league_count: number;
  leagues: PortfolioLeagueHolding[];
  exposure_flag: string | null;
};

export type PositionExposure = {
  position: string;
  holding_count: number;
  unique_players: number;
};

export type PortfolioSummary = {
  total_leagues: number;
  unique_players: number;
  multi_league_count: number;
  holdings: PortfolioPlayer[];
  by_position: PositionExposure[];
};

export type PlayerHoldings = {
  player_id: string;
  player_name: string | null;
  position: string | null;
  leagues: PortfolioLeagueHolding[];
};

export type PlayerSearchLeagueMatch = {
  league_id: string;
  league_name: string;
  ovr: number | null;
  tier: string | null;
  is_owned: boolean;
};

export type PlayerSearchHit = {
  player_id: string;
  player_name: string | null;
  position: string | null;
  nfl_team: string | null;
  headshot_url: string;
  leagues: PlayerSearchLeagueMatch[];
};

export type PlayerSearchResults = {
  query: string;
  hits: PlayerSearchHit[];
};

export type LeaguePlayerRow = {
  player_id: string;
  player_name: string | null;
  position: string | null;
  nfl_team: string | null;
  age: number | null;
  ovr: number | null;
  tier: string | null;
  dynasty_rookie: boolean;
  hppg: number | null;
  projected_ppg: number | null;
  worp_ppg: number | null;
  trade_value: number | null;
  hppg_expected: boolean;
  availability: number | null;
  healthy_games: number | null;
  total_games: number | null;
  season_worp: number | null;
  flex_rating: number | null;
  porp: number | null;
  projection_source: string | null;
  headshot_url: string;
  is_free_agent: boolean;
  roster_team_name: string | null;
  roster_id: string | null;
};

export type LeaguePlayerDirectory = {
  league_id: string;
  league_name: string;
  total_players: number;
  computed_at: string | null;
  players: LeaguePlayerRow[];
};

export function getLeaguePlayers(leagueId: string): Promise<LeaguePlayerDirectory> {
  return apiFetch<LeaguePlayerDirectory>(`/leagues/${leagueId}/players`);
}

export type FreeAgentRow = {
  player_id: string;
  player_name: string | null;
  position: string | null;
  nfl_team: string | null;
  age: number | null;
  ovr: number | null;
  tier: string | null;
  dynasty_rookie: boolean;
  hppg: number | null;
  projected_ppg: number | null;
  worp_ppg: number | null;
  trade_value: number | null;
  hppg_expected: boolean;
  headshot_url: string;
  league_id: string;
  league_name: string;
  computed_at: string | null;
};

export type FreeAgentBoard = {
  league_id: string;
  league_name: string;
  superflex: boolean;
  position_filter: string | null;
  fa_pool_size: number;
  total_available: number;
  players: FreeAgentRow[];
};

export function getPortfolio(): Promise<PortfolioSummary> {
  return apiFetch<PortfolioSummary>("/portfolio");
}

export function getPlayerHoldings(playerId: string): Promise<PlayerHoldings> {
  return apiFetch<PlayerHoldings>(`/players/${playerId}/holdings`);
}

export function searchPlayers(q: string, limit = 25): Promise<PlayerSearchResults> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  return apiFetch<PlayerSearchResults>(`/players/search?${params}`);
}

export function getFreeAgents(
  leagueId: string,
  position?: string,
): Promise<FreeAgentBoard> {
  const params = position ? `?position=${encodeURIComponent(position)}` : "";
  return apiFetch<FreeAgentBoard>(`/leagues/${leagueId}/free-agents${params}`);
}

export type UserSettings = {
  sleeper_username: string;
  dynasty_weights: Record<string, number>;
  dynasty_rating_curve: Record<string, number>;
  trade_value_blend: Record<string, number>;
  worp_blend: Record<string, unknown>;
  ktc_enabled: boolean;
  war_csv: string;
  trade_weight: number;
  worp_weight: number;
  season: string;
};

export function getSettings(): Promise<UserSettings> {
  return apiFetch<UserSettings>("/settings");
}

export function putSettings(payload: Partial<UserSettings>): Promise<UserSettings> {
  return apiFetch<UserSettings>("/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export type RookieDraftOnClock = {
  roster_id: string | null;
  team_name: string | null;
  draft_slot: number | null;
  is_me: boolean;
};

export type RookieDraftNextPickInfo = {
  pick_no: number | null;
  round: number | null;
  slot: number | null;
  is_my_pick: boolean;
  picks_until_mine: number | null;
  total_picks: number | null;
  back_to_back: boolean;
  consecutive_picks: number[];
};

export type StarterNeeds = {
  QB: number;
  RB: number;
  WR: number;
  TE: number;
  FLEX: number;
};

export type RookieBoardRow = {
  bpa_rank: number;
  ovr_rank?: number | null;
  player_id: string;
  player_name: string | null;
  position: string | null;
  nfl_team: string | null;
  age: number | null;
  ovr: number | null;
  tier: string | null;
  dynasty_rookie: boolean;
  trade_value: number | null;
  projected_ppg: number | null;
  hppg: number | null;
  worp_ppg: number | null;
  hppg_expected: boolean;
  flex_rating: number | null;
  adp_pick: number | null;
  adp_delta: number | null;
  adp_class: string | null;
  bpa_score: number | null;
  vor: number | null;
  headshot_url: string;
};

export type RookieDraftTimelineRow = {
  pick_no: number;
  round: number | null;
  team_name: string | null;
  player_id: string | null;
  player_name: string | null;
  position: string | null;
  ovr: number | null;
  dynasty_rookie: boolean;
  status: string;
  is_me: boolean;
};

export type RookieDraftView = {
  league_id: string;
  league_name: string;
  draft_id: string;
  draft_status: string | null;
  picks_made: number;
  total_picks: number;
  next_pick_no: number | null;
  on_clock: RookieDraftOnClock;
  my_roster_id: string | null;
  drafting_roster_id: string | null;
  drafting_team_name: string | null;
  is_my_pick: boolean;
  next_pick_info: RookieDraftNextPickInfo;
  starter_needs: StarterNeeds;
  board: RookieBoardRow[];
  bpa_top: RookieBoardRow[];
  timeline: RookieDraftTimelineRow[];
  strategy_notes: string[];
  adp_source: string | null;
  fetched_at: string;
  poll_seconds: number;
};

export function getRookieDraft(
  leagueId: string,
  opts?: { draftId?: string; rosterId?: string },
): Promise<RookieDraftView> {
  const params = new URLSearchParams();
  if (opts?.draftId) params.set("draft_id", opts.draftId);
  if (opts?.rosterId) params.set("roster_id", opts.rosterId);
  const qs = params.toString();
  return apiFetch<RookieDraftView>(
    `/leagues/${leagueId}/rookie-draft${qs ? `?${qs}` : ""}`,
  );
}

export type AdvisorModel = {
  id: string;
  label: string;
  provider: string;
  available: boolean;
  supports_tools: boolean;
};

export type AdvisorPrompt = {
  id: string;
  label: string;
  question: string;
};

export type AdvisorStatus = {
  configured: boolean;
  default_model: string;
  models: AdvisorModel[];
  prompts: AdvisorPrompt[];
};

export type AdvisorMessage = {
  role: string;
  content: string;
};

export type AdvisorPageContext = {
  page_type: string;
  path?: string | null;
  roster_id?: string | null;
  player_id?: string | null;
  player_name?: string | null;
  summary?: string | null;
};

export type AdvisorChatRequest = {
  league_id: string;
  question?: string;
  prompt_id?: string | null;
  model_id?: string;
  messages?: AdvisorMessage[];
  focused_roster_id?: string | null;
  page_context?: AdvisorPageContext | null;
};

export function getAdvisorStatus(): Promise<AdvisorStatus> {
  return apiFetch<AdvisorStatus>("/advisor/status");
}

function advisorNetworkError(cause?: unknown): Error {
  const detail = cause instanceof Error ? cause.message : String(cause ?? "");
  return new Error(
    `Advisor request failed${detail ? `: ${detail}` : ""}. ` +
      "Check that the API is running on :8000 (just bb-api).",
  );
}

export async function streamAdvisorChat(
  body: AdvisorChatRequest,
  onChunk: (text: string) => void,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}/advisor/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        league_id: body.league_id,
        question: body.question ?? "",
        prompt_id: body.prompt_id ?? null,
        model_id: body.model_id ?? "claude-sonnet-4-6",
        messages: body.messages ?? [],
        focused_roster_id: body.focused_roster_id ?? null,
        page_context: body.page_context ?? null,
      }),
      cache: "no-store",
    });
  } catch (err) {
    throw advisorNetworkError(err);
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Advisor chat failed: ${response.status} ${text}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Advisor chat failed: no response body");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6).trim();
      if (data === "[DONE]") return;
      try {
        const parsed = JSON.parse(data) as { text?: string; error?: string };
        if (parsed.error) throw new Error(parsed.error);
        if (parsed.text) onChunk(parsed.text);
      } catch (err) {
        if (err instanceof SyntaxError) continue;
        throw err;
      }
    }
  }
}

export type TradePickRef = {
  season: string;
  round: number;
  original_roster_id: string;
};

export type TradeSideInput = {
  players: string[];
  picks: TradePickRef[];
};

export type TradeEvaluateRequest = {
  side_a_roster_id: string;
  side_b_roster_id: string;
  side_a_gives: TradeSideInput;
  side_b_gives: TradeSideInput;
};

export type TradeAssetPlayer = {
  player_id: string;
  name?: string | null;
  position?: string | null;
  ovr?: number | null;
  tv?: number | null;
  hppg?: number | null;
  injury?: string | null;
};

export type TradeAssetPick = {
  season: string;
  round: number;
  original_roster_id: string;
  owner_roster_id?: string | null;
  slot_tier?: string | null;
  trade_value?: number | null;
  label?: string | null;
};

export type TradeResolvedSide = {
  players: TradeAssetPlayer[];
  picks: TradeAssetPick[];
};

export type TradeEvaluation = {
  give_total_tv: number;
  receive_total_tv: number;
  give_value_adjustment: number;
  receive_value_adjustment: number;
  give_adjusted_tv: number;
  receive_adjusted_tv: number;
  give_effective_tv: number;
  receive_effective_tv: number;
  consolidation_tax_tv: number;
  consolidation_premium_pct: number;
  give_consolidating: boolean;
  receive_consolidating: boolean;
  net_delta_tv: number;
  net_delta_adjusted_tv: number;
  net_delta_effective_tv: number;
  net_delta_adjusted_total_tv: number;
  net_delta_pct: number;
  net_delta_adjusted_pct: number;
  fairness_band: string;
  within_band: boolean;
  fairness: "fair" | "favors_you" | "favors_counterparty";
  positional_notes: string[];
  missing_assets: string[];
  give: TradeResolvedSide;
  receive: TradeResolvedSide;
  tv_fairness_grade: string;
  favors_roster_id?: string | null;
  lineup?: TradeLineupImpact | null;
};

export type TradeLineupStarterSlot = {
  slot: string;
  player_id?: string | null;
  name?: string | null;
  position?: string | null;
  ppg?: number | null;
  ovr?: number | null;
  is_incoming?: boolean;
  is_changed?: boolean;
};

export type TradeLineupSide = {
  before?: number | null;
  after?: number | null;
  delta?: number | null;
  starters?: TradeLineupStarterSlot[];
  incoming_picks?: TradeAssetPick[];
};

export type TradeLineupImpact = {
  side_a: TradeLineupSide;
  side_b: TradeLineupSide;
};

export type TradeEvaluateResponse = {
  side_a_roster_id: string;
  side_b_roster_id: string;
  side_a_team_name?: string | null;
  side_b_team_name?: string | null;
  evaluation: TradeEvaluation;
  rookie_draft_context?: TradeRookieDraftContext | null;
};

export type TradeRookieProjection = {
  name?: string | null;
  pos?: string | null;
  ovr?: number | null;
  adp_pick?: number | null;
  trade_value?: number | null;
};

export type TradePickRookieContext = {
  label: string;
  pick_no?: number | null;
  given_by: string;
  acquired_by: string;
  projected_rookie?: TradeRookieProjection | null;
  nearby_rookies?: TradeRookieProjection[];
  likely_range?: TradeRookieProjection[];
  consensus_note?: string | null;
  fills_need_for_acquirer?: boolean | null;
  tep_note?: string | null;
};

export type TradeRookieDraftContext = {
  season: string;
  te_premium?: number;
  picks_in_trade: TradePickRookieContext[];
  board_top?: Record<string, unknown>[];
};

export type TradeFixSuggestion = {
  headline?: string | null;
  reasoning?: string | null;
  adjustments: string[];
  both_sides_likely_accept?: boolean | null;
  skipped?: boolean;
  error?: string | null;
};

export type TradeSideValidation = {
  roster_id: string;
  team_name?: string | null;
  accept_likelihood?: "low" | "medium" | "high" | null;
  fairness_view?: "favors_them" | "fair" | "favors_you" | null;
  fairness_label?: string | null;
  would_improve_roster?: boolean | null;
  reasoning?: string | null;
  blockers: string[];
  suggested_tweak?: string | null;
  grade?: string | null;
  skipped?: boolean;
  error?: string | null;
};

export type TradeValidationResult = {
  evaluation: TradeEvaluation;
  side_a: TradeSideValidation;
  side_b: TradeSideValidation;
  overall_grade: string;
  summary?: string | null;
  rookie_draft_context?: TradeRookieDraftContext | null;
  trade_fix?: TradeFixSuggestion | null;
};

export function evaluateTrade(
  leagueId: string,
  body: TradeEvaluateRequest,
): Promise<TradeEvaluateResponse> {
  return apiFetch<TradeEvaluateResponse>(`/leagues/${leagueId}/trade/evaluate`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function validateTrade(
  leagueId: string,
  body: TradeEvaluateRequest,
): Promise<TradeValidationResult> {
  return apiFetch<TradeValidationResult>(`/leagues/${leagueId}/trade/validate`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * API client for the Chess Analyzer backend.
 *
 * All requests go through Next.js rewrites → FastAPI backend.
 * JWT auth tokens are automatically fetched from the NextAuth token endpoint
 * and attached to every request.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/backend";

// ─── Token cache ────────────────────────────────────────

let cachedToken: string | null = null;
let tokenFetchedAt = 0;
const TOKEN_TTL = 4 * 60 * 1000; // refresh every 4 minutes

async function getToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;

  const now = Date.now();
  if (cachedToken && now - tokenFetchedAt < TOKEN_TTL) {
    return cachedToken;
  }

  try {
    const res = await fetch("/api/auth/token", { credentials: "include" });
    if (res.ok) {
      const data = await res.json();
      cachedToken = data.token ?? null;
      tokenFetchedAt = now;
      return cachedToken;
    }
  } catch {
    // Not authenticated
  }

  cachedToken = null;
  return null;
}

/** Clear the cached token (call on sign-out). */
export function clearTokenCache() {
  cachedToken = null;
  tokenFetchedAt = 0;
}

// ─── Core fetch wrapper ─────────────────────────────────

async function fetchAPI<T = unknown>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const token = await getToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new APIError(res.status, body.detail ?? res.statusText);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export class APIError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = "APIError";
  }
}

// ─── Types ──────────────────────────────────────────────

export interface GameSummary {
  id: number;
  platform: string;
  platform_game_id: string | null;
  date: string;
  color: "white" | "black";
  result: "win" | "loss" | "draw";
  white_player: string | null;
  black_player: string | null;
  opening_name: string | null;
  eco_code: string | null;
  time_control: string | null;
  player_elo: number | null;
  opponent_elo: number | null;
  moves_count: number | null;
  has_analysis: boolean;
}

export interface GamesListResponse {
  games: GameSummary[];
  total: number;
  page: number;
  per_page: number;
}

export interface GameDetail extends GameSummary {
  white_player: string | null;
  black_player: string | null;
  moves_pgn: string;
  analysis?: {
    overall_cpl: number;
    phase_opening_cpl: number | null;
    phase_middlegame_cpl: number | null;
    phase_endgame_cpl: number | null;
    blunders: number;
    mistakes: number;
    inaccuracies: number;
    best_moves: number;
    great_moves: number;
    brilliant_moves: number;
    missed_wins: number;
    accuracy: number | null;
    depth: number;
  };
}

export interface MoveEval {
  move_number: number;
  color: string;
  san: string;
  cp_loss: number;
  phase: string | null;
  move_quality: string | null;
  blunder_subtype: string | null;
  eval_before: number | null;
  eval_after: number | null;
  fen_before: string | null;
  best_move_san: string | null;
  best_move_uci: string | null;
  win_prob_before: number | null;
  win_prob_after: number | null;
  accuracy: number | null;
}

export interface AnalysisResult {
  game_id: number;
  summary: GameDetail["analysis"];
  moves: MoveEval[];
}

export interface JobStatus {
  job_id: number;
  status: "pending" | "processing" | "completed" | "failed";
  total_games: number;
  games_completed: number;
  error: string | null;
}

export interface InsightsOverview {
  total_games: number;
  overall_cpl: number | null;
  win_rate: number | null;
  blunder_rate: number | null;
  recent_cpl: number | null;
  trend: "improving" | "declining" | "stable" | null;
  current_elo: number | null;
  elo_trend: number | null;
  phase_accuracy: {
    opening: number | null;
    middlegame: number | null;
    endgame: number | null;
  };
  puzzle_count: number;
}

export interface PhaseBreakdown {
  opening: number | null;
  middlegame: number | null;
  endgame: number | null;
}

export interface Weakness {
  area: string;
  severity: "high" | "medium" | "low";
  message: string;
  cpl?: number;
  count?: number;
  action: string;
}

export interface SkillAxis {
  axis: string;
  score: number;
}

export interface SkillProfile {
  has_data: boolean;
  message?: string;
  analyzed_games?: number;
  axes?: SkillAxis[];
  overall_score?: number;
}

export interface ProgressDataPoint {
  period: string;
  games: number;
  avg_cpl: number | null;
  accuracy: number | null;
  blunder_rate: number | null;
}

export interface ProgressResponse {
  months: number;
  data: ProgressDataPoint[];
}

export interface PuzzleHistoryAttempt {
  id: number;
  puzzle_id: number;
  correct: boolean;
  time_taken: number | null;
  attempted_at: string | null;
  puzzle: {
    fen: string;
    difficulty: string;
    phase: string;
    puzzle_type: string;
  } | null;
}

export interface PuzzleHistoryResponse {
  total: number;
  offset: number;
  limit: number;
  stats: {
    total_attempts: number;
    correct_count: number;
    accuracy: number;
    avg_time: number | null;
    best_streak: number;
  };
  attempts: PuzzleHistoryAttempt[];
}

export interface DailyWarmupPuzzle {
  id: number;
  fen: string;
  side_to_move: string;
  best_move_san: string;
  best_move_uci: string | null;
  eval_loss_cp: number;
  phase: string;
  puzzle_type: string;
  difficulty: string;
  themes: string[];
  source: "review" | "weakness" | "random";
}

export interface DailyWarmupResponse {
  completed_today: boolean;
  total_puzzles: number;
  puzzles: DailyWarmupPuzzle[];
}

export interface AdvantagePosition {
  id: number;
  game_id: number;
  fen: string;
  side_to_move: string;
  best_move_san: string;
  best_move_uci: string | null;
  played_move_san: string;
  cp_loss: number;
  eval_before: number;
  phase: string;
  move_number: number;
  advantage_cp: number;
}

export interface AdvantagePositionsResponse {
  positions: AdvantagePosition[];
  total: number;
}

export interface IntuitionOption {
  move_number: number;
  san: string;
  fen_before: string;
  is_blunder: boolean;
  cp_loss: number;
  phase: string;
}

export interface IntuitionChallenge {
  game_id: number;
  blunder_move_number: number;
  color: string;
  options: IntuitionOption[];
}

export interface IntuitionChallengeResponse {
  challenges: IntuitionChallenge[];
  total: number;
}

export interface StudyPlanActivity {
  type: string;
  title: string;
  description: string;
  duration: number;
}

export interface StudyPlanDay {
  day: string;
  date: string;
  focus: string;
  theme: string;
  is_past: boolean;
  is_today: boolean;
  total_duration_min: number;
  activities: StudyPlanActivity[];
}

export interface StudyPlanResponse {
  week_start: string;
  days: StudyPlanDay[];
  message?: string;
  stats?: {
    opening_cpl: number;
    middlegame_cpl: number;
    endgame_cpl: number;
    blunder_rate: number;
    total_puzzles: number;
  };
}

export interface TimeAnalysis {
  time_pressure_moves: number;
  time_pressure_blunders: number;
  normal_moves: number;
  normal_blunders: number;
  avg_move_time: number | null;
  time_controls: TimeControlStat[];
}

export interface TimeControlStat {
  time_control: string;
  games: number;
  avg_cpl: number | null;
  win_rate: number;
}

export interface StreakData {
  current_streak: number;
  current_streak_type: "win" | "loss" | "draw" | null;
  saved_streaks: { type: string; current: number; best: number }[];
}

// ─── Analysis progress events (SSE) ────────────────────

export type AnalysisProgressEvent =
  | { type: "start"; total: number }
  | {
      type: "progress";
      completed: number;
      total: number;
      game_id: number;
      game_label: string;
      overall_cpl: number;
      blunders: number;
      mistakes: number;
    }
  | { type: "game_error"; game_id: number; message: string }
  | { type: "complete"; analyzed: number }
  | { type: "error"; message: string };

export interface RecentGame {
  id: number;
  date: string | null;
  color: "white" | "black";
  result: "win" | "loss" | "draw";
  opening_name: string | null;
  platform: string;
  player_elo: number | null;
  opponent_elo: number | null;
  time_control: string | null;
  has_analysis: boolean;
  overall_cpl: number | null;
}

export interface OpeningStat {
  opening_name: string;
  eco_code: string;
  color: string;
  games_played: number;
  win_rate: number;
  average_cpl: number | null;
  early_deviations?: number;
}

export interface StyleTrait {
  trait: string;
  icon: string;
  description: string;
}

export interface AdvancedAnalytics {
  has_data: boolean;
  message?: string;
  analyzed_games?: number;
  total_games?: number;
  primary_style?: StyleTrait;
  secondary_styles?: StyleTrait[];
  comeback_wins?: number;
  collapses?: number;
  strengths?: { area: string; detail: string }[];
  weaknesses?: { area: string; detail: string }[];
  recommendations?: { priority: string; category: string; message: string }[];
  best_openings?: { name: string; games: number; avg_cpl: number | null; win_rate: number }[];
  worst_openings?: { name: string; games: number; avg_cpl: number | null; win_rate: number }[];
  best_pieces?: PiecePerformance[];
  worst_pieces?: PiecePerformance[];
  all_pieces?: PiecePerformance[];
  stats?: {
    avg_cpl: number;
    blunder_rate: number;
    mistake_rate: number;
    best_move_rate: number;
    win_rate: number;
    draw_rate: number;
    upsets: number;
    best_phase: string;
    worst_phase: string;
  };
}

export interface PiecePerformance {
  piece: string;
  name: string;
  icon: string;
  avg_cpl: number;
  total_moves: number;
  best_rate: number;
  blunder_rate: number;
}

export interface PuzzleItem {
  id: number;
  puzzle_key: string;
  fen: string;
  side_to_move?: string;
  best_move_san: string;
  best_move_uci?: string;
  eval_loss_cp: number;
  phase?: string;
  puzzle_type?: string;
  difficulty: string;
  explanation?: string | null;
  themes: string[];
}

export interface UserProfile {
  id: string;
  email: string;
  name: string | null;
  lichess_username: string | null;
  chesscom_username: string | null;
  subscription_tier: "free" | "pro";
  ai_coach_reviews_used: number;
}

// ─── Games ──────────────────────────────────────────────

export const gamesAPI = {
  list(params?: {
    page?: number;
    per_page?: number;
    result?: string;
    opening?: string;
    platform?: string;
  }): Promise<GamesListResponse> {
    const q = new URLSearchParams();
    if (params?.page) q.set("page", String(params.page));
    if (params?.per_page) q.set("per_page", String(params.per_page));
    if (params?.result) q.set("result", params.result);
    if (params?.opening) q.set("opening", params.opening);
    if (params?.platform) q.set("platform", params.platform);
    return fetchAPI<GamesListResponse>(`/games?${q}`);
  },

  get(id: number): Promise<GameDetail> {
    return fetchAPI<GameDetail>(`/games/${id}`);
  },

  fetchLichess(
    username: string,
    maxGames = 50
  ): Promise<{ imported: number; username: string }> {
    return fetchAPI("/games/fetch-lichess", {
      method: "POST",
      body: JSON.stringify({ username, max_games: maxGames }),
    });
  },

  fetchChesscom(
    username: string,
    maxGames = 50
  ): Promise<{ imported: number; username: string }> {
    return fetchAPI("/games/fetch-chesscom", {
      method: "POST",
      body: JSON.stringify({ username, max_games: maxGames }),
    });
  },

  importPGN(
    pgnText: string,
    platform = "chess.com"
  ): Promise<{ imported: number; platform: string }> {
    return fetchAPI("/games/import-pgn", {
      method: "POST",
      body: JSON.stringify({ pgn_text: pgnText, platform }),
    });
  },
};

// ─── Analysis ───────────────────────────────────────────

export const analysisAPI = {
  start(gameIds?: number[], depth = 12): Promise<JobStatus> {
    return fetchAPI<JobStatus>("/analysis/start", {
      method: "POST",
      body: JSON.stringify({ game_ids: gameIds, depth }),
    });
  },

  /** Run analysis synchronously via SSE — returns progress events. */
  async runAnalysis(
    params: { game_ids?: number[]; depth?: number },
    onProgress: (event: AnalysisProgressEvent) => void
  ): Promise<void> {
    const url = `${API_BASE}/analysis/run`;
    const token = await getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(params),
      credentials: "include",
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail ?? "Analysis failed");
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("No response stream");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const event: AnalysisProgressEvent = JSON.parse(line.slice(6));
            onProgress(event);
          } catch {
            // skip malformed
          }
        }
      }
    }
  },

  jobStatus(jobId: number): Promise<JobStatus> {
    return fetchAPI<JobStatus>(`/analysis/job/${jobId}`);
  },

  getGameAnalysis(gameId: number): Promise<AnalysisResult> {
    return fetchAPI<AnalysisResult>(`/analysis/game/${gameId}`);
  },
};

// ─── Puzzles ────────────────────────────────────────────

export const puzzlesAPI = {
  list(params?: {
    difficulty?: string;
    phase?: string;
    puzzle_type?: string;
    limit?: number;
    game_id?: number;
  }): Promise<PuzzleItem[]> {
    const q = new URLSearchParams();
    if (params?.difficulty) q.set("difficulty", params.difficulty);
    if (params?.phase) q.set("phase", params.phase);
    if (params?.puzzle_type) q.set("puzzle_type", params.puzzle_type);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.game_id) q.set("game_id", String(params.game_id));
    return fetchAPI<PuzzleItem[]>(`/puzzles?${q}`);
  },

  global(params?: {
    difficulty?: string;
    phase?: string;
    puzzle_type?: string;
    limit?: number;
  }): Promise<PuzzleItem[]> {
    const q = new URLSearchParams();
    if (params?.difficulty) q.set("difficulty", params.difficulty);
    if (params?.phase) q.set("phase", params.phase);
    if (params?.puzzle_type) q.set("puzzle_type", params.puzzle_type);
    if (params?.limit) q.set("limit", String(params.limit));
    return fetchAPI<PuzzleItem[]>(`/puzzles/global?${q}`);
  },

  reviewQueue(limit = 10): Promise<PuzzleItem[]> {
    return fetchAPI<PuzzleItem[]>(`/puzzles/review-queue?limit=${limit}`);
  },

  attempt(
    puzzleId: number,
    correct: boolean,
    timeTaken?: number
  ): Promise<{ streak: number; next_review_at: string }> {
    return fetchAPI(`/puzzles/${puzzleId}/attempt`, {
      method: "POST",
      body: JSON.stringify({ correct, time_taken: timeTaken }),
    });
  },

  history(params?: { limit?: number; offset?: number }): Promise<PuzzleHistoryResponse> {
    const q = new URLSearchParams();
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.offset) q.set("offset", String(params.offset));
    return fetchAPI<PuzzleHistoryResponse>(`/puzzles/history?${q}`);
  },

  dailyWarmup(): Promise<DailyWarmupResponse> {
    return fetchAPI<DailyWarmupResponse>("/puzzles/daily-warmup");
  },

  completeDailyWarmup(): Promise<{ status: string; completed_at: string }> {
    return fetchAPI("/puzzles/daily-warmup/complete", { method: "POST" });
  },

  advantagePositions(limit = 10): Promise<AdvantagePositionsResponse> {
    return fetchAPI<AdvantagePositionsResponse>(`/puzzles/advantage-positions?limit=${limit}`);
  },

  intuitionChallenge(count = 5): Promise<IntuitionChallengeResponse> {
    return fetchAPI<IntuitionChallengeResponse>(`/puzzles/intuition-challenge?count=${count}`);
  },
};

// ─── Insights ───────────────────────────────────────────

export const insightsAPI = {
  overview(): Promise<InsightsOverview> {
    return fetchAPI<InsightsOverview>("/insights/overview");
  },

  phaseBreakdown(): Promise<PhaseBreakdown> {
    return fetchAPI<PhaseBreakdown>("/insights/phase-breakdown");
  },

  openings(
    color?: string
  ): Promise<
    {
      opening_name: string;
      eco_code: string;
      color: string;
      games_played: number;
      win_rate: number;
      average_cpl: number | null;
    }[]
  > {
    const q = color ? `?color=${color}` : "";
    return fetchAPI(`/insights/openings${q}`);
  },

  weaknesses(): Promise<{ weaknesses: Weakness[]; message?: string }> {
    return fetchAPI("/insights/weaknesses");
  },

  timeAnalysis(): Promise<TimeAnalysis> {
    return fetchAPI<TimeAnalysis>("/insights/time-analysis");
  },

  streaks(): Promise<StreakData> {
    return fetchAPI<StreakData>("/insights/streaks");
  },

  recentGames(limit = 5): Promise<RecentGame[]> {
    return fetchAPI<RecentGame[]>(`/insights/recent-games?limit=${limit}`);
  },

  advancedAnalytics(timeControl?: string): Promise<AdvancedAnalytics> {
    const q = timeControl && timeControl !== "all" ? `?time_control=${timeControl}` : "";
    return fetchAPI<AdvancedAnalytics>(`/insights/advanced-analytics${q}`);
  },

  skillProfile(): Promise<SkillProfile> {
    return fetchAPI<SkillProfile>("/insights/skill-profile");
  },

  progress(months?: number): Promise<ProgressResponse> {
    const q = months ? `?months=${months}` : "";
    return fetchAPI<ProgressResponse>(`/insights/progress${q}`);
  },

  studyPlan(): Promise<StudyPlanResponse> {
    return fetchAPI<StudyPlanResponse>("/insights/study-plan");
  },
};

// ─── Users ──────────────────────────────────────────────

export const usersAPI = {
  me(): Promise<UserProfile> {
    return fetchAPI<UserProfile>("/users/me");
  },

  updateProfile(data: {
    lichess_username?: string;
    chesscom_username?: string;
    name?: string;
  }): Promise<UserProfile> {
    return fetchAPI<UserProfile>("/users/me", {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },
};

// ─── AI Coach ───────────────────────────────────────────

export interface CoachReview {
  game_id: number;
  review: string;
  sections: { title: string; content: string }[];
  reviews_used: number;
  reviews_limit: number | null;
}

export interface CoachQuota {
  reviews_used: number;
  reviews_limit: number | null;
  reviews_remaining: number | null;
  is_pro: boolean;
}

export const coachAPI = {
  review(gameId: number, focus?: string): Promise<CoachReview> {
    return fetchAPI<CoachReview>("/coach/review", {
      method: "POST",
      body: JSON.stringify({ game_id: gameId, focus }),
    });
  },

  quota(): Promise<CoachQuota> {
    return fetchAPI<CoachQuota>("/coach/quota");
  },
};

// ─── AI Move Explanations ───────────────────────────────

export interface MoveExplanation {
  explanation: string;
  concepts: string[];
  severity: "good" | "neutral" | "warning" | "critical";
  alternative: string | null;
  explanations_used: number;
  explanations_limit: number | null;
}

export const explanationsAPI = {
  explainMove(params: {
    fen: string;
    san: string;
    best_move_san?: string;
    eval_before?: number;
    eval_after?: number;
    cp_loss?: number;
    phase?: string;
    move_quality?: string;
    move_number?: number;
    color?: string;
    game_id?: number;
  }): Promise<MoveExplanation> {
    return fetchAPI<MoveExplanation>("/explanations/explain-move", {
      method: "POST",
      body: JSON.stringify(params),
    });
  },
};

// ─── Opening Explorer ───────────────────────────────────

export interface ExplorerMove {
  san: string;
  uci: string;
  white: number;
  draws: number;
  black: number;
  total: number;
  win_rate: number;
  average_rating: number | null;
}

export interface ExplorerResponse {
  fen: string;
  source: string;
  total_games: number;
  white_wins: number;
  draws: number;
  black_wins: number;
  moves: ExplorerMove[];
  opening: string | null;
  eco: string | null;
  top_games: {
    id: string;
    white: string;
    white_rating: number | null;
    black: string;
    black_rating: number | null;
    winner: string | null;
    year: number | null;
  }[];
}

export interface PersonalOpening {
  opening_name: string;
  eco_code: string | null;
  color: string;
  games_played: number;
  games_won: number;
  games_drawn: number;
  games_lost: number;
  win_rate: number;
  average_cpl: number | null;
}

export interface PersonalRepertoireResponse {
  openings: PersonalOpening[];
  total_openings: number;
  most_played: string | null;
  best_opening: string | null;
  worst_opening: string | null;
}

export const openingsAPI = {
  explore(params: {
    fen?: string;
    source?: string;
    ratings?: string;
    speeds?: string;
    player?: string;
    color?: string;
  }): Promise<ExplorerResponse> {
    const searchParams = new URLSearchParams();
    if (params.fen) searchParams.set("fen", params.fen);
    if (params.source) searchParams.set("source", params.source);
    if (params.ratings) searchParams.set("ratings", params.ratings);
    if (params.speeds) searchParams.set("speeds", params.speeds);
    if (params.player) searchParams.set("player", params.player);
    if (params.color) searchParams.set("color", params.color);
    return fetchAPI<ExplorerResponse>(`/openings/explore?${searchParams}`);
  },

  personal(params?: {
    color?: string;
    min_games?: number;
    sort_by?: string;
  }): Promise<PersonalRepertoireResponse> {
    const searchParams = new URLSearchParams();
    if (params?.color) searchParams.set("color", params.color);
    if (params?.min_games) searchParams.set("min_games", String(params.min_games));
    if (params?.sort_by) searchParams.set("sort_by", params.sort_by);
    return fetchAPI<PersonalRepertoireResponse>(`/openings/personal?${searchParams}`);
  },

  tree(params?: { color?: string; max_depth?: number }): Promise<{
    tree: unknown[];
    total_games: number;
    color: string;
  }> {
    const searchParams = new URLSearchParams();
    if (params?.color) searchParams.set("color", params.color);
    if (params?.max_depth) searchParams.set("max_depth", String(params.max_depth));
    return fetchAPI(`/openings/tree?${searchParams}`);
  },
};

// ─── Cross-Game Patterns ────────────────────────────────

export interface RecurringPattern {
  pattern_type: string;
  description: string;
  occurrences: number;
  severity: "high" | "medium" | "low";
  phase: string | null;
  avg_cp_loss: number | null;
  trend: string | null;
  examples: unknown[];
  recommendation: string;
}

export interface PatternsResponse {
  patterns: RecurringPattern[];
  total_games_analyzed: number;
  analysis_period: string;
}

export interface ProgressPoint {
  period: string;
  games: number;
  avg_cpl: number | null;
  blunder_rate: number | null;
  pattern_count: number;
}

export interface ProgressResponse {
  overall: ProgressPoint[];
  by_phase: Record<string, ProgressPoint[]>;
}

export const patternsAPI = {
  recurring(params?: {
    limit?: number;
    min_games?: number;
  }): Promise<PatternsResponse> {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set("limit", String(params.limit));
    if (params?.min_games) searchParams.set("min_games", String(params.min_games));
    return fetchAPI<PatternsResponse>(`/patterns/recurring?${searchParams}`);
  },

  progress(months?: number): Promise<ProgressResponse> {
    const searchParams = new URLSearchParams();
    if (months) searchParams.set("months", String(months));
    return fetchAPI<ProgressResponse>(`/patterns/progress?${searchParams}`);
  },
};

// ─── Anonymous Analysis ─────────────────────────────────

export interface AnonGameAnalysis {
  game_index: number;
  white: string;
  black: string;
  result: string;
  opening: string | null;
  eco: string | null;
  date: string | null;
  time_control: string | null;
  color: string;
  overall_cpl: number;
  accuracy: number | null;
  phase_opening_cpl: number | null;
  phase_middlegame_cpl: number | null;
  phase_endgame_cpl: number | null;
  blunders: number;
  mistakes: number;
  inaccuracies: number;
  best_moves: number;
  great_moves: number;
  brilliant_moves: number;
  missed_wins: number;
  moves: {
    move_number: number;
    color: string;
    san: string;
    cp_loss: number;
    phase: string | null;
    move_quality: string | null;
    eval_before: number | null;
    eval_after: number | null;
    fen_before?: string | null;
    best_move_san?: string | null;
    best_move_uci?: string | null;
    win_prob_before?: number | null;
    win_prob_after?: number | null;
    accuracy?: number | null;
  }[];
  puzzle_candidates?: {
    puzzle_key: string;
    fen: string;
    side_to_move: string;
    best_move_san: string;
    best_move_uci?: string | null;
    played_move_san: string;
    eval_loss_cp: number;
    phase: string;
    puzzle_type: string;
    difficulty: string;
    move_number: number;
    themes: string[];
  }[];
}

export interface AnonAnalysisResults {
  username: string | null;
  platform: string;
  total_games: number;
  games: AnonGameAnalysis[];
  overall_cpl: number | null;
  win_rate: number | null;
  blunder_rate: number | null;
}

export type AnonProgressEvent =
  | { type: "start"; total: number }
  | { type: "progress"; completed: number; total: number; game_cpl: number }
  | { type: "complete"; results: AnonAnalysisResults }
  | { type: "error"; message: string };

/**
 * Claim anonymous analysis results into the authenticated user's account.
 * Persists Game + GameAnalysis + MoveEvaluation rows in the database.
 */
export async function claimAnonymousResults(
  results: AnonAnalysisResults
): Promise<{ imported: number; total_submitted: number }> {
  return fetchAPI("/anonymous/claim-results", {
    method: "POST",
    body: JSON.stringify({
      username: results.username,
      platform: results.platform,
      games: results.games,
    }),
  });
}

/**
 * Start anonymous analysis via SSE stream.
 * Calls `onProgress` for each event, returns the final results.
 */
export async function startAnonymousAnalysis(
  params: {
    platform: string;
    username?: string;
    pgn_text?: string;
    max_games?: number;
  },
  onProgress: (event: AnonProgressEvent) => void
): Promise<AnonAnalysisResults> {
  const url = `${API_BASE}/anonymous/analyze`;

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? "Analysis failed");
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response stream");

  const decoder = new TextDecoder();
  let buffer = "";
  let finalResults: AnonAnalysisResults | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse SSE events
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const event: AnonProgressEvent = JSON.parse(line.slice(6));
          onProgress(event);
          if (event.type === "complete") {
            finalResults = event.results;
          }
        } catch {
          // Skip malformed events
        }
      }
    }
  }

  if (!finalResults) throw new Error("Analysis did not complete");
  return finalResults;
}

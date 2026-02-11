/**
 * API client for the Chess Analyzer backend.
 *
 * All requests go through Next.js rewrites → FastAPI backend.
 * JWT auth tokens are automatically fetched from the NextAuth token endpoint
 * and attached to every request.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api/backend";

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

export interface PuzzleItem {
  id: number;
  puzzle_key: string;
  fen: string;
  best_move_san: string;
  eval_loss_cp: number;
  difficulty: string;
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
  }): Promise<PuzzleItem[]> {
    const q = new URLSearchParams();
    if (params?.difficulty) q.set("difficulty", params.difficulty);
    if (params?.phase) q.set("phase", params.phase);
    if (params?.puzzle_type) q.set("puzzle_type", params.puzzle_type);
    if (params?.limit) q.set("limit", String(params.limit));
    return fetchAPI<PuzzleItem[]>(`/puzzles?${q}`);
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
  phase_opening_cpl: number | null;
  phase_middlegame_cpl: number | null;
  phase_endgame_cpl: number | null;
  blunders: number;
  mistakes: number;
  inaccuracies: number;
  best_moves: number;
  moves: {
    move_number: number;
    color: string;
    san: string;
    cp_loss: number;
    phase: string | null;
    move_quality: string | null;
    eval_before: number | null;
    eval_after: number | null;
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

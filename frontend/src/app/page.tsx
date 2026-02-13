"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession, signIn } from "next-auth/react";
import Link from "next/link";
import {
  Swords,
  Dumbbell,
  ArrowRight,
  LogIn,
  AlertTriangle,
  CheckCircle,
  Target,
  Zap,
  TrendingUp,
  TrendingDown,
  Minus,
  BookOpen,
  Sparkles,
} from "lucide-react";
import {
  insightsAPI,
  startAnonymousAnalysis,
  claimAnonymousResults,
  type InsightsOverview,
  type RecentGame,
  type Weakness,
  type AnonAnalysisResults,
  type AnonProgressEvent,
} from "@/lib/api";
import { Card, CardContent, StatCard, Badge, Button, Spinner } from "@/components/ui";
import { cplToAccuracy, accuracyColor, formatAccuracy } from "@/lib/utils";

type Step = "input" | "analyzing" | "results-locked" | "claiming" | "results";

export default function HomePage() {
  const { data: session, status: authStatus } = useSession();

  // ─── Logged-in dashboard state ──────────────────────
  const [overview, setOverview] = useState<InsightsOverview | null>(null);
  const [recentGames, setRecentGames] = useState<RecentGame[]>([]);
  const [weaknesses, setWeaknesses] = useState<Weakness[]>([]);
  const [dashboardLoading, setDashboardLoading] = useState(false);

  // ─── Anonymous analysis state ───────────────────────
  const [platform, setPlatform] = useState<"lichess" | "chess.com" | "pgn">("lichess");
  const [username, setUsername] = useState("");
  const [pgnText, setPgnText] = useState("");
  const [error, setError] = useState("");
  const [claimError, setClaimError] = useState("");

  // Progress
  const [progressTotal, setProgressTotal] = useState(0);
  const [progressDone, setProgressDone] = useState(0);

  // Results & step — start with defaults, hydrate from sessionStorage in useEffect
  const [results, setResults] = useState<AnonAnalysisResults | null>(null);
  const [step, setStep] = useState<Step>("input");
  const [hasMounted, setHasMounted] = useState(false);

  // Restore from sessionStorage on mount. This effect intentionally does NOT
  // depend on authStatus/session — it only reads what's stored and marks mounted.
  useEffect(() => {
    setHasMounted(true);
    try {
      const raw = sessionStorage.getItem("anon_analysis_results");
      if (raw) {
        const parsed = JSON.parse(raw) as AnonAnalysisResults;
        setResults(parsed);
        setStep("results-locked");
      }
    } catch {}
  }, []);

  // Claim helper — persists results to user account, awaits completion
  const doClaim = useCallback(async (data: AnonAnalysisResults) => {
    setStep("claiming");
    setClaimError("");
    try {
      await claimAnonymousResults(data);
      // Claim succeeded — safe to clear sessionStorage now
      try { sessionStorage.removeItem("anon_analysis_results"); } catch {}
      setStep("results");
    } catch (err) {
      console.error("Failed to claim anonymous results:", err);
      setClaimError(
        err instanceof Error ? err.message : "Failed to save your results. Please try again."
      );
      // Stay on "claiming" step so user can retry — sessionStorage still has data
      setStep("results-locked");
    }
  }, []);

  // Once auth resolves AND we're in results-locked with data, start the claim
  useEffect(() => {
    if (authStatus === "authenticated" && session && step === "results-locked" && results) {
      doClaim(results);
    }
  }, [authStatus, session, step, results, doClaim]);

  // Load dashboard data for logged-in users
  useEffect(() => {
    if (session && step === "input") {
      setDashboardLoading(true);
      Promise.all([
        insightsAPI.overview().then(setOverview).catch(() => {}),
        insightsAPI.recentGames(3).then(setRecentGames).catch(() => {}),
        insightsAPI.weaknesses().then((w) => {
          setWeaknesses(w.weaknesses ?? []);
        }).catch(() => {}),
      ]).finally(() => setDashboardLoading(false));
    }
  }, [session, step]);

  // ─── Start analysis ─────────────────────────────────
  const handleAnalyze = useCallback(async () => {
    setError("");
    if (platform !== "pgn" && !username.trim()) {
      setError("Please enter a username");
      return;
    }
    if (platform === "pgn" && !pgnText.trim()) {
      setError("Please paste your PGN");
      return;
    }

    setStep("analyzing");
    setProgressDone(0);
    setProgressTotal(0);

    try {
      const finalResults = await startAnonymousAnalysis(
        {
          platform,
          username: platform !== "pgn" ? username.trim() : undefined,
          pgn_text: platform === "pgn" ? pgnText : undefined,
          max_games: 20,
        },
        (event: AnonProgressEvent) => {
          if (event.type === "start") {
            setProgressTotal(event.total);
          } else if (event.type === "progress") {
            setProgressDone(event.completed);
            setProgressTotal(event.total);
          } else if (event.type === "error") {
            setError(event.message);
            setStep("input");
          }
        }
      );

      setResults(finalResults);
      // Save to sessionStorage so results survive sign-in redirect
      try {
        sessionStorage.setItem("anon_analysis_results", JSON.stringify(finalResults));
      } catch {}
      // If user is already signed in, claim immediately
      if (session) {
        doClaim(finalResults);
      } else {
        setStep("results-locked");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
      setStep("input");
    }
  }, [platform, username, pgnText, session, doClaim]);

  // Wait until client has mounted AND auth has resolved before deciding view
  if (!hasMounted || authStatus === "loading") {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner className="h-8 w-8 text-brand-500" />
      </div>
    );
  }

  // ─── If signed in and no analysis in progress, show dashboard ──
  if (session && step === "input" && !results) {
    return <LoggedInDashboard overview={overview} recentGames={recentGames} weaknesses={weaknesses} loading={dashboardLoading} />;
  }

  // ─── Render based on step ───────────────────────────
  return (
    <div className="max-w-3xl mx-auto px-6 py-12 animate-fade-in">
      {/* Hero */}
      <div className="text-center space-y-4 mb-10">
        <div className="mx-auto h-16 w-16 rounded-2xl bg-brand-600 flex items-center justify-center text-white text-3xl font-bold">
          ♔
        </div>
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
          Chess Analyzer
        </h1>
        <p className="text-gray-400 text-lg max-w-xl mx-auto">
          Get a free engine analysis of your games. See your mistakes, strengths,
          and where to improve.
        </p>
      </div>

      {/* Step: Input */}
      {step === "input" && (
        <AnalysisInput
          platform={platform}
          setPlatform={setPlatform}
          username={username}
          setUsername={setUsername}
          pgnText={pgnText}
          setPgnText={setPgnText}
          error={error}
          onAnalyze={handleAnalyze}
        />
      )}

      {/* Step: Analyzing */}
      {step === "analyzing" && (
        <AnalyzingProgress total={progressTotal} done={progressDone} />
      )}

      {/* Step: Results locked (need sign-in) */}
      {step === "results-locked" && results && (
        <ResultsLocked results={results} claimError={claimError} />
      )}

      {/* Step: Claiming — saving results to account */}
      {step === "claiming" && (
        <Card>
          <CardContent className="py-12 space-y-4 text-center">
            <Spinner className="h-10 w-10 text-brand-500 mx-auto" />
            <h2 className="text-xl font-semibold">Saving your results...</h2>
            <p className="text-gray-400 text-sm">
              Persisting {results?.total_games ?? 0} games to your account
            </p>
          </CardContent>
        </Card>
      )}

      {/* Step: Results (signed in) */}
      {step === "results" && results && (
        <ResultsView
          results={results}
          onAnalyzeMore={() => {
            setResults(null);
            setStep("input");
          }}
        />
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════
// Analysis Input Form
// ═══════════════════════════════════════════════════════════

function AnalysisInput({
  platform,
  setPlatform,
  username,
  setUsername,
  pgnText,
  setPgnText,
  error,
  onAnalyze,
}: {
  platform: "lichess" | "chess.com" | "pgn";
  setPlatform: (p: "lichess" | "chess.com" | "pgn") => void;
  username: string;
  setUsername: (v: string) => void;
  pgnText: string;
  setPgnText: (v: string) => void;
  error: string;
  onAnalyze: () => void;
}) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="space-y-6">
        <h2 className="text-lg font-semibold text-center">
          Analyze Your Games
        </h2>

        {/* Platform selector */}
        <div className="flex rounded-lg bg-surface-2 p-1">
          {(["lichess", "chess.com", "pgn"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              className={`flex-1 py-2.5 px-3 rounded-md text-sm font-medium transition-colors ${
                platform === p
                  ? "bg-brand-600 text-white"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {p === "lichess"
                ? "Lichess"
                : p === "chess.com"
                ? "Chess.com"
                : "Paste PGN"}
            </button>
          ))}
        </div>

        {/* Username or PGN input */}
        {platform !== "pgn" ? (
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              {platform === "lichess" ? "Lichess" : "Chess.com"} Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onAnalyze()}
              placeholder={
                platform === "lichess"
                  ? "e.g. DrNykterstein"
                  : "e.g. MagnusCarlsen"
              }
              className="w-full px-4 py-3 bg-surface-2 border border-surface-3 rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-600 focus:border-transparent text-sm"
            />
          </div>
        ) : (
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Paste PGN
            </label>
            <textarea
              value={pgnText}
              onChange={(e) => setPgnText(e.target.value)}
              placeholder="Paste your PGN text here..."
              rows={5}
              className="w-full px-4 py-3 bg-surface-2 border border-surface-3 rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-600 focus:border-transparent text-sm font-mono resize-none"
            />
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Submit */}
        <Button onClick={onAnalyze} className="w-full" size="lg">
          <Swords className="h-5 w-5" />
          Analyze Games
        </Button>

        <p className="text-xs text-center text-gray-500">
          Free • Up to 20 games • No sign-in required
        </p>
      </CardContent>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════
// Analyzing Progress
// ═══════════════════════════════════════════════════════════

function AnalyzingProgress({ total, done }: { total: number; done: number }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <Card>
      <CardContent className="py-12 space-y-6 text-center">
        <Spinner className="h-10 w-10 text-brand-500 mx-auto" />
        <div>
          <h2 className="text-xl font-semibold mb-2">
            Analyzing your games...
          </h2>
          <p className="text-gray-400 text-sm">
            {total > 0 ? `Game ${done} of ${total}` : "Fetching games..."}
          </p>
        </div>

        {/* Progress bar */}
        {total > 0 && (
          <div className="max-w-sm mx-auto">
            <div className="h-2 bg-surface-2 rounded-full overflow-hidden">
              <div
                className="h-full bg-brand-600 rounded-full transition-all duration-300"
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="text-xs text-gray-500 mt-2">{pct}% complete</p>
          </div>
        )}

        <p className="text-xs text-gray-600">
          Engine analysis with Stockfish • This may take a minute
        </p>
      </CardContent>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════
// Results Locked (Sign-in required)
// ═══════════════════════════════════════════════════════════

function ResultsLocked({ results, claimError }: { results: AnonAnalysisResults; claimError?: string }) {
  return (
    <div className="space-y-6">
      {/* Completion banner */}
      <Card>
        <CardContent className="py-8 text-center space-y-4">
          <CheckCircle className="h-12 w-12 text-green-400 mx-auto" />
          <h2 className="text-2xl font-bold">Analysis Complete!</h2>
          <p className="text-gray-400">
            {results.total_games} game
            {results.total_games !== 1 ? "s" : ""} analyzed successfully
          </p>
        </CardContent>
      </Card>

      {/* Claim error banner */}
      {claimError && (
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm text-center">
          <AlertTriangle className="h-5 w-5 inline-block mr-2" />
          {claimError} — Sign in again to retry.
        </div>
      )}

      {/* Blurred preview */}
      <div className="relative">
        <div className="filter blur-sm pointer-events-none select-none">
          <div className="grid grid-cols-3 gap-4">
            <Card className="p-4 text-center">
              <p className="text-xs text-gray-500 uppercase">Accuracy</p>
              <p className="text-2xl font-bold mt-1">
                {formatAccuracy(results.overall_cpl)}
              </p>
            </Card>
            <Card className="p-4 text-center">
              <p className="text-xs text-gray-500 uppercase">Win Rate</p>
              <p className="text-2xl font-bold mt-1">
                {results.win_rate ?? "—"}%
              </p>
            </Card>
            <Card className="p-4 text-center">
              <p className="text-xs text-gray-500 uppercase">Blunder Rate</p>
              <p className="text-2xl font-bold mt-1">
                {results.blunder_rate ?? "—"}%
              </p>
            </Card>
          </div>
        </div>

        {/* Overlay lock icon */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="bg-surface-0/80 backdrop-blur-sm p-4 rounded-xl border border-surface-3">
            <LogIn className="h-8 w-8 text-brand-400" />
          </div>
        </div>
      </div>

      {/* Sign-in button */}
      <Button
        onClick={() => signIn(undefined, { callbackUrl: "/" })}
        className="w-full"
        size="lg"
      >
        <LogIn className="h-5 w-5" />
        Sign Up to Get My Results
      </Button>

      <p className="text-xs text-center text-gray-500">
        Your analysis results will be shown immediately after signing up
      </p>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════
// Results View (signed in)
// ═══════════════════════════════════════════════════════════

function ResultsView({
  results,
  onAnalyzeMore,
}: {
  results: AnonAnalysisResults;
  onAnalyzeMore: () => void;
}) {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center space-y-2">
        <CheckCircle className="h-10 w-10 text-green-400 mx-auto" />
        <h2 className="text-2xl font-bold">Your Analysis</h2>
        <p className="text-gray-400 text-sm">
          {results.total_games} game{results.total_games !== 1 ? "s" : ""} from{" "}
          {results.platform === "pgn" ? "PGN" : results.username}
          {results.platform !== "pgn" && ` (${results.platform})`}
        </p>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard
          label="Accuracy"
          value={formatAccuracy(results.overall_cpl)}
          icon={<Target className="h-5 w-5" />}
        />
        <StatCard
          label="Win Rate"
          value={results.win_rate ? `${results.win_rate}%` : "—"}
          icon={<Zap className="h-5 w-5" />}
        />
        <StatCard
          label="Blunder Rate"
          value={results.blunder_rate ? `${results.blunder_rate}%` : "—"}
          icon={<AlertTriangle className="h-5 w-5" />}
        />
      </div>

      {/* Per-game breakdown */}
      <Card>
        <CardContent>
          <h3 className="font-semibold mb-4">Game-by-Game</h3>
          <div className="space-y-2">
            {results.games.map((g) => (
              <div
                key={g.game_index}
                className="flex items-center gap-3 px-4 py-3 rounded-lg bg-surface-2/50"
              >
                <div
                  className={`h-7 w-7 rounded flex items-center justify-center text-xs font-bold ${
                    g.color === "white"
                      ? "bg-white text-gray-900"
                      : "bg-gray-800 text-white border border-surface-3"
                  }`}
                >
                  {g.color === "white" ? "♔" : "♚"}
                </div>
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium truncate block">
                    {g.opening || "Unknown Opening"}
                  </span>
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    {g.time_control && <span>{g.time_control}</span>}
                    {g.date && <span>{g.date}</span>}
                  </div>
                </div>
                <Badge
                  variant={
                    g.result === "win"
                      ? "success"
                      : g.result === "loss"
                      ? "danger"
                      : "warning"
                  }
                >
                  {g.result.toUpperCase()}
                </Badge>
                <span
                  className={`text-xs font-semibold min-w-[50px] text-right ${accuracyColor(cplToAccuracy(g.overall_cpl))}`}
                >
                  {formatAccuracy(g.overall_cpl)}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Phase Breakdown */}
      <Card>
        <CardContent>
          <h3 className="font-semibold mb-4">Phase Accuracy (Average)</h3>
          <div className="grid grid-cols-3 gap-4">
            {(["opening", "middlegame", "endgame"] as const).map((phase) => {
              const cpls = results.games
                .map((g) =>
                  phase === "opening"
                    ? g.phase_opening_cpl
                    : phase === "middlegame"
                    ? g.phase_middlegame_cpl
                    : g.phase_endgame_cpl
                )
                .filter((v): v is number => v !== null);
              const avgCpl =
                cpls.length > 0
                  ? cpls.reduce((a, b) => a + b, 0) / cpls.length
                  : null;
              const acc = cplToAccuracy(avgCpl);
              const color = accuracyColor(acc);

              return (
                <div
                  key={phase}
                  className="text-center p-4 bg-surface-2/50 rounded-lg"
                >
                  <p className="text-sm text-gray-400 capitalize mb-1">
                    {phase}
                  </p>
                  <p className={`text-2xl font-bold ${color}`}>
                    {acc !== null ? `${acc}%` : "—"}
                  </p>
                  <p className="text-xs text-gray-500">accuracy</p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex flex-col sm:flex-row gap-3">
        <Button
          onClick={onAnalyzeMore}
          variant="secondary"
          className="flex-1"
        >
          <Swords className="h-4 w-4" />
          Analyze More Games
        </Button>
        <Link href="/games" className="flex-1">
          <Button className="w-full">
            <ArrowRight className="h-4 w-4" />
            Go to My Games
          </Button>
        </Link>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════
// Logged-In Dashboard
// ═══════════════════════════════════════════════════════════

function LoggedInDashboard({
  overview,
  recentGames,
  weaknesses,
  loading,
}: {
  overview: InsightsOverview | null;
  recentGames: RecentGame[];
  weaknesses: Weakness[];
  loading?: boolean;
}) {
  const topWeakness = weaknesses[0] ?? null;
  const [showAnalyzeSlider, setShowAnalyzeSlider] = useState(false);
  const [sliderValue, setSliderValue] = useState(20);

  const accuracy = cplToAccuracy(overview?.overall_cpl);
  const recentAccuracy = cplToAccuracy(overview?.recent_cpl);

  const trendIcon =
    overview?.trend === "improving" ? (
      <TrendingUp className="h-4 w-4" />
    ) : overview?.trend === "declining" ? (
      <TrendingDown className="h-4 w-4" />
    ) : (
      <Minus className="h-4 w-4" />
    );

  const trendText =
    overview?.trend === "improving"
      ? "Improving"
      : overview?.trend === "declining"
      ? "Declining"
      : overview?.trend === "stable"
      ? "Stable"
      : null;

  // Phase accuracy from overview
  const phaseAcc = overview?.phase_accuracy;
  const openingAcc = phaseAcc?.opening != null ? cplToAccuracy(phaseAcc.opening) : null;
  const middlegameAcc = phaseAcc?.middlegame != null ? cplToAccuracy(phaseAcc.middlegame) : null;
  const endgameAcc = phaseAcc?.endgame != null ? cplToAccuracy(phaseAcc.endgame) : null;

  return (
    <div className="max-w-4xl mx-auto px-6 py-10 animate-fade-in">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Your chess performance at a glance</p>
      </div>

      {loading && !overview && (
        <div className="flex justify-center py-12">
          <Spinner className="h-8 w-8 text-brand-500" />
        </div>
      )}

      {/* Top row: ELO + Accuracy + Trend */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {/* ELO Card */}
        <Card className="p-5 bg-gradient-to-br from-surface-0 to-surface-1 border-surface-3">
          <div className="flex items-center gap-2 mb-2">
            <div className="h-8 w-8 rounded-lg bg-brand-600/20 flex items-center justify-center">
              <span className="text-brand-400 font-bold text-sm">♔</span>
            </div>
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Rating</span>
          </div>
          <p className="text-3xl font-bold text-white">
            {overview?.current_elo ?? "—"}
          </p>
          {overview?.elo_trend != null && overview.elo_trend !== 0 && (
            <div className={`flex items-center gap-1 mt-1 text-xs font-medium ${
              overview.elo_trend > 0 ? "text-green-400" : "text-red-400"
            }`}>
              {overview.elo_trend > 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
              {overview.elo_trend > 0 ? "+" : ""}{overview.elo_trend} last 30 games
            </div>
          )}
        </Card>

        {/* Accuracy Card */}
        <Card className="p-5 bg-gradient-to-br from-surface-0 to-surface-1 border-surface-3">
          <div className="flex items-center gap-2 mb-2">
            <div className="h-8 w-8 rounded-lg bg-brand-600/20 flex items-center justify-center">
              <Target className="h-4 w-4 text-brand-400" />
            </div>
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Accuracy</span>
          </div>
          <p className={`text-3xl font-bold ${accuracyColor(accuracy)}`}>
            {accuracy != null ? `${accuracy}%` : "—"}
          </p>
          {recentAccuracy != null && (
            <p className="text-xs text-gray-500 mt-1">Recent: {recentAccuracy}%</p>
          )}
        </Card>

        {/* Win Rate Card */}
        <Card className="p-5 bg-gradient-to-br from-surface-0 to-surface-1 border-surface-3">
          <div className="flex items-center gap-2 mb-2">
            <div className="h-8 w-8 rounded-lg bg-green-600/20 flex items-center justify-center">
              <Zap className="h-4 w-4 text-green-400" />
            </div>
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Win Rate</span>
          </div>
          <p className="text-3xl font-bold text-white">
            {overview?.win_rate != null ? `${overview.win_rate}%` : "—"}
          </p>
          <p className="text-xs text-gray-500 mt-1">{overview?.total_games ?? 0} games</p>
        </Card>

        {/* Trend Card */}
        <Card className="p-5 bg-gradient-to-br from-surface-0 to-surface-1 border-surface-3">
          <div className="flex items-center gap-2 mb-2">
            <div className={`h-8 w-8 rounded-lg flex items-center justify-center ${
              overview?.trend === "improving" ? "bg-green-600/20" : overview?.trend === "declining" ? "bg-red-600/20" : "bg-surface-2"
            }`}>
              {trendIcon}
            </div>
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Trend</span>
          </div>
          <p className={`text-xl font-bold ${
            overview?.trend === "improving" ? "text-green-400" : overview?.trend === "declining" ? "text-red-400" : "text-gray-300"
          }`}>
            {trendText ?? "—"}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            {overview?.blunder_rate != null ? `${overview.blunder_rate} blunders/100` : ""}
          </p>
        </Card>
      </div>

      {/* Phase Accuracy Breakdown */}
      {(openingAcc != null || middlegameAcc != null || endgameAcc != null) && (
        <div className="mb-8">
          <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">
            Phase Accuracy
          </h2>
          <Card className="p-5">
            <div className="grid grid-cols-3 gap-6">
              {[
                { label: "Opening", acc: openingAcc, emoji: "📖" },
                { label: "Middlegame", acc: middlegameAcc, emoji: "⚔️" },
                { label: "Endgame", acc: endgameAcc, emoji: "🏁" },
              ].map(({ label, acc: phAcc, emoji }) => (
                <div key={label} className="text-center">
                  <div className="text-lg mb-1">{emoji}</div>
                  <p className={`text-2xl font-bold ${accuracyColor(phAcc)}`}>
                    {phAcc != null ? `${phAcc}%` : "—"}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">{label}</p>
                  {phAcc != null && (
                    <div className="mt-2 h-1.5 bg-surface-2 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          phAcc >= 75 ? "bg-green-500" : phAcc >= 60 ? "bg-yellow-500" : phAcc >= 45 ? "bg-orange-500" : "bg-red-500"
                        }`}
                        style={{ width: `${Math.min(100, phAcc)}%` }}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* Two-column: CTA + Today's Focus */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
        {/* Analyze CTA */}
        <Card className="p-6 bg-gradient-to-br from-brand-600/10 to-brand-600/5 border-brand-600/20">
          <div className="flex items-center gap-3 mb-3">
            <div className="h-10 w-10 rounded-xl bg-brand-600/20 flex items-center justify-center">
              <Swords className="h-5 w-5 text-brand-400" />
            </div>
            <div>
              <h3 className="font-semibold">Analyze Games</h3>
              <p className="text-xs text-gray-500">Import new games for analysis</p>
            </div>
          </div>
          <Link href="/games">
            <Button className="w-full" size="lg">
              <Swords className="h-4 w-4" />
              Analyze New Games
            </Button>
          </Link>
        </Card>

        {/* Today's Focus */}
        {topWeakness ? (
          <Link href="/train">
            <Card className="p-6 hover:border-brand-600/50 transition-colors cursor-pointer h-full">
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-xl bg-orange-600/20 flex items-center justify-center">
                  <Dumbbell className="h-5 w-5 text-orange-400" />
                </div>
                <div>
                  <h3 className="font-semibold">Today&apos;s Focus</h3>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={
                        topWeakness.severity === "high"
                          ? "danger"
                          : topWeakness.severity === "medium"
                          ? "warning"
                          : "default"
                      }
                    >
                      {topWeakness.severity}
                    </Badge>
                    <span className="text-xs text-gray-500">{topWeakness.area}</span>
                  </div>
                </div>
              </div>
              <p className="text-sm text-gray-400 line-clamp-2">{topWeakness.message}</p>
              <p className="text-sm text-brand-400 mt-3 flex items-center gap-1">
                Train this weakness <ArrowRight className="h-3 w-3" />
              </p>
            </Card>
          </Link>
        ) : (
          <Link href="/train">
            <Card className="p-6 hover:border-brand-600/50 transition-colors cursor-pointer h-full flex flex-col items-center justify-center text-center">
              <Dumbbell className="h-8 w-8 text-gray-600 mb-2" />
              <h3 className="font-semibold">Training</h3>
              <p className="text-xs text-gray-500 mt-1">
                {overview?.puzzle_count ? `${overview.puzzle_count} puzzles available` : "Solve puzzles from your games"}
              </p>
              <p className="text-sm text-brand-400 mt-3 flex items-center gap-1">
                Start training <ArrowRight className="h-3 w-3" />
              </p>
            </Card>
          </Link>
        )}
      </div>

      {/* Study Recommendations */}
      {weaknesses.length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
            <BookOpen className="h-4 w-4" />
            Study Recommendations
          </h2>
          <div className="space-y-3">
            {weaknesses.map((w, i) => (
              <Card key={i} className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <AlertTriangle className={`h-5 w-5 mt-0.5 flex-shrink-0 ${
                      w.severity === "high" ? "text-red-400" : w.severity === "medium" ? "text-yellow-400" : "text-gray-400"
                    }`} />
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold text-sm">{w.area}</span>
                        <Badge variant={w.severity === "high" ? "danger" : w.severity === "medium" ? "warning" : "default"}>
                          {w.severity}
                        </Badge>
                      </div>
                      <p className="text-sm text-gray-400">{w.message}</p>
                    </div>
                  </div>
                  <Link href="/train">
                    <Button size="sm" variant="secondary" className="flex-shrink-0">
                      <Dumbbell className="h-3.5 w-3.5" />
                      Train
                    </Button>
                  </Link>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Analyze More Games for Better Accuracy */}
      <div className="mb-8">
        <Card className="p-6 bg-gradient-to-br from-surface-0 to-surface-1 border-surface-3">
          <div className="flex items-center gap-3 mb-4">
            <div className="h-10 w-10 rounded-xl bg-brand-600/20 flex items-center justify-center">
              <Swords className="h-5 w-5 text-brand-400" />
            </div>
            <div>
              <h3 className="font-semibold">Analyze More Games for Better Accuracy</h3>
              <p className="text-xs text-gray-500">More analyzed games = more precise insights</p>
            </div>
          </div>

          {!showAnalyzeSlider ? (
            <Button
              onClick={() => setShowAnalyzeSlider(true)}
              className="w-full"
              variant="secondary"
            >
              <Swords className="h-4 w-4" />
              Choose number of games
              <ArrowRight className="h-4 w-4" />
            </Button>
          ) : (
            <div className="space-y-4 animate-fade-in">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-gray-400">Number of games</span>
                  <span className="text-lg font-bold text-brand-400">{sliderValue}</span>
                </div>
                <input
                  type="range"
                  min={5}
                  max={50}
                  step={5}
                  value={sliderValue}
                  onChange={(e) => setSliderValue(Number(e.target.value))}
                  className="w-full h-2 bg-surface-2 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:shadow-lg"
                />
                <div className="flex justify-between text-xs text-gray-600 mt-1">
                  <span>5</span>
                  <span>25</span>
                  <span>50</span>
                </div>
              </div>

              {sliderValue >= 50 && (
                <div className="p-3 rounded-lg bg-brand-600/10 border border-brand-600/20 text-sm text-brand-300 flex items-center gap-2">
                  <Sparkles className="h-4 w-4 flex-shrink-0" />
                  Upgrade to analyse 50+ games at once
                </div>
              )}

              <Link href="/games">
                <Button className="w-full" size="lg">
                  <Swords className="h-4 w-4" />
                  Import &amp; Analyze {sliderValue} Games
                </Button>
              </Link>
            </div>
          )}
        </Card>
      </div>

      {/* Recent games */}
      {recentGames.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider">
              Recent Games
            </h2>
            <Link
              href="/games"
              className="text-xs text-brand-400 hover:text-brand-300 flex items-center gap-1"
            >
              View all <ArrowRight className="h-3 w-3" />
            </Link>
          </div>
          <div className="space-y-2">
            {recentGames.map((g) => {
              const date = g.date
                ? new Date(g.date).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                  })
                : "";
              const acc = cplToAccuracy(g.overall_cpl);
              return (
                <Link key={g.id} href={`/games/${g.id}`}>
                  <Card className="flex items-center gap-4 px-5 py-3 hover:bg-surface-2/50 transition-colors cursor-pointer">
                    <div
                      className={`h-7 w-7 rounded flex items-center justify-center text-xs font-bold ${
                        g.color === "white"
                          ? "bg-white text-gray-900"
                          : "bg-gray-800 text-white border border-surface-3"
                      }`}
                    >
                      {g.color === "white" ? "♔" : "♚"}
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium truncate block">
                        {g.opening_name || "Unknown Opening"}
                      </span>
                      <div className="flex items-center gap-2 text-xs text-gray-500">
                        <span>{date}</span>
                        {g.time_control && <span>{g.time_control}</span>}
                        {g.player_elo && (
                          <span className="text-gray-600">{g.player_elo}</span>
                        )}
                      </div>
                    </div>
                    <Badge
                      variant={
                        g.result === "win"
                          ? "success"
                          : g.result === "loss"
                          ? "danger"
                          : "warning"
                      }
                    >
                      {g.result.toUpperCase()}
                    </Badge>
                    {acc !== null && (
                      <span className={`text-xs font-semibold ${accuracyColor(acc)}`}>
                        {acc}%
                      </span>
                    )}
                  </Card>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Bottom stats row */}
      {overview && overview.total_games > 0 && (
        <div>
          <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">
            Overview
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Card className="p-4 text-center">
              <p className="text-xs text-gray-500">Games</p>
              <p className="text-xl font-bold mt-1">{overview.total_games}</p>
            </Card>
            <Card className="p-4 text-center">
              <p className="text-xs text-gray-500">Win Rate</p>
              <p className="text-xl font-bold mt-1">
                {overview.win_rate ? `${overview.win_rate}%` : "—"}
              </p>
            </Card>
            <Card className="p-4 text-center">
              <p className="text-xs text-gray-500">Blunders/100</p>
              <p className="text-xl font-bold mt-1">
                {overview.blunder_rate ?? "—"}
              </p>
            </Card>
            <Card className="p-4 text-center">
              <p className="text-xs text-gray-500">Puzzles</p>
              <p className="text-xl font-bold mt-1">
                {overview.puzzle_count ?? 0}
              </p>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
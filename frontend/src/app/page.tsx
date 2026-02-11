"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession, signIn } from "next-auth/react";
import Link from "next/link";
import {
  Swords,
  Dumbbell,
  BarChart3,
  BookOpen,
  ArrowRight,
  Upload,
  LogIn,
  AlertTriangle,
  CheckCircle,
  Target,
  Zap,
} from "lucide-react";
import {
  insightsAPI,
  startAnonymousAnalysis,
  type InsightsOverview,
  type RecentGame,
  type AnonAnalysisResults,
  type AnonProgressEvent,
} from "@/lib/api";
import { Card, CardContent, StatCard, Badge, Button, Spinner } from "@/components/ui";

type Step = "input" | "analyzing" | "results-locked" | "results";

export default function HomePage() {
  const { data: session, status: authStatus } = useSession();

  // ─── Logged-in dashboard state ──────────────────────
  const [overview, setOverview] = useState<InsightsOverview | null>(null);
  const [recentGames, setRecentGames] = useState<RecentGame[]>([]);

  // ─── Anonymous analysis state ───────────────────────
  const [platform, setPlatform] = useState<"lichess" | "chess.com" | "pgn">("lichess");
  const [username, setUsername] = useState("");
  const [pgnText, setPgnText] = useState("");
  const [error, setError] = useState("");

  // Progress
  const [progressTotal, setProgressTotal] = useState(0);
  const [progressDone, setProgressDone] = useState(0);

  // Results — initialize from sessionStorage if available
  const [results, setResults] = useState<AnonAnalysisResults | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const stored = sessionStorage.getItem("anon_analysis_results");
      if (stored) return JSON.parse(stored) as AnonAnalysisResults;
    } catch {}
    return null;
  });

  // Determine initial step based on stored results
  const [step, setStep] = useState<Step>(() => {
    if (typeof window === "undefined") return "input";
    try {
      const stored = sessionStorage.getItem("anon_analysis_results");
      if (stored) return "results-locked"; // Will switch to "results" once session loads
    } catch {}
    return "input";
  });

  // When session loads and we have stored results, unlock them
  useEffect(() => {
    if (authStatus === "loading") return;
    if (session && results && step === "results-locked") {
      setStep("results");
      sessionStorage.removeItem("anon_analysis_results");
    }
  }, [session, authStatus, results, step]);

  // Load dashboard data for logged-in users
  useEffect(() => {
    if (session && step === "input") {
      insightsAPI.overview().then(setOverview).catch(() => {});
      insightsAPI.recentGames(5).then(setRecentGames).catch(() => {});
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
      // If user is already signed in, go straight to results
      if (session) {
        setStep("results");
        sessionStorage.removeItem("anon_analysis_results");
      } else {
        setStep("results-locked");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
      setStep("input");
    }
  }, [platform, username, pgnText, session]);

  // ─── If signed in and no analysis in progress, show dashboard ──
  if (session && step === "input" && !results) {
    return <LoggedInDashboard overview={overview} recentGames={recentGames} />;
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
        <ResultsLocked results={results} />
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

function ResultsLocked({ results }: { results: AnonAnalysisResults }) {
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

      {/* Blurred preview */}
      <div className="relative">
        <div className="filter blur-sm pointer-events-none select-none">
          <div className="grid grid-cols-3 gap-4">
            <Card className="p-4 text-center">
              <p className="text-xs text-gray-500 uppercase">Overall CPL</p>
              <p className="text-2xl font-bold mt-1">
                {results.overall_cpl ?? "—"}
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

        {/* Overlay CTA */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="bg-surface-0/80 backdrop-blur-sm px-6 py-4 rounded-xl border border-surface-3 text-center space-y-3">
            <LogIn className="h-6 w-6 text-brand-400 mx-auto" />
            <p className="text-sm text-gray-300 font-medium">
              Sign in to see your results
            </p>
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
          label="Overall CPL"
          value={results.overall_cpl ?? "—"}
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
                  className={`text-xs font-semibold min-w-[50px] text-right ${
                    g.overall_cpl < 30
                      ? "text-green-400"
                      : g.overall_cpl < 60
                      ? "text-yellow-400"
                      : "text-red-400"
                  }`}
                >
                  {Math.round(g.overall_cpl)} CPL
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Phase Breakdown */}
      <Card>
        <CardContent>
          <h3 className="font-semibold mb-4">Phase Breakdown (Average)</h3>
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
              const avg =
                cpls.length > 0
                  ? Math.round(
                      cpls.reduce((a, b) => a + b, 0) / cpls.length
                    )
                  : null;
              const color =
                avg === null
                  ? "text-gray-600"
                  : avg < 25
                  ? "text-green-400"
                  : avg < 50
                  ? "text-yellow-400"
                  : "text-red-400";

              return (
                <div
                  key={phase}
                  className="text-center p-4 bg-surface-2/50 rounded-lg"
                >
                  <p className="text-sm text-gray-400 capitalize mb-1">
                    {phase}
                  </p>
                  <p className={`text-2xl font-bold ${color}`}>
                    {avg ?? "—"}
                  </p>
                  <p className="text-xs text-gray-500">avg CPL</p>
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
}: {
  overview: InsightsOverview | null;
  recentGames: RecentGame[];
}) {
  return (
    <div className="max-w-5xl mx-auto px-6 py-12 animate-fade-in">
      <div className="text-center space-y-4 mb-12">
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
          Welcome back.
          <br />
          <span className="text-brand-400">Keep improving.</span>
        </h1>
      </div>

      {/* Stats */}
      {overview && overview.total_games > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <StatCard
            label="Games"
            value={overview.total_games}
            icon={<Swords className="h-5 w-5" />}
          />
          <StatCard
            label="Overall CPL"
            value={overview.overall_cpl ?? "—"}
            subtitle={
              overview.trend === "improving"
                ? "↗ Improving"
                : overview.trend === "declining"
                ? "↘ Declining"
                : undefined
            }
            trend={
              overview.trend === "improving"
                ? "up"
                : overview.trend === "declining"
                ? "down"
                : "neutral"
            }
          />
          <StatCard
            label="Win Rate"
            value={overview.win_rate ? `${overview.win_rate}%` : "—"}
          />
          <StatCard
            label="Blunders/100"
            value={overview.blunder_rate ?? "—"}
          />
        </div>
      )}

      {/* Quick actions */}
      <div className="grid md:grid-cols-4 gap-4 mb-8">
        <QuickAction
          href="/games"
          icon={Swords}
          title="My Games"
          desc="Import and review your analyzed games"
        />
        <QuickAction
          href="/openings"
          icon={BookOpen}
          title="Openings"
          desc="Your opening repertoire stats"
        />
        <QuickAction
          href="/train"
          icon={Dumbbell}
          title="Train"
          desc="Solve puzzles from your own mistakes"
        />
        <QuickAction
          href="/insights"
          icon={BarChart3}
          title="Insights"
          desc="See your strengths and weaknesses"
        />
      </div>

      {/* Recent games */}
      {recentGames.length > 0 && (
        <div className="mb-16">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Recent Games</h2>
            <Link
              href="/games"
              className="text-sm text-brand-400 hover:text-brand-300 flex items-center gap-1"
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
                      <span className="text-sm font-medium truncate">
                        {g.opening_name || "Unknown Opening"}
                      </span>
                      <div className="flex items-center gap-2 text-xs text-gray-500">
                        <span>{date}</span>
                        {g.time_control && <span>{g.time_control}</span>}
                        <span className="capitalize">{g.platform}</span>
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
                    {g.overall_cpl !== null && (
                      <span
                        className={`text-xs font-medium ${
                          g.overall_cpl < 30
                            ? "text-green-400"
                            : g.overall_cpl < 60
                            ? "text-yellow-400"
                            : "text-red-400"
                        }`}
                      >
                        {Math.round(g.overall_cpl)} CPL
                      </span>
                    )}
                  </Card>
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function QuickAction({
  href,
  icon: Icon,
  title,
  desc,
}: {
  href: string;
  icon: any;
  title: string;
  desc: string;
}) {
  return (
    <Link
      href={href}
      className="group flex flex-col gap-3 p-5 rounded-xl bg-surface-1 border border-surface-3 hover:border-brand-600/50 transition-colors"
    >
      <div className="h-10 w-10 rounded-lg bg-surface-2 flex items-center justify-center group-hover:bg-brand-600/20 transition-colors">
        <Icon className="h-5 w-5 text-gray-400 group-hover:text-brand-400 transition-colors" />
      </div>
      <div>
        <h3 className="font-semibold text-white">{title}</h3>
        <p className="text-sm text-gray-500 mt-1">{desc}</p>
      </div>
    </Link>
  );
}
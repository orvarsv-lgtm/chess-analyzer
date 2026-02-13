"use client";

import { type CSSProperties, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Chess, Square } from "chess.js";
import { Chessboard } from "react-chessboard";
import {
  Dumbbell,
  CheckCircle,
  XCircle,
  SkipForward,
  Flame,
  RotateCcw,
  Zap,
  Target,
  ArrowRight,
  AlertTriangle,
  Globe,
  User,
  Clock,
  History,
  Sunrise,
  Trophy,
  Shield,
  Eye,
} from "lucide-react";
import { puzzlesAPI, insightsAPI, type PuzzleItem, type Weakness, type PuzzleHistoryResponse, type DailyWarmupResponse, type AdvantagePositionsResponse, type IntuitionChallengeResponse } from "@/lib/api";
import { playMove, playCorrect, playIncorrect, playStreak, playWarmupComplete } from "@/lib/sounds";
import {
  Button,
  Badge,
  Card,
  CardContent,
  EmptyState,
  Spinner,
} from "@/components/ui";

type TrainView = "hub" | "session" | "intuition";
type PuzzleState = "solving" | "correct" | "incorrect";
type PuzzleSource = "my" | "global" | "game";

export default function TrainPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-full"><Spinner className="h-8 w-8 text-brand-500" /></div>}>
      <TrainPageInner />
    </Suspense>
  );
}

function TrainPageInner() {
  const { data: session } = useSession();
  const searchParams = useSearchParams();
  const gameIdParam = searchParams.get("game_id");
  const timedParam = searchParams.get("mode") === "timed";

  // ─── Timed mode ───────────────────────────────────
  const TIMED_LIMIT = 10;
  const YELLOW_AT = 6;
  const RED_AT = 8;
  const [isTimed, setIsTimed] = useState(timedParam);

  // ─── View state ──────────────────────────────────────
  const [view, setView] = useState<TrainView>("hub");
  const [puzzleSource, setPuzzleSource] = useState<PuzzleSource>(
    gameIdParam ? "game" : "my"
  );

  // ─── Hub data ────────────────────────────────────────
  const [weaknesses, setWeaknesses] = useState<Weakness[]>([]);
  const [hubLoading, setHubLoading] = useState(true);
  const [hubTab, setHubTab] = useState<"train" | "history">("train");
  const [history, setHistory] = useState<PuzzleHistoryResponse | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  // ─── Daily Warmup ────────────────────────────────────
  const [warmup, setWarmup] = useState<DailyWarmupResponse | null>(null);
  const [warmupLoading, setWarmupLoading] = useState(false);
  const [isWarmupSession, setIsWarmupSession] = useState(false);
  const [advantagePositions, setAdvantagePositions] = useState<AdvantagePositionsResponse | null>(null);

  // ─── Intuition Trainer ───────────────────────────────
  const [intuitionChallenges, setIntuitionChallenges] = useState<IntuitionChallengeResponse | null>(null);
  const [intuitionIdx, setIntuitionIdx] = useState(0);
  const [intuitionPicked, setIntuitionPicked] = useState<number | null>(null);
  const [intuitionScore, setIntuitionScore] = useState(0);

  // ─── Puzzle queue state ──────────────────────────────
  const [queue, setQueue] = useState<PuzzleItem[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [loading, setLoading] = useState(false);

  // ─── Solving state ───────────────────────────────────
  const [puzzleState, setPuzzleState] = useState<PuzzleState>("solving");
  const [startTime, setStartTime] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [timedOut, setTimedOut] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval>>();
  const [selectedSquare, setSelectedSquare] = useState<Square | null>(null);
  const [legalMoves, setLegalMoves] = useState<Square[]>([]);

  // ─── Stats ───────────────────────────────────────────
  const [streak, setStreak] = useState(0);
  const [solvedToday, setSolvedToday] = useState(0);
  const [correctToday, setCorrectToday] = useState(0);

  const currentPuzzle = queue[currentIdx] ?? null;

  // ─── Chess instance for puzzle position ──────────────
  const chessRef = useRef<Chess | null>(null);
  const [boardFen, setBoardFen] = useState(currentPuzzle?.fen ?? "start");

  useEffect(() => {
    if (currentPuzzle) {
      try {
        chessRef.current = new Chess(currentPuzzle.fen);
      } catch {
        chessRef.current = null;
      }
      setBoardFen(currentPuzzle.fen);
      setPuzzleState("solving");
      setStartTime(Date.now());
      setElapsedSeconds(0);
      setTimedOut(false);
      setSelectedSquare(null);
      setLegalMoves([]);
    }
  }, [currentPuzzle]);

  // ─── Timer tick ──────────────────────────────────
  useEffect(() => {
    if (puzzleState === "solving" && startTime > 0) {
      const tick = () => setElapsedSeconds(Math.floor((Date.now() - startTime) / 1000));
      tick();
      timerRef.current = setInterval(tick, 200);
      return () => clearInterval(timerRef.current);
    }
    return () => clearInterval(timerRef.current);
  }, [puzzleState, startTime]);

  // ─── Timed mode auto-fail ───────────────────────
  useEffect(() => {
    if (isTimed && puzzleState === "solving" && elapsedSeconds >= TIMED_LIMIT) {
      setPuzzleState("incorrect");
      setTimedOut(true);
      setStreak(0);
      setSolvedToday((s) => s + 1);
      reportAttempt(false);
    }
  }, [isTimed, puzzleState, elapsedSeconds]); // eslint-disable-line react-hooks/exhaustive-deps

  // Determine board orientation from FEN
  const boardOrientation = useMemo(() => {
    if (!currentPuzzle?.fen) return "white" as const;
    const parts = currentPuzzle.fen.split(" ");
    return parts[1] === "w" ? ("white" as const) : ("black" as const);
  }, [currentPuzzle?.fen]);

  // ─── Load hub data ───────────────────────────────────
  useEffect(() => {
    if (!session) return;
    setHubLoading(true);
    Promise.all([
      insightsAPI
        .weaknesses()
        .then((w) => setWeaknesses(w.weaknesses ?? []))
        .catch(() => {}),
      puzzlesAPI
        .dailyWarmup()
        .then((w) => setWarmup(w))
        .catch(() => {}),
      puzzlesAPI
        .advantagePositions(10)
        .then((a) => setAdvantagePositions(a))
        .catch(() => {}),
    ]).finally(() => setHubLoading(false));
  }, [session]);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const data = await puzzlesAPI.history({ limit: 50 });
      setHistory(data);
    } catch { /* */ }
    finally { setHistoryLoading(false); }
  }, []);

  // ─── Load puzzles ────────────────────────────────────
  const loadPuzzles = useCallback(async (source?: PuzzleSource) => {
    const src = source ?? puzzleSource;
    setLoading(true);
    try {
      let puzzles: PuzzleItem[] = [];

      if (src === "game" && gameIdParam) {
        // Puzzles from a specific game
        puzzles = await puzzlesAPI.list({ game_id: Number(gameIdParam), limit: 20 });
      } else if (src === "global") {
        // Community puzzles from all users
        puzzles = await puzzlesAPI.global({ limit: 20 });
      } else {
        // User's own puzzles (spaced repetition first)
        puzzles = await puzzlesAPI.reviewQueue(10);
        if (!puzzles || puzzles.length === 0) {
          puzzles = await puzzlesAPI.list({ limit: 10 });
        }
      }

      setQueue(puzzles);
      setCurrentIdx(0);
    } catch {
      // API not ready yet
    } finally {
      setLoading(false);
    }
  }, [puzzleSource, gameIdParam]);

  // Auto-start session if game_id is in URL
  useEffect(() => {
    if (gameIdParam && session) {
      setPuzzleSource("game");
      loadPuzzles("game");
      setView("session");
    }
  }, [gameIdParam, session]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-start session if mode=timed from URL
  useEffect(() => {
    if (timedParam && !gameIdParam && session) {
      loadPuzzles("my");
      setView("session");
    }
  }, [timedParam, session]); // eslint-disable-line react-hooks/exhaustive-deps

  function startSession(source?: PuzzleSource, timed?: boolean) {
    const src = source ?? puzzleSource;
    if (timed !== undefined) setIsTimed(timed);
    setPuzzleSource(src);
    loadPuzzles(src);
    setView("session");
    setSolvedToday(0);
    setCorrectToday(0);
    setStreak(0);
    setIsWarmupSession(false);
  }

  function startWarmup() {
    if (!warmup || warmup.puzzles.length === 0) return;
    // Convert warmup puzzles to PuzzleItem format
    const items: PuzzleItem[] = warmup.puzzles.map((p) => ({
      id: p.id,
      puzzle_key: `warmup-${p.id}`,
      fen: p.fen,
      side_to_move: p.side_to_move,
      best_move_san: p.best_move_san,
      best_move_uci: p.best_move_uci ?? undefined,
      eval_loss_cp: p.eval_loss_cp,
      phase: p.phase,
      puzzle_type: p.puzzle_type,
      difficulty: p.difficulty,
      explanation: null,
      themes: p.themes,
    }));
    setQueue(items);
    setCurrentIdx(0);
    setView("session");
    setSolvedToday(0);
    setCorrectToday(0);
    setStreak(0);
    setIsTimed(false);
    setIsWarmupSession(true);
  }

  function startAdvantageSession() {
    if (!advantagePositions || advantagePositions.positions.length === 0) return;
    const items: PuzzleItem[] = advantagePositions.positions.map((p) => ({
      id: p.id,
      puzzle_key: `advantage-${p.id}`,
      fen: p.fen,
      side_to_move: p.side_to_move,
      best_move_san: p.best_move_san,
      best_move_uci: p.best_move_uci ?? undefined,
      eval_loss_cp: p.cp_loss,
      phase: p.phase,
      puzzle_type: "advantage",
      difficulty: p.advantage_cp > 500 ? "gold" : "silver",
      explanation: null,
      themes: ["advantage_capitalization"],
    }));
    setQueue(items);
    setCurrentIdx(0);
    setView("session");
    setSolvedToday(0);
    setCorrectToday(0);
    setStreak(0);
    setIsTimed(false);
    setIsWarmupSession(false);
  }

  async function startIntuition() {
    setView("intuition");
    setIntuitionIdx(0);
    setIntuitionPicked(null);
    setIntuitionScore(0);
    try {
      const data = await puzzlesAPI.intuitionChallenge(5);
      setIntuitionChallenges(data);
    } catch {
      setIntuitionChallenges({ challenges: [], total: 0 });
    }
  }

  // ─── Handle move ─────────────────────────────────────
  function tryMove(sourceSquare: Square, targetSquare: Square): boolean {
    if (!chessRef.current || !currentPuzzle || puzzleState !== "solving") return false;

    const move = chessRef.current.move({
      from: sourceSquare,
      to: targetSquare,
      promotion: "q",
    });

    if (!move) return false;

    setBoardFen(chessRef.current.fen());
    setSelectedSquare(null);
    setLegalMoves([]);
    playMove();

    const bestMoveSan = currentPuzzle.best_move_san;
    const isCorrect = move.san === bestMoveSan;

    if (isCorrect) {
      setPuzzleState("correct");
      setStreak((s) => {
        const newStreak = s + 1;
        if (newStreak > 0 && newStreak % 5 === 0) playStreak();
        else playCorrect();
        return newStreak;
      });
      setSolvedToday((s) => s + 1);
      setCorrectToday((s) => s + 1);
      reportAttempt(true);
    } else {
      setPuzzleState("incorrect");
      setStreak(0);
      setSolvedToday((s) => s + 1);
      playIncorrect();
      reportAttempt(false);
    }

    return true;
  }

  function onPieceClick(piece: string, square: Square) {
    if (!chessRef.current || puzzleState !== "solving") return;

    const clicked = chessRef.current.get(square);

    if (selectedSquare) {
      // Toggle off when clicking the same piece again
      if (selectedSquare === square) {
        setSelectedSquare(null);
        setLegalMoves([]);
        return;
      }

      // If clicking another friendly piece, just clear selection/dots
      // (do not immediately switch selection)
      if (clicked && clicked.color === chessRef.current.turn()) {
        setSelectedSquare(null);
        setLegalMoves([]);
        return;
      }

      // Otherwise try to move (e.g. capture on enemy piece)
      if (tryMove(selectedSquare, square)) return;
    }

    if (clicked && clicked.color === chessRef.current.turn()) {
      setSelectedSquare(square);
      const moves = chessRef.current.moves({ square, verbose: true });
      setLegalMoves(moves.map((m) => m.to as Square));
    } else {
      setSelectedSquare(null);
      setLegalMoves([]);
    }
  }

  function onSquareClick(square: Square, piece?: string) {
    if (!chessRef.current || puzzleState !== "solving") return;

    const clicked = chessRef.current.get(square);

    if (selectedSquare) {
      // Toggle off when clicking same square
      if (selectedSquare === square) {
        setSelectedSquare(null);
        setLegalMoves([]);
        return;
      }

      // Clicking another friendly piece should clear selection/dots
      if (clicked && clicked.color === chessRef.current.turn()) {
        setSelectedSquare(null);
        setLegalMoves([]);
        return;
      }

      if (tryMove(selectedSquare, square)) return;
    }

    // Fallback selection path: react-chessboard always passes piece on square-click,
    // even when onPieceClick doesn't fire in some interaction modes.
    if (piece) {
      if (clicked && clicked.color === chessRef.current.turn()) {
        setSelectedSquare(square);
        const moves = chessRef.current.moves({ square, verbose: true });
        setLegalMoves(moves.map((m) => m.to as Square));
        return;
      }
    }

    setSelectedSquare(null);
    setLegalMoves([]);
  }

  function onPieceDragBegin(piece: string, square: Square) {
    if (!chessRef.current || puzzleState !== "solving") return;
    const p = chessRef.current.get(square);
    if (p && p.color === chessRef.current.turn()) {
      setSelectedSquare(square);
      const moves = chessRef.current.moves({ square, verbose: true });
      setLegalMoves(moves.map((m) => m.to as Square));
    }
  }

  function onPieceDrop(sourceSquare: string, targetSquare: string): boolean {
    return tryMove(sourceSquare as Square, targetSquare as Square);
  }

  const squareStyles = useMemo(() => {
    const styles: Record<string, CSSProperties> = {};

    if (selectedSquare) {
      styles[selectedSquare] = {
        backgroundColor: "rgba(255, 255, 0, 0.35)",
      };
    }

    for (const sq of legalMoves) {
      const piece = chessRef.current?.get(sq);
      if (piece) {
        styles[sq] = {
          background: "radial-gradient(transparent 56%, rgba(0,0,0,0.35) 56%)",
        };
      } else {
        styles[sq] = {
          background: "radial-gradient(circle, rgba(0,0,0,0.35) 22%, transparent 23%)",
        };
      }
    }

    return styles;
  }, [selectedSquare, legalMoves, boardFen]);

  async function reportAttempt(correct: boolean) {
    if (!currentPuzzle) return;
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    try {
      const res = await puzzlesAPI.attempt(currentPuzzle.id, correct, elapsed);
      if (res.streak > streak) setStreak(res.streak);
    } catch {
      // best-effort
    }
  }

  function nextPuzzle() {
    if (currentIdx < queue.length - 1) {
      setCurrentIdx((i) => i + 1);
    } else if (isWarmupSession) {
      // Warmup finished — mark complete and go back to hub
      puzzlesAPI.completeDailyWarmup().catch(() => {});
      setWarmup((prev) => prev ? { ...prev, completed_today: true } : prev);
      setIsWarmupSession(false);
      playWarmupComplete();
      setView("hub");
    } else {
      loadPuzzles();
    }
  }

  function retryPuzzle() {
    if (!currentPuzzle) return;
    try {
      chessRef.current = new Chess(currentPuzzle.fen);
      setBoardFen(currentPuzzle.fen);
      setPuzzleState("solving");
      setStartTime(Date.now());
      setElapsedSeconds(0);
      setTimedOut(false);
      setSelectedSquare(null);
      setLegalMoves([]);
    } catch {}
  }

  // ─── Auth guard ──────────────────────────────────────
  if (!session) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-500">Sign in to access training puzzles.</p>
      </div>
    );
  }

  const accuracy = solvedToday > 0 ? Math.round((correctToday / solvedToday) * 100) : null;

  // ─── Hub view ────────────────────────────────────────
  if (view === "hub") {
    return (
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
        <div>
          <h1 className="text-2xl font-bold">Train</h1>
          <p className="text-gray-500 mt-1">
            Solve puzzles to improve your game.
          </p>
        </div>

        {/* Top tabs: Train / History */}
        <div className="flex rounded-lg bg-surface-2 p-1">
          <button
            onClick={() => setHubTab("train")}
            className={`flex-1 py-2.5 px-3 rounded-md text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
              hubTab === "train" ? "bg-brand-600 text-white" : "text-gray-400 hover:text-white"
            }`}
          >
            <Dumbbell className="h-4 w-4" /> Train
          </button>
          <button
            onClick={() => { setHubTab("history"); if (!history) loadHistory(); }}
            className={`flex-1 py-2.5 px-3 rounded-md text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
              hubTab === "history" ? "bg-brand-600 text-white" : "text-gray-400 hover:text-white"
            }`}
          >
            <History className="h-4 w-4" /> History
          </button>
        </div>

        {/* ─── History Tab ─── */}
        {hubTab === "history" && (
          <div className="space-y-6">
            {historyLoading ? (
              <div className="flex justify-center py-12">
                <Spinner className="h-8 w-8 text-brand-500" />
              </div>
            ) : !history || history.stats.total_attempts === 0 ? (
              <Card>
                <EmptyState
                  icon={<History className="h-12 w-12" />}
                  title="No attempts yet"
                  description="Start solving puzzles and your history will appear here."
                />
              </Card>
            ) : (
              <>
                {/* Stats summary */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <Card className="p-4 text-center">
                    <p className="text-xs text-gray-500 uppercase">Solved</p>
                    <p className="text-2xl font-bold mt-1">{history.stats.total_attempts}</p>
                  </Card>
                  <Card className="p-4 text-center">
                    <p className="text-xs text-gray-500 uppercase">Accuracy</p>
                    <p className="text-2xl font-bold mt-1 text-brand-400">{history.stats.accuracy}%</p>
                  </Card>
                  <Card className="p-4 text-center">
                    <p className="text-xs text-gray-500 uppercase">Avg Time</p>
                    <p className="text-2xl font-bold mt-1">{history.stats.avg_time ? `${history.stats.avg_time}s` : "—"}</p>
                  </Card>
                  <Card className="p-4 text-center">
                    <p className="text-xs text-gray-500 uppercase">Best Streak</p>
                    <p className="text-2xl font-bold mt-1 text-orange-400">{history.stats.best_streak}</p>
                  </Card>
                </div>

                {/* Attempt list */}
                <Card>
                  <div className="p-5">
                    <h3 className="font-semibold text-sm text-gray-400 uppercase tracking-wider mb-4">Recent Attempts</h3>
                    <div className="space-y-2 max-h-[500px] overflow-y-auto">
                      {history.attempts.map((a) => (
                        <div
                          key={a.id}
                          className={`flex items-center justify-between px-4 py-2.5 rounded-lg text-sm ${
                            a.correct ? "bg-green-900/10 border border-green-800/20" : "bg-red-900/10 border border-red-800/20"
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            {a.correct ? (
                              <CheckCircle className="h-4 w-4 text-green-400" />
                            ) : (
                              <XCircle className="h-4 w-4 text-red-400" />
                            )}
                            <div>
                              <span className="font-medium capitalize">
                                {a.puzzle?.puzzle_type ?? "Puzzle"} • {a.puzzle?.phase ?? ""}
                              </span>
                              <div className="flex items-center gap-2 text-xs text-gray-500">
                                <Badge variant={
                                  a.puzzle?.difficulty === "platinum" || a.puzzle?.difficulty === "gold" ? "warning" :
                                  a.puzzle?.difficulty === "silver" ? "default" : "success"
                                }>
                                  {a.puzzle?.difficulty}
                                </Badge>
                                {a.time_taken && <span>{a.time_taken}s</span>}
                              </div>
                            </div>
                          </div>
                          <span className="text-xs text-gray-500">
                            {a.attempted_at ? new Date(a.attempted_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : ""}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </Card>
              </>
            )}
          </div>
        )}

        {/* ─── Train Tab ─── */}
        {hubTab === "train" && (
          <>

        {/* ─── Daily Warmup ─── */}
        {warmup && !warmup.completed_today && warmup.total_puzzles > 0 && (
          <Card className="p-5 border-amber-500/30 bg-gradient-to-r from-amber-900/10 to-orange-900/10">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="h-12 w-12 rounded-xl bg-amber-500/20 flex items-center justify-center">
                  <Sunrise className="h-6 w-6 text-amber-400" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold">Daily Warmup</h2>
                  <p className="text-sm text-gray-400">
                    {warmup.total_puzzles} puzzles • Review + Weak spots + Fresh
                  </p>
                </div>
              </div>
              <Button onClick={startWarmup} size="lg" className="bg-amber-600 hover:bg-amber-500 border-0">
                <Sunrise className="h-5 w-5" />
                Start
              </Button>
            </div>
          </Card>
        )}
        {warmup?.completed_today && (
          <Card className="p-4 border-green-800/30 bg-green-900/10">
            <div className="flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-green-400" />
              <span className="text-sm text-green-300 font-medium">Daily Warmup Complete ✓</span>
            </div>
          </Card>
        )}

        {/* Puzzle source tabs */}
        <div className="flex rounded-lg bg-surface-2 p-1">
          {[
            { key: "my" as PuzzleSource, label: "My Puzzles", icon: <User className="h-4 w-4" /> },
            { key: "global" as PuzzleSource, label: "Global Puzzles", icon: <Globe className="h-4 w-4" /> },
          ].map(({ key, label, icon }) => (
            <button
              key={key}
              onClick={() => setPuzzleSource(key)}
              className={`flex-1 py-2.5 px-3 rounded-md text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                puzzleSource === key
                  ? "bg-brand-600 text-white"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {icon}
              {label}
            </button>
          ))}
        </div>

        {hubLoading ? (
          <div className="flex justify-center py-12">
            <Spinner className="h-8 w-8 text-brand-500" />
          </div>
        ) : (
          <>
            {/* Source-specific content */}
            {puzzleSource === "my" && (
              <>
                {/* Today's Training Focus */}
                {weaknesses.length > 0 && (
                  <Card className="p-6 border-brand-600/30">
                    <div className="flex items-start gap-4">
                      <div className="h-12 w-12 rounded-xl bg-brand-600/20 flex items-center justify-center flex-shrink-0">
                        <Target className="h-6 w-6 text-brand-400" />
                      </div>
                      <div className="flex-1">
                        <h2 className="text-lg font-semibold mb-1">Today&apos;s Focus</h2>
                        <p className="text-sm text-gray-400 mb-1">{weaknesses[0].area}</p>
                        <p className="text-sm text-gray-500">{weaknesses[0].message}</p>
                      </div>
                    </div>
                    <Button onClick={() => startSession("my")} className="w-full mt-5" size="lg">
                      <Dumbbell className="h-5 w-5" />
                      Start Training Session
                    </Button>
                  </Card>
                )}

                {weaknesses.length === 0 && (
                  <Card className="p-6 text-center">
                    <Dumbbell className="h-10 w-10 text-gray-600 mx-auto mb-3" />
                    <h2 className="text-lg font-semibold mb-2">Ready to train?</h2>
                    <p className="text-sm text-gray-500 mb-5">
                      Analyze some games first, and we&apos;ll generate puzzles from your mistakes.
                    </p>
                    <Button onClick={() => startSession("my")} size="lg">
                      <Dumbbell className="h-5 w-5" />
                      Start Session
                    </Button>
                  </Card>
                )}

                {/* From Your Mistakes — top 3 weakness cards */}
                {weaknesses.length > 1 && (
                  <div>
                    <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">
                      From Your Mistakes
                    </h2>
                    <div className="grid gap-3 sm:grid-cols-3">
                      {weaknesses.slice(0, 3).map((w, i) => {
                        const isTimeMgmt = w.area.toLowerCase().includes("time");
                        return (
                          <Card
                            key={i}
                            className={`p-4 cursor-pointer transition-colors ${
                              isTimeMgmt ? "hover:border-yellow-500/50 border-yellow-600/20" : "hover:border-brand-600/50"
                            }`}
                            onClick={() => startSession("my", isTimeMgmt)}
                          >
                            <div className="flex items-center gap-2 mb-2">
                              {isTimeMgmt ? (
                                <Clock className={`h-4 w-4 text-yellow-400`} />
                              ) : (
                                <AlertTriangle
                                  className={`h-4 w-4 ${
                                    w.severity === "high"
                                      ? "text-red-400"
                                      : w.severity === "medium"
                                      ? "text-yellow-400"
                                      : "text-gray-400"
                                  }`}
                                />
                              )}
                              <span className="font-semibold text-sm">{w.area}</span>
                            </div>
                            <p className="text-xs text-gray-500 line-clamp-2">
                              {w.message}
                            </p>
                            <p className={`text-xs mt-2 flex items-center gap-1 ${
                              isTimeMgmt ? "text-yellow-400" : "text-brand-400"
                            }`}>
                              {isTimeMgmt ? "⏱ Timed Training" : "Practice"} <ArrowRight className="h-3 w-3" />
                            </p>
                          </Card>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* ─── Training Modes ─── */}
                <div>
                  <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">
                    Training Modes
                  </h2>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {/* Advantage Capitalization */}
                    {advantagePositions && advantagePositions.total > 0 && (
                      <Card
                        className="p-4 cursor-pointer transition-colors hover:border-amber-500/50 border-amber-600/20"
                        onClick={startAdvantageSession}
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <Trophy className="h-4 w-4 text-amber-400" />
                          <span className="font-semibold text-sm">Capitalize Advantages</span>
                        </div>
                        <p className="text-xs text-gray-500 line-clamp-2">
                          {advantagePositions.total} positions where you were winning but didn&apos;t convert.
                        </p>
                        <p className="text-xs mt-2 text-amber-400 flex items-center gap-1">
                          Practice <ArrowRight className="h-3 w-3" />
                        </p>
                      </Card>
                    )}

                    {/* Blunder Preventer */}
                    <Card
                      className="p-4 cursor-pointer transition-colors hover:border-red-500/50 border-red-600/20"
                      onClick={() => startSession("my")}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <Shield className="h-4 w-4 text-red-400" />
                        <span className="font-semibold text-sm">Blunder Preventer</span>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">
                        Can you find the safe move? Avoid the blunders from your games.
                      </p>
                      <p className="text-xs mt-2 text-red-400 flex items-center gap-1">
                        Practice <ArrowRight className="h-3 w-3" />
                      </p>
                    </Card>

                    {/* Intuition Trainer */}
                    <Card
                      className="p-4 cursor-pointer transition-colors hover:border-purple-500/50 border-purple-600/20"
                      onClick={startIntuition}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <Eye className="h-4 w-4 text-purple-400" />
                        <span className="font-semibold text-sm">Intuition Trainer</span>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">
                        Spot the blunder! Given 4 moves, can you identify which one was the mistake?
                      </p>
                      <p className="text-xs mt-2 text-purple-400 flex items-center gap-1">
                        Play <ArrowRight className="h-3 w-3" />
                      </p>
                    </Card>
                  </div>
                </div>
              </>
            )}

            {puzzleSource === "global" && (
              <Card className="p-6 text-center">
                <Globe className="h-10 w-10 text-brand-400 mx-auto mb-3" />
                <h2 className="text-lg font-semibold mb-2">Community Puzzles</h2>
                <p className="text-sm text-gray-500 mb-5">
                  Solve puzzles generated from games across all users.
                  Fresh positions you haven&apos;t seen before.
                </p>
                <Button onClick={() => startSession("global")} size="lg">
                  <Globe className="h-5 w-5" />
                  Start Global Session
                </Button>
              </Card>
            )}
          </>
        )}

          </>
        )}
      </div>
    );
  }

  // ─── Intuition Trainer view ──────────────────────────
  if (view === "intuition") {
    const challenge = intuitionChallenges?.challenges[intuitionIdx];
    const isLast = intuitionIdx >= (intuitionChallenges?.total ?? 0) - 1;

    return (
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Eye className="h-6 w-6 text-purple-400" /> Intuition Trainer
            </h1>
            <p className="text-gray-500 mt-1">
              Spot the blunder among these moves
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="default">
              Score: {intuitionScore}/{intuitionIdx + (intuitionPicked !== null ? 1 : 0)}
            </Badge>
            <Button variant="ghost" size="sm" onClick={() => setView("hub")}>
              ← Back
            </Button>
          </div>
        </div>

        {!intuitionChallenges ? (
          <div className="flex justify-center py-12">
            <Spinner className="h-8 w-8 text-purple-500" />
          </div>
        ) : !challenge ? (
          <Card className="p-8 text-center">
            <Eye className="h-12 w-12 text-purple-400 mx-auto mb-4" />
            <h2 className="text-xl font-semibold mb-2">
              {intuitionChallenges.total === 0
                ? "No challenges available"
                : `Session Complete! ${intuitionScore}/${intuitionChallenges.total} correct`}
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              {intuitionChallenges.total === 0
                ? "Analyze more games to generate intuition challenges."
                : "Great work training your chess intuition!"}
            </p>
            <Button onClick={() => setView("hub")}>Back to Hub</Button>
          </Card>
        ) : (
          <>
            <p className="text-sm text-gray-400 text-center">
              Challenge {intuitionIdx + 1} of {intuitionChallenges.total} — Which move is the blunder?
            </p>
            <div className="grid grid-cols-2 gap-4">
              {challenge.options.map((opt, i) => {
                const picked = intuitionPicked !== null;
                const isThis = intuitionPicked === i;
                const isBlunder = opt.is_blunder;

                let borderClass = "border-surface-3 hover:border-purple-500/50";
                if (picked) {
                  if (isBlunder) borderClass = "border-green-500 bg-green-900/10";
                  else if (isThis) borderClass = "border-red-500 bg-red-900/10";
                  else borderClass = "border-surface-3 opacity-60";
                }

                return (
                  <Card
                    key={i}
                    className={`p-5 cursor-pointer transition-all ${borderClass} ${!picked ? "hover:scale-[1.02]" : ""}`}
                    onClick={() => {
                      if (picked) return;
                      setIntuitionPicked(i);
                      if (isBlunder) setIntuitionScore((s) => s + 1);
                    }}
                  >
                    <div className="text-center">
                      <p className="text-xs text-gray-500 mb-1">Move {opt.move_number}</p>
                      <p className="text-2xl font-bold font-mono">{opt.san}</p>
                      <Badge className="mt-2" variant="default">{opt.phase}</Badge>
                      {picked && isBlunder && (
                        <p className="text-xs text-red-400 mt-2">Blunder! (−{opt.cp_loss} cp)</p>
                      )}
                      {picked && isThis && !isBlunder && (
                        <p className="text-xs text-gray-500 mt-2">Not a blunder (−{opt.cp_loss} cp)</p>
                      )}
                    </div>
                  </Card>
                );
              })}
            </div>
            {intuitionPicked !== null && (
              <div className="flex justify-center">
                <Button
                  onClick={() => {
                    if (isLast) {
                      setIntuitionIdx((i) => i + 1); // triggers "complete" screen
                    } else {
                      setIntuitionIdx((i) => i + 1);
                      setIntuitionPicked(null);
                    }
                  }}
                  size="lg"
                >
                  {isLast ? "See Results" : "Next Challenge"} <ArrowRight className="h-4 w-4 ml-1" />
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    );
  }

  // ─── Session view — puzzle board ─────────────────────
  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">
            {isTimed
              ? "⏱ Timed Training"
              : puzzleSource === "game"
              ? "Game Puzzles"
              : puzzleSource === "global"
              ? "Global Puzzles"
              : "Training Session"}
          </h1>
          <p className="text-gray-500 mt-1">
            {puzzleSource === "game"
              ? `Puzzles from game #${gameIdParam}`
              : puzzleSource === "global"
              ? "Community puzzles from all users"
              : "Find the best move."}
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setView("hub")}>
          End Session
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner className="h-8 w-8 text-brand-500" />
        </div>
      ) : !currentPuzzle ? (
        <Card>
          <EmptyState
            icon={<Dumbbell className="h-12 w-12" />}
            title="No puzzles available"
            description="Analyze some games first — puzzles will be generated from your mistakes."
            action={
              <Button variant="secondary" onClick={() => loadPuzzles()}>
                <RotateCcw className="h-4 w-4" /> Retry
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Board */}
          <div className="flex-1 max-w-[560px]">
            {/* Timer */}
            <div className={`text-center mb-3 font-mono text-3xl font-bold transition-colors ${
              puzzleState === "correct" ? "text-green-400" :
              puzzleState === "incorrect" || timedOut ? "text-red-400" :
              isTimed && elapsedSeconds >= RED_AT ? "text-red-400 animate-pulse" :
              isTimed && elapsedSeconds >= YELLOW_AT ? "text-yellow-400" :
              "text-gray-400"
            }`}>
              {isTimed && puzzleState === "solving" && (
                <div className="text-xs text-gray-500 font-sans font-normal mb-1 flex items-center justify-center gap-1">
                  <Clock className="h-3 w-3" /> Time Limit: {TIMED_LIMIT}s
                </div>
              )}
              <span>{Math.floor(elapsedSeconds / 60)}:{(elapsedSeconds % 60).toString().padStart(2, '0')}</span>
            </div>

            <div className="relative">
              <Chessboard
                position={boardFen}
                onPieceClick={onPieceClick}
                onSquareClick={onSquareClick}
                onPieceDragBegin={onPieceDragBegin}
                onPieceDrop={onPieceDrop}
                boardOrientation={boardOrientation}
                boardWidth={560}
                arePiecesDraggable={puzzleState === "solving"}
                customSquareStyles={squareStyles}
                customBoardStyle={{
                  borderRadius: "8px",
                  boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
                }}
                customDarkSquareStyle={{ backgroundColor: "#779952" }}
                customLightSquareStyle={{ backgroundColor: "#edeed1" }}
              />

              {/* Feedback overlay */}
              <AnimatePresence>
              {puzzleState !== "solving" && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  transition={{ duration: 0.2 }}
                  className="absolute inset-0 flex items-center justify-center bg-black/40 rounded-lg"
                >
                  <motion.div
                    initial={{ y: 20 }}
                    animate={{ y: 0 }}
                    transition={{ type: "spring", stiffness: 300, damping: 20 }}
                    className={`flex flex-col items-center gap-3 px-8 py-6 rounded-xl ${
                      puzzleState === "correct"
                        ? "bg-green-900/90"
                        : "bg-red-900/90"
                    }`}
                  >
                    {puzzleState === "correct" ? (
                      <>
                        <CheckCircle className="h-12 w-12 text-green-400" />
                        <p className="text-lg font-bold text-green-300">
                          Correct!
                        </p>
                      </>
                    ) : (
                      <>
                        {timedOut ? (
                          <Clock className="h-12 w-12 text-red-400" />
                        ) : (
                          <XCircle className="h-12 w-12 text-red-400" />
                        )}
                        <p className="text-lg font-bold text-red-300">
                          {timedOut ? "Time\u2019s Up!" : "Incorrect"}
                        </p>
                        <p className="text-sm text-red-400/80">
                          Best move was{" "}
                          <span className="font-mono font-bold">
                            {currentPuzzle.best_move_san}
                          </span>
                        </p>
                      </>
                    )}
                    <div className="flex gap-2 mt-2">
                      {puzzleState === "incorrect" && (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={retryPuzzle}
                        >
                          <RotateCcw className="h-4 w-4" /> Retry
                        </Button>
                      )}
                      <Button size="sm" onClick={nextPuzzle}>
                        <SkipForward className="h-4 w-4" /> Next
                      </Button>
                    </div>
                  </motion.div>
                </motion.div>
              )}
              </AnimatePresence>
            </div>

            {/* Prompt */}
            <div className="mt-4 text-center">
              <p className="text-sm text-gray-400">
                {boardOrientation === "white"
                  ? "Find the best move for White"
                  : "Find the best move for Black"}
              </p>
            </div>
          </div>

          {/* Info panel */}
          <div className="lg:w-[280px] space-y-4">
            <Card>
              <CardContent>
                <h3 className="font-semibold text-sm text-gray-400 uppercase tracking-wider mb-3">
                  Puzzle Info
                </h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Difficulty</span>
                    <Badge
                      variant={
                        currentPuzzle.difficulty === "hard"
                          ? "danger"
                          : currentPuzzle.difficulty === "medium"
                          ? "warning"
                          : "success"
                      }
                    >
                      {currentPuzzle.difficulty}
                    </Badge>
                  </div>
                  {currentPuzzle.themes?.length > 0 && (
                    <div className="flex justify-between items-start">
                      <span className="text-gray-500">Themes</span>
                      <div className="flex flex-wrap gap-1 justify-end">
                        {currentPuzzle.themes.map((t) => (
                          <Badge key={t} variant="default">
                            {t}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-gray-500">Eval loss</span>
                    <span className="text-gray-300">
                      {currentPuzzle.eval_loss_cp} cp
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <h3 className="font-semibold text-sm text-gray-400 uppercase tracking-wider mb-3">
                  Session Stats
                </h3>
                <div className="space-y-3 text-sm">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <motion.div
                        key={streak}
                        initial={streak > 0 ? { scale: 1.4, rotate: -10 } : {}}
                        animate={{ scale: 1, rotate: 0 }}
                        transition={{ type: "spring", stiffness: 400, damping: 15 }}
                      >
                        <Flame
                          className={`h-4 w-4 ${
                            streak > 0 ? "text-orange-400" : "text-gray-600"
                          }`}
                        />
                      </motion.div>
                      <span className="text-gray-500">Streak</span>
                    </div>
                    <span
                      className={`font-bold text-lg ${
                        streak >= 5
                          ? "text-orange-400"
                          : streak > 0
                          ? "text-gray-300"
                          : "text-gray-600"
                      }`}
                    >
                      {streak}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Zap className="h-4 w-4 text-gray-600" />
                      <span className="text-gray-500">Solved today</span>
                    </div>
                    <span className="font-semibold text-gray-300">
                      {solvedToday}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Accuracy</span>
                    <span className="font-semibold text-gray-300">
                      {accuracy !== null ? `${accuracy}%` : "—"}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Queue progress */}
            <div className="text-center text-xs text-gray-600">
              Puzzle {currentIdx + 1} of {queue.length}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

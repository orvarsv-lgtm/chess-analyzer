"use client";

import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSession } from "next-auth/react";
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
} from "lucide-react";
import { puzzlesAPI, insightsAPI, type PuzzleItem, type Weakness } from "@/lib/api";
import {
  Button,
  Badge,
  Card,
  CardContent,
  EmptyState,
  Spinner,
} from "@/components/ui";

type TrainView = "hub" | "session";
type PuzzleState = "solving" | "correct" | "incorrect";

export default function TrainPage() {
  const { data: session } = useSession();

  // ─── View state ──────────────────────────────────────
  const [view, setView] = useState<TrainView>("hub");

  // ─── Hub data ────────────────────────────────────────
  const [weaknesses, setWeaknesses] = useState<Weakness[]>([]);
  const [hubLoading, setHubLoading] = useState(true);

  // ─── Puzzle queue state ──────────────────────────────
  const [queue, setQueue] = useState<PuzzleItem[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [loading, setLoading] = useState(false);

  // ─── Solving state ───────────────────────────────────
  const [puzzleState, setPuzzleState] = useState<PuzzleState>("solving");
  const [startTime, setStartTime] = useState(0);
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
      setSelectedSquare(null);
      setLegalMoves([]);
    }
  }, [currentPuzzle]);

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
    insightsAPI
      .weaknesses()
      .then((w) => setWeaknesses(w.weaknesses ?? []))
      .catch(() => {})
      .finally(() => setHubLoading(false));
  }, [session]);

  // ─── Load puzzles ────────────────────────────────────
  const loadPuzzles = useCallback(async () => {
    setLoading(true);
    try {
      let puzzles = await puzzlesAPI.reviewQueue(10);
      if (!puzzles || puzzles.length === 0) {
        puzzles = await puzzlesAPI.list({ limit: 10 });
      }
      setQueue(puzzles);
      setCurrentIdx(0);
    } catch {
      // API not ready yet
    } finally {
      setLoading(false);
    }
  }, []);

  function startSession() {
    loadPuzzles();
    setView("session");
    setSolvedToday(0);
    setCorrectToday(0);
    setStreak(0);
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

    const bestMoveSan = currentPuzzle.best_move_san;
    const isCorrect = move.san === bestMoveSan;

    if (isCorrect) {
      setPuzzleState("correct");
      setStreak((s) => s + 1);
      setSolvedToday((s) => s + 1);
      setCorrectToday((s) => s + 1);
      reportAttempt(true);
    } else {
      setPuzzleState("incorrect");
      setStreak(0);
      setSolvedToday((s) => s + 1);
      reportAttempt(false);
    }

    return true;
  }

  function onPieceClick(piece: string, square: Square) {
    if (!chessRef.current || puzzleState !== "solving") return;

    if (selectedSquare && selectedSquare !== square) {
      if (tryMove(selectedSquare, square)) return;
    }

    const p = chessRef.current.get(square);
    if (p && p.color === chessRef.current.turn()) {
      setSelectedSquare(square);
      const moves = chessRef.current.moves({ square, verbose: true });
      setLegalMoves(moves.map((m) => m.to as Square));
    } else {
      setSelectedSquare(null);
      setLegalMoves([]);
    }
  }

  function onSquareClick(square: Square) {
    if (!chessRef.current || puzzleState !== "solving") return;

    if (selectedSquare) {
      if (tryMove(selectedSquare, square)) return;
    }

    setSelectedSquare(null);
    setLegalMoves([]);
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
            Solve puzzles generated from your own mistakes.
          </p>
        </div>

        {hubLoading ? (
          <div className="flex justify-center py-12">
            <Spinner className="h-8 w-8 text-brand-500" />
          </div>
        ) : (
          <>
            {/* Today's Training Focus */}
            {weaknesses.length > 0 && (
              <Card className="p-6 border-brand-600/30">
                <div className="flex items-start gap-4">
                  <div className="h-12 w-12 rounded-xl bg-brand-600/20 flex items-center justify-center flex-shrink-0">
                    <Target className="h-6 w-6 text-brand-400" />
                  </div>
                  <div className="flex-1">
                    <h2 className="text-lg font-semibold mb-1">Today's Focus</h2>
                    <p className="text-sm text-gray-400 mb-1">{weaknesses[0].area}</p>
                    <p className="text-sm text-gray-500">{weaknesses[0].message}</p>
                  </div>
                </div>
                <Button onClick={startSession} className="w-full mt-5" size="lg">
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
                  Analyze some games first, and we'll generate puzzles from your mistakes.
                </p>
                <Button onClick={startSession} size="lg">
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
                  {weaknesses.slice(0, 3).map((w, i) => (
                    <Card
                      key={i}
                      className="p-4 cursor-pointer hover:border-brand-600/50 transition-colors"
                      onClick={startSession}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <AlertTriangle
                          className={`h-4 w-4 ${
                            w.severity === "high"
                              ? "text-red-400"
                              : w.severity === "medium"
                              ? "text-yellow-400"
                              : "text-gray-400"
                          }`}
                        />
                        <span className="font-semibold text-sm">{w.area}</span>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">
                        {w.message}
                      </p>
                      <p className="text-xs text-brand-400 mt-2 flex items-center gap-1">
                        Practice <ArrowRight className="h-3 w-3" />
                      </p>
                    </Card>
                  ))}
                </div>
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
          <h1 className="text-2xl font-bold">Training Session</h1>
          <p className="text-gray-500 mt-1">
            Find the best move.
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
              <Button variant="secondary" onClick={loadPuzzles}>
                <RotateCcw className="h-4 w-4" /> Retry
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Board */}
          <div className="flex-1 max-w-[560px]">
            <div className="relative">
              <Chessboard
                position={boardFen}
                onPieceClick={onPieceClick}
                onSquareClick={onSquareClick}
                boardOrientation={boardOrientation}
                boardWidth={560}
                arePiecesDraggable={false}
                customSquareStyles={squareStyles}
                customBoardStyle={{
                  borderRadius: "8px",
                  boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
                }}
                customDarkSquareStyle={{ backgroundColor: "#779952" }}
                customLightSquareStyle={{ backgroundColor: "#edeed1" }}
              />

              {/* Feedback overlay */}
              {puzzleState !== "solving" && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/40 rounded-lg">
                  <div
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
                        <XCircle className="h-12 w-12 text-red-400" />
                        <p className="text-lg font-bold text-red-300">
                          Incorrect
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
                  </div>
                </div>
              )}
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
                      <Flame
                        className={`h-4 w-4 ${
                          streak > 0 ? "text-orange-400" : "text-gray-600"
                        }`}
                      />
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

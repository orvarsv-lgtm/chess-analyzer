"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
} from "lucide-react";
import { puzzlesAPI, type PuzzleItem } from "@/lib/api";
import {
  Button,
  Badge,
  Card,
  CardContent,
  EmptyState,
  Spinner,
} from "@/components/ui";

type PuzzleState = "solving" | "correct" | "incorrect";

export default function TrainPage() {
  const { data: session } = useSession();

  // ─── Puzzle queue state ──────────────────────────────
  const [queue, setQueue] = useState<PuzzleItem[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [loading, setLoading] = useState(true);

  // ─── Solving state ───────────────────────────────────
  const [puzzleState, setPuzzleState] = useState<PuzzleState>("solving");
  const [startTime, setStartTime] = useState(0);

  // ─── Stats ───────────────────────────────────────────
  const [streak, setStreak] = useState(0);
  const [solvedToday, setSolvedToday] = useState(0);
  const [correctToday, setCorrectToday] = useState(0);

  const currentPuzzle = queue[currentIdx] ?? null;

  // ─── Chess instance for puzzle position ──────────────
  const chess = useMemo(() => {
    if (!currentPuzzle) return null;
    try {
      return new Chess(currentPuzzle.fen);
    } catch {
      return null;
    }
  }, [currentPuzzle]);

  const [boardFen, setBoardFen] = useState(currentPuzzle?.fen ?? "start");

  useEffect(() => {
    if (currentPuzzle) {
      setBoardFen(currentPuzzle.fen);
      setPuzzleState("solving");
      setStartTime(Date.now());
    }
  }, [currentPuzzle]);

  // Determine board orientation from FEN (side to move)
  const boardOrientation = useMemo(() => {
    if (!currentPuzzle?.fen) return "white" as const;
    // The puzzle FEN has the side that needs to find the best move
    const parts = currentPuzzle.fen.split(" ");
    return parts[1] === "w" ? ("white" as const) : ("black" as const);
  }, [currentPuzzle?.fen]);

  // ─── Load puzzles ────────────────────────────────────
  const loadPuzzles = useCallback(async () => {
    setLoading(true);
    try {
      // Try review queue first (spaced repetition), fallback to general
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

  useEffect(() => {
    if (session) loadPuzzles();
  }, [session, loadPuzzles]);

  // ─── Handle move ─────────────────────────────────────
  function onDrop(sourceSquare: Square, targetSquare: Square): boolean {
    if (!chess || !currentPuzzle || puzzleState !== "solving") return false;

    // Attempt the move
    const move = chess.move({
      from: sourceSquare,
      to: targetSquare,
      promotion: "q", // Auto-promote to queen
    });

    if (!move) return false;

    setBoardFen(chess.fen());

    // Check if this is the best move
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

  async function reportAttempt(correct: boolean) {
    if (!currentPuzzle) return;
    const elapsed = Math.round((Date.now() - startTime) / 1000);
    try {
      const res = await puzzlesAPI.attempt(currentPuzzle.id, correct, elapsed);
      if (res.streak > streak) setStreak(res.streak);
    } catch {
      // Attempt reporting is best-effort
    }
  }

  function nextPuzzle() {
    if (currentIdx < queue.length - 1) {
      setCurrentIdx((i) => i + 1);
    } else {
      // Reload queue
      loadPuzzles();
    }
  }

  function retryPuzzle() {
    if (!currentPuzzle) return;
    try {
      const c = new Chess(currentPuzzle.fen);
      setBoardFen(c.fen());
      setPuzzleState("solving");
      setStartTime(Date.now());
    } catch {
      // noop
    }
  }

  // ─── Render ──────────────────────────────────────────
  if (!session) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-500">Sign in to access training puzzles.</p>
      </div>
    );
  }

  const accuracy =
    solvedToday > 0
      ? Math.round((correctToday / solvedToday) * 100)
      : null;

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">Train</h1>
        <p className="text-gray-500 mt-1">
          Solve puzzles generated from your own mistakes.
        </p>
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
                onPieceDrop={onDrop}
                boardOrientation={boardOrientation}
                boardWidth={560}
                arePiecesDraggable={puzzleState === "solving"}
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

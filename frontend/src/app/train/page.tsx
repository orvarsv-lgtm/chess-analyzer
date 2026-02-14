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
  SlidersHorizontal,
  ChevronDown,
  BookOpen,
} from "lucide-react";
import { puzzlesAPI, insightsAPI, openingsAPI, explanationsAPI, type PuzzleItem, type Weakness, type PuzzleHistoryResponse, type DailyWarmupResponse, type AdvantagePositionsResponse, type IntuitionChallengeResponse } from "@/lib/api";
import { playMove, playCorrect, playIncorrect, playStreak, playWarmupComplete } from "@/lib/sounds";
import {
  Button,
  Badge,
  Card,
  CardContent,
  EmptyState,
  Spinner,
} from "@/components/ui";

type TrainView = "hub" | "session" | "intuition" | "opening-drill";
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
  const tacticParam = searchParams.get("tactic");
  const phaseParam = searchParams.get("phase");
  const modeParam = searchParams.get("mode");

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
  const [intuitionPreviewIdx, setIntuitionPreviewIdx] = useState(0);

  // ─── Opening Drill ──────────────────────────────────
  type OpeningTreeNode = { san: string; uci?: string; games: number; wins: number; draws: number; losses: number; win_rate: number; best_move_san?: string | null; eval_cp?: number | null; children: OpeningTreeNode[] };
  const [openingTree, setOpeningTree] = useState<OpeningTreeNode[]>([]);
  const [openingDrillColor, setOpeningDrillColor] = useState<"white" | "black">("white");
  const [openingDrillGame] = useState(() => new Chess());
  const [openingDrillFen, setOpeningDrillFen] = useState("start");
  const [openingDrillMoves, setOpeningDrillMoves] = useState<string[]>([]);
  const [openingDrillState, setOpeningDrillState] = useState<"playing" | "validating" | "correct" | "wrong" | "done">("playing");
  const [openingDrillHint, setOpeningDrillHint] = useState<string>("");
  const [openingDrillScore, setOpeningDrillScore] = useState({ correct: 0, total: 0 });
  const [openingDrillCurrentPath, setOpeningDrillCurrentPath] = useState<OpeningTreeNode[]>([]);
  const [openingDrillExplanation, setOpeningDrillExplanation] = useState<string>("");
  const [openingDrillExplanationLoading, setOpeningDrillExplanationLoading] = useState(false);
  const [openingDrillSelectedSquare, setOpeningDrillSelectedSquare] = useState<Square | null>(null);
  const [openingDrillLegalMoves, setOpeningDrillLegalMoves] = useState<Square[]>([]);
  const [openingDrillWrongFen, setOpeningDrillWrongFen] = useState<string>("");
  const [openingDrillWrongMoveIdx, setOpeningDrillWrongMoveIdx] = useState<number>(0);

  // ─── Puzzle queue state ──────────────────────────────
  const [queue, setQueue] = useState<PuzzleItem[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [loading, setLoading] = useState(false);

  // ─── Puzzle Options / Filters ────────────────────────
  const [filterTactic, setFilterTactic] = useState<string>("");
  const [filterPhase, setFilterPhase] = useState<string>("");
  const [filterType, setFilterType] = useState<string>("");
  const [showOptions, setShowOptions] = useState(false);
  const hasFilters = filterTactic || filterPhase || filterType;

  const puzzleFilters = useMemo(() => {
    const f: { tactic?: string; phase?: string; puzzle_type?: string } = {};
    if (filterTactic) f.tactic = filterTactic;
    if (filterPhase) f.phase = filterPhase;
    if (filterType) f.puzzle_type = filterType;
    return f;
  }, [filterTactic, filterPhase, filterType]);

  // ─── Solving state ───────────────────────────────────
  const [puzzleState, setPuzzleState] = useState<PuzzleState>("solving");
  const [startTime, setStartTime] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [timedOut, setTimedOut] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval>>();
  const [selectedSquare, setSelectedSquare] = useState<Square | null>(null);
  const [legalMoves, setLegalMoves] = useState<Square[]>([]);

  // ─── Multi-move sequence state ───────────────────────
  const [seqIdx, setSeqIdx] = useState(0); // current index in solution_line (0, 2, 4 = user moves)
  const [isOpponentMoving, setIsOpponentMoving] = useState(false);

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
      setSeqIdx(0);
      setIsOpponentMoving(false);
    }
  }, [currentPuzzle]);

  // Derived: how many user moves are in this puzzle's solution
  const solutionLine = currentPuzzle?.solution_line ?? [];
  const totalUserMoves = solutionLine.length > 0
    ? Math.ceil(solutionLine.length / 2)
    : 1; // single-move fallback
  const currentUserMoveNum = Math.floor(seqIdx / 2) + 1;

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
  const loadPuzzles = useCallback(async (source?: PuzzleSource, filters?: { tactic?: string; phase?: string; puzzle_type?: string }) => {
    const src = source ?? puzzleSource;
    const f = filters ?? puzzleFilters;
    setLoading(true);
    try {
      let puzzles: PuzzleItem[] = [];

      if (src === "game" && gameIdParam) {
        // Puzzles from a specific game
        puzzles = await puzzlesAPI.list({ game_id: Number(gameIdParam), limit: 20, ...f });
      } else if (src === "global") {
        // Community puzzles from all users
        puzzles = await puzzlesAPI.global({ limit: 20, ...f });
      } else {
        // User's own puzzles (spaced repetition first, then own, then global fallback)
        puzzles = await puzzlesAPI.reviewQueue(10);
        if (!puzzles || puzzles.length === 0) {
          puzzles = await puzzlesAPI.list({ limit: 10, ...f });
        }
        // If still no puzzles from user's games, fall back to global pool
        if (!puzzles || puzzles.length === 0) {
          puzzles = await puzzlesAPI.global({ limit: 10, ...f });
        }
      }

      setQueue(puzzles);
      setCurrentIdx(0);
    } catch {
      // API not ready yet
    } finally {
      setLoading(false);
    }
  }, [puzzleSource, gameIdParam, puzzleFilters]);

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

  // Auto-start from URL params (coach report CTAs)
  useEffect(() => {
    if (!session || gameIdParam || timedParam) return;

    // ?mode=warmup → start daily warmup directly
    if (modeParam === "warmup") {
      puzzlesAPI.dailyWarmup().then((w) => {
        if (w && w.puzzles.length > 0) {
          setWarmup(w);
          const items: PuzzleItem[] = w.puzzles.map((p) => ({
            id: p.id, puzzle_key: `warmup-${p.id}`, fen: p.fen,
            side_to_move: p.side_to_move, best_move_san: p.best_move_san,
            best_move_uci: p.best_move_uci ?? undefined, eval_loss_cp: p.eval_loss_cp,
            phase: p.phase, puzzle_type: p.puzzle_type, explanation: null, themes: p.themes,
          }));
          setQueue(items); setCurrentIdx(0); setView("session");
          setSolvedToday(0); setCorrectToday(0); setStreak(0); setIsWarmupSession(true);
        } else { loadPuzzles("my"); setView("session"); }
      }).catch(() => { loadPuzzles("my"); setView("session"); });
      return;
    }

    // ?mode=advantage → start advantage capitalization directly
    if (modeParam === "advantage") {
      puzzlesAPI.advantagePositions(10).then((a) => {
        if (a && a.positions.length > 0) {
          setAdvantagePositions(a);
          const items: PuzzleItem[] = a.positions.map((p) => ({
            id: p.id, puzzle_key: `advantage-${p.id}`, fen: p.fen,
            side_to_move: p.side_to_move, best_move_san: p.best_move_san,
            best_move_uci: p.best_move_uci ?? undefined, eval_loss_cp: p.cp_loss,
            phase: p.phase, puzzle_type: "advantage", explanation: null,
            themes: ["advantage_capitalization"],
          }));
          setQueue(items); setCurrentIdx(0); setView("session");
          setSolvedToday(0); setCorrectToday(0); setStreak(0); setIsWarmupSession(false);
        } else { loadPuzzles("my"); setView("session"); }
      }).catch(() => { loadPuzzles("my"); setView("session"); });
      return;
    }

    // ?mode=intuition → start intuition trainer directly
    if (modeParam === "intuition") {
      startIntuition();
      return;
    }

    // ?tactic=fork or ?phase=endgame → start filtered puzzle session
    if (tacticParam || phaseParam) {
      const filters: { tactic?: string; phase?: string } = {};
      if (tacticParam) { setFilterTactic(tacticParam); filters.tactic = tacticParam; }
      if (phaseParam) { setFilterPhase(phaseParam); filters.phase = phaseParam; }
      loadPuzzles("global", filters);
      setView("session");
      return;
    }
  }, [tacticParam, phaseParam, modeParam, session]); // eslint-disable-line react-hooks/exhaustive-deps

  function weaknessToFilters(w: Weakness): { tactic?: string; phase?: string; puzzle_type?: string } {
    const area = w.area.toLowerCase();
    if (area === "opening") return { phase: "opening" };
    if (area === "middlegame") return { phase: "middlegame" };
    if (area === "endgame") return { phase: "endgame" };
    if (area === "blunder pattern") return { puzzle_type: "blunder" };
    if (area === "converting advantages") return { puzzle_type: "missed_win" };
    // Tactic-specific weaknesses
    if (area.includes("fork")) return { tactic: "fork" };
    if (area.includes("pin")) return { tactic: "pin" };
    if (area.includes("skewer")) return { tactic: "skewer" };
    if (area.includes("king")) return { tactic: "king_activity" };
    if (area.includes("back rank") || area.includes("back-rank")) return { tactic: "back_rank" };
    if (area.includes("discovery") || area.includes("discovered")) return { tactic: "discovered_attack" };
    return {};
  }

  function startSession(source?: PuzzleSource, timed?: boolean, overrideFilters?: { tactic?: string; phase?: string; puzzle_type?: string }) {
    const src = source ?? puzzleSource;
    if (timed !== undefined) setIsTimed(timed);
    setPuzzleSource(src);
    loadPuzzles(src, overrideFilters ?? puzzleFilters);
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
    setIntuitionPreviewIdx(0);
    try {
      const data = await puzzlesAPI.intuitionChallenge(5);
      setIntuitionChallenges(data);
    } catch {
      setIntuitionChallenges({ challenges: [], total: 0 });
    }
  }

  // ─── Keyboard navigation for Intuition Trainer ───────
  useEffect(() => {
    if (view !== "intuition") return;
    const challenge = intuitionChallenges?.challenges[intuitionIdx];
    if (!challenge) return;
    const maxIdx = Math.max(0, challenge.options.length - 1);

    function handleKey(e: KeyboardEvent) {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setIntuitionPreviewIdx((i) => Math.max(0, i - 1));
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setIntuitionPreviewIdx((i) => Math.min(maxIdx, i + 1));
      }
    }

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [view, intuitionChallenges, intuitionIdx]);

  // ─── Opening Drill functions ─────────────────────────

  function pickWeightedRandom(nodes: OpeningTreeNode[]): OpeningTreeNode {
    const totalGames = nodes.reduce((sum, n) => sum + n.games, 0);
    let roll = Math.random() * totalGames;
    for (const n of nodes) {
      roll -= n.games;
      if (roll <= 0) return n;
    }
    return nodes[0];
  }

  async function startOpeningDrill(color: "white" | "black") {
    setOpeningDrillColor(color);
    setView("opening-drill");
    setOpeningDrillState("playing");
    setOpeningDrillScore({ correct: 0, total: 0 });
    setOpeningDrillMoves([]);
    setOpeningDrillHint("");
    setOpeningDrillExplanation("");
    setOpeningDrillExplanationLoading(false);
    setOpeningDrillSelectedSquare(null);
    setOpeningDrillLegalMoves([]);
    setOpeningDrillWrongFen("");
    setOpeningDrillWrongMoveIdx(0);
    openingDrillGame.reset();
    setOpeningDrillFen(openingDrillGame.fen());
    setOpeningDrillCurrentPath([]);

    try {
      const data = await openingsAPI.tree({ color, max_depth: 12 });
      const tree = (data.tree || []) as OpeningTreeNode[];
      setOpeningTree(tree);
      // If playing black, auto-play white's first move (weighted random)
      if (color === "black" && tree.length > 0) {
        const topMove = pickWeightedRandom(tree);
        openingDrillGame.move(topMove.san);
        setOpeningDrillFen(openingDrillGame.fen());
        setOpeningDrillMoves([topMove.san]);
        setOpeningDrillCurrentPath(topMove.children || []);
      } else {
        setOpeningDrillCurrentPath(tree);
      }
    } catch {
      setOpeningTree([]);
      setOpeningDrillCurrentPath([]);
    }
  }

  function openingDrillTryMove(sourceSquare: Square, targetSquare: Square): boolean {
    if (openingDrillState !== "playing") return false;

    const moveCopy = new Chess(openingDrillGame.fen());
    const move = moveCopy.move({ from: sourceSquare, to: targetSquare, promotion: "q" });
    if (!move) return false;

    // Clear selection state
    setOpeningDrillSelectedSquare(null);
    setOpeningDrillLegalMoves([]);

    const fenBeforeMove = openingDrillGame.fen();
    const moveSan = move.san;

    // Lock the board while Stockfish validates
    setOpeningDrillState("validating");
    // Show the move on the board optimistically
    openingDrillGame.move(moveSan);
    setOpeningDrillFen(openingDrillGame.fen());
    const newMoves = [...openingDrillMoves, moveSan];
    setOpeningDrillMoves(newMoves);

    // Ask Stockfish: is this move ≤50 CPL?
    openingsAPI
      .validateMove(fenBeforeMove, moveSan)
      .then((result) => {
        const matchingNode = openingDrillCurrentPath.find((n) => n.san === moveSan);

        if (result.viable) {
          // Move is good (≤50 cp loss) — accept it
          setOpeningDrillScore((s) => ({ correct: s.correct + 1, total: s.total + 1 }));
          setOpeningDrillHint("");
          setOpeningDrillExplanation("");
          playCorrect();

          // Traverse into matching tree node if it exists, otherwise line ends
          if (matchingNode && matchingNode.children.length > 0) {
            const reply = pickWeightedRandom(matchingNode.children);
            setTimeout(() => {
              openingDrillGame.move(reply.san);
              setOpeningDrillFen(openingDrillGame.fen());
              setOpeningDrillMoves((prev) => [...prev, reply.san]);
              playMove();

              if (reply.children.length === 0) {
                setOpeningDrillState("done");
              } else {
                setOpeningDrillCurrentPath(reply.children);
                setOpeningDrillState("playing");
              }
            }, 500);
          } else {
            // Move was viable but not in our tree — line ends
            setOpeningDrillState("done");
          }
        } else {
          // Move loses too much (>50 cp) — wrong
          // Undo the optimistic move
          openingDrillGame.undo();
          setOpeningDrillFen(openingDrillGame.fen());
          setOpeningDrillMoves(openingDrillMoves);

          setOpeningDrillScore((s) => ({ ...s, total: s.total + 1 }));
          playIncorrect();

          setOpeningDrillHint(`Best was ${result.best_move_san} (your move lost ${result.cp_loss} cp)`);
          setOpeningDrillState("wrong");

          setOpeningDrillWrongFen(fenBeforeMove);
          setOpeningDrillWrongMoveIdx(openingDrillMoves.length);

          // Fetch AI explanation
          setOpeningDrillExplanationLoading(true);
          setOpeningDrillExplanation("");
          explanationsAPI
            .explainMove({
              fen: fenBeforeMove,
              san: moveSan,
              best_move_san: result.best_move_san,
              cp_loss: result.cp_loss,
              eval_before: result.eval_before,
              eval_after: result.eval_after,
              phase: "opening",
              move_quality: result.cp_loss >= 100 ? "Blunder" : "Mistake",
              move_number: Math.floor(openingDrillMoves.length / 2) + 1,
              color: openingDrillColor,
            })
            .then((res) => setOpeningDrillExplanation(res.explanation))
            .catch(() => setOpeningDrillExplanation(""))
            .finally(() => setOpeningDrillExplanationLoading(false));
        }
      })
      .catch(() => {
        // Stockfish unavailable — fall back to tree-based check
        const matchingNode = openingDrillCurrentPath.find((n) => n.san === moveSan);
        if (matchingNode) {
          setOpeningDrillScore((s) => ({ correct: s.correct + 1, total: s.total + 1 }));
          playCorrect();

          if (matchingNode.children.length > 0) {
            const reply = pickWeightedRandom(matchingNode.children);
            setTimeout(() => {
              openingDrillGame.move(reply.san);
              setOpeningDrillFen(openingDrillGame.fen());
              setOpeningDrillMoves((prev) => [...prev, reply.san]);
              playMove();
              if (reply.children.length === 0) setOpeningDrillState("done");
              else { setOpeningDrillCurrentPath(reply.children); setOpeningDrillState("playing"); }
            }, 500);
          } else {
            setOpeningDrillState("done");
          }
        } else {
          // Undo the optimistic move
          openingDrillGame.undo();
          setOpeningDrillFen(openingDrillGame.fen());
          setOpeningDrillMoves(openingDrillMoves);

          setOpeningDrillScore((s) => ({ ...s, total: s.total + 1 }));
          playIncorrect();
          setOpeningDrillHint("Move not in your repertoire");
          setOpeningDrillState("wrong");
          setOpeningDrillWrongFen(fenBeforeMove);
          setOpeningDrillWrongMoveIdx(openingDrillMoves.length);
        }
      });

    return true;
  }

  function openingDrillRetry() {
    openingDrillGame.reset();
    setOpeningDrillFen(openingDrillGame.fen());
    setOpeningDrillMoves([]);
    setOpeningDrillState("playing");
    setOpeningDrillHint("");
    setOpeningDrillExplanation("");
    setOpeningDrillExplanationLoading(false);
    setOpeningDrillSelectedSquare(null);
    setOpeningDrillLegalMoves([]);

    if (openingDrillColor === "black" && openingTree.length > 0) {
      const topMove = pickWeightedRandom(openingTree);
      openingDrillGame.move(topMove.san);
      setOpeningDrillFen(openingDrillGame.fen());
      setOpeningDrillMoves([topMove.san]);
      setOpeningDrillCurrentPath(topMove.children || []);
    } else {
      setOpeningDrillCurrentPath(openingTree);
    }
  }

  function openingDrillRetryFromHere() {
    // Replay moves up to the point of the mistake to restore the position
    openingDrillGame.reset();
    const movesToReplay = openingDrillMoves.slice(0, openingDrillWrongMoveIdx);
    for (const m of movesToReplay) {
      openingDrillGame.move(m);
    }
    setOpeningDrillFen(openingDrillGame.fen());
    setOpeningDrillMoves(movesToReplay);
    setOpeningDrillState("playing");
    setOpeningDrillHint("");
    setOpeningDrillExplanation("");
    setOpeningDrillExplanationLoading(false);
    setOpeningDrillSelectedSquare(null);
    setOpeningDrillLegalMoves([]);

    // Walk the tree to find the current path at this position
    let currentNodes = openingTree;
    for (const m of movesToReplay) {
      const node = currentNodes.find((n) => n.san === m);
      if (node) {
        currentNodes = node.children;
      } else {
        break;
      }
    }
    setOpeningDrillCurrentPath(currentNodes);
  }

  // Opening drill click-to-move handlers
  function onDrillPieceClick(_piece: string, square: Square) {
    if (openingDrillState !== "playing") return;


    const clicked = openingDrillGame.get(square);

    if (openingDrillSelectedSquare) {
      if (openingDrillSelectedSquare === square) {
        setOpeningDrillSelectedSquare(null);
        setOpeningDrillLegalMoves([]);
        return;
      }
      if (clicked && clicked.color === openingDrillGame.turn()) {
        setOpeningDrillSelectedSquare(null);
        setOpeningDrillLegalMoves([]);
        return;
      }
      if (openingDrillTryMove(openingDrillSelectedSquare, square)) return;
    }

    if (clicked && clicked.color === openingDrillGame.turn()) {
      setOpeningDrillSelectedSquare(square);
      const moves = openingDrillGame.moves({ square, verbose: true });
      setOpeningDrillLegalMoves(moves.map((m) => m.to as Square));
    } else {
      setOpeningDrillSelectedSquare(null);
      setOpeningDrillLegalMoves([]);
    }
  }

  function onDrillSquareClick(square: Square, piece?: string) {
    if (openingDrillState !== "playing") return;


    const clicked = openingDrillGame.get(square);

    if (openingDrillSelectedSquare) {
      if (openingDrillSelectedSquare === square) {
        setOpeningDrillSelectedSquare(null);
        setOpeningDrillLegalMoves([]);
        return;
      }
      if (clicked && clicked.color === openingDrillGame.turn()) {
        setOpeningDrillSelectedSquare(null);
        setOpeningDrillLegalMoves([]);
        return;
      }
      if (openingDrillTryMove(openingDrillSelectedSquare, square)) return;
    }

    if (piece) {
      if (clicked && clicked.color === openingDrillGame.turn()) {
        setOpeningDrillSelectedSquare(square);
        const moves = openingDrillGame.moves({ square, verbose: true });
        setOpeningDrillLegalMoves(moves.map((m) => m.to as Square));
        return;
      }
    }

    setOpeningDrillSelectedSquare(null);
    setOpeningDrillLegalMoves([]);
  }

  const drillSquareStyles = useMemo(() => {
    const styles: Record<string, CSSProperties> = {};
    if (openingDrillSelectedSquare) {
      styles[openingDrillSelectedSquare] = { backgroundColor: "rgba(255, 255, 0, 0.35)" };
    }
    for (const sq of openingDrillLegalMoves) {
      const piece = openingDrillGame.get(sq);
      if (piece) {
        styles[sq] = { background: "radial-gradient(transparent 56%, rgba(0,0,0,0.35) 56%)" };
      } else {
        styles[sq] = { background: "radial-gradient(circle, rgba(0,0,0,0.35) 22%, transparent 23%)" };
      }
    }
    return styles;
  }, [openingDrillSelectedSquare, openingDrillLegalMoves, openingDrillFen]);

  // ─── Handle move ─────────────────────────────────────
  function tryMove(sourceSquare: Square, targetSquare: Square): boolean {
    if (!chessRef.current || !currentPuzzle || puzzleState !== "solving" || isOpponentMoving) return false;

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

    const line = currentPuzzle.solution_line;
    const hasLine = line && line.length > 1;

    // Determine which move the user should play
    let expectedUci: string;
    if (hasLine) {
      expectedUci = line[seqIdx];
    } else {
      // Legacy single-move: fall back to best_move_uci or compare SAN
      expectedUci = currentPuzzle.best_move_uci || "";
    }

    // Compare: UCI match or SAN match (for backwards compat)
    const moveUci = move.from + move.to + (move.promotion ? move.promotion : "");
    const isCorrect = expectedUci
      ? moveUci === expectedUci
      : move.san === currentPuzzle.best_move_san;

    if (!isCorrect) {
      // Wrong move — puzzle failed
      setPuzzleState("incorrect");
      setStreak(0);
      setSolvedToday((s) => s + 1);
      playIncorrect();
      reportAttempt(false);
      return true;
    }

    // Correct move — check if there are more moves in the sequence
    const nextIdx = seqIdx + 1;

    if (hasLine && nextIdx < line.length) {
      // There's an opponent reply — play it automatically after a delay
      setIsOpponentMoving(true);
      setSeqIdx(nextIdx);

      setTimeout(() => {
        if (!chessRef.current) return;
        const opponentUci = line[nextIdx];
        const from = opponentUci.slice(0, 2) as Square;
        const to = opponentUci.slice(2, 4) as Square;
        const promo = opponentUci.length > 4 ? opponentUci[4] : undefined;

        const opMove = chessRef.current.move({
          from,
          to,
          promotion: promo as "q" | "r" | "b" | "n" | undefined,
        });

        if (opMove) {
          setBoardFen(chessRef.current.fen());
          playMove();
        }

        const afterOpponentIdx = nextIdx + 1;

        if (afterOpponentIdx >= line.length) {
          // Opponent's reply was the last move — puzzle complete!
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
          // More user moves needed
          setSeqIdx(afterOpponentIdx);
        }

        setIsOpponentMoving(false);
      }, 500);
    } else {
      // No more moves — puzzle complete!
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
      setSeqIdx(0);
      setIsOpponentMoving(false);
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
                                {a.puzzle?.themes?.filter((t: string) => !["opening", "middlegame", "endgame", "blunder", "mistake", "missed_win"].includes(t)).slice(0, 2).map((t: string) => (
                                  <Badge key={t} variant="default">
                                    {t.replace(/_/g, " ")}
                                  </Badge>
                                ))}
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

        {/* ─── Puzzle Options ─── */}
        <Card className="overflow-hidden">
          <button
            onClick={() => setShowOptions(!showOptions)}
            className="w-full flex items-center justify-between p-4 text-left hover:bg-white/[0.02] transition-colors"
          >
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="h-4 w-4 text-gray-400" />
              <span className="text-sm font-medium">Puzzle Options</span>
              {hasFilters && (
                <Badge variant="success" className="text-[10px] px-1.5 py-0">
                  Filtered
                </Badge>
              )}
            </div>
            <ChevronDown className={`h-4 w-4 text-gray-500 transition-transform ${showOptions ? "rotate-180" : ""}`} />
          </button>
          <AnimatePresence>
            {showOptions && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <div className="px-4 pb-4 grid gap-3 sm:grid-cols-3">
                  {/* Tactic */}
                  <div>
                    <label className="text-xs text-gray-500 uppercase tracking-wider mb-1.5 block">Tactic</label>
                    <select
                      value={filterTactic}
                      onChange={(e) => setFilterTactic(e.target.value)}
                      className="w-full rounded-lg bg-surface-2 border border-white/10 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-500"
                    >
                      <option value="">All</option>
                      <option value="fork">Fork</option>
                      <option value="pin">Pin</option>
                      <option value="skewer">Skewer</option>
                      <option value="discovered_attack">Discovered Attack</option>
                      <option value="back_rank">Back Rank</option>
                      <option value="sacrifice">Sacrifice</option>
                      <option value="promotion">Promotion</option>
                      <option value="checkmate_pattern">Checkmate Pattern</option>
                      <option value="king_activity">King Play</option>
                      <option value="deflection">Deflection</option>
                      <option value="winning_capture">Winning Capture</option>
                      <option value="positional">Positional</option>
                    </select>
                  </div>
                  {/* Game Phase */}
                  <div>
                    <label className="text-xs text-gray-500 uppercase tracking-wider mb-1.5 block">Phase</label>
                    <select
                      value={filterPhase}
                      onChange={(e) => setFilterPhase(e.target.value)}
                      className="w-full rounded-lg bg-surface-2 border border-white/10 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-500"
                    >
                      <option value="">All</option>
                      <option value="opening">Opening</option>
                      <option value="middlegame">Middlegame</option>
                      <option value="endgame">Endgame</option>
                    </select>
                  </div>
                  {/* Puzzle Type */}
                  <div>
                    <label className="text-xs text-gray-500 uppercase tracking-wider mb-1.5 block">Type</label>
                    <select
                      value={filterType}
                      onChange={(e) => setFilterType(e.target.value)}
                      className="w-full rounded-lg bg-surface-2 border border-white/10 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-500"
                    >
                      <option value="">All</option>
                      <option value="blunder">Blunder</option>
                      <option value="mistake">Mistake</option>
                      <option value="missed_win">Missed Win</option>
                    </select>
                  </div>
                </div>
                {hasFilters && (
                  <div className="px-4 pb-4">
                    <button
                      onClick={() => { setFilterTactic(""); setFilterPhase(""); setFilterType(""); }}
                      className="text-xs text-brand-400 hover:text-brand-300 transition-colors"
                    >
                      Clear all filters
                    </button>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </Card>

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
                    <Button onClick={() => startSession("my", false, weaknessToFilters(weaknesses[0]))} className="w-full mt-5" size="lg">
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
                            onClick={() => startSession("my", isTimeMgmt, isTimeMgmt ? undefined : weaknessToFilters(w))}
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
                      onClick={() => startSession("global", false, { puzzle_type: "blunder" })}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <Shield className="h-4 w-4 text-red-400" />
                        <span className="font-semibold text-sm">Blunder Preventer</span>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">
                        Can you find the safe move? Avoid blunders from games across the community.
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

                {/* ─── Opening Drill ─── */}
                <div>
                  <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">
                    Opening Practice
                  </h2>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Card
                      className="p-4 cursor-pointer transition-colors hover:border-emerald-500/50 border-emerald-600/20"
                      onClick={() => startOpeningDrill("white")}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <BookOpen className="h-4 w-4 text-emerald-400" />
                        <span className="font-semibold text-sm">White Repertoire</span>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">
                        Find the engine&apos;s best move in your White openings. Opponents respond as they do in your games.
                      </p>
                      <p className="text-xs mt-2 text-emerald-400 flex items-center gap-1">
                        Drill <ArrowRight className="h-3 w-3" />
                      </p>
                    </Card>
                    <Card
                      className="p-4 cursor-pointer transition-colors hover:border-sky-500/50 border-sky-600/20"
                      onClick={() => startOpeningDrill("black")}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <BookOpen className="h-4 w-4 text-sky-400" />
                        <span className="font-semibold text-sm">Black Repertoire</span>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">
                        Find the engine&apos;s best move in your Black openings. Opponents respond as they do in your games.
                      </p>
                      <p className="text-xs mt-2 text-sky-400 flex items-center gap-1">
                        Drill <ArrowRight className="h-3 w-3" />
                      </p>
                    </Card>
                  </div>
                </div>
              </>
            )}

            {puzzleSource === "global" && (
              <>
                {/* Quick Start */}
                <Card className="p-5 border-brand-600/30 bg-gradient-to-r from-brand-900/10 to-blue-900/10">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="h-12 w-12 rounded-xl bg-brand-600/20 flex items-center justify-center">
                        <Globe className="h-6 w-6 text-brand-400" />
                      </div>
                      <div>
                        <h2 className="text-lg font-semibold">Random Mix</h2>
                        <p className="text-sm text-gray-400">
                          A mixed set of puzzles from games across the community
                        </p>
                      </div>
                    </div>
                    <Button onClick={() => startSession("global")} size="lg">
                      <Globe className="h-5 w-5" />
                      Go
                    </Button>
                  </div>
                </Card>

                {/* By Game Phase */}
                <div>
                  <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">
                    Train by Phase
                  </h2>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Card
                      className="p-4 cursor-pointer transition-colors hover:border-emerald-500/50 border-emerald-600/20"
                      onClick={() => startSession("global", false, { phase: "opening" })}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <BookOpen className="h-4 w-4 text-emerald-400" />
                        <span className="font-semibold text-sm">Opening</span>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">
                        Punish early mistakes. Recognize traps, gambits, and opening principles.
                      </p>
                      <p className="text-xs mt-2 text-emerald-400 flex items-center gap-1">
                        Practice <ArrowRight className="h-3 w-3" />
                      </p>
                    </Card>
                    <Card
                      className="p-4 cursor-pointer transition-colors hover:border-blue-500/50 border-blue-600/20"
                      onClick={() => startSession("global", false, { phase: "middlegame" })}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <Zap className="h-4 w-4 text-blue-400" />
                        <span className="font-semibold text-sm">Middlegame</span>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">
                        Navigate the chaos. Sharpen your calculation in complex positions.
                      </p>
                      <p className="text-xs mt-2 text-blue-400 flex items-center gap-1">
                        Practice <ArrowRight className="h-3 w-3" />
                      </p>
                    </Card>
                    <Card
                      className="p-4 cursor-pointer transition-colors hover:border-purple-500/50 border-purple-600/20"
                      onClick={() => startSession("global", false, { phase: "endgame" })}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <Target className="h-4 w-4 text-purple-400" />
                        <span className="font-semibold text-sm">Endgame</span>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">
                        Convert advantages. Learn to finish what you started.
                      </p>
                      <p className="text-xs mt-2 text-purple-400 flex items-center gap-1">
                        Practice <ArrowRight className="h-3 w-3" />
                      </p>
                    </Card>
                  </div>
                </div>

                {/* By Tactic */}
                <div>
                  <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wider mb-3">
                    Train by Tactic
                  </h2>
                  <div className="grid gap-3 sm:grid-cols-3">
                    {[
                      { tactic: "fork", label: "Forks", desc: "Attack two pieces at once. The bread and butter of tactics.", color: "amber" },
                      { tactic: "pin", label: "Pins", desc: "Immobilize a piece. Exploit the line between their piece and their king.", color: "cyan" },
                      { tactic: "skewer", label: "Skewers", desc: "Force the bigger piece to move and win what's behind it.", color: "orange" },
                      { tactic: "discovered_attack", label: "Discovered Attacks", desc: "Move one piece, unleash another. Double threats that are hard to defend.", color: "rose" },
                      { tactic: "back_rank", label: "Back Rank", desc: "Exploit a trapped king. One of the deadliest patterns in chess.", color: "red" },
                      { tactic: "checkmate_pattern", label: "Checkmate Patterns", desc: "Spot the mating net. End the game in style.", color: "pink" },
                    ].map(({ tactic, label, desc, color }) => (
                      <Card
                        key={tactic}
                        className={`p-4 cursor-pointer transition-colors hover:border-${color}-500/50 border-${color}-600/20`}
                        onClick={() => startSession("global", false, { tactic })}
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <Flame className={`h-4 w-4 text-${color}-400`} />
                          <span className="font-semibold text-sm">{label}</span>
                        </div>
                        <p className="text-xs text-gray-500 line-clamp-2">{desc}</p>
                        <p className={`text-xs mt-2 text-${color}-400 flex items-center gap-1`}>
                          Practice <ArrowRight className="h-3 w-3" />
                        </p>
                      </Card>
                    ))}
                  </div>
                </div>

                {/* Training Modes */}
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
                          {advantagePositions.total} positions where you were winning but didn&apos;t convert. Practice finishing the job.
                        </p>
                        <p className="text-xs mt-2 text-amber-400 flex items-center gap-1">
                          Practice <ArrowRight className="h-3 w-3" />
                        </p>
                      </Card>
                    )}

                    {/* Blunder Preventer */}
                    <Card
                      className="p-4 cursor-pointer transition-colors hover:border-red-500/50 border-red-600/20"
                      onClick={() => startSession("global", false, { puzzle_type: "blunder" })}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <Shield className="h-4 w-4 text-red-400" />
                        <span className="font-semibold text-sm">Blunder Preventer</span>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">
                        Train your instinct for danger. Spot the safe move before disaster strikes.
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
                        Spot the blunder! Given 4 moves, can you tell which one was the mistake?
                      </p>
                      <p className="text-xs mt-2 text-purple-400 flex items-center gap-1">
                        Play <ArrowRight className="h-3 w-3" />
                      </p>
                    </Card>

                    {/* Timed Challenge */}
                    <Card
                      className="p-4 cursor-pointer transition-colors hover:border-yellow-500/50 border-yellow-600/20"
                      onClick={() => startSession("global", true)}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <Clock className="h-4 w-4 text-yellow-400" />
                        <span className="font-semibold text-sm">Speed Drill</span>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">
                        10 seconds per puzzle. Train your pattern recognition under pressure.
                      </p>
                      <p className="text-xs mt-2 text-yellow-400 flex items-center gap-1">
                        Start <ArrowRight className="h-3 w-3" />
                      </p>
                    </Card>
                  </div>
                </div>
              </>
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
    const previewMaxIdx = Math.max(0, (challenge?.options.length ?? 1) - 1);
    const previewIdx = Math.min(intuitionPreviewIdx, previewMaxIdx);
    const previewOption = challenge?.options[previewIdx];

    let previewFen = previewOption?.fen_before ?? challenge?.options[0]?.fen_before;
    if (previewFen && previewOption?.san) {
      try {
        const previewChess = new Chess(previewFen);
        previewChess.move(previewOption.san);
        previewFen = previewChess.fen();
      } catch {
        // Keep original FEN if SAN parsing fails
      }
    }

    return (
      <div className="max-w-4xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
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
            {/* Preview board */}
            {challenge.options[0]?.fen_before && (
              <div className="flex justify-center">
                <div className="w-[420px] max-w-full">
                  <Chessboard
                    position={previewFen}
                    boardOrientation={challenge.color === "black" ? "black" : "white"}
                    boardWidth={420}
                    arePiecesDraggable={false}
                    customBoardStyle={{
                      borderRadius: "8px",
                      boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
                    }}
                    customDarkSquareStyle={{ backgroundColor: "#779952" }}
                    customLightSquareStyle={{ backgroundColor: "#edeed1" }}
                  />
                  <div className="mt-3 flex items-center justify-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setIntuitionPreviewIdx((i) => Math.max(0, i - 1))}
                      disabled={previewIdx <= 0}
                    >
                      Previous
                    </Button>
                    <p className="text-xs text-gray-400 text-center min-w-[180px]">
                      Preview {previewIdx + 1}/{challenge.options.length}: {previewOption?.san ?? "-"}
                    </p>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setIntuitionPreviewIdx((i) => Math.min(previewMaxIdx, i + 1))}
                      disabled={previewIdx >= previewMaxIdx}
                    >
                      Next
                    </Button>
                  </div>
                  <p className="text-xs text-gray-500 text-center mt-2">
                    Use ← → arrow keys or buttons to preview moves
                  </p>
                </div>
              </div>
            )}
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
                      setIntuitionPreviewIdx(i);
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
                      setIntuitionPreviewIdx(0);
                    } else {
                      setIntuitionIdx((i) => i + 1);
                      setIntuitionPicked(null);
                      setIntuitionPreviewIdx(0);
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

  // ─── Opening Drill view ──────────────────────────────
  if (view === "opening-drill") {
    const accuracy = openingDrillScore.total > 0 ? Math.round((openingDrillScore.correct / openingDrillScore.total) * 100) : null;

    return (
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <BookOpen className="h-6 w-6 text-emerald-400" /> Opening Drill
            </h1>
            <p className="text-gray-500 mt-1">
              Play the best move in your {openingDrillColor === "white" ? "White" : "Black"} openings
            </p>
          </div>
          <div className="flex items-center gap-3">
            {accuracy !== null && (
              <Badge variant="default">
                {openingDrillScore.correct}/{openingDrillScore.total} correct
              </Badge>
            )}
            <Button variant="ghost" size="sm" onClick={() => setView("hub")}>
              ← Back
            </Button>
          </div>
        </div>

        {openingTree.length === 0 ? (
          <Card className="p-8 text-center">
            <BookOpen className="h-12 w-12 text-emerald-400 mx-auto mb-4" />
            <h2 className="text-xl font-semibold mb-2">No opening data yet</h2>
            <p className="text-sm text-gray-500 mb-4">
              Import and analyze some games first. We&apos;ll build your repertoire from the openings you actually play.
            </p>
            <Button onClick={() => setView("hub")}>Back to Hub</Button>
          </Card>
        ) : (
          <div className="flex flex-col lg:flex-row gap-6">
            {/* Board */}
            <div className="flex-1 max-w-[560px]">
              <div className="relative">
                <Chessboard
                  position={openingDrillFen}
                  onPieceClick={onDrillPieceClick}
                  onSquareClick={onDrillSquareClick}
                  onPieceDrop={(s, t) => openingDrillTryMove(s as Square, t as Square)}
                  boardOrientation={openingDrillColor}
                  boardWidth={560}
                  arePiecesDraggable={openingDrillState === "playing"}
                  customSquareStyles={drillSquareStyles}
                  customBoardStyle={{
                    borderRadius: "8px",
                    boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
                  }}
                  customDarkSquareStyle={{ backgroundColor: "#779952" }}
                  customLightSquareStyle={{ backgroundColor: "#edeed1" }}
                />

                {/* Feedback overlay */}
                <AnimatePresence>
                  {openingDrillState === "wrong" && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.9 }}
                      className="absolute inset-0 flex items-center justify-center bg-black/40 rounded-lg"
                    >
                      <div className="flex flex-col items-center gap-3 px-8 py-6 rounded-xl bg-red-900/90 max-w-[90%]">
                        <XCircle className="h-10 w-10 text-red-400" />
                        <p className="text-lg font-bold text-red-300">Not in your repertoire</p>
                        {openingDrillHint && (
                          <p className="text-sm text-red-400/80 font-mono">{openingDrillHint}</p>
                        )}
                        {openingDrillExplanationLoading && (
                          <div className="flex items-center gap-2 text-sm text-red-400/60">
                            <Spinner className="h-4 w-4" /> Getting explanation...
                          </div>
                        )}
                        {openingDrillExplanation && (
                          <p className="text-sm text-gray-300 bg-black/30 rounded-lg px-4 py-3 leading-relaxed max-w-[400px] text-center">
                            {openingDrillExplanation}
                          </p>
                        )}
                        <div className="flex gap-2 mt-2">
                          <Button variant="secondary" size="sm" onClick={openingDrillRetryFromHere}>
                            <RotateCcw className="h-4 w-4" /> Try Again
                          </Button>
                          <Button variant="secondary" size="sm" onClick={openingDrillRetry}>
                            <RotateCcw className="h-4 w-4" /> Start Over
                          </Button>
                          <Button size="sm" onClick={() => setView("hub")}>
                            Back to Hub
                          </Button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                  {openingDrillState === "done" && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.9 }}
                      className="absolute inset-0 flex items-center justify-center bg-black/40 rounded-lg"
                    >
                      <div className="flex flex-col items-center gap-3 px-8 py-6 rounded-xl bg-green-900/90">
                        <CheckCircle className="h-12 w-12 text-green-400" />
                        <p className="text-lg font-bold text-green-300">Line Complete!</p>
                        <p className="text-sm text-green-400/80">
                          {openingDrillScore.correct}/{openingDrillScore.total} moves correct
                        </p>
                        <div className="flex gap-2 mt-2">
                          <Button variant="secondary" size="sm" onClick={openingDrillRetry}>
                            <RotateCcw className="h-4 w-4" /> Again
                          </Button>
                          <Button size="sm" onClick={() => startOpeningDrill(openingDrillColor === "white" ? "black" : "white")}>
                            Try {openingDrillColor === "white" ? "Black" : "White"}
                          </Button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Move list */}
              <div className="mt-4 flex flex-wrap gap-1 items-center justify-center">
                {openingDrillMoves.map((m, i) => (
                  <span key={i} className="text-sm text-gray-300">
                    {i % 2 === 0 && <span className="text-gray-600 mr-1">{Math.floor(i / 2) + 1}.</span>}
                    {m}{" "}
                  </span>
                ))}
                {openingDrillState === "playing" && (
                  <span className="text-sm text-brand-400 animate-pulse">Your move...</span>
                )}
                {openingDrillState === "validating" && (
                  <span className="text-sm text-yellow-400 animate-pulse flex items-center gap-1">
                    <Spinner className="h-3 w-3" /> Checking...
                  </span>
                )}
              </div>
            </div>

            {/* Info panel */}
            <div className="lg:w-[280px] space-y-4">
              <Card>
                <CardContent>
                  <h3 className="font-semibold text-sm text-gray-400 uppercase tracking-wider mb-3">
                    How It Works
                  </h3>
                  <div className="space-y-2 text-sm text-gray-400">
                    <p>Play any <span className="text-emerald-400 font-medium">viable move</span> — anything under 50 centipawn loss is accepted.</p>
                    <p>Your opponent responds with moves from your actual games, weighted by how often they occur.</p>
                    <p>If your move loses too much, Stockfish will explain why and you can try again.</p>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent>
                  <h3 className="font-semibold text-sm text-gray-400 uppercase tracking-wider mb-3">
                    Session
                  </h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-500">Color</span>
                      <span className="text-gray-300 capitalize">{openingDrillColor}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Moves played</span>
                      <span className="text-gray-300">{openingDrillMoves.length}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Accuracy</span>
                      <span className="text-gray-300">{accuracy !== null ? `${accuracy}%` : "—"}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
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
              : "Solve the position."}
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
                arePiecesDraggable={puzzleState === "solving" && !isOpponentMoving}
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
                            {solutionLine.length > 0 && seqIdx < solutionLine.length
                              ? solutionLine[seqIdx].slice(0,2) + "-" + solutionLine[seqIdx].slice(2,4)
                              : currentPuzzle.best_move_san}
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
                {totalUserMoves > 1
                  ? `Find move ${currentUserMoveNum} of ${totalUserMoves}`
                  : boardOrientation === "white"
                  ? "Find the best move for White"
                  : "Find the best move for Black"}
              </p>
              {isOpponentMoving && (
                <p className="text-xs text-yellow-400 mt-1 animate-pulse">Opponent is playing…</p>
              )}
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
                  {currentPuzzle.themes?.length > 0 && (
                    <div className="flex justify-between items-start">
                      <span className="text-gray-500">Tactics</span>
                      <div className="flex flex-wrap gap-1 justify-end">
                        {currentPuzzle.themes
                          .filter((t) => !["opening", "middlegame", "endgame", "blunder", "mistake", "missed_win"].includes(t))
                          .map((t) => (
                          <Badge key={t} variant="default">
                            {t.replace(/_/g, " ")}
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

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { Chess } from "chess.js";
import { Chessboard } from "react-chessboard";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  BarChart3,
  Play,
  MessageSquare,
  Loader2,
  Dumbbell,
  ChevronDown,
  Lightbulb,
  Sparkles,
} from "lucide-react";
import {
  gamesAPI,
  analysisAPI,
  coachAPI,
  explanationsAPI,
  type GameDetail,
  type MoveEval,
  type AnalysisResult,
  type CoachReview,
  type MoveExplanation,
} from "@/lib/api";
import {
  Button,
  Badge,
  Card,
  CardContent,
  Spinner,
  moveQualityColor,
  moveQualityBg,
  resultBadgeVariant,
} from "@/components/ui";
import { cplToAccuracy, accuracyColor, formatAccuracy, getAccuracy, moveQualityAnnotation } from "@/lib/utils";
import Link from "next/link";

export default function GameDetailPage() {
  const { data: session } = useSession();
  const params = useParams();
  const router = useRouter();
  const gameId = Number(params.id);

  // ─── Data ────────────────────────────────────────────
  const [game, setGame] = useState<GameDetail | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ─── AI Coach ────────────────────────────────────────
  const [coachReview, setCoachReview] = useState<CoachReview | null>(null);
  const [coachLoading, setCoachLoading] = useState(false);

  // ─── AI Move Explanation ─────────────────────────────
  const [explanation, setExplanation] = useState<MoveExplanation | null>(null);
  const [explanationLoading, setExplanationLoading] = useState(false);
  const [explanationMoveIdx, setExplanationMoveIdx] = useState<number>(-1);

  // ─── Board state ─────────────────────────────────────
  const [moveIndex, setMoveIndex] = useState(0);

  // Parse game moves
  const { positions, parsedMoves } = useMemo(() => {
    if (!game?.moves_pgn) return { positions: ["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"], parsedMoves: [] };

    const chess = new Chess();
    const posArr = [chess.fen()];
    const moveArr: { san: string; color: "w" | "b"; moveNumber: number }[] = [];

    try {
      chess.loadPgn(game.moves_pgn);
      const history = chess.history({ verbose: true });

      // Reset and replay
      chess.reset();
      for (const move of history) {
        chess.move(move.san);
        posArr.push(chess.fen());
        moveArr.push({
          san: move.san,
          color: move.color,
          moveNumber: Math.ceil(posArr.length / 2),
        });
      }
    } catch {
      // PGN parse error — show starting position
    }

    return { positions: posArr, parsedMoves: moveArr };
  }, [game?.moves_pgn]);

  const currentFen = positions[moveIndex] || positions[0];

  // Map analysis moves by index for quick lookup
  const moveEvalMap = useMemo(() => {
    if (!analysis?.moves) return new Map<number, MoveEval>();
    const map = new Map<number, MoveEval>();
    // analysis.moves indices correspond to parsedMoves indices
    for (let i = 0; i < analysis.moves.length; i++) {
      map.set(i, analysis.moves[i]);
    }
    return map;
  }, [analysis]);

  // ─── Fetch data ──────────────────────────────────────
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const g = await gamesAPI.get(gameId);
      setGame(g);

      if (g.analysis) {
        try {
          const a = await analysisAPI.getGameAnalysis(gameId);
          setAnalysis(a);
        } catch {
          // Analysis endpoint may fail if no move-level data yet
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load game");
    } finally {
      setLoading(false);
    }
  }, [gameId]);

  useEffect(() => {
    if (session) fetchData();
  }, [session, fetchData]);

  // ─── Navigation ──────────────────────────────────────
  function goFirst() {
    setMoveIndex(0);
    setExplanation(null);
  }
  function goPrev() {
    setMoveIndex((i) => Math.max(0, i - 1));
    setExplanation(null);
  }
  function goNext() {
    setMoveIndex((i) => Math.min(positions.length - 1, i + 1));
    setExplanation(null);
  }
  function goLast() {
    setMoveIndex(positions.length - 1);
    setExplanation(null);
  }

  // Keyboard navigation
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "ArrowLeft") goPrev();
      if (e.key === "ArrowRight") goNext();
      if (e.key === "Home") goFirst();
      if (e.key === "End") goLast();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [positions.length]);

  if (!session) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-500">Sign in to view game analysis.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Spinner className="h-8 w-8 text-brand-500" />
      </div>
    );
  }

  if (error || !game) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <p className="text-red-400">{error || "Game not found"}</p>
        <Button variant="ghost" onClick={() => router.push("/games")}>
          <ArrowLeft className="h-4 w-4" /> Back to games
        </Button>
      </div>
    );
  }

  const boardOrientation = game.color === "black" ? "black" : "white";
  const currentMoveEval = moveIndex > 0 ? moveEvalMap.get(moveIndex - 1) : null;

  // Build "User vs Opponent" label
  const wp = game.white_player || "White";
  const bp = game.black_player || "Black";
  const gameTitle = `${wp} vs ${bp}`;

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <Button variant="ghost" size="sm" onClick={() => router.push("/games")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1">
          <h1 className="text-xl font-bold">
            {gameTitle}
          </h1>
          <div className="flex items-center gap-3 text-sm text-gray-500 mt-0.5">
            <span>
              {new Date(game.date).toLocaleDateString("en-US", {
                month: "long",
                day: "numeric",
                year: "numeric",
              })}
            </span>
            {game.time_control && <span>{game.time_control}</span>}
            <span className="capitalize">{game.platform}</span>
            <Badge variant={resultBadgeVariant(game.result)}>
              {game.result.toUpperCase()}
            </Badge>
            {game.opening_name && (
              <span className="text-gray-600">
                {game.opening_name}
                {game.eco_code && ` (${game.eco_code})`}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Left: Board + controls */}
        <div className="flex-shrink-0">
          {/* Eval bar + board */}
          <div className="flex gap-2">
            {/* Eval bar */}
            {analysis && (
              <EvalBar
                evalCp={currentMoveEval?.eval_after ?? 0}
                orientation={boardOrientation}
              />
            )}

            {/* Board */}
            <div className="w-[480px] h-[480px]">
              <Chessboard
                position={currentFen}
                boardOrientation={boardOrientation}
                boardWidth={480}
                arePiecesDraggable={false}
                customBoardStyle={{
                  borderRadius: "8px",
                  boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
                }}
                customDarkSquareStyle={{ backgroundColor: "#779952" }}
                customLightSquareStyle={{ backgroundColor: "#edeed1" }}
              />
            </div>
          </div>

          {/* Move controls */}
          <div className="flex items-center justify-center gap-2 mt-4">
            <Button variant="ghost" size="sm" onClick={goFirst} disabled={moveIndex === 0}>
              <ChevronsLeft className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="sm" onClick={goPrev} disabled={moveIndex === 0}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm text-gray-500 min-w-[80px] text-center">
              {moveIndex === 0
                ? "Start"
                : `Move ${Math.ceil(moveIndex / 2)}`}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={goNext}
              disabled={moveIndex >= positions.length - 1}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={goLast}
              disabled={moveIndex >= positions.length - 1}
            >
              <ChevronsRight className="h-4 w-4" />
            </Button>
          </div>

          {/* Current move annotation + AI Explain */}
          {currentMoveEval && (
            <div className="mt-3 space-y-2">
              <div
                className={`px-4 py-2 rounded-lg text-sm flex items-center justify-between ${moveQualityBg(
                  currentMoveEval.move_quality
                )}`}
              >
                <div>
                  <span className={moveQualityColor(currentMoveEval.move_quality)}>
                    {currentMoveEval.move_quality}
                  </span>
                  <span className="text-gray-400 ml-2">
                    {currentMoveEval.san}
                    {currentMoveEval.cp_loss > 0 && (
                      <span className="text-gray-500 ml-1">
                        (−{currentMoveEval.cp_loss} cp)
                      </span>
                    )}
                  </span>
                </div>
                <button
                  onClick={async () => {
                    if (explanationLoading) return;
                    if (explanationMoveIdx === moveIndex && explanation) {
                      setExplanation(null);
                      setExplanationMoveIdx(-1);
                      return;
                    }
                    setExplanationLoading(true);
                    setExplanation(null);
                    try {
                      const fenBefore = moveIndex > 0 ? positions[moveIndex - 1] : positions[0];
                      const result = await explanationsAPI.explainMove({
                        fen: fenBefore,
                        san: currentMoveEval.san,
                        best_move_san: currentMoveEval.best_move_san ?? undefined,
                        eval_before: currentMoveEval.eval_before ?? undefined,
                        eval_after: currentMoveEval.eval_after ?? undefined,
                        cp_loss: currentMoveEval.cp_loss,
                        phase: currentMoveEval.phase ?? undefined,
                        move_quality: currentMoveEval.move_quality ?? undefined,
                        move_number: currentMoveEval.move_number,
                        color: currentMoveEval.color,
                        game_id: gameId,
                      });
                      setExplanation(result);
                      setExplanationMoveIdx(moveIndex);
                    } catch {
                      // AI service error
                    } finally {
                      setExplanationLoading(false);
                    }
                  }}
                  className="flex items-center gap-1 px-2 py-1 rounded-md text-xs bg-brand-600/20 text-brand-300 hover:bg-brand-600/30 transition-colors"
                  title="AI Explain"
                >
                  {explanationLoading ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Sparkles className="h-3 w-3" />
                  )}
                  Explain
                </button>
              </div>

              {/* AI Explanation panel */}
              {explanation && explanationMoveIdx === moveIndex && (
                <div className="px-4 py-3 rounded-lg bg-brand-600/10 border border-brand-600/20 text-sm space-y-2 animate-fade-in">
                  <div className="flex items-center gap-1.5 text-brand-300 text-xs font-semibold uppercase tracking-wider">
                    <Lightbulb className="h-3.5 w-3.5" />
                    AI Explanation
                  </div>
                  <p className="text-gray-300 leading-relaxed">
                    {explanation.explanation}
                  </p>
                  {explanation.alternative && (
                    <p className="text-gray-500 text-xs italic">
                      {explanation.alternative}
                    </p>
                  )}
                  {explanation.concepts.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-1">
                      {explanation.concepts.map((concept, i) => (
                        <span
                          key={i}
                          className="px-1.5 py-0.5 text-[10px] rounded bg-surface-2 text-gray-500"
                        >
                          {concept}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right: Analysis panel */}
        <div className="flex-1 min-w-0 space-y-4">
          {/* Slim top bar — 3 key metrics */}
          {game.analysis && (
            <div className="flex items-center gap-4 px-4 py-3 rounded-xl bg-surface-1 border border-surface-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 uppercase">Accuracy</span>
                <span className={`text-lg font-bold ${accuracyColor(getAccuracy(game.analysis.accuracy, game.analysis.overall_cpl))}`}>
                  {formatAccuracy(game.analysis.overall_cpl, game.analysis.accuracy)}
                </span>
              </div>
              <div className="w-px h-6 bg-surface-3" />
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 uppercase">Blunders</span>
                <span className="text-lg font-bold text-red-400">{game.analysis.blunders}</span>
              </div>
              <div className="w-px h-6 bg-surface-3" />
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 uppercase">Mistakes</span>
                <span className="text-lg font-bold text-orange-400">{game.analysis.mistakes}</span>
              </div>
            </div>
          )}

          {/* Analysis sections — all collapsible, collapsed by default */}
          {game.analysis ? (
            <>
              <CollapsibleSection title="Key Moments" defaultOpen={false}>
                <div className="space-y-2">
                  {analysis?.moves
                    ?.filter((m) => m.move_quality === "Blunder" || m.move_quality === "Mistake" || m.move_quality === "Missed Win" || m.move_quality === "Brilliant")
                    .slice(0, 5)
                    .map((m, i) => (
                      <div
                        key={i}
                        className={`px-3 py-2 rounded-lg text-sm cursor-pointer hover:bg-surface-2 transition-colors ${moveQualityBg(m.move_quality)}`}
                        onClick={() => {
                          // Find move index and navigate
                          const idx = analysis?.moves?.findIndex((mv) => mv === m) ?? -1;
                          if (idx >= 0) setMoveIndex(idx + 1);
                        }}
                      >
                        <span className={moveQualityColor(m.move_quality)}>
                          {m.move_quality}
                        </span>
                        <span className="text-gray-400 ml-2">
                          Move {m.move_number} • {m.san}
                          {m.cp_loss > 0 && (
                            <span className="text-gray-500 ml-1">(−{m.cp_loss} cp)</span>
                          )}
                        </span>
                      </div>
                    ))}
                  {(!analysis?.moves?.some((m) => m.move_quality === "Blunder" || m.move_quality === "Mistake" || m.move_quality === "Missed Win" || m.move_quality === "Brilliant")) && (
                    <p className="text-sm text-gray-500">No blunders or mistakes — clean game!</p>
                  )}
                </div>
              </CollapsibleSection>

              <CollapsibleSection title="Phase Accuracy" defaultOpen={false}>
                <div className="flex gap-4 text-sm">
                  <PhaseChip label="Opening" cpl={game.analysis.phase_opening_cpl} />
                  <PhaseChip label="Middle" cpl={game.analysis.phase_middlegame_cpl} />
                  <PhaseChip label="Endgame" cpl={game.analysis.phase_endgame_cpl} />
                </div>
              </CollapsibleSection>

              <CollapsibleSection title="Full Details" defaultOpen={false}>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  {(game.analysis.brilliant_moves ?? 0) > 0 && (
                    <div>
                      <span className="text-gray-500">Brilliant</span>
                      <p className="text-lg font-bold text-cyan-300">{game.analysis.brilliant_moves}</p>
                    </div>
                  )}
                  {(game.analysis.great_moves ?? 0) > 0 && (
                    <div>
                      <span className="text-gray-500">Great</span>
                      <p className="text-lg font-bold text-blue-400">{game.analysis.great_moves}</p>
                    </div>
                  )}
                  <div>
                    <span className="text-gray-500">Best moves</span>
                    <p className="text-lg font-bold text-cyan-400">{game.analysis.best_moves}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Inaccuracies</span>
                    <p className="text-lg font-bold text-yellow-400">{game.analysis.inaccuracies}</p>
                  </div>
                  {(game.analysis.missed_wins ?? 0) > 0 && (
                    <div>
                      <span className="text-gray-500">Missed wins</span>
                      <p className="text-lg font-bold text-orange-500">{game.analysis.missed_wins}</p>
                    </div>
                  )}
                  <div>
                    <span className="text-gray-500">Depth</span>
                    <p className="text-lg font-bold">{game.analysis.depth}</p>
                  </div>
                </div>
              </CollapsibleSection>
            </>
          ) : (
            <Card>
              <CardContent className="text-center py-8">
                <BarChart3 className="h-8 w-8 text-gray-600 mx-auto mb-3" />
                <p className="text-gray-400 mb-3">
                  This game hasn't been analyzed yet.
                </p>
                <Button onClick={() => analysisAPI.start([gameId]).then(fetchData)}>
                  <Play className="h-4 w-4" /> Analyze Game
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Move list */}
          <CollapsibleSection title="Moves" defaultOpen={true}>
            <div className="max-h-[400px] overflow-y-auto space-y-0.5 pr-2 custom-scrollbar">
              {parsedMoves.length === 0 ? (
                <p className="text-gray-500 text-sm">No moves available</p>
              ) : (
                <MoveList
                  moves={parsedMoves}
                  evals={moveEvalMap}
                  currentIndex={moveIndex}
                  onSelect={(i) => setMoveIndex(i + 1)}
                />
              )}
            </div>
          </CollapsibleSection>

          {/* AI Coach Review */}
          {game.analysis && (
            <CollapsibleSection title="AI Coach" defaultOpen={false} icon={<MessageSquare className="h-4 w-4 text-brand-400" />}>
              {!coachReview && !coachLoading && (
                <div className="flex items-center justify-between">
                  <p className="text-sm text-gray-500">
                    Get a personalized coaching review.
                  </p>
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={coachLoading}
                    disabled={coachLoading}
                    onClick={async () => {
                      setCoachLoading(true);
                      try {
                        const review = await coachAPI.review(gameId);
                        setCoachReview(review);
                      } catch {
                        // quota error, etc.
                      } finally {
                        setCoachLoading(false);
                      }
                    }}
                  >
                    Get Review
                  </Button>
                </div>
              )}

              {coachLoading && !coachReview && (
                <div className="flex items-center gap-2 text-sm text-gray-400 py-4">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Coach is analyzing your game...
                </div>
              )}

              {coachReview && (
                <div className="space-y-4">
                  {coachReview.sections.map((section, i) => (
                    <div key={i}>
                      <h4 className="text-sm font-semibold text-brand-300 mb-1">
                        {section.title}
                      </h4>
                      <p className="text-sm text-gray-400 whitespace-pre-line leading-relaxed line-clamp-6">
                        {section.content}
                      </p>
                    </div>
                  ))}
                  {coachReview.reviews_limit && (
                    <p className="text-xs text-gray-600 pt-2 border-t border-surface-3">
                      {coachReview.reviews_used}/{coachReview.reviews_limit} free reviews used
                    </p>
                  )}
                </div>
              )}
            </CollapsibleSection>
          )}

          {/* Train From This Game CTA */}
          {game.analysis && (
            <Link href="/train">
              <Button variant="secondary" className="w-full">
                <Dumbbell className="h-4 w-4" />
                Train From This Game
              </Button>
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Eval Bar ───────────────────────────────────────────

function EvalBar({
  evalCp,
  orientation,
}: {
  evalCp: number;
  orientation: "white" | "black";
}) {
  // Convert centipawns to percentage (clamped)
  const clampedEval = Math.max(-500, Math.min(500, evalCp));
  const whitePct = 50 + (clampedEval / 500) * 50;
  const displayPct = orientation === "white" ? whitePct : 100 - whitePct;

  const evalText =
    Math.abs(evalCp) >= 10000
      ? evalCp > 0
        ? "M"
        : "-M"
      : (evalCp / 100).toFixed(1);

  return (
    <div className="w-6 h-[480px] rounded-lg overflow-hidden flex flex-col relative bg-gray-800">
      <div
        className="bg-white transition-all duration-300"
        style={{
          height: `${orientation === "white" ? 100 - displayPct : displayPct}%`,
        }}
      />
      <div
        className="bg-gray-900 flex-1"
      />
      <div className="absolute inset-0 flex items-center justify-center">
        <span
          className={`text-[10px] font-bold -rotate-90 ${
            whitePct > 50 ? "text-gray-800" : "text-gray-300"
          }`}
        >
          {evalText}
        </span>
      </div>
    </div>
  );
}

// ─── Move List ──────────────────────────────────────────

function MoveList({
  moves,
  evals,
  currentIndex,
  onSelect,
}: {
  moves: { san: string; color: "w" | "b"; moveNumber: number }[];
  evals: Map<number, MoveEval>;
  currentIndex: number; // 0 = starting position, 1 = after first move, etc.
  onSelect: (moveIdx: number) => void;
}) {
  // Group moves into pairs (white + black)
  const rows: {
    moveNum: number;
    white?: { san: string; idx: number; eval?: MoveEval };
    black?: { san: string; idx: number; eval?: MoveEval };
  }[] = [];

  for (let i = 0; i < moves.length; i++) {
    const move = moves[i];
    const evalData = evals.get(i);

    if (move.color === "w") {
      rows.push({
        moveNum: Math.ceil((i + 1) / 2),
        white: { san: move.san, idx: i, eval: evalData },
      });
    } else {
      if (rows.length > 0 && !rows[rows.length - 1].black) {
        rows[rows.length - 1].black = {
          san: move.san,
          idx: i,
          eval: evalData,
        };
      } else {
        rows.push({
          moveNum: Math.ceil((i + 1) / 2),
          black: { san: move.san, idx: i, eval: evalData },
        });
      }
    }
  }

  return (
    <div className="font-mono text-sm">
      {rows.map((row, ri) => (
        <div key={ri} className="flex items-center">
          <span className="w-8 text-right text-gray-600 mr-2 text-xs">
            {row.moveNum}.
          </span>
          {row.white && (
            <MoveCell
              san={row.white.san}
              eval={row.white.eval}
              isActive={currentIndex === row.white.idx + 1}
              onClick={() => onSelect(row.white!.idx)}
            />
          )}
          {row.black && (
            <MoveCell
              san={row.black.san}
              eval={row.black.eval}
              isActive={currentIndex === row.black.idx + 1}
              onClick={() => onSelect(row.black!.idx)}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function MoveCell({
  san,
  eval: evalData,
  isActive,
  onClick,
}: {
  san: string;
  eval?: MoveEval;
  isActive: boolean;
  onClick: () => void;
}) {
  const quality = evalData?.move_quality ?? null;

  return (
    <button
      onClick={onClick}
      className={`flex-1 px-2 py-1 rounded text-left transition-colors ${
        isActive
          ? "bg-brand-600/30 text-white"
          : "hover:bg-surface-2 text-gray-300"
      } ${moveQualityColor(isActive ? null : quality)}`}
    >
      {san}
      {quality && quality !== "Best" && quality !== "Excellent" && quality !== "Good" && quality !== "Forced" && (
        <span className={`ml-1 text-[10px] opacity-60 ${quality === "Brilliant" ? "text-cyan-300" : quality === "Great" ? "text-blue-400" : ""}`}>
          {moveQualityAnnotation(quality)}
        </span>
      )}
      {quality === "Brilliant" && <span className="ml-0.5 text-[10px]">💎</span>}
      {quality === "Great" && <span className="ml-0.5 text-[10px]">⭐</span>}
    </button>
  );
}

// ─── Collapsible Section ────────────────────────────────

function CollapsibleSection({
  title,
  defaultOpen = false,
  icon,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <Card>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-5 py-3.5 text-left"
      >
        <span className="font-semibold text-sm text-gray-400 uppercase tracking-wider flex items-center gap-2">
          {icon}
          {title}
        </span>
        <ChevronDown
          className={`h-4 w-4 text-gray-500 transition-transform ${isOpen ? "rotate-180" : ""}`}
        />
      </button>
      {isOpen && (
        <div className="px-5 pb-4">
          {children}
        </div>
      )}
    </Card>
  );
}

// ─── Phase Chip ─────────────────────────────────────────

function PhaseChip({
  label,
  cpl,
}: {
  label: string;
  cpl: number | null;
}) {
  if (cpl === null) return null;

  const acc = getAccuracy(null, cpl);
  const color = accuracyColor(acc);

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-gray-500">{label}:</span>
      <span className={`font-semibold ${color}`}>{acc !== null ? `${acc}%` : "—"}</span>
    </div>
  );
}

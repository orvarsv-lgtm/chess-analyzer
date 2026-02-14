"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import {
  Upload,
  Search,
  ChevronRight,
  Swords,
  BarChart3,
  RefreshCw,
  ChevronLeft,
  Play,
  X,
  Plus,
  Zap,
  CheckCircle2,
  AlertCircle,
  MessageSquare,
} from "lucide-react";
import {
  gamesAPI,
  analysisAPI,
  coachAPI,
  type GameSummary,
  type GamesListResponse,
  type AnalysisProgressEvent,
  type CoachReview,
  APIError,
} from "@/lib/api";
import {
  Button,
  Badge,
  Card,
  EmptyState,
  Spinner,
  resultBadgeVariant,
} from "@/components/ui";
import { cplToAccuracy, accuracyColor, formatAccuracy } from "@/lib/utils";

// Helper: build game label "User vs Opponent"
function gameLabel(game: GameSummary): string {
  const wp = game.white_player || "White";
  const bp = game.black_player || "Black";
  return `${wp} vs ${bp}`;
}

export default function GamesPage() {
  const { data: session } = useSession();

  // ─── Import modal state ──────────────────────────────
  const [showImportModal, setShowImportModal] = useState(false);
  const [importTab, setImportTab] = useState<"lichess" | "chess.com" | "pgn">("lichess");
  const [lichessUser, setLichessUser] = useState("");
  const [chesscomUser, setChesscomUser] = useState("");
  const [pgnText, setPgnText] = useState("");
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  // ─── Games list state ────────────────────────────────
  const [games, setGames] = useState<GameSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage] = useState(20);
  const [loadingGames, setLoadingGames] = useState(true);
  const [filterResult, setFilterResult] = useState<string>("");
  const [filterPlatform, setFilterPlatform] = useState<string>("");

  // ─── Analysis state ──────────────────────────────────
  const [analyzingIds, setAnalyzingIds] = useState<Set<number>>(new Set());

  // ─── AI review state ─────────────────────────────────
  const [reviewingIds, setReviewingIds] = useState<Set<number>>(new Set());
  const [aiReviewModal, setAiReviewModal] = useState<{
    open: boolean;
    gameLabel: string;
    review: CoachReview | null;
    error: string | null;
  }>({ open: false, gameLabel: "", review: null, error: null });

  // ─── Analyse All state ───────────────────────────────
  const [showAnalyseAll, setShowAnalyseAll] = useState(false);
  const [analyseAllRunning, setAnalyseAllRunning] = useState(false);
  const [analyseAllProgress, setAnalyseAllProgress] = useState<{
    completed: number;
    total: number;
    currentLabel: string;
    results: { game_id: number; label: string; cpl: number; blunders: number; mistakes: number }[];
    error: string | null;
    done: boolean;
  }>({ completed: 0, total: 0, currentLabel: "", results: [], error: null, done: false });

  // ─── Selected game ───────────────────────────────────
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selectedGame = games.find((g) => g.id === selectedId) ?? null;

  // ─── Derived: how many unanalyzed ────────────────────
  const unanalyzedCount = games.filter((g) => !g.has_analysis).length;

  // ─── Fetch games ─────────────────────────────────────
  const fetchGames = useCallback(async () => {
    setLoadingGames(true);
    try {
      const res: GamesListResponse = await gamesAPI.list({
        page,
        per_page: perPage,
        result: filterResult || undefined,
        platform: filterPlatform || undefined,
      });
      setGames(res.games);
      setTotal(res.total);
    } catch (err) {
      if (err instanceof APIError && err.status === 401) {
        // Not logged in
      }
    } finally {
      setLoadingGames(false);
    }
  }, [page, perPage, filterResult, filterPlatform]);

  useEffect(() => {
    if (session) fetchGames();
  }, [session, fetchGames]);

  // ─── Import handlers ─────────────────────────────────
  async function handleImport() {
    setImporting(true);
    setImportMsg(null);
    try {
      if (importTab === "lichess") {
        if (!lichessUser.trim()) return;
        const res = await gamesAPI.fetchLichess(lichessUser.trim());
        setImportMsg({ type: "success", text: `Imported ${res.imported} games from Lichess` });
        setLichessUser("");
      } else if (importTab === "chess.com") {
        if (!chesscomUser.trim()) return;
        const res = await gamesAPI.fetchChesscom(chesscomUser.trim());
        setImportMsg({ type: "success", text: `Imported ${res.imported} games from Chess.com` });
        setChesscomUser("");
      } else {
        if (!pgnText.trim()) return;
        const res = await gamesAPI.importPGN(pgnText);
        setImportMsg({ type: "success", text: `Imported ${res.imported} games from PGN` });
        setPgnText("");
      }
      fetchGames();
      // Close modal on success after a short delay
      setTimeout(() => setShowImportModal(false), 1200);
    } catch (err) {
      setImportMsg({ type: "error", text: err instanceof Error ? err.message : "Import failed" });
    } finally {
      setImporting(false);
    }
  }

  async function handleAnalyze(gameId: number) {
    setAnalyzingIds((prev) => new Set(prev).add(gameId));
    try {
      await analysisAPI.runAnalysis({ game_ids: [gameId] }, (event) => {
        if (event.type === "complete" || event.type === "error") {
          fetchGames();
          setAnalyzingIds((prev) => {
            const next = new Set(prev);
            next.delete(gameId);
            return next;
          });
        }
      });
    } catch {
      setAnalyzingIds((prev) => {
        const next = new Set(prev);
        next.delete(gameId);
        return next;
      });
      fetchGames();
    }
  }

  async function handleAIReview(game: GameSummary) {
    if (!game.has_analysis) return;

    setReviewingIds((prev) => new Set(prev).add(game.id));
    setAiReviewModal({
      open: true,
      gameLabel: gameLabel(game),
      review: null,
      error: null,
    });

    try {
      const review = await coachAPI.review(game.id);
      setAiReviewModal((prev) => ({ ...prev, review }));
    } catch (err) {
      setAiReviewModal((prev) => ({
        ...prev,
        error: err instanceof Error ? err.message : "AI review failed",
      }));
    } finally {
      setReviewingIds((prev) => {
        const next = new Set(prev);
        next.delete(game.id);
        return next;
      });
    }
  }

  // ─── Analyse All handler ─────────────────────────────
  async function handleAnalyseAll() {
    setAnalyseAllRunning(true);
    setAnalyseAllProgress({
      completed: 0,
      total: 0,
      currentLabel: "Starting analysis...",
      results: [],
      error: null,
      done: false,
    });
    setShowAnalyseAll(true);

    try {
      await analysisAPI.runAnalysis({}, (event: AnalysisProgressEvent) => {
        if (event.type === "start") {
          setAnalyseAllProgress((prev) => ({
            ...prev,
            total: event.total,
            currentLabel: `Analyzing game 1 of ${event.total}...`,
          }));
        } else if (event.type === "progress") {
          setAnalyseAllProgress((prev) => ({
            ...prev,
            completed: event.completed,
            total: event.total,
            currentLabel:
              event.completed < event.total
                ? `Analyzing game ${event.completed + 1} of ${event.total}...`
                : "Finishing up...",
            results: [
              ...prev.results,
              {
                game_id: event.game_id,
                label: event.game_label,
                cpl: event.overall_cpl,
                blunders: event.blunders,
                mistakes: event.mistakes,
              },
            ],
          }));
        } else if (event.type === "complete") {
          setAnalyseAllProgress((prev) => ({
            ...prev,
            done: true,
            currentLabel: `Done! Analyzed ${event.analyzed} games.`,
          }));
        } else if (event.type === "error") {
          setAnalyseAllProgress((prev) => ({
            ...prev,
            done: true,
            error: event.message,
          }));
        }
      });
    } catch (err) {
      setAnalyseAllProgress((prev) => ({
        ...prev,
        done: true,
        error: err instanceof Error ? err.message : "Analysis failed",
      }));
    } finally {
      setAnalyseAllRunning(false);
      fetchGames();
    }
  }

  if (!session) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-500">Sign in to view your games.</p>
      </div>
    );
  }

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">My Games</h1>
          <p className="text-gray-500 mt-1">
            {total} game{total !== 1 ? "s" : ""} imported
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={fetchGames}
            disabled={loadingGames}
          >
            <RefreshCw className={`h-4 w-4 ${loadingGames ? "animate-spin" : ""}`} />
          </Button>
          {unanalyzedCount > 0 && (
            <Button
              variant="secondary"
              onClick={handleAnalyseAll}
              disabled={analyseAllRunning}
            >
              <Zap className="h-4 w-4" />
              Analyse All ({unanalyzedCount})
            </Button>
          )}
          <Button onClick={() => { setShowImportModal(true); setImportMsg(null); }}>
            <Plus className="h-4 w-4" />
            Import Games
          </Button>
        </div>
      </div>

      {/* Filters — collapsible on mobile */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={filterResult}
          onChange={(e) => { setFilterResult(e.target.value); setPage(1); }}
          className="px-3 py-2 rounded-lg bg-surface-2 border border-surface-3 text-sm text-gray-300 focus:outline-none focus:ring-2 focus:ring-brand-600/50"
        >
          <option value="">All results</option>
          <option value="win">Wins</option>
          <option value="loss">Losses</option>
          <option value="draw">Draws</option>
        </select>
        <select
          value={filterPlatform}
          onChange={(e) => { setFilterPlatform(e.target.value); setPage(1); }}
          className="px-3 py-2 rounded-lg bg-surface-2 border border-surface-3 text-sm text-gray-300 focus:outline-none focus:ring-2 focus:ring-brand-600/50"
        >
          <option value="">All platforms</option>
          <option value="lichess">Lichess</option>
          <option value="chess.com">Chess.com</option>
        </select>
      </div>

      {/* Main content — split layout on desktop */}
      {loadingGames ? (
        <div className="flex justify-center py-12">
          <Spinner className="h-8 w-8 text-brand-500" />
        </div>
      ) : games.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Swords className="h-12 w-12" />}
            title="No games yet"
            description="Import games from Lichess, Chess.com, or paste PGN to get started."
            action={
              <Button onClick={() => setShowImportModal(true)}>
                <Plus className="h-4 w-4" /> Import Games
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Left: game list */}
          <div className="flex-1 min-w-0 space-y-2">
            {games.map((game) => (
              <GameRow
                key={game.id}
                game={game}
                analyzing={analyzingIds.has(game.id)}
                reviewing={reviewingIds.has(game.id)}
                onAnalyze={() => handleAnalyze(game.id)}
                onAIReview={() => handleAIReview(game)}
                isSelected={selectedId === game.id}
                onSelect={() => setSelectedId(game.id)}
              />
            ))}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 pt-4">
                <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="text-sm text-gray-400">
                  {page} / {totalPages}
                </span>
                <Button variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>

          {/* Right: selected game summary (desktop) */}
          <div className="hidden lg:block lg:w-[320px]">
            {selectedGame ? (
              <GameSummaryPanel
                game={selectedGame}
                analyzing={analyzingIds.has(selectedGame.id)}
                reviewing={reviewingIds.has(selectedGame.id)}
                onAnalyze={() => handleAnalyze(selectedGame.id)}
                onAIReview={() => handleAIReview(selectedGame)}
              />
            ) : (
              <Card className="p-8 text-center">
                <p className="text-gray-500 text-sm">
                  Select a game to see details
                </p>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* ─── Import modal ─── */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-lg relative animate-fade-in">
            <button
              onClick={() => setShowImportModal(false)}
              className="absolute top-4 right-4 text-gray-500 hover:text-white transition-colors"
            >
              <X className="h-5 w-5" />
            </button>

            <div className="p-6 space-y-5">
              <h2 className="text-lg font-semibold">Import Games</h2>

              {/* Tab selector */}
              <div className="flex rounded-lg bg-surface-2 p-1">
                {(["lichess", "chess.com", "pgn"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => { setImportTab(tab); setImportMsg(null); }}
                    className={`flex-1 py-2.5 px-3 rounded-md text-sm font-medium transition-colors ${
                      importTab === tab
                        ? "bg-brand-600 text-white"
                        : "text-gray-400 hover:text-white"
                    }`}
                  >
                    {tab === "lichess" ? "Lichess" : tab === "chess.com" ? "Chess.com" : "Paste PGN"}
                  </button>
                ))}
              </div>

              {/* Input */}
              {importTab === "lichess" && (
                <input
                  type="text"
                  placeholder="Lichess username"
                  value={lichessUser}
                  onChange={(e) => setLichessUser(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleImport()}
                  className="w-full px-4 py-3 bg-surface-2 border border-surface-3 rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-600 text-sm"
                />
              )}
              {importTab === "chess.com" && (
                <input
                  type="text"
                  placeholder="Chess.com username"
                  value={chesscomUser}
                  onChange={(e) => setChesscomUser(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleImport()}
                  className="w-full px-4 py-3 bg-surface-2 border border-surface-3 rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-600 text-sm"
                />
              )}
              {importTab === "pgn" && (
                <textarea
                  placeholder="Paste PGN text here..."
                  value={pgnText}
                  onChange={(e) => setPgnText(e.target.value)}
                  rows={5}
                  className="w-full px-4 py-3 bg-surface-2 border border-surface-3 rounded-lg text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-600 text-sm font-mono resize-none"
                />
              )}

              {/* Feedback */}
              {importMsg && (
                <div className={`px-4 py-3 rounded-lg text-sm ${
                  importMsg.type === "success"
                    ? "bg-green-900/30 text-green-400 border border-green-800/50"
                    : "bg-red-900/30 text-red-400 border border-red-800/50"
                }`}>
                  {importMsg.text}
                </div>
              )}

              {/* Submit */}
              <Button
                onClick={handleImport}
                className="w-full"
                loading={importing}
                disabled={importing}
              >
                <Upload className="h-4 w-4" />
                Import
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* ─── Analyse All modal ─── */}
      {showAnalyseAll && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-lg relative animate-fade-in">
            {analyseAllProgress.done && (
              <button
                onClick={() => setShowAnalyseAll(false)}
                className="absolute top-4 right-4 text-gray-500 hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            )}

            <div className="p-6 space-y-5">
              <div className="flex items-center gap-3">
                {analyseAllProgress.done ? (
                  analyseAllProgress.error ? (
                    <AlertCircle className="h-6 w-6 text-red-400" />
                  ) : (
                    <CheckCircle2 className="h-6 w-6 text-green-400" />
                  )
                ) : (
                  <Spinner className="h-6 w-6 text-brand-500" />
                )}
                <h2 className="text-lg font-semibold">
                  {analyseAllProgress.done ? "Analysis Complete" : "Analysing Games..."}
                </h2>
              </div>

              {/* Progress bar */}
              {analyseAllProgress.total > 0 && (
                <div>
                  <div className="flex justify-between text-xs text-gray-400 mb-2">
                    <span>{analyseAllProgress.currentLabel}</span>
                    <span>{analyseAllProgress.completed}/{analyseAllProgress.total}</span>
                  </div>
                  <div className="w-full h-2 bg-surface-2 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-brand-500 rounded-full transition-all duration-500"
                      style={{
                        width: `${(analyseAllProgress.completed / analyseAllProgress.total) * 100}%`,
                      }}
                    />
                  </div>
                </div>
              )}

              {/* Error */}
              {analyseAllProgress.error && (
                <div className="px-4 py-3 rounded-lg text-sm bg-red-900/30 text-red-400 border border-red-800/50">
                  {analyseAllProgress.error}
                </div>
              )}

              {/* Results list */}
              {analyseAllProgress.results.length > 0 && (
                <div className="max-h-[300px] overflow-y-auto space-y-1.5 custom-scrollbar">
                  {analyseAllProgress.results.map((r, i) => {
                    const acc = cplToAccuracy(r.cpl);
                    return (
                      <Link
                        href={`/games/${r.game_id}`}
                        key={r.game_id}
                        className="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface-2/50 hover:bg-surface-2 transition-colors group"
                      >
                        <span className="text-xs text-gray-500 w-5">{i + 1}</span>
                        <span className="flex-1 text-sm truncate">{r.label}</span>
                        <span className={`text-sm font-semibold ${accuracyColor(acc)}`}>
                          {acc !== null ? `${acc}%` : "—"}
                        </span>
                        <div className="flex items-center gap-2 text-xs">
                          {r.blunders > 0 && (
                            <span className="text-red-400">{r.blunders}B</span>
                          )}
                          {r.mistakes > 0 && (
                            <span className="text-orange-400">{r.mistakes}M</span>
                          )}
                          {r.blunders === 0 && r.mistakes === 0 && (
                            <span className="text-green-400">Clean</span>
                          )}
                        </div>
                        <ChevronRight className="h-3 w-3 text-gray-600 group-hover:text-gray-400" />
                      </Link>
                    );
                  })}
                </div>
              )}

              {/* Done button */}
              {analyseAllProgress.done && !analyseAllProgress.error && (
                <Button className="w-full" onClick={() => setShowAnalyseAll(false)}>
                  <CheckCircle2 className="h-4 w-4" />
                  Done — View Games
                </Button>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* ─── AI Review modal ─── */}
      {aiReviewModal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-2xl relative animate-fade-in">
            <button
              onClick={() =>
                setAiReviewModal({ open: false, gameLabel: "", review: null, error: null })
              }
              className="absolute top-4 right-4 text-gray-500 hover:text-white transition-colors"
            >
              <X className="h-5 w-5" />
            </button>

            <div className="p-6 space-y-4">
              <h2 className="text-lg font-semibold">AI Game Review</h2>
              <p className="text-sm text-gray-500">{aiReviewModal.gameLabel}</p>

              {!aiReviewModal.review && !aiReviewModal.error && (
                <div className="flex items-center gap-2 text-sm text-gray-400 py-3">
                  <Spinner className="h-4 w-4 text-brand-500" />
                  AI coach is analyzing this game...
                </div>
              )}

              {aiReviewModal.error && (
                <div className="px-4 py-3 rounded-lg text-sm bg-red-900/30 text-red-400 border border-red-800/50">
                  {aiReviewModal.error}
                </div>
              )}

              {aiReviewModal.review && (
                <div className="space-y-4 max-h-[60vh] overflow-y-auto custom-scrollbar pr-1">
                  {aiReviewModal.review.sections.map((section, i) => (
                    <div key={i}>
                      <h4 className="text-sm font-semibold text-brand-300 mb-1">{section.title}</h4>
                      <p className="text-sm text-gray-300 whitespace-pre-line leading-relaxed">
                        {section.content}
                      </p>
                    </div>
                  ))}
                  {aiReviewModal.review.reviews_limit && (
                    <p className="text-xs text-gray-600 pt-2 border-t border-surface-3">
                      {aiReviewModal.review.reviews_used}/{aiReviewModal.review.reviews_limit} free reviews used
                    </p>
                  )}
                </div>
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

// ─── Game Row Component ─────────────────────────────────

function GameRow({
  game,
  analyzing,
  reviewing,
  onAnalyze,
  onAIReview,
  isSelected,
  onSelect,
}: {
  game: GameSummary;
  analyzing: boolean;
  reviewing: boolean;
  onAnalyze: () => void;
  onAIReview: () => void;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const date = new Date(game.date);
  const dateStr = date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
  const label = gameLabel(game);

  return (
    <div
      onClick={onSelect}
      className={`cursor-pointer rounded-xl border transition-colors ${
        isSelected
          ? "border-brand-600/50 bg-brand-600/5"
          : "border-surface-3 bg-surface-1 hover:bg-surface-2/50"
      }`}
    >
      <Link href={`/games/${game.id}`} className="flex items-center gap-4 px-5 py-3.5 group">
        {/* Color indicator */}
        <div
          className={`h-8 w-8 rounded-lg flex items-center justify-center text-sm font-bold ${
            game.color === "white"
              ? "bg-white text-gray-900"
              : "bg-gray-800 text-white border border-surface-3"
          }`}
        >
          {game.color === "white" ? "♔" : "♚"}
        </div>

        {/* Game info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm truncate">
              {label}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500 mt-0.5">
            <span>{dateStr}</span>
            {game.time_control && <span>{game.time_control}</span>}
            {game.opening_name && (
              <span className="truncate max-w-[160px]">{game.opening_name}</span>
            )}
          </div>
        </div>

        {/* Result badge */}
        <Badge variant={resultBadgeVariant(game.result)}>
          {game.result.toUpperCase()}
        </Badge>

        {/* Analysis status */}
        {game.has_analysis ? (
          <div className="flex items-center gap-2">
            <Badge variant="info">
              <BarChart3 className="h-3 w-3 mr-1" />
              Reviewed
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onAIReview();
              }}
              loading={reviewing}
              disabled={reviewing}
            >
              <MessageSquare className="h-3 w-3" />
              AI Review
            </Button>
          </div>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onAnalyze();
            }}
            loading={analyzing}
            disabled={analyzing}
          >
            <Play className="h-3 w-3" />
            Analyze
          </Button>
        )}
      </Link>
    </div>
  );
}

// ─── Game Summary Panel ─────────────────────────────────

function GameSummaryPanel({
  game,
  analyzing,
  reviewing,
  onAnalyze,
  onAIReview,
}: {
  game: GameSummary;
  analyzing: boolean;
  reviewing: boolean;
  onAnalyze: () => void;
  onAIReview: () => void;
}) {
  const date = new Date(game.date);
  const dateStr = date.toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
  const label = gameLabel(game);

  return (
    <Card className="sticky top-8 space-y-0">
      <div className="p-5 border-b border-surface-3">
        <div className="flex items-center gap-3 mb-3">
          <div
            className={`h-10 w-10 rounded-lg flex items-center justify-center font-bold ${
              game.color === "white"
                ? "bg-white text-gray-900"
                : "bg-gray-800 text-white border border-surface-3"
            }`}
          >
            {game.color === "white" ? "♔" : "♚"}
          </div>
          <div>
            <Badge variant={resultBadgeVariant(game.result)}>
              {game.result.toUpperCase()}
            </Badge>
          </div>
        </div>
        <h3 className="font-semibold truncate">{label}</h3>
        {game.opening_name && <p className="text-xs text-gray-500 mt-0.5">{game.opening_name}</p>}
        {game.eco_code && <p className="text-xs text-gray-600">{game.eco_code}</p>}
      </div>

      <div className="p-5 space-y-3 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">Date</span>
          <span>{dateStr}</span>
        </div>
        {game.time_control && (
          <div className="flex justify-between">
            <span className="text-gray-500">Time control</span>
            <span>{game.time_control}</span>
          </div>
        )}
        {game.player_elo && (
          <div className="flex justify-between">
            <span className="text-gray-500">Rating</span>
            <span>
              {game.player_elo}
              {game.opponent_elo && ` vs ${game.opponent_elo}`}
            </span>
          </div>
        )}
        <div className="flex justify-between">
          <span className="text-gray-500">Platform</span>
          <span className="capitalize">{game.platform}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Status</span>
          {game.has_analysis ? (
            <Badge variant="info">Analyzed</Badge>
          ) : (
            <Badge variant="default">Not analyzed</Badge>
          )}
        </div>
      </div>

      <div className="p-5 pt-0">
        {game.has_analysis ? (
          <div className="space-y-2">
            <Link href={`/games/${game.id}`}>
              <Button className="w-full">
                Review Game <ChevronRight className="h-4 w-4" />
              </Button>
            </Link>
            <Button
              className="w-full"
              variant="secondary"
              onClick={onAIReview}
              loading={reviewing}
              disabled={reviewing}
            >
              <MessageSquare className="h-4 w-4" /> Analyze with AI
            </Button>
          </div>
        ) : (
          <Button
            className="w-full"
            onClick={onAnalyze}
            loading={analyzing}
            disabled={analyzing}
          >
            <Play className="h-4 w-4" /> Analyze Game
          </Button>
        )}
      </div>
    </Card>
  );
}
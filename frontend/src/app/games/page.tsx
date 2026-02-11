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
} from "lucide-react";
import {
  gamesAPI,
  analysisAPI,
  type GameSummary,
  type GamesListResponse,
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

export default function GamesPage() {
  const { data: session } = useSession();

  // ─── Import state ────────────────────────────────────
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
  async function handleLichessImport() {
    if (!lichessUser.trim()) return;
    setImporting(true);
    setImportMsg(null);
    try {
      const res = await gamesAPI.fetchLichess(lichessUser.trim());
      setImportMsg({
        type: "success",
        text: `Imported ${res.imported} games from Lichess (${res.username})`,
      });
      setLichessUser("");
      fetchGames();
    } catch (err) {
      setImportMsg({
        type: "error",
        text: err instanceof Error ? err.message : "Import failed",
      });
    } finally {
      setImporting(false);
    }
  }

  async function handleChesscomImport() {
    if (!chesscomUser.trim()) return;
    setImporting(true);
    setImportMsg(null);
    try {
      const res = await gamesAPI.fetchChesscom(chesscomUser.trim());
      setImportMsg({
        type: "success",
        text: `Imported ${res.imported} games from Chess.com (${res.username})`,
      });
      setChesscomUser("");
      fetchGames();
    } catch (err) {
      setImportMsg({
        type: "error",
        text: err instanceof Error ? err.message : "Import failed",
      });
    } finally {
      setImporting(false);
    }
  }

  async function handlePGNImport() {
    if (!pgnText.trim()) return;
    setImporting(true);
    setImportMsg(null);
    try {
      const res = await gamesAPI.importPGN(pgnText);
      setImportMsg({
        type: "success",
        text: `Imported ${res.imported} games from PGN`,
      });
      setPgnText("");
      fetchGames();
    } catch (err) {
      setImportMsg({
        type: "error",
        text: err instanceof Error ? err.message : "Import failed",
      });
    } finally {
      setImporting(false);
    }
  }

  async function handleAnalyze(gameId: number) {
    setAnalyzingIds((prev) => new Set(prev).add(gameId));
    try {
      await analysisAPI.start([gameId]);
      // Poll briefly then refresh
      setTimeout(() => {
        fetchGames();
        setAnalyzingIds((prev) => {
          const next = new Set(prev);
          next.delete(gameId);
          return next;
        });
      }, 2000);
    } catch {
      setAnalyzingIds((prev) => {
        const next = new Set(prev);
        next.delete(gameId);
        return next;
      });
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
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">My Games</h1>
          <p className="text-gray-500 mt-1">
            Import games from Lichess, Chess.com, or paste PGN directly.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={fetchGames}
          disabled={loadingGames}
        >
          <RefreshCw className={`h-4 w-4 ${loadingGames ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Import feedback */}
      {importMsg && (
        <div
          className={`px-4 py-3 rounded-lg text-sm ${
            importMsg.type === "success"
              ? "bg-green-900/30 text-green-400 border border-green-800/50"
              : "bg-red-900/30 text-red-400 border border-red-800/50"
          }`}
        >
          {importMsg.text}
        </div>
      )}

      {/* Import section */}
      <div className="grid md:grid-cols-3 gap-4">
        {/* Lichess import */}
        <Card className="p-5 space-y-3">
          <h3 className="font-semibold flex items-center gap-2">
            <Search className="h-4 w-4 text-brand-400" />
            Lichess Import
          </h3>
          <input
            type="text"
            placeholder="Enter Lichess username"
            value={lichessUser}
            onChange={(e) => setLichessUser(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleLichessImport()}
            className="w-full px-3 py-2 rounded-lg bg-surface-2 border border-surface-3 text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-600/50"
          />
          <Button
            onClick={handleLichessImport}
            disabled={!lichessUser || importing}
            loading={importing}
            className="w-full"
          >
            Fetch Games
          </Button>
        </Card>

        {/* Chess.com import */}
        <Card className="p-5 space-y-3">
          <h3 className="font-semibold flex items-center gap-2">
            <Search className="h-4 w-4 text-green-400" />
            Chess.com Import
          </h3>
          <input
            type="text"
            placeholder="Enter Chess.com username"
            value={chesscomUser}
            onChange={(e) => setChesscomUser(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleChesscomImport()}
            className="w-full px-3 py-2 rounded-lg bg-surface-2 border border-surface-3 text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-600/50"
          />
          <Button
            onClick={handleChesscomImport}
            disabled={!chesscomUser || importing}
            loading={importing}
            className="w-full"
          >
            Fetch Games
          </Button>
        </Card>

        {/* PGN import */}
        <Card className="p-5 space-y-3">
          <h3 className="font-semibold flex items-center gap-2">
            <Upload className="h-4 w-4 text-brand-400" />
            Manual PGN Import
          </h3>
          <textarea
            placeholder="Paste PGN text here..."
            value={pgnText}
            onChange={(e) => setPgnText(e.target.value)}
            rows={3}
            className="w-full px-3 py-2 rounded-lg bg-surface-2 border border-surface-3 text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-600/50 resize-none text-sm font-mono"
          />
          <Button
            onClick={handlePGNImport}
            disabled={!pgnText || importing}
            loading={importing}
            className="w-full"
          >
            Import PGN
          </Button>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={filterResult}
          onChange={(e) => {
            setFilterResult(e.target.value);
            setPage(1);
          }}
          className="px-3 py-2 rounded-lg bg-surface-2 border border-surface-3 text-sm text-gray-300 focus:outline-none focus:ring-2 focus:ring-brand-600/50"
        >
          <option value="">All results</option>
          <option value="win">Wins</option>
          <option value="loss">Losses</option>
          <option value="draw">Draws</option>
        </select>

        <select
          value={filterPlatform}
          onChange={(e) => {
            setFilterPlatform(e.target.value);
            setPage(1);
          }}
          className="px-3 py-2 rounded-lg bg-surface-2 border border-surface-3 text-sm text-gray-300 focus:outline-none focus:ring-2 focus:ring-brand-600/50"
        >
          <option value="">All platforms</option>
          <option value="lichess">Lichess</option>
          <option value="chess.com">Chess.com</option>
        </select>

        <span className="text-sm text-gray-500 ml-auto">
          {total} game{total !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Games list */}
      {loadingGames ? (
        <div className="flex justify-center py-12">
          <Spinner className="h-8 w-8 text-brand-500" />
        </div>
      ) : games.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Swords className="h-12 w-12" />}
            title="No games yet"
            description="Import games from Lichess or paste PGN from Chess.com to get started."
          />
        </Card>
      ) : (
        <div className="space-y-2">
          {games.map((game) => (
            <GameRow
              key={game.id}
              game={game}
              analyzing={analyzingIds.has(game.id)}
              onAnalyze={() => handleAnalyze(game.id)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-4">
          <Button
            variant="ghost"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm text-gray-400">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="ghost"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}

// ─── Game Row Component ─────────────────────────────────

function GameRow({
  game,
  analyzing,
  onAnalyze,
}: {
  game: GameSummary;
  analyzing: boolean;
  onAnalyze: () => void;
}) {
  const date = new Date(game.date);
  const dateStr = date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return (
    <Link href={`/games/${game.id}`}>
      <Card className="flex items-center gap-4 px-5 py-3.5 hover:bg-surface-2/50 transition-colors cursor-pointer group">
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
              {game.opening_name || "Unknown Opening"}
            </span>
            {game.eco_code && (
              <span className="text-xs text-gray-500">{game.eco_code}</span>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500 mt-0.5">
            <span>{dateStr}</span>
            {game.time_control && <span>{game.time_control}</span>}
            {game.player_elo && (
              <span>
                {game.player_elo}
                {game.opponent_elo && ` vs ${game.opponent_elo}`}
              </span>
            )}
            <span className="capitalize">{game.platform}</span>
          </div>
        </div>

        {/* Result badge */}
        <Badge variant={resultBadgeVariant(game.result)}>
          {game.result.toUpperCase()}
        </Badge>

        {/* Analysis status */}
        {game.has_analysis ? (
          <Badge variant="info">
            <BarChart3 className="h-3 w-3 mr-1" />
            Analyzed
          </Badge>
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

        {/* Arrow */}
        <ChevronRight className="h-4 w-4 text-gray-600 group-hover:text-gray-400 transition-colors" />
      </Card>
    </Link>
  );
}
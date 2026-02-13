"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSession } from "next-auth/react";
import { Chess, Square } from "chess.js";
import { Chessboard } from "react-chessboard";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  Database,
  Globe,
  RotateCcw,
  TrendingUp,
  User,
  Loader2,
} from "lucide-react";
import {
  openingsAPI,
  type ExplorerResponse,
  type PersonalRepertoireResponse,
  type PersonalOpening,
} from "@/lib/api";
import {
  Button,
  Badge,
  Card,
  CardContent,
  CardHeader,
  Spinner,
} from "@/components/ui";

type DatabaseSource = "masters" | "lichess" | "personal";

export default function OpeningsPage() {
  const { data: session } = useSession();

  // ─── State ───────────────────────────────────────────
  const [source, setSource] = useState<DatabaseSource>("masters");
  const [game] = useState(() => new Chess());
  const [fen, setFen] = useState(game.fen());
  const [moveHistory, setMoveHistory] = useState<string[]>([]);
  const [explorer, setExplorer] = useState<ExplorerResponse | null>(null);
  const [personal, setPersonal] = useState<PersonalRepertoireResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [personalLoading, setPersonalLoading] = useState(false);
  const [personalColor, setPersonalColor] = useState<string | undefined>(undefined);
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [selectedSquare, setSelectedSquare] = useState<Square | null>(null);
  const [legalMoves, setLegalMoves] = useState<Square[]>([]);

  // ─── Board interaction ─────────────────────────────
  function onPieceClick(piece: string, square: Square) {
    // If a piece is already selected, try to move to the clicked square
    // (capturing the piece on that square)
    if (selectedSquare && selectedSquare !== square) {
      const moves = game.moves({ square: selectedSquare, verbose: true });
      const target = moves.find((m) => m.to === square);
      if (target) {
        game.move({ from: selectedSquare, to: square, promotion: "q" });
        setFen(game.fen());
        setMoveHistory((prev) => [...prev, target.san]);
        setSelectedSquare(null);
        setLegalMoves([]);
        return;
      }
    }

    // Select this piece (if it belongs to the side to move)
    const p = game.get(square);
    if (p && p.color === game.turn()) {
      setSelectedSquare(square);
      const moves = game.moves({ square, verbose: true });
      setLegalMoves(moves.map((m) => m.to as Square));
    } else {
      setSelectedSquare(null);
      setLegalMoves([]);
    }
  }

  function onSquareClick(square: Square) {
    // If a piece is already selected, try to move to the clicked square
    if (selectedSquare) {
      const moves = game.moves({ square: selectedSquare, verbose: true });
      const target = moves.find((m) => m.to === square);
      if (target) {
        game.move({ from: selectedSquare, to: square, promotion: "q" });
        setFen(game.fen());
        setMoveHistory((prev) => [...prev, target.san]);
        setSelectedSquare(null);
        setLegalMoves([]);
        return;
      }
    }

    // Clicked on an empty square or non-target — deselect
    setSelectedSquare(null);
    setLegalMoves([]);
  }

  function onPieceDrop(sourceSquare: string, targetSquare: string) {
    try {
      const result = game.move({ from: sourceSquare, to: targetSquare, promotion: "q" });
      if (result) {
        setFen(game.fen());
        setMoveHistory((prev) => [...prev, result.san]);
        setSelectedSquare(null);
        setLegalMoves([]);
        return true;
      }
    } catch {
      // invalid move
    }
    return false;
  }

  // Build custom square styles for selection highlight + legal move dots
  const squareStyles = useMemo(() => {
    const styles: Record<string, React.CSSProperties> = {};
    if (selectedSquare) {
      styles[selectedSquare] = {
        backgroundColor: "rgba(255, 255, 0, 0.4)",
      };
    }
    for (const sq of legalMoves) {
      const piece = game.get(sq as Square);
      if (piece) {
        // Capture: ring around the square
        styles[sq] = {
          background: "radial-gradient(transparent 51%, rgba(0,0,0,0.3) 51%)",
        };
      } else {
        // Empty square: small dot
        styles[sq] = {
          background: "radial-gradient(circle, rgba(0,0,0,0.3) 25%, transparent 25%)",
        };
      }
    }
    return styles;
  }, [selectedSquare, legalMoves, game]);

  // ─── Fetch explorer data ─────────────────────────────
  const fetchExplorer = useCallback(async (currentFen: string) => {
    setLoading(true);
    try {
      const data = await openingsAPI.explore({
        fen: currentFen,
        source: source === "personal" ? "lichess" : source,
      });
      setExplorer(data);
    } catch {
      setExplorer(null);
    } finally {
      setLoading(false);
    }
  }, [source]);

  // ─── Fetch personal repertoire ───────────────────────
  const fetchPersonal = useCallback(async () => {
    if (!session) return;
    setPersonalLoading(true);
    try {
      const data = await openingsAPI.personal({ color: personalColor, sort_by: "games" });
      setPersonal(data);
    } catch {
      setPersonal(null);
    } finally {
      setPersonalLoading(false);
    }
  }, [session, personalColor]);

  useEffect(() => {
    if (source !== "personal") {
      fetchExplorer(fen);
    }
  }, [fen, source, fetchExplorer]);

  useEffect(() => {
    if (source === "personal") {
      fetchPersonal();
    }
  }, [source, fetchPersonal]);

  // ─── Make a move ─────────────────────────────────────
  function makeMove(san: string) {
    try {
      game.move(san);
      const newFen = game.fen();
      setFen(newFen);
      setMoveHistory((prev) => [...prev, san]);
      setSelectedSquare(null);
      setLegalMoves([]);
    } catch {
      // Invalid move
    }
  }

  function resetBoard() {
    game.reset();
    setFen(game.fen());
    setMoveHistory([]);
    setSelectedSquare(null);
    setLegalMoves([]);
  }

  function undoMove() {
    game.undo();
    setFen(game.fen());
    setMoveHistory((prev) => prev.slice(0, -1));
    setSelectedSquare(null);
    setLegalMoves([]);
  }

  // ─── Move history display ───────────────────────────
  const moveHistoryDisplay = useMemo(() => {
    const pairs: string[] = [];
    for (let i = 0; i < moveHistory.length; i += 2) {
      const num = Math.floor(i / 2) + 1;
      const white = moveHistory[i];
      const black = moveHistory[i + 1];
      pairs.push(`${num}. ${white}${black ? ` ${black}` : ""}`);
    }
    return pairs.join(" ");
  }, [moveHistory]);

  if (!session) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-500">Sign in to use the Opening Explorer.</p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-8 animate-fade-in">
      <div className="flex items-center gap-3 mb-6">
        <BookOpen className="h-6 w-6 text-brand-400" />
        <h1 className="text-2xl font-bold">Opening Explorer</h1>
      </div>

      {/* Database source tabs */}
      <div className="flex gap-2 mb-6">
        <SourceTab
          icon={<Database className="h-3.5 w-3.5" />}
          label="Masters"
          active={source === "masters"}
          onClick={() => setSource("masters")}
        />
        <SourceTab
          icon={<Globe className="h-3.5 w-3.5" />}
          label="Lichess"
          active={source === "lichess"}
          onClick={() => setSource("lichess")}
        />
        <SourceTab
          icon={<User className="h-3.5 w-3.5" />}
          label="My Openings"
          active={source === "personal"}
          onClick={() => setSource("personal")}
        />
      </div>

      {source !== "personal" ? (
        /* Explorer view (Masters / Lichess) */
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Left: Board */}
          <div className="flex-shrink-0">
            <div className="w-[400px] h-[400px]">
              <Chessboard
                position={fen}
                boardOrientation={orientation}
                boardWidth={400}
                arePiecesDraggable={true}
                onPieceDrop={onPieceDrop}
                onPieceClick={onPieceClick}
                onSquareClick={onSquareClick}
                customSquareStyles={squareStyles}
                customBoardStyle={{
                  borderRadius: "8px",
                  boxShadow: "0 4px 20px rgba(0,0,0,0.4)",
                }}
                customDarkSquareStyle={{ backgroundColor: "#779952" }}
                customLightSquareStyle={{ backgroundColor: "#edeed1" }}
              />
            </div>

            {/* Board controls */}
            <div className="flex items-center justify-center gap-2 mt-4">
              <Button variant="ghost" size="sm" onClick={resetBoard}>
                <RotateCcw className="h-4 w-4" /> Reset
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={undoMove}
                disabled={moveHistory.length === 0}
              >
                Undo
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  setOrientation((o) => (o === "white" ? "black" : "white"))
                }
              >
                Flip
              </Button>
            </div>

            {/* Move history */}
            {moveHistory.length > 0 && (
              <div className="mt-3 px-3 py-2 rounded-lg bg-surface-1 text-sm text-gray-400 font-mono">
                {moveHistoryDisplay}
              </div>
            )}
          </div>

          {/* Right: Explorer data */}
          <div className="flex-1 min-w-0 space-y-4">
            {/* Opening name */}
            {explorer?.opening && (
              <div className="px-4 py-3 rounded-lg bg-surface-1 border border-surface-3">
                <p className="text-sm text-gray-500">Current Opening</p>
                <p className="text-lg font-semibold">
                  {explorer.opening}
                  {explorer.eco && (
                    <span className="text-gray-500 text-sm ml-2">
                      ({explorer.eco})
                    </span>
                  )}
                </p>
              </div>
            )}

            {/* Result bar */}
            {explorer && explorer.total_games > 0 && (
              <div className="px-4 py-3 rounded-lg bg-surface-1 border border-surface-3">
                <p className="text-xs text-gray-500 mb-2">
                  {explorer.total_games.toLocaleString()} games
                </p>
                <ResultBar
                  white={explorer.white_wins}
                  draws={explorer.draws}
                  black={explorer.black_wins}
                  total={explorer.total_games}
                />
              </div>
            )}

            {/* Move table */}
            <Card>
              <CardHeader>
                <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
                  Moves
                </h3>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-5 w-5 animate-spin text-gray-500" />
                  </div>
                ) : explorer?.moves.length ? (
                  <div className="space-y-0">
                    {/* Header */}
                    <div className="grid grid-cols-[60px_1fr_60px_60px_60px_80px] gap-2 text-xs text-gray-600 pb-2 border-b border-surface-3">
                      <span>Move</span>
                      <span>Result bar</span>
                      <span className="text-right">Games</span>
                      <span className="text-right">Win %</span>
                      <span className="text-right">Draw %</span>
                      <span className="text-right">Avg Elo</span>
                    </div>
                    {explorer.moves.map((m) => (
                      <button
                        key={m.san}
                        className="w-full grid grid-cols-[60px_1fr_60px_60px_60px_80px] gap-2 items-center py-2 text-sm hover:bg-surface-2 rounded transition-colors"
                        onClick={() => makeMove(m.san)}
                      >
                        <span className="font-mono font-semibold text-brand-300">
                          {m.san}
                        </span>
                        <MiniResultBar
                          white={m.white}
                          draws={m.draws}
                          black={m.black}
                          total={m.total}
                        />
                        <span className="text-right text-gray-400">
                          {m.total.toLocaleString()}
                        </span>
                        <span className="text-right text-gray-300">
                          {m.win_rate}%
                        </span>
                        <span className="text-right text-gray-500">
                          {m.total > 0
                            ? (
                                (m.draws / m.total) *
                                100
                              ).toFixed(0)
                            : 0}
                          %
                        </span>
                        <span className="text-right text-gray-500">
                          {m.average_rating ?? "—"}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500 py-4 text-center">
                    No data for this position.
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Top games */}
            {explorer?.top_games && explorer.top_games.length > 0 && (
              <Card>
                <CardHeader>
                  <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">
                    Notable Games
                  </h3>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {explorer.top_games.map((g, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between text-sm px-2 py-1.5 rounded hover:bg-surface-2"
                      >
                        <div>
                          <span className="text-gray-300">
                            {g.white}
                            {g.white_rating && (
                              <span className="text-gray-600 text-xs ml-1">
                                ({g.white_rating})
                              </span>
                            )}
                          </span>
                          <span className="text-gray-600 mx-2">vs</span>
                          <span className="text-gray-300">
                            {g.black}
                            {g.black_rating && (
                              <span className="text-gray-600 text-xs ml-1">
                                ({g.black_rating})
                              </span>
                            )}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          {g.year && (
                            <span className="text-xs text-gray-600">
                              {g.year}
                            </span>
                          )}
                          <Badge
                            variant={
                              g.winner === "white"
                                ? "success"
                                : g.winner === "black"
                                ? "danger"
                                : "default"
                            }
                          >
                            {g.winner === "white"
                              ? "1-0"
                              : g.winner === "black"
                              ? "0-1"
                              : "½-½"}
                          </Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      ) : (
        /* Personal repertoire view */
        <div className="space-y-6">
          {/* Color filter */}
          <div className="flex gap-2">
            <Button
              variant={!personalColor ? "primary" : "ghost"}
              size="sm"
              onClick={() => setPersonalColor(undefined)}
            >
              All
            </Button>
            <Button
              variant={personalColor === "white" ? "primary" : "ghost"}
              size="sm"
              onClick={() => setPersonalColor("white")}
            >
              White
            </Button>
            <Button
              variant={personalColor === "black" ? "primary" : "ghost"}
              size="sm"
              onClick={() => setPersonalColor("black")}
            >
              Black
            </Button>
          </div>

          {/* Summary cards */}
          {personal && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card>
                <CardContent>
                  <p className="text-xs text-gray-500 uppercase">
                    Total Openings
                  </p>
                  <p className="text-2xl font-bold mt-1">
                    {personal.total_openings}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent>
                  <p className="text-xs text-gray-500 uppercase">
                    Best Opening
                  </p>
                  <p className="text-lg font-bold mt-1 text-green-400 truncate">
                    {personal.best_opening || "—"}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent>
                  <p className="text-xs text-gray-500 uppercase">
                    Needs Work
                  </p>
                  <p className="text-lg font-bold mt-1 text-red-400 truncate">
                    {personal.worst_opening || "—"}
                  </p>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Opening table */}
          <Card>
            <CardContent>
              {personalLoading ? (
                <div className="flex items-center justify-center py-12">
                  <Spinner className="h-6 w-6 text-brand-500" />
                </div>
              ) : personal?.openings.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs text-gray-600 uppercase border-b border-surface-3">
                        <th className="text-left py-2 pr-4">Opening</th>
                        <th className="text-left py-2 pr-4">Color</th>
                        <th className="text-right py-2 pr-4">Games</th>
                        <th className="text-right py-2 pr-4">Win Rate</th>
                        <th className="text-right py-2 pr-4">Avg CPL</th>
                        <th className="py-2">Results</th>
                      </tr>
                    </thead>
                    <tbody>
                      {personal.openings.map((o, i) => (
                        <tr
                          key={i}
                          className="border-b border-surface-3/50 hover:bg-surface-2 transition-colors"
                        >
                          <td className="py-2.5 pr-4">
                            <span className="font-medium text-gray-300">
                              {o.opening_name}
                            </span>
                            {o.eco_code && (
                              <span className="text-gray-600 text-xs ml-1.5">
                                {o.eco_code}
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 pr-4">
                            <span
                              className={`inline-block w-3 h-3 rounded-full ${
                                o.color === "white"
                                  ? "bg-white"
                                  : "bg-gray-800 border border-gray-600"
                              }`}
                            />
                          </td>
                          <td className="text-right py-2.5 pr-4 text-gray-400">
                            {o.games_played}
                          </td>
                          <td className="text-right py-2.5 pr-4">
                            <span
                              className={
                                o.win_rate >= 60
                                  ? "text-green-400"
                                  : o.win_rate >= 45
                                  ? "text-gray-300"
                                  : "text-red-400"
                              }
                            >
                              {o.win_rate}%
                            </span>
                          </td>
                          <td className="text-right py-2.5 pr-4 text-gray-500">
                            {o.average_cpl !== null
                              ? `${o.average_cpl}`
                              : "—"}
                          </td>
                          <td className="py-2.5">
                            <MiniResultBar
                              white={o.games_won}
                              draws={o.games_drawn}
                              black={o.games_lost}
                              total={o.games_played}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-12">
                  <BookOpen className="h-8 w-8 text-gray-600 mx-auto mb-3" />
                  <p className="text-gray-500">
                    No opening data yet. Analyze some games first!
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// ─── Components ─────────────────────────────────────────

function SourceTab({
  icon,
  label,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
        active
          ? "bg-brand-600 text-white"
          : "bg-surface-1 text-gray-400 hover:bg-surface-2 border border-surface-3"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

function ResultBar({
  white,
  draws,
  black,
  total,
}: {
  white: number;
  draws: number;
  black: number;
  total: number;
}) {
  if (total === 0) return null;
  const wPct = (white / total) * 100;
  const dPct = (draws / total) * 100;
  const bPct = (black / total) * 100;

  return (
    <div className="flex h-5 rounded-lg overflow-hidden text-[10px] font-semibold">
      {wPct > 0 && (
        <div
          className="bg-white text-gray-900 flex items-center justify-center"
          style={{ width: `${wPct}%` }}
        >
          {wPct >= 10 && `${wPct.toFixed(0)}%`}
        </div>
      )}
      {dPct > 0 && (
        <div
          className="bg-gray-500 text-white flex items-center justify-center"
          style={{ width: `${dPct}%` }}
        >
          {dPct >= 10 && `${dPct.toFixed(0)}%`}
        </div>
      )}
      {bPct > 0 && (
        <div
          className="bg-gray-800 text-gray-300 flex items-center justify-center"
          style={{ width: `${bPct}%` }}
        >
          {bPct >= 10 && `${bPct.toFixed(0)}%`}
        </div>
      )}
    </div>
  );
}

function MiniResultBar({
  white,
  draws,
  black,
  total,
}: {
  white: number;
  draws: number;
  black: number;
  total: number;
}) {
  if (total === 0) return null;
  const wPct = (white / total) * 100;
  const dPct = (draws / total) * 100;
  const bPct = (black / total) * 100;

  return (
    <div className="flex h-2.5 rounded-full overflow-hidden w-full min-w-[60px]">
      <div className="bg-white" style={{ width: `${wPct}%` }} />
      <div className="bg-gray-500" style={{ width: `${dPct}%` }} />
      <div className="bg-gray-800" style={{ width: `${bPct}%` }} />
    </div>
  );
}

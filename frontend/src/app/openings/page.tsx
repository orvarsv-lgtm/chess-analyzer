"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  Trophy,
  Target,
  AlertTriangle,
} from "lucide-react";
import {
  insightsAPI,
  type OpeningStat,
} from "@/lib/api";
import {
  Card,
  CardContent,
  Badge,
  Spinner,
  EmptyState,
  Button,
} from "@/components/ui";

export default function OpeningsPage() {
  const { data: session } = useSession();

  const [openings, setOpenings] = useState<OpeningStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [colorFilter, setColorFilter] = useState<string>("");
  const [sortKey, setSortKey] = useState<"games_played" | "win_rate" | "average_cpl">("games_played");
  const [sortAsc, setSortAsc] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await insightsAPI.openings(colorFilter || undefined);
      setOpenings(data);
    } catch {
      // API may not be ready
    } finally {
      setLoading(false);
    }
  }, [colorFilter]);

  useEffect(() => {
    if (session) load();
  }, [session, load]);

  function toggleSort(key: typeof sortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  const sorted = [...openings].sort((a, b) => {
    const aVal = a[sortKey] ?? 0;
    const bVal = b[sortKey] ?? 0;
    return sortAsc ? aVal - bVal : bVal - aVal;
  });

  if (!session) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-500">Sign in to view your opening repertoire.</p>
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

  // Summary stats
  const totalGames = openings.reduce((s, o) => s + o.games_played, 0);
  const uniqueOpenings = openings.length;
  const bestOpening = openings.length > 0
    ? [...openings].filter(o => o.games_played >= 3).sort((a, b) => b.win_rate - a.win_rate)[0]
    : null;
  const worstOpening = openings.length > 0
    ? [...openings].filter(o => o.games_played >= 3).sort((a, b) => a.win_rate - b.win_rate)[0]
    : null;

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">Opening Repertoire</h1>
        <p className="text-gray-500 mt-1">
          See how you perform with each opening across all your games.
        </p>
      </div>

      {openings.length === 0 ? (
        <Card>
          <EmptyState
            icon={<BookOpen className="h-12 w-12" />}
            title="No opening data yet"
            description="Import and analyze some games to see your opening statistics."
          />
        </Card>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card className="p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wider">Total Games</p>
              <p className="text-2xl font-bold mt-1">{totalGames}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wider">Unique Openings</p>
              <p className="text-2xl font-bold mt-1">{uniqueOpenings}</p>
            </Card>
            <Card className="p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wider">Best Opening</p>
              <p className="text-lg font-bold mt-1 text-green-400 truncate">
                {bestOpening ? bestOpening.opening_name : "—"}
              </p>
              {bestOpening && (
                <p className="text-xs text-gray-500">{bestOpening.win_rate}% win rate</p>
              )}
            </Card>
            <Card className="p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wider">Weakest Opening</p>
              <p className="text-lg font-bold mt-1 text-red-400 truncate">
                {worstOpening ? worstOpening.opening_name : "—"}
              </p>
              {worstOpening && (
                <p className="text-xs text-gray-500">{worstOpening.win_rate}% win rate</p>
              )}
            </Card>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-3 flex-wrap">
            <select
              value={colorFilter}
              onChange={(e) => setColorFilter(e.target.value)}
              className="px-3 py-2 rounded-lg bg-surface-2 border border-surface-3 text-sm text-gray-300 focus:outline-none focus:ring-2 focus:ring-brand-600/50"
            >
              <option value="">All colors</option>
              <option value="white">White</option>
              <option value="black">Black</option>
            </select>

            <span className="text-sm text-gray-500 ml-auto">
              {sorted.length} opening{sorted.length !== 1 ? "s" : ""}
            </span>
          </div>

          {/* Table */}
          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-3 text-gray-400">
                    <th className="text-left px-5 py-3 font-medium">Opening</th>
                    <th className="text-center px-3 py-3 font-medium">Color</th>
                    <th className="text-center px-3 py-3 font-medium">ECO</th>
                    <SortHeader
                      label="Games"
                      sortKey="games_played"
                      currentKey={sortKey}
                      asc={sortAsc}
                      onToggle={toggleSort}
                    />
                    <SortHeader
                      label="Win Rate"
                      sortKey="win_rate"
                      currentKey={sortKey}
                      asc={sortAsc}
                      onToggle={toggleSort}
                    />
                    <SortHeader
                      label="Avg CPL"
                      sortKey="average_cpl"
                      currentKey={sortKey}
                      asc={sortAsc}
                      onToggle={toggleSort}
                    />
                    <th className="text-center px-3 py-3 font-medium">Quality</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((o, i) => (
                    <OpeningRow key={`${o.opening_name}-${o.color}-${i}`} opening={o} />
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

// ─── Sort Header ────────────────────────────────────────

function SortHeader({
  label,
  sortKey,
  currentKey,
  asc,
  onToggle,
}: {
  label: string;
  sortKey: "games_played" | "win_rate" | "average_cpl";
  currentKey: string;
  asc: boolean;
  onToggle: (key: "games_played" | "win_rate" | "average_cpl") => void;
}) {
  const isActive = currentKey === sortKey;

  return (
    <th
      className="text-center px-3 py-3 font-medium cursor-pointer select-none hover:text-white transition-colors"
      onClick={() => onToggle(sortKey)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {isActive ? (
          asc ? (
            <ChevronUp className="h-3 w-3" />
          ) : (
            <ChevronDown className="h-3 w-3" />
          )
        ) : null}
      </span>
    </th>
  );
}

// ─── Opening Row ────────────────────────────────────────

function OpeningRow({ opening }: { opening: OpeningStat }) {
  const winColor =
    opening.win_rate >= 60
      ? "text-green-400"
      : opening.win_rate >= 45
      ? "text-yellow-400"
      : "text-red-400";

  const cplColor =
    opening.average_cpl === null
      ? "text-gray-600"
      : opening.average_cpl < 25
      ? "text-green-400"
      : opening.average_cpl < 50
      ? "text-yellow-400"
      : opening.average_cpl < 75
      ? "text-orange-400"
      : "text-red-400";

  // Quality badge
  let qualityBadge: { label: string; variant: "success" | "warning" | "danger" | "default" } | null = null;
  if (opening.games_played >= 3) {
    if (opening.win_rate >= 65 && (opening.average_cpl === null || opening.average_cpl < 40)) {
      qualityBadge = { label: "Strong", variant: "success" };
    } else if (opening.win_rate < 35 || (opening.average_cpl !== null && opening.average_cpl > 60)) {
      qualityBadge = { label: "Needs work", variant: "danger" };
    } else {
      qualityBadge = { label: "Solid", variant: "default" };
    }
  }

  return (
    <tr className="border-b border-surface-3/50 hover:bg-surface-2/30 transition-colors">
      <td className="px-5 py-3">
        <span className="font-medium text-white">{opening.opening_name}</span>
      </td>
      <td className="text-center px-3 py-3">
        <span
          className={`inline-flex h-6 w-6 rounded items-center justify-center text-xs font-bold ${
            opening.color === "white"
              ? "bg-white text-gray-900"
              : "bg-gray-800 text-white border border-surface-3"
          }`}
        >
          {opening.color === "white" ? "♔" : "♚"}
        </span>
      </td>
      <td className="text-center px-3 py-3 text-gray-500 text-xs font-mono">
        {opening.eco_code || "—"}
      </td>
      <td className="text-center px-3 py-3 font-medium">{opening.games_played}</td>
      <td className={`text-center px-3 py-3 font-semibold ${winColor}`}>
        {opening.win_rate}%
      </td>
      <td className={`text-center px-3 py-3 font-medium ${cplColor}`}>
        {opening.average_cpl !== null ? Math.round(opening.average_cpl) : "—"}
      </td>
      <td className="text-center px-3 py-3">
        {qualityBadge ? (
          <Badge variant={qualityBadge.variant}>{qualityBadge.label}</Badge>
        ) : (
          <span className="text-xs text-gray-600">—</span>
        )}
      </td>
    </tr>
  );
}

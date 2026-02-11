"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  Swords,
  Target,
  Zap,
  Clock,
  Flame,
} from "lucide-react";
import {
  insightsAPI,
  type InsightsOverview,
  type PhaseBreakdown,
  type Weakness,
  type TimeAnalysis,
  type StreakData,
} from "@/lib/api";
import {
  Card,
  CardContent,
  StatCard,
  Badge,
  Spinner,
  EmptyState,
} from "@/components/ui";

export default function InsightsPage() {
  const { data: session } = useSession();

  const [overview, setOverview] = useState<InsightsOverview | null>(null);
  const [phases, setPhases] = useState<PhaseBreakdown | null>(null);
  const [weaknesses, setWeaknesses] = useState<Weakness[]>([]);
  const [timeData, setTimeData] = useState<TimeAnalysis | null>(null);
  const [streakData, setStreakData] = useState<StreakData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!session) return;

    async function load() {
      setLoading(true);
      try {
        const [ov, ph, wk, tm, st] = await Promise.all([
          insightsAPI.overview(),
          insightsAPI.phaseBreakdown(),
          insightsAPI.weaknesses(),
          insightsAPI.timeAnalysis().catch(() => null),
          insightsAPI.streaks().catch(() => null),
        ]);
        setOverview(ov);
        setPhases(ph);
        setWeaknesses(wk.weaknesses ?? []);
        setTimeData(tm);
        setStreakData(st);
      } catch {
        // API may not be connected yet
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [session]);

  if (!session) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-gray-500">Sign in to view your insights.</p>
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

  const hasData = overview && overview.total_games > 0;

  const trendIcon =
    overview?.trend === "improving" ? (
      <TrendingUp className="h-4 w-4" />
    ) : overview?.trend === "declining" ? (
      <TrendingDown className="h-4 w-4" />
    ) : (
      <Minus className="h-4 w-4" />
    );

  const trendDirection =
    overview?.trend === "improving"
      ? ("up" as const)
      : overview?.trend === "declining"
      ? ("down" as const)
      : ("neutral" as const);

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">Insights</h1>
        <p className="text-gray-500 mt-1">
          Your performance overview and coaching insights.
        </p>
      </div>

      {!hasData ? (
        <Card>
          <EmptyState
            icon={<BarChart3 className="h-12 w-12" />}
            title="No data yet"
            description="Import and analyze some games to see your insights."
          />
        </Card>
      ) : (
        <>
          {/* Stats grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Games Analyzed"
              value={overview!.total_games}
              icon={<Swords className="h-5 w-5" />}
            />
            <StatCard
              label="Overall CPL"
              value={overview!.overall_cpl ?? "—"}
              subtitle={
                overview!.recent_cpl
                  ? `Recent: ${overview!.recent_cpl}`
                  : undefined
              }
              trend={trendDirection}
              icon={<Target className="h-5 w-5" />}
            />
            <StatCard
              label="Win Rate"
              value={overview!.win_rate ? `${overview!.win_rate}%` : "—"}
              icon={<Zap className="h-5 w-5" />}
            />
            <StatCard
              label="Blunder Rate"
              value={
                overview!.blunder_rate !== null
                  ? `${overview!.blunder_rate}/100`
                  : "—"
              }
              subtitle="per 100 moves"
              icon={<AlertTriangle className="h-5 w-5" />}
            />
          </div>

          {/* Trend indicator */}
          {overview!.trend && (
            <div
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm ${
                overview!.trend === "improving"
                  ? "bg-green-900/20 text-green-400 border border-green-800/30"
                  : overview!.trend === "declining"
                  ? "bg-red-900/20 text-red-400 border border-red-800/30"
                  : "bg-surface-1 text-gray-400 border border-surface-3"
              }`}
            >
              {trendIcon}
              <span>
                {overview!.trend === "improving"
                  ? "Your play is improving! Recent games are stronger than your average."
                  : overview!.trend === "declining"
                  ? "Your recent games show slightly lower accuracy. Consider reviewing your mistakes."
                  : "Your play is consistent. Keep it up!"}
              </span>
            </div>
          )}

          {/* Phase breakdown */}
          <Card>
            <CardContent>
              <h3 className="font-semibold mb-4">Phase Breakdown</h3>
              <div className="grid grid-cols-3 gap-6">
                <PhaseColumn
                  label="Opening"
                  cpl={phases?.opening ?? null}
                  baseline={overview!.overall_cpl}
                />
                <PhaseColumn
                  label="Middlegame"
                  cpl={phases?.middlegame ?? null}
                  baseline={overview!.overall_cpl}
                />
                <PhaseColumn
                  label="Endgame"
                  cpl={phases?.endgame ?? null}
                  baseline={overview!.overall_cpl}
                />
              </div>
            </CardContent>
          </Card>

          {/* Weaknesses */}
          <Card>
            <CardContent>
              <h3 className="font-semibold mb-4">Top Weaknesses</h3>
              {weaknesses.length === 0 ? (
                <p className="text-gray-500 text-sm">
                  Not enough data to determine weaknesses yet.
                </p>
              ) : (
                <div className="space-y-3">
                  {weaknesses.map((w, i) => (
                    <WeaknessCard key={i} weakness={w} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Time Analysis */}
          {timeData && (
            <Card>
              <CardContent>
                <h3 className="font-semibold mb-4 flex items-center gap-2">
                  <Clock className="h-4 w-4 text-brand-400" />
                  Time Management
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                  <div className="p-3 bg-surface-2 rounded-lg">
                    <p className="text-xs text-gray-500 uppercase">Avg Move Time</p>
                    <p className="text-xl font-bold mt-1">
                      {timeData.avg_move_time ? `${timeData.avg_move_time}s` : "—"}
                    </p>
                  </div>
                  <div className="p-3 bg-surface-2 rounded-lg">
                    <p className="text-xs text-gray-500 uppercase">Time Pressure Blunders</p>
                    <p className="text-xl font-bold mt-1 text-red-400">
                      {timeData.time_pressure_blunders ?? 0}
                    </p>
                    <p className="text-xs text-gray-500">
                      out of {timeData.time_pressure_moves ?? 0} moves under 30s
                    </p>
                  </div>
                  <div className="p-3 bg-surface-2 rounded-lg">
                    <p className="text-xs text-gray-500 uppercase">Normal Blunders</p>
                    <p className="text-xl font-bold mt-1 text-orange-400">
                      {timeData.normal_blunders ?? 0}
                    </p>
                    <p className="text-xs text-gray-500">
                      out of {timeData.normal_moves ?? 0} moves with 30s+
                    </p>
                  </div>
                </div>
                {timeData.time_controls.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-gray-400 mb-2">By Time Control</h4>
                    <div className="space-y-2">
                      {timeData.time_controls.map((tc) => (
                        <div
                          key={tc.time_control}
                          className="flex items-center justify-between px-3 py-2 bg-surface-2/50 rounded-lg text-sm"
                        >
                          <span className="font-medium">{tc.time_control}</span>
                          <div className="flex items-center gap-4 text-gray-400">
                            <span>{tc.games} games</span>
                            <span className="text-green-400">{tc.win_rate}% WR</span>
                            <span className={tc.avg_cpl && tc.avg_cpl < 40 ? "text-green-400" : tc.avg_cpl && tc.avg_cpl > 60 ? "text-red-400" : ""}>
                              {tc.avg_cpl ? `${tc.avg_cpl} CPL` : "—"}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Streaks */}
          {streakData && streakData.current_streak > 0 && (
            <Card>
              <CardContent>
                <h3 className="font-semibold mb-3 flex items-center gap-2">
                  <Flame className="h-4 w-4 text-orange-400" />
                  Current Streak
                </h3>
                <div className="flex items-center gap-3">
                  <div
                    className={`text-3xl font-bold ${
                      streakData.current_streak_type === "win"
                        ? "text-green-400"
                        : streakData.current_streak_type === "loss"
                        ? "text-red-400"
                        : "text-yellow-400"
                    }`}
                  >
                    {streakData.current_streak}
                  </div>
                  <div>
                    <p className="font-medium capitalize">
                      {streakData.current_streak_type} streak
                    </p>
                    <p className="text-xs text-gray-500">
                      {streakData.current_streak_type === "win"
                        ? "Keep it going!"
                        : streakData.current_streak_type === "loss"
                        ? "Time for a break?"
                        : "Consistent draws"}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

// ─── Phase Column ───────────────────────────────────────

function PhaseColumn({
  label,
  cpl,
  baseline,
}: {
  label: string;
  cpl: number | null;
  baseline: number | null;
}) {
  // Bar height: normalize CPL to a percentage (max bar at 100 CPL)
  const maxCpl = 100;
  const barPct = cpl !== null ? Math.min(100, (cpl / maxCpl) * 100) : 0;

  const color =
    cpl === null
      ? "bg-surface-3"
      : cpl < 25
      ? "bg-green-500"
      : cpl < 50
      ? "bg-yellow-500"
      : cpl < 75
      ? "bg-orange-500"
      : "bg-red-500";

  const textColor =
    cpl === null
      ? "text-gray-600"
      : cpl < 25
      ? "text-green-400"
      : cpl < 50
      ? "text-yellow-400"
      : cpl < 75
      ? "text-orange-400"
      : "text-red-400";

  const isWeak = baseline && cpl ? cpl > baseline * 1.15 : false;

  return (
    <div className="text-center">
      <p className="text-sm text-gray-400 mb-2">{label}</p>
      <div className="h-32 bg-surface-2 rounded-lg flex items-end justify-center pb-0 overflow-hidden">
        {cpl !== null ? (
          <div
            className={`w-10 ${color} rounded-t transition-all duration-500`}
            style={{ height: `${Math.max(8, barPct)}%` }}
          />
        ) : (
          <span className="text-gray-600 text-xs pb-4">No data</span>
        )}
      </div>
      <p className={`text-xl font-bold mt-2 ${textColor}`}>
        {cpl !== null ? Math.round(cpl) : "—"}
      </p>
      <p className="text-xs text-gray-500">avg CPL</p>
      {isWeak && (
        <Badge variant="warning" className="mt-1">
          Weak spot
        </Badge>
      )}
    </div>
  );
}

// ─── Weakness Card ──────────────────────────────────────

function WeaknessCard({ weakness }: { weakness: Weakness }) {
  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-lg border ${
        weakness.severity === "high"
          ? "bg-red-900/10 border-red-800/30"
          : weakness.severity === "medium"
          ? "bg-yellow-900/10 border-yellow-800/30"
          : "bg-surface-2 border-surface-3"
      }`}
    >
      <AlertTriangle
        className={`h-5 w-5 mt-0.5 flex-shrink-0 ${
          weakness.severity === "high"
            ? "text-red-400"
            : weakness.severity === "medium"
            ? "text-yellow-400"
            : "text-gray-400"
        }`}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm">{weakness.area}</span>
          <Badge
            variant={
              weakness.severity === "high"
                ? "danger"
                : weakness.severity === "medium"
                ? "warning"
                : "default"
            }
          >
            {weakness.severity}
          </Badge>
          {weakness.cpl && (
            <span className="text-xs text-gray-500">{weakness.cpl} CPL</span>
          )}
        </div>
        <p className="text-sm text-gray-400 mt-1">{weakness.message}</p>
        <p className="text-sm text-brand-400 mt-1.5">→ {weakness.action}</p>
      </div>
    </div>
  );
}

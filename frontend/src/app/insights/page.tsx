"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import Link from "next/link";
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Minus,
  AlertTriangle,
  Target,
  Zap,
  Clock,
  Flame,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Dumbbell,
  ArrowRight,
  Sparkles,
  Shield,
  Swords,
  GraduationCap,
  ThumbsUp,
  ThumbsDown,
} from "lucide-react";
import {
  insightsAPI,
  type InsightsOverview,
  type PhaseBreakdown,
  type Weakness,
  type TimeAnalysis,
  type StreakData,
  type OpeningStat,
  type AdvancedAnalytics,
  type PiecePerformance,
} from "@/lib/api";
import {
  Card,
  CardContent,
  Badge,
  Button,
  Spinner,
  EmptyState,
} from "@/components/ui";
import { cplToAccuracy, accuracyColor, formatAccuracy } from "@/lib/utils";

export default function InsightsPage() {
  const { data: session } = useSession();

  const [overview, setOverview] = useState<InsightsOverview | null>(null);
  const [phases, setPhases] = useState<PhaseBreakdown | null>(null);
  const [weaknesses, setWeaknesses] = useState<Weakness[]>([]);
  const [timeData, setTimeData] = useState<TimeAnalysis | null>(null);
  const [streakData, setStreakData] = useState<StreakData | null>(null);
  const [openings, setOpenings] = useState<OpeningStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [advanced, setAdvanced] = useState<AdvancedAnalytics | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advancedLoading, setAdvancedLoading] = useState(false);
  const [advancedFilter, setAdvancedFilter] = useState<string>("all");

  useEffect(() => {
    if (!session) return;

    async function load() {
      setLoading(true);
      try {
        const [ov, ph, wk, tm, st, op] = await Promise.all([
          insightsAPI.overview(),
          insightsAPI.phaseBreakdown(),
          insightsAPI.weaknesses(),
          insightsAPI.timeAnalysis().catch(() => null),
          insightsAPI.streaks().catch(() => null),
          insightsAPI.openings().catch(() => []),
        ]);
        setOverview(ov);
        setPhases(ph);
        setWeaknesses(wk.weaknesses ?? []);
        setTimeData(tm);
        setStreakData(st);
        setOpenings(op);
      } catch {
        // API may not be connected yet
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [session]);

  async function loadAdvanced(filter?: string) {
    if (advancedLoading) return;
    setAdvancedLoading(true);
    try {
      const data = await insightsAPI.advancedAnalytics(filter || advancedFilter);
      setAdvanced(data);
    } catch {
      // not available
    } finally {
      setAdvancedLoading(false);
    }
  }

  function handleShowAdvanced() {
    setShowAdvanced(true);
    loadAdvanced();
  }

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
  const accuracy = cplToAccuracy(overview?.overall_cpl);
  const recentAccuracy = cplToAccuracy(overview?.recent_cpl);

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold">Insights</h1>
        <p className="text-gray-500 mt-1">
          Your performance overview and where to improve.
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
          {/* ─── Above the fold: Accuracy hero + 3 insight cards ─── */}
          <div className="text-center py-4">
            <p className="text-sm text-gray-500 uppercase tracking-wider mb-1">Overall Accuracy</p>
            <p className={`text-5xl font-bold ${accuracyColor(accuracy)}`}>
              {accuracy !== null ? `${accuracy}%` : "—"}
            </p>
            {overview!.trend && (
              <div className={`inline-flex items-center gap-1.5 mt-2 text-xs font-medium px-3 py-1 rounded-full ${
                overview!.trend === "improving"
                  ? "bg-green-900/20 text-green-400"
                  : overview!.trend === "declining"
                  ? "bg-red-900/20 text-red-400"
                  : "bg-surface-2 text-gray-400"
              }`}>
                {overview!.trend === "improving" ? <TrendingUp className="h-3 w-3" /> : overview!.trend === "declining" ? <TrendingDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                {overview!.trend === "improving"
                  ? "Improving"
                  : overview!.trend === "declining"
                  ? "Declining"
                  : "Stable"}
                {recentAccuracy !== null && <span className="opacity-80 ml-1">({recentAccuracy}% recent)</span>}
              </div>
            )}
          </div>

          {/* 3 insight cards — max above the fold */}
          <div className="grid sm:grid-cols-3 gap-4">
            <InsightCard
              icon={<Target className="h-5 w-5 text-brand-400" />}
              label="Games"
              value={String(overview!.total_games)}
              sub={`${overview!.win_rate ?? 0}% win rate`}
            />
            <InsightCard
              icon={<Zap className="h-5 w-5 text-yellow-400" />}
              label="Blunders"
              value={overview!.blunder_rate !== null ? `${overview!.blunder_rate}` : "—"}
              sub="per 100 moves"
            />
            {streakData && streakData.current_streak > 0 ? (
              <InsightCard
                icon={<Flame className="h-5 w-5 text-orange-400" />}
                label="Streak"
                value={String(streakData.current_streak)}
                sub={`${streakData.current_streak_type} streak`}
              />
            ) : (
              <InsightCard
                icon={<Flame className="h-5 w-5 text-gray-600" />}
                label="Streak"
                value="0"
                sub="No active streak"
              />
            )}
          </div>

          {/* ─── Collapsible sections below the fold ─── */}

          {/* Weaknesses */}
          <CollapsibleInsight title="Weaknesses" icon={<AlertTriangle className="h-4 w-4 text-red-400" />} defaultOpen={true}>
            {weaknesses.length === 0 ? (
              <p className="text-gray-500 text-sm">Not enough data to determine weaknesses yet.</p>
            ) : (
              <div className="space-y-3">
                {weaknesses.slice(0, 3).map((w, i) => (
                  <div
                    key={i}
                    className={`flex items-start gap-3 p-4 rounded-lg border ${
                      w.severity === "high"
                        ? "bg-red-900/10 border-red-800/30"
                        : w.severity === "medium"
                        ? "bg-yellow-900/10 border-yellow-800/30"
                        : "bg-surface-2 border-surface-3"
                    }`}
                  >
                    <AlertTriangle className={`h-5 w-5 mt-0.5 flex-shrink-0 ${
                      w.severity === "high" ? "text-red-400" : w.severity === "medium" ? "text-yellow-400" : "text-gray-400"
                    }`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm">{w.area}</span>
                        <Badge variant={w.severity === "high" ? "danger" : w.severity === "medium" ? "warning" : "default"}>
                          {w.severity}
                        </Badge>
                      </div>
                      <p className="text-sm text-gray-400 mt-1">{w.message}</p>
                      <Link href="/train" className="text-sm text-brand-400 mt-1.5 flex items-center gap-1 hover:gap-2 transition-all">
                        <Dumbbell className="h-3 w-3" /> Train this <ArrowRight className="h-3 w-3" />
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CollapsibleInsight>

          {/* Phase Accuracy */}
          <CollapsibleInsight title="Phase Accuracy" icon={<BarChart3 className="h-4 w-4 text-brand-400" />}>
            <div className="grid grid-cols-3 gap-6">
              <PhaseColumn label="Opening" cpl={phases?.opening ?? null} />
              <PhaseColumn label="Middlegame" cpl={phases?.middlegame ?? null} />
              <PhaseColumn label="Endgame" cpl={phases?.endgame ?? null} />
            </div>
          </CollapsibleInsight>

          {/* Openings (merged from openings page) */}
          {openings.length > 0 && (
            <CollapsibleInsight title="Opening Repertoire" icon={<BookOpen className="h-4 w-4 text-green-400" />}>
              <div className="space-y-2">
                {[...openings]
                  .sort((a, b) => b.games_played - a.games_played)
                  .slice(0, 8)
                  .map((o, i) => {
                    const acc = cplToAccuracy(o.average_cpl);
                    const winColor = o.win_rate >= 60 ? "text-green-400" : o.win_rate >= 45 ? "text-yellow-400" : "text-red-400";
                    return (
                      <div
                        key={`${o.opening_name}-${o.color}-${i}`}
                        className="flex items-center justify-between px-4 py-2.5 bg-surface-2/50 rounded-lg text-sm"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className={`inline-flex h-6 w-6 rounded items-center justify-center text-xs font-bold ${
                            o.color === "white"
                              ? "bg-white text-gray-900"
                              : "bg-gray-800 text-white border border-surface-3"
                          }`}>
                            {o.color === "white" ? "♔" : "♚"}
                          </span>
                          <span className="font-medium truncate">{o.opening_name}</span>
                          <span className="text-xs text-gray-600">{o.eco_code}</span>
                        </div>
                        <div className="flex items-center gap-4 text-gray-400 flex-shrink-0">
                          <span>{o.games_played}g</span>
                          <span className={winColor}>{o.win_rate}%</span>
                          <span className={accuracyColor(acc)}>{acc !== null ? `${acc}%` : "—"}</span>
                        </div>
                      </div>
                    );
                  })}
              </div>
            </CollapsibleInsight>
          )}

          {/* Time Management */}
          {timeData && (
            <CollapsibleInsight title="Time Management" icon={<Clock className="h-4 w-4 text-brand-400" />}>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
                <div className="p-3 bg-surface-2 rounded-lg">
                  <p className="text-xs text-gray-500 uppercase">Avg Move Time</p>
                  <p className="text-xl font-bold mt-1">
                    {timeData.avg_move_time ? `${timeData.avg_move_time}s` : "—"}
                  </p>
                </div>
                <div className="p-3 bg-surface-2 rounded-lg">
                  <p className="text-xs text-gray-500 uppercase">Time Pressure Blunders</p>
                  <p className="text-xl font-bold mt-1 text-red-400">{timeData.time_pressure_blunders ?? 0}</p>
                  <p className="text-xs text-gray-500">in {timeData.time_pressure_moves ?? 0} moves</p>
                </div>
                <div className="p-3 bg-surface-2 rounded-lg">
                  <p className="text-xs text-gray-500 uppercase">Normal Blunders</p>
                  <p className="text-xl font-bold mt-1 text-orange-400">{timeData.normal_blunders ?? 0}</p>
                  <p className="text-xs text-gray-500">in {timeData.normal_moves ?? 0} moves</p>
                </div>
              </div>
              {timeData.time_controls.length > 0 && (
                <div className="space-y-2">
                  {timeData.time_controls.slice(0, 4).map((tc) => (
                    <div key={tc.time_control} className="flex items-center justify-between px-3 py-2 bg-surface-2/50 rounded-lg text-sm">
                      <span className="font-medium">{tc.time_control}</span>
                      <div className="flex items-center gap-4 text-gray-400">
                        <span>{tc.games}g</span>
                        <span className="text-green-400">{tc.win_rate}%</span>
                        <span className={accuracyColor(cplToAccuracy(tc.avg_cpl))}>
                          {formatAccuracy(tc.avg_cpl)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CollapsibleInsight>
          )}

          {/* ─── See Advanced Analytics ─── */}
          {!showAdvanced ? (
            <button
              onClick={handleShowAdvanced}
              className="w-full flex items-center justify-center gap-2 py-4 px-6 rounded-xl border border-dashed border-surface-3 hover:border-brand-500/50 hover:bg-surface-2/50 transition-all text-gray-400 hover:text-brand-400 group"
            >
              <Sparkles className="h-4 w-4" />
              <span className="font-medium">See Advanced Analytics</span>
              <ChevronRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
            </button>
          ) : (
            <div className="space-y-6 animate-fade-in">
              <div className="flex items-center justify-between pt-2">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-brand-400" />
                  <h2 className="text-lg font-bold">Advanced Analytics</h2>
                </div>
              </div>

              {/* Time Control Filter Tabs */}
              <div className="flex gap-1.5 p-1 bg-surface-2 rounded-lg w-fit">
                {(["all", "bullet", "blitz", "rapid", "classical"] as const).map((tc) => {
                  const icons: Record<string, string> = { all: "🎯", bullet: "⚡", blitz: "🔥", rapid: "⏱️", classical: "🏛️" };
                  const isActive = advancedFilter === tc;
                  return (
                    <button
                      key={tc}
                      onClick={() => {
                        setAdvancedFilter(tc);
                        setAdvanced(null);
                        loadAdvanced(tc);
                      }}
                      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                        isActive
                          ? "bg-brand-500/20 text-brand-400 shadow-sm"
                          : "text-gray-400 hover:text-gray-300 hover:bg-surface-3/50"
                      }`}
                    >
                      <span className="mr-1">{icons[tc]}</span>
                      {tc.charAt(0).toUpperCase() + tc.slice(1)}
                    </button>
                  );
                })}
              </div>

              {advancedLoading && (
                <Card className="py-12 flex items-center justify-center">
                  <Spinner className="h-6 w-6 text-brand-500" />
                </Card>
              )}

              {advanced && !advanced.has_data && (
                <Card>
                  <div className="p-6 text-center text-gray-500">
                    <p>{advanced.message || "Not enough data yet."}</p>
                  </div>
                </Card>
              )}

              {advanced && advanced.has_data && (
                <>
                  {/* Player Style */}
                  {advanced.primary_style && (
                    <Card>
                      <div className="p-6">
                        <h3 className="font-semibold text-sm text-gray-500 uppercase tracking-wider mb-4">Your Playing Style</h3>
                        <div className="flex items-start gap-4 mb-4">
                          <span className="text-4xl">{advanced.primary_style.icon}</span>
                          <div>
                            <p className="text-xl font-bold text-brand-400">{advanced.primary_style.trait}</p>
                            <p className="text-sm text-gray-400 mt-1">{advanced.primary_style.description}</p>
                          </div>
                        </div>
                        {advanced.secondary_styles && advanced.secondary_styles.length > 0 && (
                          <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-surface-3">
                            {advanced.secondary_styles.map((s, i) => (
                              <span
                                key={i}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-2 text-sm"
                                title={s.description}
                              >
                                <span>{s.icon}</span>
                                <span className="font-medium">{s.trait}</span>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </Card>
                  )}

                  {/* Comeback & Collapse */}
                  <div className="grid sm:grid-cols-2 gap-4">
                    <Card className="p-5">
                      <div className="flex items-start justify-between">
                        <div>
                          <p className="text-xs text-gray-500 uppercase tracking-wider">Comeback Wins</p>
                          <p className="text-3xl font-bold text-green-400 mt-1">{advanced.comeback_wins ?? 0}</p>
                          <p className="text-xs text-gray-500 mt-1">Won from losing positions (−2+ pawns)</p>
                        </div>
                        <ThumbsUp className="h-5 w-5 text-green-400/60" />
                      </div>
                    </Card>
                    <Card className="p-5">
                      <div className="flex items-start justify-between">
                        <div>
                          <p className="text-xs text-gray-500 uppercase tracking-wider">Collapses</p>
                          <p className="text-3xl font-bold text-red-400 mt-1">{advanced.collapses ?? 0}</p>
                          <p className="text-xs text-gray-500 mt-1">Lost from winning positions (+2 pawns)</p>
                        </div>
                        <ThumbsDown className="h-5 w-5 text-red-400/60" />
                      </div>
                    </Card>
                  </div>

                  {/* Best & Worst Openings */}
                  {((advanced.best_openings && advanced.best_openings.length > 0) ||
                    (advanced.worst_openings && advanced.worst_openings.length > 0)) && (
                    <div className="grid sm:grid-cols-2 gap-4">
                      {advanced.best_openings && advanced.best_openings.length > 0 && (
                        <Card>
                          <div className="p-5">
                            <div className="flex items-center gap-2 mb-3">
                              <BookOpen className="h-4 w-4 text-green-400" />
                              <h3 className="font-semibold text-sm">Best Openings</h3>
                            </div>
                            <div className="space-y-2">
                              {advanced.best_openings.map((o, i) => (
                                <div key={i} className="flex items-center justify-between px-3 py-2 bg-green-900/10 border border-green-800/20 rounded-lg text-sm">
                                  <span className="font-medium truncate flex-1 mr-2">{o.name}</span>
                                  <div className="flex items-center gap-3 text-xs flex-shrink-0">
                                    <span className="text-gray-400">{o.games}g</span>
                                    <span className="text-green-400">{o.win_rate}%</span>
                                    <span className={accuracyColor(cplToAccuracy(o.avg_cpl))}>
                                      {cplToAccuracy(o.avg_cpl) !== null ? `${cplToAccuracy(o.avg_cpl)}%` : "—"}
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </Card>
                      )}
                      {advanced.worst_openings && advanced.worst_openings.length > 0 && (
                        <Card>
                          <div className="p-5">
                            <div className="flex items-center gap-2 mb-3">
                              <BookOpen className="h-4 w-4 text-red-400" />
                              <h3 className="font-semibold text-sm">Worst Openings</h3>
                            </div>
                            <div className="space-y-2">
                              {advanced.worst_openings.map((o, i) => (
                                <div key={i} className="flex items-center justify-between px-3 py-2 bg-red-900/10 border border-red-800/20 rounded-lg text-sm">
                                  <span className="font-medium truncate flex-1 mr-2">{o.name}</span>
                                  <div className="flex items-center gap-3 text-xs flex-shrink-0">
                                    <span className="text-gray-400">{o.games}g</span>
                                    <span className="text-red-400">{o.win_rate}%</span>
                                    <span className={accuracyColor(cplToAccuracy(o.avg_cpl))}>
                                      {cplToAccuracy(o.avg_cpl) !== null ? `${cplToAccuracy(o.avg_cpl)}%` : "—"}
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </Card>
                      )}
                    </div>
                  )}

                  {/* Piece Performance */}
                  {advanced.all_pieces && advanced.all_pieces.length > 0 && (
                    <Card>
                      <div className="p-5">
                        <div className="flex items-center gap-2 mb-4">
                          <span className="text-lg">♟</span>
                          <h3 className="font-semibold text-sm">Piece Performance</h3>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
                          {advanced.all_pieces.map((p) => {
                            const acc = cplToAccuracy(p.avg_cpl);
                            return (
                              <div
                                key={p.piece}
                                className="flex flex-col items-center p-3 bg-surface-2 rounded-lg"
                              >
                                <span className="text-3xl mb-1">{p.icon}</span>
                                <span className="text-xs font-medium text-gray-400">{p.name}</span>
                                <span className={`text-lg font-bold mt-1 ${accuracyColor(acc)}`}>
                                  {acc !== null ? `${acc}%` : "—"}
                                </span>
                                <div className="flex gap-2 mt-1 text-[10px] text-gray-500">
                                  <span>{p.total_moves} moves</span>
                                </div>
                                <div className="flex gap-2 mt-0.5 text-[10px]">
                                  <span className="text-green-400">⭐ {p.best_rate}%</span>
                                  <span className="text-red-400">💥 {p.blunder_rate}%</span>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </Card>
                  )}

                  {/* Strengths & Weaknesses */}
                  <div className="grid sm:grid-cols-2 gap-4">
                    <Card>
                      <div className="p-5">
                        <div className="flex items-center gap-2 mb-3">
                          <Shield className="h-4 w-4 text-green-400" />
                          <h3 className="font-semibold text-sm">Strengths</h3>
                        </div>
                        <div className="space-y-2.5">
                          {(advanced.strengths ?? []).map((s, i) => (
                            <div key={i} className="p-3 bg-green-900/10 border border-green-800/20 rounded-lg">
                              <p className="text-sm font-medium text-green-400">{s.area}</p>
                              <p className="text-xs text-gray-400 mt-0.5">{s.detail}</p>
                            </div>
                          ))}
                          {(!advanced.strengths || advanced.strengths.length === 0) && (
                            <p className="text-sm text-gray-500">Keep analyzing games to discover your strengths.</p>
                          )}
                        </div>
                      </div>
                    </Card>
                    <Card>
                      <div className="p-5">
                        <div className="flex items-center gap-2 mb-3">
                          <Swords className="h-4 w-4 text-red-400" />
                          <h3 className="font-semibold text-sm">Weaknesses</h3>
                        </div>
                        <div className="space-y-2.5">
                          {(advanced.weaknesses ?? []).map((w, i) => (
                            <div key={i} className="p-3 bg-red-900/10 border border-red-800/20 rounded-lg">
                              <p className="text-sm font-medium text-red-400">{w.area}</p>
                              <p className="text-xs text-gray-400 mt-0.5">{w.detail}</p>
                            </div>
                          ))}
                          {(!advanced.weaknesses || advanced.weaknesses.length === 0) && (
                            <p className="text-sm text-gray-500">No major weaknesses detected — great work!</p>
                          )}
                        </div>
                      </div>
                    </Card>
                  </div>

                  {/* Study Recommendations */}
                  {advanced.recommendations && advanced.recommendations.length > 0 && (
                    <Card>
                      <div className="p-5">
                        <div className="flex items-center gap-2 mb-4">
                          <GraduationCap className="h-4 w-4 text-brand-400" />
                          <h3 className="font-semibold text-sm">Study Recommendations</h3>
                        </div>
                        <div className="space-y-3">
                          {advanced.recommendations.map((r, i) => (
                            <div key={i} className="flex items-start gap-3">
                              <span className={`mt-0.5 h-2 w-2 rounded-full flex-shrink-0 ${
                                r.priority === "high" ? "bg-red-400" : r.priority === "medium" ? "bg-yellow-400" : "bg-green-400"
                              }`} />
                              <div>
                                <p className="text-sm font-medium">{r.category}</p>
                                <p className="text-xs text-gray-400 mt-0.5">{r.message}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </Card>
                  )}

                  {/* Raw Stats Footer */}
                  {advanced.stats && (
                    <Card>
                      <div className="p-5">
                        <h3 className="font-semibold text-sm text-gray-500 uppercase tracking-wider mb-3">Key Numbers</h3>
                        <div className="grid grid-cols-3 sm:grid-cols-5 gap-4 text-center">
                          <div>
                            <p className="text-lg font-bold">{advanced.stats.avg_cpl}</p>
                            <p className="text-xs text-gray-500">Avg CPL</p>
                          </div>
                          <div>
                            <p className="text-lg font-bold">{advanced.stats.best_move_rate}%</p>
                            <p className="text-xs text-gray-500">Best Moves</p>
                          </div>
                          <div>
                            <p className="text-lg font-bold">{advanced.stats.blunder_rate}</p>
                            <p className="text-xs text-gray-500">Blunders/100</p>
                          </div>
                          <div>
                            <p className="text-lg font-bold">{advanced.stats.win_rate}%</p>
                            <p className="text-xs text-gray-500">Win Rate</p>
                          </div>
                          <div>
                            <p className="text-lg font-bold">{advanced.stats.upsets}</p>
                            <p className="text-xs text-gray-500">Giant Kills</p>
                          </div>
                        </div>
                      </div>
                    </Card>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Insight Card ───────────────────────────────────────

function InsightCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
          <p className="text-xs text-gray-500 mt-0.5">{sub}</p>
        </div>
        <div className="text-gray-500">{icon}</div>
      </div>
    </Card>
  );
}

// ─── Collapsible Insight Section ────────────────────────

function CollapsibleInsight({
  title,
  icon,
  defaultOpen = false,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <Card>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-5 py-4 text-left"
      >
        <span className="font-semibold flex items-center gap-2">
          {icon}
          {title}
        </span>
        <ChevronDown className={`h-4 w-4 text-gray-500 transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>
      {isOpen && (
        <div className="px-5 pb-5">
          {children}
        </div>
      )}
    </Card>
  );
}

// ─── Phase Column ───────────────────────────────────────

function PhaseColumn({
  label,
  cpl,
}: {
  label: string;
  cpl: number | null;
}) {
  const acc = cplToAccuracy(cpl);
  const color = accuracyColor(acc);

  // Bar height: normalize accuracy to percentage
  const barPct = acc !== null ? acc : 0;

  const barColor =
    acc === null
      ? "bg-surface-3"
      : acc >= 90
      ? "bg-green-500"
      : acc >= 75
      ? "bg-green-400"
      : acc >= 60
      ? "bg-yellow-500"
      : acc >= 45
      ? "bg-orange-500"
      : "bg-red-500";

  return (
    <div className="text-center">
      <p className="text-sm text-gray-400 mb-2">{label}</p>
      <div className="h-32 bg-surface-2 rounded-lg flex items-end justify-center pb-0 overflow-hidden">
        {acc !== null ? (
          <div
            className={`w-10 ${barColor} rounded-t transition-all duration-500`}
            style={{ height: `${Math.max(8, barPct)}%` }}
          />
        ) : (
          <span className="text-gray-600 text-xs pb-4">No data</span>
        )}
      </div>
      <p className={`text-xl font-bold mt-2 ${color}`}>
        {acc !== null ? `${acc}%` : "—"}
      </p>
      <p className="text-xs text-gray-500">accuracy</p>
    </div>
  );
}
